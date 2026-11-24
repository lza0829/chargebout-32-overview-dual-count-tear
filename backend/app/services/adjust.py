"""手工改计口（臂 A：一律拒绝，整笔留痕，不得伪装写口成功）。

钉桩桩数与充电中会话数由充电中/结算中会话集合按选定口径重放推导，
没有可写的计数存储 —— 手工改计不开放写入口：
- 不改任何业务状态；
- 写「手工改计被拒」审计（含请求内容、拒因、当时重放双计数）；
- 回执状态恒为「已拒绝」，HTTP 409，绝不伪装成写口成功；
- 幂等键同键重试返回同一张拒绝回执，审计不重复。
- 回执/审计里没有任何「已对齐」宣称：只有重放快照，刷不绿任何一格。
"""
from __future__ import annotations
from app.services import audit, counters
from app.services.receipts import new_key, stored_receipt, store_receipt

REJECTION = (
    "ARM_A_SESSION_DERIVED：钉桩桩数与充电中会话数由充电中/结算中会话集合按选定口径重放推导，"
    "手工改计不开放写入口；如需变动请走开充/结算关账/超时/中断写口。"
)


def manual_adjust(
    conn,
    operator: str,
    pinned_piles: int | None = None,
    charging_sessions: int | None = None,
    note: str = "",
    idem_key: str | None = None,
) -> dict:
    key = new_key(idem_key, "改计")
    cached = stored_receipt(conn, key, "改计")
    if cached is not None:
        return cached
    before = counters.evidence_fingerprint(conn)
    dual = counters.replay_dual_counters(conn)
    report = counters.consistency_report(conn)
    requested = {"钉桩桩数": pinned_piles, "充电中会话数": charging_sessions, "备注": note}
    seq = audit.append(conn, audit.手工改计被拒, {
        "写口": "改计", "幂等键": key, "操作员": operator,
        "请求": requested, "拒因": REJECTION, "双计数": dual,
        "证据重放": report["重放"], "当前对齐": report["对齐"],
    })
    counters.assert_evidence_unchanged(conn, before, "改计")
    receipt = {
        "状态": "已拒绝",
        "写口": "改计",
        "幂等键": key,
        "拒因": REJECTION,
        "请求": requested,
        "双计数": dual,
        "证据重放": report["重放"],
        "当前对齐": report["对齐"],
        "审计序号": seq,
        "消息": "手工改计已拒绝并留痕：双计数由会话集合重放推导，不开放手工写入口",
    }
    store_receipt(conn, key, "改计", receipt)
    return receipt
