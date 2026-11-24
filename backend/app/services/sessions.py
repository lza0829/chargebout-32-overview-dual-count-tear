from app.services import dual_surface
"""写口：开充 / 结算关账 / 超时 / 中断 / 桩位状态口（臂 A 全局贯彻）。

铁律：
1. 每个写口一个写事务（路由层 write_db）：会话状态列、桩/枪占用列投影、
   审计流水、幂等回执同事务落库；回执内嵌的双计数由 counters.replay_dual_counters
   同事务算出，与总览刷新同一谓词。
2. 占用列投影只按真源重算，绝不增量加减 —— 并发开充关账不会一边加一边减。
3. 幂等键兜底半截回执：同键重试返回原回执；同键跨写口 409。
"""
from __future__ import annotations
import sqlite3
from fastapi import HTTPException

from app.services import audit, counters
from app.services.core import current_band_price, get_setting, is_day_sealed, now_str, today
from app.services.receipts import new_key, stored_receipt, store_receipt

ACTIVE = ("充电中", "结算中")  # 钉桩（占用）状态集合
TERMINAL = ("已关账", "已超时", "已中断")  # 计数域终结态


def _next_slip(conn) -> str:
    n = int(get_setting(conn, "会话序号", "1000")) + 1
    conn.execute(
        "INSERT INTO settings(key,value) VALUES('会话序号',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(n),),
    )
    return f"充{n}"


def _load_session(conn, session_id: int):
    se = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not se:
        raise HTTPException(404, detail="会话不存在")
    return se


def _has_active_on_pile(conn, pile_id: int) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sessions WHERE pile_id=? AND status IN ('充电中','结算中') LIMIT 1",
            (pile_id,),
        ).fetchone()
    )


def open_session(conn, pile_id: int, gun_id: int | None = None, idem_key: str | None = None) -> dict:
    """开充写口：会话钉桩 + 占用列投影 + 审计 + 回执，同事务一次落库。"""
    key = new_key(idem_key, "开充")
    cached = stored_receipt(conn, key, "开充")
    if cached is not None:
        return cached
    if is_day_sealed(conn):
        raise HTTPException(400, detail="充日已封印，禁止新开充")
    pile = conn.execute("SELECT * FROM piles WHERE id=?", (pile_id,)).fetchone()
    if not pile:
        raise HTTPException(404, detail="桩位不存在")
    if pile["status"] in ("故障", "维护"):
        raise HTTPException(400, detail=f"桩位当前为{pile['status']}，不可开充")
    # 臂 A：占用/空闲是投影不是闸门 —— 同桩多枪可各钉一条会话，钉桩数按桩去重
    site = conn.execute("SELECT * FROM sites WHERE id=?", (pile["site_id"],)).fetchone()
    if not site or not site["active"]:
        raise HTTPException(400, detail="站点未启用")

    if gun_id is None:
        gun = conn.execute(
            "SELECT * FROM guns WHERE pile_id=? AND status='可用' ORDER BY id LIMIT 1",
            (pile_id,),
        ).fetchone()
    else:
        gun = conn.execute(
            "SELECT * FROM guns WHERE id=? AND pile_id=?", (gun_id, pile_id)
        ).fetchone()
    if not gun:
        raise HTTPException(400, detail="无可用枪线")
    if gun["status"] != "可用":
        raise HTTPException(400, detail=f"枪线当前为{gun['status']}")

    price = current_band_price(conn, pile["rate_plan_id"])
    slip = _next_slip(conn)
    ts = now_str()
    try:
        cur = conn.execute(
            """INSERT INTO sessions(slip_no,site_id,pile_id,gun_id,rate_plan_id,business_day,status,kwh,amount,price_locked,started_at,note)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (slip, pile["site_id"], pile_id, gun["id"], pile["rate_plan_id"], today(),
             "充电中", 0, 0, price, ts, ""),
        )
    except sqlite3.IntegrityError as exc:  # 唯一索引兜底：同枪并发开充
        raise HTTPException(409, detail="枪线并发开充冲突，请重试") from exc
    sid = cur.lastrowid
    counters.refresh_projection(conn, pile_id, gun["id"])
    dual = counters.replay_dual_counters(conn)  # 同事务可对读：回执双计数 = 总览刷新谓词
    seq = audit.append(conn, audit.开充, {
        "写口": "开充", "幂等键": key, "会话编号": sid, "会话号": slip,
        "桩位编号": pile_id, "枪线编号": gun["id"], "至状态": "充电中", "双计数": dual,
    })
    conn.execute(
        "INSERT INTO session_events(session_id,action,created_at,note) VALUES(?,?,?,?)",
        (sid, "开会话", ts, f"锁定电价{price}"),
    )
    receipt = {
        "会话号": slip, "会话编号": sid, "锁定电价": price, "状态": "充电中",
        "双计数": dual, "幂等键": key, "审计序号": seq,
    }
    store_receipt(conn, key, "开充", receipt)
    return receipt


def add_pulse(conn, session_id: int, delta_kwh: float, power_kw: float = 0) -> dict:
    # 电量真源与计价另立需求；此处保持原语义，仅纳入写事务（路由层 write_db）
    if delta_kwh <= 0:
        raise HTTPException(400, detail="脉冲电量须大于零")
    se = _load_session(conn, session_id)
    if se["status"] != "充电中":
        raise HTTPException(400, detail=f"会话状态为{se['status']}，不可记脉冲")
    ts = now_str()
    conn.execute(
        "INSERT INTO pulses(session_id,delta_kwh,power_kw,created_at) VALUES(?,?,?,?)",
        (session_id, delta_kwh, power_kw, ts),
    )
    new_kwh = float(se["kwh"]) + float(delta_kwh)
    price = float(se["price_locked"] or current_band_price(conn, se["rate_plan_id"]))
    amount = round(new_kwh * price, 2)
    conn.execute(
        "UPDATE sessions SET kwh=?, amount=? WHERE id=?",
        (round(new_kwh, 3), amount, session_id),
    )
    conn.execute(
        "INSERT INTO session_events(session_id,action,created_at,note) VALUES(?,?,?,?)",
        (session_id, "脉冲", ts, f"+{delta_kwh}"),
    )
    return {"会话编号": session_id, "累计电量": round(new_kwh, 3), "预估金额": amount}


def settle(conn, session_id: int, idem_key: str | None = None) -> dict:
    """结算关账写口：充电中→结算中→已关账 单事务完成，同事务释放钉桩。

    已超时会话允许补关账（计价域收尾，另立需求），双计数不再变动。
    """
    key = new_key(idem_key, "关账")
    cached = stored_receipt(conn, key, "关账")
    if cached is not None:
        return cached
    se = _load_session(conn, session_id)
    if se["status"] in ("已关账", "已中断"):
        raise HTTPException(400, detail=f"会话状态为{se['status']}，不可关账")
    ts = now_str()
    price = float(se["price_locked"] or current_band_price(conn, se["rate_plan_id"]))
    amount = round(float(se["kwh"]) * price, 2)
    transitions: list[list[str]] = []
    if se["status"] == "充电中":
        conn.execute("UPDATE sessions SET status='结算中' WHERE id=?", (session_id,))
        transitions.append(["充电中", "结算中"])
        audit.append(conn, audit.结算, {
            "写口": "关账", "幂等键": key, "会话编号": session_id, "至状态": "结算中",
            "双计数": counters.replay_dual_counters(conn),
        })
    transitions.append([se["status"] if se["status"] != "充电中" else "结算中", "已关账"])
    conn.execute(
        "UPDATE sessions SET status='已关账', amount=?, closed_at=?, price_locked=? WHERE id=?",
        (amount, ts, price, session_id),
    )
    counters.refresh_projection(conn, se["pile_id"], se["gun_id"])
    dual = counters.replay_dual_counters(conn)
    seq = audit.append(conn, audit.关账, {
        "写口": "关账", "幂等键": key, "会话编号": session_id,
        "状态迁移": transitions, "金额": amount, "双计数": dual,
    })
    conn.execute(
        "INSERT INTO session_events(session_id,action,created_at,note) VALUES(?,?,?,?)",
        (session_id, "结算关账", ts, f"金额{amount}"),
    )
    receipt = {
        "会话编号": session_id, "电量": float(se["kwh"]), "金额": amount, "状态": "已关账",
        "双计数": dual, "幂等键": key, "审计序号": seq,
    }
    store_receipt(conn, key, "关账", receipt)
    return receipt


def mark_timeout(conn, session_id: int, idem_key: str | None = None) -> dict:
    """超时写口：会话终结为已超时，同事务释放钉桩与枪线占用。"""
    key = new_key(idem_key, "超时")
    cached = stored_receipt(conn, key, "超时")
    if cached is not None:
        return cached
    se = _load_session(conn, session_id)
    if se["status"] not in ACTIVE:
        raise HTTPException(400, detail=f"会话状态为{se['status']}，不可标超时")
    minutes = int(get_setting(conn, "超时分钟", "120"))
    ts = now_str()
    conn.execute(
        "UPDATE sessions SET status='已超时', closed_at=?, note=? WHERE id=?",
        (ts, f"超过{minutes}分钟未关", session_id),
    )
    counters.refresh_projection(conn, se["pile_id"], se["gun_id"])
    dual = counters.replay_dual_counters(conn)
    seq = audit.append(conn, audit.超时, {
        "写口": "超时", "幂等键": key, "会话编号": session_id,
        "由状态": se["status"], "至状态": "已超时", "阈值分钟": minutes, "双计数": dual,
    })
    conn.execute(
        "INSERT INTO session_events(session_id,action,created_at,note) VALUES(?,?,?,?)",
        (session_id, "超时", ts, f"阈值{minutes}分钟"),
    )
    receipt = {
        "会话编号": session_id, "状态": "已超时",
        "双计数": dual, "幂等键": key, "审计序号": seq,
    }
    store_receipt(conn, key, "超时", receipt)
    return receipt


def abort_session(conn, session_id: int, reason: str = "急停", idem_key: str | None = None) -> dict:
    """中断写口：会话终结为已中断，同事务释放钉桩与枪线占用。"""
    key = new_key(idem_key, "中断")
    cached = stored_receipt(conn, key, "中断")
    if cached is not None:
        return cached
    se = _load_session(conn, session_id)
    if se["status"] not in ACTIVE and se["status"] != "已超时":
        raise HTTPException(400, detail=f"会话状态为{se['status']}，不可中断")
    ts = now_str()
    conn.execute(
        "UPDATE sessions SET status='已中断', closed_at=?, note=? WHERE id=?",
        (ts, reason, session_id),
    )
    counters.refresh_projection(conn, se["pile_id"], se["gun_id"])
    dual = counters.replay_dual_counters(conn)
    seq = audit.append(conn, audit.中断, {
        "写口": "中断", "幂等键": key, "会话编号": session_id,
        "由状态": se["status"], "至状态": "已中断", "原因": reason, "双计数": dual,
    })
    conn.execute(
        "INSERT INTO session_events(session_id,action,created_at,note) VALUES(?,?,?,?)",
        (session_id, "异常中断", ts, reason),
    )
    receipt = {
        "会话编号": session_id, "状态": "已中断", "原因": reason,
        "双计数": dual, "幂等键": key, "审计序号": seq,
    }
    store_receipt(conn, key, "中断", receipt)
    return receipt


def set_pile_status(conn, pile_id: int, status: str, operator: str = "") -> dict:
    """桩位状态口：只管故障/维护/恢复；占用态由会话集合推导，手工钉桩一律拒绝并留痕。"""
    if status not in ("空闲", "占用", "故障", "维护"):
        raise HTTPException(400, detail="非法桩位状态")
    pile = conn.execute("SELECT * FROM piles WHERE id=?", (pile_id,)).fetchone()
    if not pile:
        raise HTTPException(404, detail="桩位不存在")
    active = _has_active_on_pile(conn, pile_id)
    if status == "占用":
        # 臂 A：占用态只能由开充写口钉桩推导 —— 手工钉桩 = 手工改计变种，拒绝且留痕，不得伪装成功
        reason = "占用态由充电中/结算中会话集合推导，不开放手工钉桩；请走开充写口"
        seq = audit.append(conn, audit.桩位状态, {
            "写口": "桩位状态", "桩位编号": pile_id, "请求状态": "占用",
            "结果": "已拒绝", "拒因": reason, "操作员": operator,
        })
        return {"桩位编号": pile_id, "状态": "已拒绝", "拒因": reason, "审计序号": seq}
    if active and status in ("故障", "维护"):
        raise HTTPException(400, detail="仍有在充会话，不可直接改故障或维护")
    if status == "空闲":
        if active:
            raise HTTPException(400, detail="仍有在充会话，不可改空闲")
        if pile["status"] == "占用":
            raise HTTPException(409, detail="占用列与会话册不一致，请调 /api/重放修复 按选定真源纠正")
    conn.execute("UPDATE piles SET status=? WHERE id=?", (status, pile_id))
    seq = audit.append(conn, audit.桩位状态, {
        "写口": "桩位状态", "桩位编号": pile_id, "由": pile["status"], "至": status,
        "结果": "已应用", "操作员": operator,
    })
    return {"桩位编号": pile_id, "状态": status, "审计序号": seq}

_open_session_impl = open_session


def open_session(*args, **kwargs):
    out = _open_session_impl(*args, **kwargs)
    return dual_surface.after_open(args[0] if args else None, out, *args[1:], **kwargs)

_settle_impl = settle


def settle(*args, **kwargs):
    out = _settle_impl(*args, **kwargs)
    return dual_surface.after_settle(args[0] if args else None, out, *args[1:], **kwargs)

