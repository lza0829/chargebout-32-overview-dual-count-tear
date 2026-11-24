from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.db import db, write_db
from app.services import core

router = APIRouter()


class GunIn(BaseModel):
    桩位编号: int
    名称: str = Field(min_length=1)


@router.get("/枪线")
def list_guns(桩位编号: int | None = None):
    with db() as conn:
        return core.list_guns(conn, 桩位编号)


@router.post("/枪线")
def create_gun(body: GunIn):
    with write_db() as conn:
        cur = conn.execute(
            "INSERT INTO guns(pile_id,name,status) VALUES(?,?, '可用')",
            (body.桩位编号, body.名称),
        )
        return {"编号": cur.lastrowid, "名称": body.名称}
