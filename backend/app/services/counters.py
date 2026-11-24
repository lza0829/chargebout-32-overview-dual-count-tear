"""选定架构臂 A（全局唯一，不混用臂 B）：以充电中/结算中会话集合推导钉桩。

「假钉桩对齐如何收口」的唯一正确性口径：
  两格数字必须能由【充电中/结算中去重钉桩会话集合】∪【桩位/枪线占用列】重放。
  - 钉桩桩数     = COUNT(DISTINCT pile_id) WHERE status IN ('充电中','结算中')
  - 充电中会话数 = COUNT(*)               WHERE status = '充电中'

收口规则（全局只有这一套）：
  1. 总览双格无独立存储、不落快照：读即重放；只有四面对照（会话集合 ∪
     占用列投影 ∪ 审计重放）全部一致时才允许 `对齐=True`。
  2. 对不上则禁止亮已对齐：读返回 `对齐=False` 并列出 `拧花`；不提供任何
     「只改首页文案」或「旁路写两格数字」的入口。
  3. 改计数的写口若落账后证据仍对不上，整笔回退（HTTP 409），绝不留下
     半截假齐；非计数写口（脉冲、锁账/封印、桩位状态）动到双计数证据同样
     整笔回退。
  4. 审计流水与回执只记录【重放推导】的双计数快照，不得单独把两格刷绿；
     对账时同时重放审计与回执，发现旁路对齐宣称即判定未对齐。
  5. 桩/枪占用列只是本谓词的投影：写口同事务按真源重算（绝不增量加减），
     漂移时由 replay_and_repair 按同一谓词纠正并写「重放纠正」审计。
"""
from __future__ import annotations

import json

from fastapi import HTTPException

from app.services import audit

CHARGING = "充电中"
ACTIVE_STATES = ("充电中", "结算中")  # 钉桩会话状态集合（结算中仍钉桩、不计充电中）
PREDICATE_ID = "arm-a/session-derived/v1"


def replay_dual_counters(conn) -> dict:
    """选定口径唯一谓词：钉桩桩数 + 充电中会话数。写口回执与总览刷新同调此函数。"""
    pinned = conn.execute(
        "SELECT COUNT(DISTINCT pile_id) AS n FROM sessions WHERE status IN ('充电中','结算中')"
    ).fetchone()["n"]
    charging = conn.execute(
        "SELECT COUNT(*) AS n FROM sessions WHERE status='充电中'"
    ).fetchone()["n"]
    return {"钉桩桩数": int(pinned), "充电中会话数": int(charging)}


def charging_session_ids(conn) -> list[int]:
    return [
        r["id"]
        for r in conn.execute("SELECT id FROM sessions WHERE status='充电中' ORDER BY id").fetchall()
    ]


def pinned_pile_ids(conn) -> list[int]:
    return [
        r["pile_id"]
        for r in conn.execute(
            "SELECT DISTINCT pile_id FROM sessions WHERE status IN ('充电中','结算中') ORDER BY pile_id"
        ).fetchall()
    ]


def active_gun_ids(conn) -> list[int]:
    return [
        r["gun_id"]
        for r in conn.execute(
            "SELECT DISTINCT gun_id FROM sessions WHERE status IN ('充电中','结算中') ORDER BY gun_id"
        ).fetchall()
    ]


def active_session_rows(conn) -> list[tuple]:
    return [
        (r["id"], r["status"], r["pile_id"], r["gun_id"])
        for r in conn.execute(
            "SELECT id,status,pile_id,gun_id FROM sessions "
            "WHERE status IN ('充电中','结算中') ORDER BY id"
        ).fetchall()
    ]


def occupied_pile_ids(conn) -> list[int]:
    return [
        r["id"] for r in conn.execute("SELECT id FROM piles WHERE status='占用' ORDER BY id").fetchall()
    ]


def occupied_gun_ids(conn) -> list[int]:
    return [
        r["id"] for r in conn.execute("SELECT id FROM guns WHERE status='占用' ORDER BY id").fetchall()
    ]


def evidence_fingerprint(conn) -> dict:
    """双计数证据指纹：非计数写口必须保持指纹不变，否则视为误拧两格。"""
    return {
        "活跃会话": tuple(active_session_rows(conn)),
        "会话钉桩": tuple(pinned_pile_ids(conn)),
        "会话钉枪": tuple(active_gun_ids(conn)),
        "桩位占用列": tuple(occupied_pile_ids(conn)),
        "枪线占用列": tuple(occupied_gun_ids(conn)),
        "双计数": replay_dual_counters(conn),
    }


def evidence_snapshot(conn) -> dict:
    """可读证据快照（对账 / 总览展示用）。"""
    return {
        "充电中会话": charging_session_ids(conn),
        "充电中/结算中钉桩": pinned_pile_ids(conn),
        "充电中/结算中钉枪": active_gun_ids(conn),
        "桩位占用列": occupied_pile_ids(conn),
        "枪线占用列": occupied_gun_ids(conn),
    }


def refresh_projection(conn, pile_id: int, gun_id: int | None = None) -> None:
    """桩/枪占用列 = 会话集合投影：按真源重算，绝不增量加减；故障/维护等人工态不动。"""
    if gun_id is not None:
        conn.execute(
            """UPDATE guns SET status = CASE WHEN EXISTS(
                 SELECT 1 FROM sessions s WHERE s.gun_id=guns.id AND s.status IN ('充电中','结算中')
               ) THEN '占用' ELSE '可用' END
             WHERE id=? AND status IN ('占用','可用')""",
            (gun_id,),
        )
    conn.execute(
        """UPDATE piles SET status = CASE WHEN EXISTS(
             SELECT 1 FROM sessions s WHERE s.pile_id=piles.id AND s.status IN ('充电中','结算中')
           ) THEN '占用' ELSE '空闲' END
         WHERE id=? AND status IN ('占用','空闲')""",
        (pile_id,),
    )


def _last_audit_dual(conn) -> dict | None:
    """最新一条带双计数快照的业务审计；用于识破绕过写口的直改。"""
    for row in conn.execute(
        "SELECT detail_json FROM audit_log ORDER BY seq DESC"
    ).fetchall():
        try:
            detail = json.loads(row["detail_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(detail, dict):
            continue
        dual = detail.get("双计数")
        if not isinstance(dual, dict):
            continue
        try:
            return {"钉桩桩数": int(dual["钉桩桩数"]), "充电中会话数": int(dual["充电中会话数"])}
        except (KeyError, TypeError, ValueError):
            continue
    return None


BYPASS_SETTING_KEYS = ("surface_last", "surface_ok")


def _bypass_setting_keys(conn) -> list[str]:
    marks = ",".join("?" for _ in BYPASS_SETTING_KEYS)
    return [
        r["key"]
        for r in conn.execute(
            f"SELECT key FROM settings WHERE key IN ({marks}) ORDER BY key", BYPASS_SETTING_KEYS
        ).fetchall()
    ]


def _acked_bypass_sources(conn) -> set[str]:
    """已被「重放修复」明确作废的旁路宣称（作废事实本身也落在只增审计里）。"""
    acked: set[str] = set()
    for r in conn.execute(
        "SELECT detail_json FROM audit_log WHERE kind=?", (audit.重放纠正,)
    ).fetchall():
        try:
            detail = json.loads(r["detail_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(detail, dict):
            continue
        for src in detail.get("作废旁路宣称") or []:
            if isinstance(src, str):
                acked.add(src)
    return acked


def _bypass_claims(conn) -> list[dict]:
    """扫描回执、审计与设置表：臂 A 下不存在任何「已对齐 / surface」独立宣称。"""
    forged: list[dict] = []
    acked = _acked_bypass_sources(conn)
    for r in conn.execute("SELECT idem_key, body_json FROM receipts ORDER BY idem_key").fetchall():
        src = f"回执:{r['idem_key']}"
        if src in acked:
            continue
        try:
            body = json.loads(r["body_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(body, dict):
            continue
        if body.get("已对齐") is True or body.get("surface_ok") is True:
            forged.append({"来源": src, "宣称": "已对齐", "内容": body})
    for r in conn.execute("SELECT seq, kind, detail_json FROM audit_log ORDER BY seq").fetchall():
        src = f"审计:{r['seq']}:{r['kind']}"
        if src in acked:
            continue
        try:
            detail = json.loads(r["detail_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(detail, dict):
            continue
        if detail.get("已对齐") is True or detail.get("surface_ok") is True:
            forged.append({"来源": src, "宣称": "已对齐", "内容": detail})
    for key in _bypass_setting_keys(conn):
        src = f"设置:{key}"
        if src in acked:
            continue
        forged.append({"来源": src, "宣称": "首页加速对齐旁路", "内容": None})
    return forged


def purge_bypass_claims(conn) -> list[dict]:
    """重放修复的一部分：清除首页旁路缓存，并把历史旁路宣称在审计里作废（不删审计）。"""
    claims = _bypass_claims(conn)
    if not claims:
        return []
    setting_keys = [c["来源"][3:] for c in claims if c["来源"].startswith("设置:")]
    declared = [c["来源"] for c in claims if not c["来源"].startswith("设置:")]
    if setting_keys:
        marks = ",".join("?" for _ in setting_keys)
        conn.execute(f"DELETE FROM settings WHERE key IN ({marks})", setting_keys)
    audit.append(
        conn,
        audit.重放纠正,
        {
            "真源": "sessions(status IN ('充电中','结算中'))",
            "口径": PREDICATE_ID,
            "面": "首页旁路对齐宣称",
            "清除设置": setting_keys,
            "作废旁路宣称": declared,
        },
    )
    out = []
    for k in setting_keys:
        out.append({"面": "首页旁路缓存", "编号": k, "由": "存在", "至": "已清除"})
    for src in declared:
        out.append({"面": "旁路对齐宣称", "编号": src, "由": "未作废", "至": "已作废"})
    return out


def consistency_report(conn) -> dict:
    """四面对照 + 审计重放 + 回执宣称核对（同一谓词）。"""
    dual = replay_dual_counters(conn)
    ledger_charging = charging_session_ids(conn)
    ledger_pinned = pinned_pile_ids(conn)
    ledger_guns = active_gun_ids(conn)
    page_pinned = occupied_pile_ids(conn)
    col_guns = occupied_gun_ids(conn)
    evidence = {
        "充电中会话": ledger_charging,
        "充电中/结算中钉桩": ledger_pinned,
        "充电中/结算中钉枪": ledger_guns,
        "桩位占用列": page_pinned,
        "枪线占用列": col_guns,
    }
    replayed = {"钉桩桩数": len(ledger_pinned), "充电中会话数": len(ledger_charging)}
    violations: list[str] = []
    if dual["钉桩桩数"] != replayed["钉桩桩数"]:
        violations.append(f"总览钉桩格{dual['钉桩桩数']}≠会话册钉桩去重{replayed['钉桩桩数']}")
    if dual["充电中会话数"] != replayed["充电中会话数"]:
        violations.append(f"总览充电中格{dual['充电中会话数']}≠会话册充电中{replayed['充电中会话数']}")
    if page_pinned != ledger_pinned:
        violations.append(f"桩位页占用{page_pinned}≠会话册钉桩{ledger_pinned}")
    if col_guns != ledger_guns:
        violations.append(f"枪线占用列{col_guns}≠会话册钉枪{ledger_guns}")
    # 故障/维护桩或故障枪上的钉桩会话无法由占用列表达：属不可重放证据，必须显式报出。
    unresolved: list[str] = []
    for r in conn.execute(
        """SELECT DISTINCT s.pile_id, p.status FROM sessions s
           JOIN piles p ON p.id=s.pile_id
           WHERE s.status IN ('充电中','结算中') AND p.status IN ('故障','维护')"""
    ).fetchall():
        unresolved.append(f"桩位{r['pile_id']}状态为{r['status']}却有钉桩会话")
    for r in conn.execute(
        """SELECT DISTINCT s.gun_id, g.status FROM sessions s
           JOIN guns g ON g.id=s.gun_id
           WHERE s.status IN ('充电中','结算中') AND g.status NOT IN ('占用','可用')"""
    ).fetchall():
        unresolved.append(f"枪线{r['gun_id']}状态为{r['status']}却有钉桩会话")
    for r in conn.execute(
        """SELECT gun_id, COUNT(*) AS n FROM sessions
           WHERE status IN ('充电中','结算中') GROUP BY gun_id HAVING COUNT(*) > 1"""
    ).fetchall():
        unresolved.append(f"枪线{r['gun_id']}并发双钉桩会话{r['n']}条")
    violations.extend(unresolved)

    # 审计重放：绕过写口直改会话/占用列会与最新业务审计快照对不上。
    last_dual = _last_audit_dual(conn)
    audit_ok = last_dual is None or last_dual == dual
    if last_dual is None:
        # 有双计数证据却一条带快照的审计都没有：落账绕过写口。
        if ledger_charging or ledger_pinned or ledger_guns or page_pinned or col_guns:
            audit_ok = False
            violations.append("无审计双计数快照却有钉桩/充电中证据（疑似绕过写口落账）")
    elif last_dual != dual:
        violations.append(f"最新审计双计数{last_dual}≠当前重放{dual}（疑似绕过写口落账）")
    # 回执/审计自带的「已对齐」旁路宣称一律不算数。
    forged = _bypass_claims(conn)
    if forged:
        violations.append(f"回执/审计存在旁路对齐宣称{len(forged)}处")

    return {
        "对齐": not violations,
        "拧花": violations,
        "口径": PREDICATE_ID,
        "总览双格": dual,
        "重放": replayed,
        "证据": evidence,
        "会话册": {"充电中会话": ledger_charging, "钉桩桩位": ledger_pinned, "钉枪枪线": ledger_guns},
        "桩位页": {"占用桩位": page_pinned},
        "枪线占用列": {"占用枪线": col_guns},
        "审计": {
            "最新双计数": last_dual,
            "重放一致": audit_ok,
        },
        "回执": {"旁路宣称": forged},
        "不可重放": unresolved,
    }


def assert_evidence_aligned(conn, port: str) -> dict:
    """计数写口收口：落账后四面对照不齐 → 整笔回退，禁止亮已对齐。"""
    rep = consistency_report(conn)
    if not rep["对齐"]:
        raise HTTPException(
            409,
            detail={
                "写口": port,
                "结果": "整笔回退",
                "原因": "计数证据不一致：禁止落账后宣称已对齐",
                "拧花": rep["拧花"],
                "双计数": rep["总览双格"],
                "口径": PREDICATE_ID,
            },
        )
    return rep


def assert_evidence_unchanged(conn, before: dict, port: str) -> dict:
    """非计数写口收口：动了双计数证据（含占用列）→ 整笔回退。"""
    after = evidence_fingerprint(conn)
    if after != before:
        changed = [k for k in after if after[k] != before.get(k)]
        raise HTTPException(
            409,
            detail={
                "写口": port,
                "结果": "整笔回退",
                "原因": "非计数写口不得改动双计数证据",
                "变化": changed,
                "口径": PREDICATE_ID,
            },
        )
    return after


def replay_and_repair(conn) -> list[dict]:
    """按选定真源全量重放，纠正桩/枪占用列投影；每处纠正写「重放纠正」审计。

    只纠正占用列与旁路宣称，不改会话集合，也不写双计数快照 —— 保持对审计重放的识别力。
    """
    want_piles = set(pinned_pile_ids(conn))
    want_guns = set(active_gun_ids(conn))
    corrections: list[dict] = []
    for r in conn.execute("SELECT id,status FROM piles WHERE status IN ('占用','空闲')").fetchall():
        want = "占用" if r["id"] in want_piles else "空闲"
        if r["status"] != want:
            conn.execute("UPDATE piles SET status=? WHERE id=?", (want, r["id"]))
            corrections.append({"面": "桩位占用列", "编号": r["id"], "由": r["status"], "至": want})
    for r in conn.execute("SELECT id,status FROM guns WHERE status IN ('占用','可用')").fetchall():
        want = "占用" if r["id"] in want_guns else "可用"
        if r["status"] != want:
            conn.execute("UPDATE guns SET status=? WHERE id=?", (want, r["id"]))
            corrections.append({"面": "枪线占用列", "编号": r["id"], "由": r["status"], "至": want})
    for c in corrections:
        audit.append(
            conn,
            audit.重放纠正,
            {"真源": "sessions(status IN ('充电中','结算中'))", "口径": PREDICATE_ID, **c},
        )
    corrections.extend(purge_bypass_claims(conn))
    # 对账受理：把「当前会话集合」作为本次重放的已核对事实记入只增审计。
    # 只有显式调用重放修复才会写，事后仍可从审计流水看出何时、按哪份证据对过账。
    audit.append(
        conn,
        audit.对账受理,
        {
            "真源": "sessions(status IN ('充电中','结算中'))",
            "口径": PREDICATE_ID,
            "双计数": replay_dual_counters(conn),
            "证据": evidence_snapshot(conn),
            "纠正条数": len(corrections),
        },
    )
    return corrections
