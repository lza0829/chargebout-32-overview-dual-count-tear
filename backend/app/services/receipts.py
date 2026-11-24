"""幂等回执：半截回执兜底。

每个写口回执按幂等键落库（与业务写入同事务）：
- 同键重试 → 返回原回执，不重复落数；
- 同键跨写口 → 409 干净拒绝；
- 写口半截崩溃 → 整笔回滚，回执不留痕，同键重试可干净重放。
"""
from __future__ import annotations
import json
import uuid
from fastapi import HTTPException

from app.services.core import now_str


def new_key(idem_key: str | None, port: str) -> str:
    """调用方未给幂等键时生成一次性键（仅落库备查，不具备跨重试去重能力）。"""
    return idem_key or f"auto-{port}-{uuid.uuid4().hex}"


def stored_receipt(conn, idem_key: str, port: str) -> dict | None:
    row = conn.execute("SELECT port, body_json FROM receipts WHERE idem_key=?", (idem_key,)).fetchone()
    if row is None:
        return None
    if row["port"] != port:
        raise HTTPException(409, detail=f"幂等键 {idem_key!r} 已被写口「{row['port']}」占用")
    return json.loads(row["body_json"])


def store_receipt(conn, idem_key: str, port: str, receipt: dict) -> None:
    conn.execute(
        "INSERT INTO receipts(idem_key,port,body_json,created_at) VALUES(?,?,?,?)",
        (idem_key, port, json.dumps(receipt, ensure_ascii=False, sort_keys=True), now_str()),
    )
