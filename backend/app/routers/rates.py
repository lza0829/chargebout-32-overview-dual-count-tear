from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.db import db, write_db
from app.services import core

router = APIRouter()


class RateIn(BaseModel):
    名称: str = Field(min_length=1)
    峰价: float
    平价: float
    谷价: float


@router.get("/费率")
def list_rates():
    with db() as conn:
        return core.list_rates(conn)


@router.post("/费率")
def create_rate(body: RateIn):
    with write_db() as conn:
        cur = conn.execute(
            "INSERT INTO rate_plans(name,peak_price,flat_price,valley_price) VALUES(?,?,?,?)",
            (body.名称, body.峰价, body.平价, body.谷价),
        )
        return {"编号": cur.lastrowid, "名称": body.名称}
