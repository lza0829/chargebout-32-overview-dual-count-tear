from __future__ import annotations
from fastapi import HTTPException

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
    }


def seal_day(conn, note: str = "") -> dict:
    d = today()
    if is_day_sealed(conn, d):
        raise HTTPException(400, detail="本日已封印")
    ts = now_str()
    conn.execute(
        """INSERT INTO day_seals(business_day,sealed,sealed_at,note) VALUES(?,?,?,?)
           ON CONFLICT(business_day) DO UPDATE SET sealed=1, sealed_at=excluded.sealed_at, note=excluded.note""",
        (d, 1, ts, note),
    )
    return get_day(conn, d)


def unseal_day(conn) -> dict:
    d = today()
    r = conn.execute("SELECT * FROM day_seals WHERE business_day=?", (d,)).fetchone()
    if not r or not r["sealed"]:
        raise HTTPException(400, detail="本日未封印")
    conn.execute(
        "UPDATE day_seals SET sealed=0, sealed_at=NULL, note='' WHERE business_day=?",
        (d,),
    )
    return get_day(conn, d)
