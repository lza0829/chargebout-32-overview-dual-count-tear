from __future__ import annotations
from fastapi import HTTPException

from app.services import audit, counters
from app.services.core import is_day_sealed, now_str, today


def get_day(conn, day: str | None = None) -> dict:
    d = day or today()
    r = conn.execute("SELECT * FROM day_seals WHERE business_day=?", (d,)).fetchone()
    open_n = conn.execute(
        "SELECT COUNT(*) AS n FROM sessions WHERE business_day=? AND status IN ('充电中','结算中')",
        (d,),
    ).fetchone()["n"]
    return {
        "营业日": d,
        "已封印": bool(r and r["sealed"]),
        "封印时间": r["sealed_at"] if r else None,
        "备注": r["note"] if r else "",
        "未结会话数": open_n,
        "双计数": counters.replay_dual_counters(conn),
    }


def seal_day(conn, note: str = "") -> dict:
    """锁账写口（封印）：只落「充日封印」这一锁账事实，不得拧动双计数证据。"""
    d = today()
    if is_day_sealed(conn, d):
        raise HTTPException(400, detail="本日已封印")
    before = counters.evidence_fingerprint(conn)
    ts = now_str()
    conn.execute(
        """INSERT INTO day_seals(business_day,sealed,sealed_at,note) VALUES(?,?,?,?)
           ON CONFLICT(business_day) DO UPDATE SET sealed=1, sealed_at=excluded.sealed_at, note=excluded.note""",
        (d, 1, ts, note),
    )
    dual = counters.replay_dual_counters(conn)
    audit.append(conn, audit.封印, {
        "写口": "封印", "营业日": d, "备注": note, "双计数": dual,
    })
    counters.assert_evidence_unchanged(conn, before, "封印")
    return get_day(conn, d)


def unseal_day(conn) -> dict:
    d = today()
    r = conn.execute("SELECT * FROM day_seals WHERE business_day=?", (d,)).fetchone()
    if not r or not r["sealed"]:
        raise HTTPException(400, detail="本日未封印")
    before = counters.evidence_fingerprint(conn)
    conn.execute(
        "UPDATE day_seals SET sealed=0, sealed_at=NULL, note='' WHERE business_day=?",
        (d,),
    )
    dual = counters.replay_dual_counters(conn)
    audit.append(conn, audit.解封, {
        "写口": "解封", "营业日": d, "双计数": dual,
    })
    counters.assert_evidence_unchanged(conn, before, "解封")
    return get_day(conn, d)
