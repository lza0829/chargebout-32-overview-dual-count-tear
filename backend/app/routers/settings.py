from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.db import db, rows, write_db
from app.services import audit, counters
from app.services.core import set_setting

router = APIRouter()

# 臂 A 下不存在的首页加速/对齐旁路键：设置口也不得把它们写回来。
BYPASS_KEYS = frozenset(counters.BYPASS_SETTING_KEYS)


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
        before = counters.evidence_fingerprint(conn)
        if body.键 in BYPASS_KEYS:
            reason = (
                "该键为「首页加速计数/对齐旁路」，臂 A 下两格由会话集合重放推导，"
                "不开放任何旁路对齐写入；如需纠正占用列请调 /api/重放修复"
            )
            seq = audit.append(conn, audit.设置被拒, {
                "写口": "设置", "键": body.键, "值": body.值,
                "结果": "已拒绝", "拒因": reason, "双计数": counters.replay_dual_counters(conn),
            })
            counters.assert_evidence_unchanged(conn, before, "设置")
            return JSONResponse(
                status_code=409,
                content={"键": body.键, "结果": "已拒绝", "拒因": reason, "审计序号": seq},
            )
        set_setting(conn, body.键, body.值)
        dual = counters.replay_dual_counters(conn)
        audit.append(conn, audit.设置, {"写口": "设置", "键": body.键, "值": body.值, "双计数": dual})
        counters.assert_evidence_unchanged(conn, before, "设置")
        return {"键": body.键, "值": body.值}
