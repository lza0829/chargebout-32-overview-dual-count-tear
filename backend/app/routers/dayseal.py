from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from app.db import db, write_db
from app.services import dayseal as svc

router = APIRouter()


class SealIn(BaseModel):
    备注: str = ""


@router.get("/充日")
def get_day():
    with db() as conn:
        return svc.get_day(conn)


@router.post("/充日/封印")
def seal(body: SealIn | None = None):
    with write_db() as conn:
        return svc.seal_day(conn, body.备注 if body else "")


@router.post("/充日/解封")
def unseal():
    with write_db() as conn:
        return svc.unseal_day(conn)
