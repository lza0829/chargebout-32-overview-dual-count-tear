from __future__ import annotations
from fastapi import APIRouter
from app.db import db, write_db
from app.services import audit as audit_svc
from app.services import core, counters

router = APIRouter()


@router.get("/总览")
def get_overview():
    """总览双计数刷新：钉桩桩数/充电中会话数按选定口径读即重放。"""
    with db() as conn:
        return core.overview(conn)


@router.get("/对照")
def get_consistency():
    """四面对照：总览双格 ↔ 会话册 ↔ 桩位页 ↔ 枪线占用列。"""
    with db() as conn:
        return counters.consistency_report(conn)


@router.post("/重放修复")
def post_replay_repair():
    """按选定真源（充电中/结算中会话集合）重放，纠正桩/枪占用列投影并留审计。"""
    with write_db() as conn:
        corrections = counters.replay_and_repair(conn)
        return {"纠正": corrections, "对照": counters.consistency_report(conn)}


@router.get("/审计")
def get_audit(类别: str | None = None, 条数: int = 200):
    with db() as conn:
        return audit_svc.list_audit(conn, 类别, 条数)
