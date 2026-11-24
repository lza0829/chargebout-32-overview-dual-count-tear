"""审计流水：只追加，禁改禁删（由触发器兜底）。

每个写口在同事务内落审计，明细带「双计数」快照（同事务算出），
使审计流水本身即可按选定口径逐条对照重放。
"""
from __future__ import annotations
import json
from datetime import datetime

# 审计事件类别
开充 = "开充"
结算 = "结算"
关账 = "关账"
超时 = "超时"
中断 = "中断"
桩位状态 = "桩位状态"
手工改计被拒 = "手工改计被拒"
重放纠正 = "重放纠正"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append(conn, kind: str, detail: dict) -> int:
    cur = conn.execute(
        "INSERT INTO audit_log(ts,kind,detail_json) VALUES(?,?,?)",
        (_now(), kind, json.dumps(detail, ensure_ascii=False, sort_keys=True)),
    )
    return int(cur.lastrowid)


def list_audit(conn, kind: str | None = None, limit: int = 200) -> list[dict]:
    sql = "SELECT seq,ts,kind,detail_json FROM audit_log"
    args: list = []
    if kind:
        sql += " WHERE kind=?"
        args.append(kind)
    sql += " ORDER BY seq DESC LIMIT ?"
    args.append(limit)
    return [
        {"序号": r["seq"], "时间": r["ts"], "类别": r["kind"], "明细": json.loads(r["detail_json"])}
        for r in conn.execute(sql, args).fetchall()
    ]
