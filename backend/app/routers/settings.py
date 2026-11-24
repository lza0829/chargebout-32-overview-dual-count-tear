from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from app.db import db, rows, write_db
from app.services.core import set_setting

router = APIRouter()


class SettingIn(BaseModel):
    键: str
    值: str


@router.get("/设置")
def list_settings():
    with db() as conn:
        return rows(conn.execute("SELECT key AS 键, value AS 值 FROM settings ORDER BY key").fetchall())


@router.post("/设置")
def upsert(body: SettingIn):
    with write_db() as conn:
        set_setting(conn, body.键, body.值)
        return {"键": body.键, "值": body.值}
