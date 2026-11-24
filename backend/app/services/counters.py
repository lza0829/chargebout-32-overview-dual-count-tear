"""选定架构臂 A（全局唯一）：以充电中/结算中会话集合推导钉桩。

正确性口径（唯一谓词，总览双格、写口回执、四面对照、重放修复共用）：
  钉桩桩数     = COUNT(DISTINCT pile_id) WHERE status IN ('充电中','结算中')
  充电中会话数 = COUNT(*)               WHERE status = '充电中'

总览双格无独立存储、不落快照：读即重放，从根上杜绝"只改两格展示"与手工改计假齐。
桩/枪占用列只是本谓词的投影：写口同事务按真源重算（绝不增量加减），
漂移时由 replay_and_repair 按同一谓词纠正并写「重放纠正」审计。
"""
from __future__ import annotations
from app.services import audit

ACTIVE_STATES = ("充电中", "结算中")  # 钉桩会话状态集合（臂内规则：结算中仍钉桩、不计充电中）
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


def consistency_report(conn) -> dict:
    """四面对照：总览双格 ↔ 会话册 ↔ 桩位页 ↔ 枪线占用列（同一谓词）。"""
    dual = replay_dual_counters(conn)
    ledger_charging = charging_session_ids(conn)
    ledger_pinned = pinned_pile_ids(conn)
    ledger_guns = active_gun_ids(conn)
    page_pinned = [
        r["id"] for r in conn.execute("SELECT id FROM piles WHERE status='占用' ORDER BY id").fetchall()
    ]
    col_guns = [
        r["id"] for r in conn.execute("SELECT id FROM guns WHERE status='占用' ORDER BY id").fetchall()
    ]
    violations: list[str] = []
    if dual["钉桩桩数"] != len(ledger_pinned):
        violations.append(f"总览钉桩格{dual['钉桩桩数']}≠会话册钉桩去重{len(ledger_pinned)}")
    if dual["充电中会话数"] != len(ledger_charging):
        violations.append(f"总览充电中格{dual['充电中会话数']}≠会话册充电中{len(ledger_charging)}")
    if page_pinned != ledger_pinned:
        violations.append(f"桩位页占用{page_pinned}≠会话册钉桩{ledger_pinned}")
    if col_guns != ledger_guns:
        violations.append(f"枪线占用列{col_guns}≠会话册钉枪{ledger_guns}")
    return {
        "对齐": not violations,
        "拧花": violations,
        "口径": PREDICATE_ID,
        "总览双格": dual,
        "会话册": {"充电中会话": ledger_charging, "钉桩桩位": ledger_pinned, "钉枪枪线": ledger_guns},
        "桩位页": {"占用桩位": page_pinned},
        "枪线占用列": {"占用枪线": col_guns},
    }


def replay_and_repair(conn) -> list[dict]:
    """按选定真源全量重放，纠正桩/枪占用列投影；每处纠正写「重放纠正」审计。"""
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
    return corrections
