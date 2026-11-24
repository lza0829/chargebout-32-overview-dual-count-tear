from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.db import db, write_db
from app.services import core

router = APIRouter()


class SiteIn(BaseModel):
    名称: str = Field(min_length=1)
    地址: str = ""
    启用: bool = True


@router.get("/站点")
def list_sites():
    with db() as conn:
        return core.list_sites(conn)


@router.post("/站点")
def create_site(body: SiteIn):
    with write_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO sites(name,address,active) VALUES(?,?,?)",
                (body.名称, body.地址, 1 if body.启用 else 0),
            )
        except Exception as e:
            raise HTTPException(400, detail=f"无法新建站点：{e}") from e
        return {"编号": cur.lastrowid, "名称": body.名称}


@router.post("/站点/{site_id}/启用")
def enable_site(site_id: int):
    with write_db() as conn:
        conn.execute("UPDATE sites SET active=1 WHERE id=?", (site_id,))
        return {"编号": site_id, "启用": True}


@router.post("/站点/{site_id}/停用")
def disable_site(site_id: int):
    with write_db() as conn:
        conn.execute("UPDATE sites SET active=0 WHERE id=?", (site_id,))
        return {"编号": site_id, "启用": False}
