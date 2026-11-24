from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.db import db, write_db
from app.services import core
from app.services import sessions as svc

router = APIRouter()


class OpenIn(BaseModel):
    桩位编号: int
    枪线编号: int | None = None
    幂等键: str | None = None


class PulseIn(BaseModel):
    电量: float = Field(gt=0)
    功率: float = 0
    幂等键: str | None = None


class KeyIn(BaseModel):
    幂等键: str | None = None


class AbortIn(BaseModel):
    原因: str = "急停"
    幂等键: str | None = None


@router.get("/会话")
def list_sessions(状态: str | None = None):
    with db() as conn:
        return core.list_sessions(conn, 状态)


@router.get("/会话/{session_id}")
def get_session(session_id: int):
    with db() as conn:
        d = core.session_detail(conn, session_id)
        if not d:
            raise HTTPException(404, detail="会话不存在")
        return d


@router.post("/开会话")
def open_session(body: OpenIn):
    with write_db() as conn:
        return svc.open_session(conn, body.桩位编号, body.枪线编号, body.幂等键)


@router.post("/会话/{session_id}/脉冲")
def add_pulse(session_id: int, body: PulseIn):
    with write_db() as conn:
        return svc.add_pulse(conn, session_id, body.电量, body.功率, body.幂等键)


@router.post("/会话/{session_id}/结算")
def settle(session_id: int, body: KeyIn | None = None):
    with write_db() as conn:
        return svc.settle(conn, session_id, body.幂等键 if body else None)


@router.post("/会话/{session_id}/超时")
def timeout(session_id: int, body: KeyIn | None = None):
    with write_db() as conn:
        return svc.mark_timeout(conn, session_id, body.幂等键 if body else None)


@router.post("/会话/{session_id}/中断")
def abort(session_id: int, body: AbortIn | None = None):
    with write_db() as conn:
        reason = body.原因 if body else "急停"
        return svc.abort_session(conn, session_id, reason, body.幂等键 if body else None)
