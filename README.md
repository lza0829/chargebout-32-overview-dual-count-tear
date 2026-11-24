# 充桩条

开会话 → 计量脉冲累加 → 结算关账 → 超时/异常命运。

- 前端 http://127.0.0.1:6500
- API http://127.0.0.1:11500

```powershell
# 本地 API
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 11500

# 本地前端（另开）
cd frontend
npm install
npm run dev
```

或 `docker compose up -d --build`。

```bash
# 双计数夹具（34 例）
cd backend && .venv/bin/python -m unittest discover -s tests -t . -v
```

---

## 总览双计数一致性（钉桩桩数 / 充电中会话数）

### 选定架构臂：A —— 以充电中/结算中会话集合推导钉桩（全局唯一，不混用臂 B）

正确性口径（唯一谓词，`backend/app/services/counters.py: replay_dual_counters`）：

```sql
钉桩桩数     = SELECT COUNT(DISTINCT pile_id) FROM sessions WHERE status IN ('充电中','结算中')
充电中会话数 = SELECT COUNT(*)               FROM sessions WHERE status = '充电中'
```

- **总览双格无独立存储、不落快照：读即重放。**「只改两格展示」与「手工改计假齐」在本臂无落点。
- **假钉桩对齐的收口口径（全局唯一）**：两格数字必须能由「充电中去重钉桩会话集合 ∪ 桩位占用列」
  重放出来；对不上则 `GET /api/总览` 返回 `已对齐=false` 并列出 `拧花`，**禁止只改首页文案、
  禁止旁路改两格数字**。计数写口落账后若证据仍对不上，**整笔回退**（HTTP 409），不留半截假齐。
- 桩/枪占用列只是谓词的**投影**：写口同事务按真源**重算**（绝不增量加减，并发开充关账不会一边加一边减）；
  漂移时由 `POST /api/重放修复` 按同一谓词纠正并写「重放纠正」审计。
- 旧世界的首页加速计数器（`settings.surface_last` / `surface_ok`、`surface_*` 覆盖字段、
  任何「已对齐/surface_ok」自证）已被移除：读到即判定为旁路宣称，`已对齐` 恒为 false，
  直到 `POST /api/重放修复` 清除设置并把作废事实写进只增审计。
- 臂内去重规则：同桩多枪可各钉一条会话，钉桩数按桩 `DISTINCT` 去重；一条枪线至多一条钉桩会话
  （部分唯一索引 `ux_sessions_active_gun` 兜底并发）。
- 臂 B（桩表占用态点计）未选用：代码库不存在桩表点计路径，全局不混用。

### 不变式

1. 会话状态机：`充电中 →(结算关账,单事务)→ 结算中 → 已关账`；`充电中/结算中 →(超时)→ 已超时`、
   `→(中断)→ 已中断`。`已关账/已超时/已中断` 为计数域终结态；已超时仅可补关账（计价域，双计数不再动）。
2. 每个写口一个写事务（`write_db()` = `BEGIN IMMEDIATE`，写口串行化）：会话状态列 + 占用列投影 +
   审计流水 + 幂等回执**同事务**落库；回执内嵌双计数与总览刷新**同一谓词、同事务**算出。
3. 幂等键兜底半截回执：同键重试返回原回执不重复落数；同键跨写口 409；半截崩溃整笔回滚，同键可干净重放。
4. 手工改计一律拒绝：不改任何业务状态，写「手工改计被拒」审计，HTTP 409 + `状态=已拒绝`，
   绝不伪装写口成功；同键重试回同一张拒绝回执，审计不重复；回执**不含任何对齐宣称**。
5. 审计流水只增不改不删（触发器兜底），每条写口事件带「双计数」快照，审计流本身即可按口径逐条回放。
   对账时同时重放审计：最新双计数快照 ≠ 当前重放 → 判「疑似绕过写口落账」，`已对齐=false`。
   回执/审计/设置中任何 `已对齐`/`surface_ok` 宣称都不算数，只按重放判定。
6. 桩位状态口只管 故障/维护/恢复；手工「占用」= 手工钉桩，拒绝并留痕（409）。
7. **非计数写口零证据改动**：脉冲（`POST /api/会话/{id}/脉冲`，可带幂等键）、充日封印/解封、
   桩位状态写口落账前后比对双计数证据指纹（会话集合 + 桩/枪占用列 + 双格），
   变了即整笔回退（409）—— 脉冲进电量、锁账拒写若误拧两格会被识破，电量本身也不落。
8. 对账受理：`POST /api/重放修复` 在全量纠正后写一条「对账受理」审计（含当日重放双计数与证据），
   使直改后的系统能在保留完整审计痕迹的前提下恢复如实对齐。

### 定位面映射

| 面 | 位置 |
| --- | --- |
| 开充入口 | `POST /api/开会话` → `services/sessions.py: open_session` |
| 结算关账入口 | `POST /api/会话/{id}/结算` → `services/sessions.py: settle` |
| 超时入口 | `POST /api/会话/{id}/超时` → `services/sessions.py: mark_timeout` |
| 中断入口 | `POST /api/会话/{id}/中断` → `services/sessions.py: abort_session` |
| 脉冲入口 | `POST /api/会话/{id}/脉冲` → `services/sessions.py: add_pulse`（零证据改动） |
| 锁账入口（充日封印/解封） | `POST /api/充日/封印` `/解封` → `services/dayseal.py`（零证据改动） |
| 手工改计入口 | `POST /api/改计` → `services/adjust.py: manual_adjust`（一律拒绝） |
| 桩位状态口 | `POST /api/桩位/{id}/状态` → `services/sessions.py: set_pile_status` |
| 桩位占用列 / 枪线占用列 | `piles.status` / `guns.status`（投影，`counters.refresh_projection` 维护） |
| 会话状态列 / 充电中会话集合 | `sessions.status` / `counters.charging_session_ids` |
| 总览钉桩格 / 充电中格 / 双计数刷新 | `GET /api/总览` → `services/core.py: overview`（读即重放） |
| 桩位页 / 会话册 / 对账页 | `GET /api/桩位` / `GET /api/会话` / 前端 `对账` 页（`GET /api/对照` + `GET /api/审计`） |
| 审计流水 | `GET /api/审计` → `audit_log` 表（append-only） |
| 四面对照 / 审计重放 / 旁路宣称核对 | `GET /api/对照` → `counters.consistency_report` |
| 读路径重放纠正 | `POST /api/重放修复` → `counters.replay_and_repair` |

### 夹具对照（`backend/tests/test_dual_counters.py`，34 例）

| 场景 | 测试 |
| --- | --- |
| 手工改计假齐 | `TestManualAdjust`（409 拒绝 + 留痕 + 状态零改动 + 幂等） |
| 关账减会话留钉桩 | `test_settle_close_releases_pin_with_session` |
| 开充关账并发漂数 | `test_concurrent_open_settle_no_drift` |
| 超时中断后仪表未减 | `test_timeout_interrupt_decrement_dashboard` |
| 桩位页与仪表长期拧花 | `test_long_term_alignment_soak`（200 步随机 + 故障注入，每步对照） |
| 会话册充电中与仪表两格对不上 | `test_ledger_charging_matches_dashboard_cells` |
| 枪线占用与桩位占用同时漂数 | `test_gun_pile_occupancy_dedup_and_release` |
| 半截回滚后总览与会话册假齐 | `test_half_rollback_settle/open_leaves_no_divergence` |
| 开充成功总览充电中未加 / 关账成功总览钉桩未减 | `test_open_receipt_increments_dashboard` 等回执断言 |
| 半截回执 | `test_half_receipt_retry_returns_same_receipt` |
| 并发开充关账半截 | `test_concurrent_crash_retry_no_drift` |
| 同枪并发双钉 | `test_concurrent_same_gun_single_pin` |
| 占用列漂移重放纠正 | `test_replay_repairs_projection_drift` |
| 桩位状态口手工钉桩 | `test_manual_pin_rejected_and_audited` |
| 审计只增 / 谓词结算中口径 | `TestAuditTrail` / `test_arm_predicate_settling_pins_but_not_charging` |
| 两格亮齐与去重钉桩不一致（旁路缓存） | `TestEvidenceTear.test_aligned_claim_never_overrides_dedup_pins` |
| 桩位页与首页分叉 + 重放纠正 | `TestEvidenceTear.test_ledger_and_pages_fork_detected_and_repaired` |
| 直改会话被审计重放识破 | `TestEvidenceTear.test_direct_session_write_is_detected_by_audit_replay` |
| 流水/回执单独刷绿 | `TestEvidenceTear.test_receipt_or_audit_claim_alone_cannot_paint_green` |
| 改计口假齐（回执无对齐宣称） | `TestEvidenceTear.test_manual_adjust_receipt_never_claims_alignment` |
| 超时写口误拧占用列 → 整笔回退 | `TestMiswiredWritePorts.test_timeout_miswiring_projection_rolls_back` |
| 急停写口误拧另一会话 → 整笔回退 | `TestMiswiredWritePorts.test_abort_miswiring_runtime_evidence_rolls_back` |
| 脉冲写口误改两格 → 整笔回退 | `TestMiswiredWritePorts.test_pulse_miswiring_counts_rolls_back` |
| 锁账写口误改两格 → 整笔回退 | `TestMiswiredWritePorts.test_seal_miswiring_rolls_back` |
| 开充关账交错漂数 | `TestInterleavedAndHalfRollback.test_interleaved_open_settle_never_one_up_one_down` |
| 半截回滚后不得假齐（关账/开充） | `TestInterleavedAndHalfRollback.test_half_rollback_settle/open_never_fake_aligned` |
| 脉冲幂等且证据中性 | `TestInterleavedAndHalfRollback.test_pulse_is_idempotent_and_evidence_neutral` |
| 重放修复作废旁路宣称 | `TestReplayRepairPurgesBypass` |
| 直改后重放修复恢复如实对齐 | `TestReconcileAcceptance` |

### 范围

只覆盖总览「钉桩桩数」与「充电中会话数」双计数口径；电量真源与计价另立需求
（`已超时` 会话补关账仅收尾金额，不动双计数）。前端随之改动：总览页不再读 `surface_*` 旁路字段、
如实展示「已对齐/未对齐 + 拧花 + 证据」，桩位页与会话册标注与首页是否对齐，并新增「对账」页
（四面对照 + 审计重放 + 重放修复）。
