from __future__ import annotations
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from app.db import db, write_db
from app.services import core
from app.services.sessions import set_pile_status

router = APIRouter()


class PileStatusIn(BaseModel):
    状态: str
    操作员: str = ""


class PileIn(BaseModel):
    站点编号: int
    名称: str = Field(min_length=1)
    额定功率: float = 7
    费率编号: int = 1


@router.get("/桩位")
def list_piles(站点编号: int | None = None):
    with db() as conn:
        return core.list_piles(conn, 站点编号)


@router.post("/桩位")
def create_pile(body: PileIn):
    with write_db() as conn:
        cur = conn.execute(
            "INSERT INTO piles(site_id,name,rated_kw,status,rate_plan_id) VALUES(?,?,?,?,?)",
            (body.站点编号, body.名称, body.额定功率, "空闲", body.费率编号),
        )
        pid = cur.lastrowid
        conn.execute(
            "INSERT INTO guns(pile_id,name,status) VALUES(?,?, '可用')",
            (pid, "主枪"),
        )
        return {"编号": pid, "名称": body.名称}


@router.post("/桩位/{pile_id}/状态")
def change_status(pile_id: int, body: PileStatusIn):
    with write_db() as conn:
        receipt = set_pile_status(conn, pile_id, body.状态, body.操作员)
        if receipt.get("状态") == "已拒绝":
            # 手工钉桩被拒：留痕已落库，409 返回，不得伪装写口成功
            return JSONResponse(status_code=409, content=receipt)
        return receipt
