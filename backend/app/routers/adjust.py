from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from app.db import write_db
from app.services import adjust as svc

router = APIRouter()


class AdjustIn(BaseModel):
    操作员: str = Field(min_length=1)
    钉桩桩数: int | None = None
    充电中会话数: int | None = None
    备注: str = ""
    幂等键: str | None = None


@router.post("/改计")
def manual_adjust(body: AdjustIn):
    """手工改计口（臂 A）：一律拒绝并留痕，HTTP 409，绝不伪装写口成功。"""
    with write_db() as conn:
        receipt = svc.manual_adjust(
            conn,
            operator=body.操作员,
            pinned_piles=body.钉桩桩数,
            charging_sessions=body.充电中会话数,
            note=body.备注,
            idem_key=body.幂等键,
        )
        return JSONResponse(status_code=409, content=receipt)
