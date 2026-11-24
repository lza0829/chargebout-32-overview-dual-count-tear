"""双计数口径夹具（臂 A：以充电中/结算中会话集合推导钉桩）。

覆盖任务点名场景：
  手工改计假齐 / 关账减会话留钉桩 / 开充关账并发漂数 / 超时中断后仪表未减 /
  桩位页与仪表长期拧花 / 会话册充电中与仪表两格对不上 /
  枪线占用与桩位占用同时漂数 / 半截回滚后总览与会话册假齐 /
  开充成功总览充电中未加 / 关账成功总览钉桩未减 /
  半截回执幂等 / 读路径重放纠正 / 同枪并发单钉 / 审计流水只增 / 桩位状态口规则
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock

from fastapi import HTTPException

import app.db as db_mod
from app.routers import adjust as adjust_router
from app.routers import dashboard as dash_router
from app.routers import piles as piles_router
from app.services import adjust as adjust_svc
from app.services import core, counters
from app.services import dayseal as dayseal_svc
from app.services import sessions as svc


class FaultInjected(Exception):
    """夹具注入：模拟写口半截崩溃（进程宕机），事务须整笔回滚。"""


class DualCounterBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_mod.DB_PATH = os.path.join(self.tmp.name, "t.db")
        db_mod.init_db()
        with db_mod.write_db() as conn:
            conn.execute("INSERT INTO sites(name,address,active) VALUES('甲站','',1)")
            conn.execute(
                "INSERT INTO rate_plans(name,peak_price,flat_price,valley_price) VALUES('费率',1,1,1)"
            )
            for pname, gnames in [("桩一", ["左枪", "右枪"]), ("桩二", ["单枪"]), ("桩三", ["单枪"])]:
                cur = conn.execute(
                    "INSERT INTO piles(site_id,name,rated_kw,status,rate_plan_id) VALUES(1,?,7,'空闲',1)",
                    (pname,),
                )
                pid = cur.lastrowid
                for g in gnames:
                    conn.execute("INSERT INTO guns(pile_id,name,status) VALUES(?,?,'可用')", (pid, g))
            conn.execute("INSERT INTO settings(key,value) VALUES('会话序号','1000')")
            conn.execute("INSERT INTO settings(key,value) VALUES('超时分钟','120')")
        with db_mod.db() as conn:
            piles = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM piles").fetchall()}
            by_pile: dict[int, list[int]] = {}
            for r in conn.execute("SELECT id,pile_id FROM guns ORDER BY id").fetchall():
                by_pile.setdefault(r["pile_id"], []).append(r["id"])
        self.p1, self.p2, self.p3 = piles["桩一"], piles["桩二"], piles["桩三"]
        self.g1, self.g2 = by_pile[self.p1]
        self.g3, self.g4 = by_pile[self.p2][0], by_pile[self.p3][0]

    def tearDown(self):
        self.tmp.cleanup()

    # ---- 读面便捷 ----
    def overview(self) -> dict:
        with db_mod.db() as conn:
            return core.overview(conn)

    def report(self) -> dict:
        with db_mod.db() as conn:
            return counters.consistency_report(conn)

    def assertAligned(self):
        rep = self.report()
        self.assertTrue(rep["对齐"], msg=f"四面对照拧花: {rep['拧花']}")

    def assertDual(self, pinned: int, charging: int):
        o = self.overview()
        self.assertEqual(o["桩位占用"], pinned, "总览钉桩格")
        self.assertEqual(o["充电中"], charging, "总览充电中格")

    def _audit(self) -> list[dict]:
        with db_mod.db() as conn:
            rows = conn.execute("SELECT kind, detail_json FROM audit_log ORDER BY seq").fetchall()
            return [{"类别": r["kind"], "明细": json.loads(r["detail_json"])} for r in rows]

    def _session_state(self, sid: int) -> str:
        with db_mod.db() as conn:
            return conn.execute("SELECT status FROM sessions WHERE id=?", (sid,)).fetchone()["status"]

    def _pile_status(self, pid: int) -> str:
        with db_mod.db() as conn:
            return conn.execute("SELECT status FROM piles WHERE id=?", (pid,)).fetchone()["status"]

    def _gun_status(self, gid: int) -> str:
        with db_mod.db() as conn:
            return conn.execute("SELECT status FROM guns WHERE id=?", (gid,)).fetchone()["status"]

    def _session_count(self) -> int:
        with db_mod.db() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]

    def _biz_state(self) -> dict:
        """业务状态快照（不含回执/审计等端口自留痕表），用于断言手工改计零改动。"""
        with db_mod.db() as conn:
            return {
                t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()]
                for t in ("sessions", "piles", "guns")
            }

    # ---- 写口便捷（各起一个写事务，与路由层等价） ----
    def _open(self, pile, gun, key):
        with db_mod.write_db() as conn:
            return svc.open_session(conn, pile, gun, key)

    def _settle(self, sid, key):
        with db_mod.write_db() as conn:
            return svc.settle(conn, sid, key)

    def _timeout(self, sid, key):
        with db_mod.write_db() as conn:
            return svc.mark_timeout(conn, sid, key)

    def _abort(self, sid, reason, key):
        with db_mod.write_db() as conn:
            return svc.abort_session(conn, sid, reason, key)


class TestWritePorts(DualCounterBase):
    """四类写口改数 + 回执双计数同事务可对读。"""

    def test_open_receipt_increments_dashboard(self):
        """夹具[开充成功总览充电中未加]：回执双格同事务算出，与总览刷新一致。"""
        r = self._open(self.p1, self.g1, "k1")
        self.assertEqual(r["双计数"], {"钉桩桩数": 1, "充电中会话数": 1})
        self.assertDual(1, 1)
        self.assertEqual(self._pile_status(self.p1), "占用")
        self.assertEqual(self._gun_status(self.g1), "占用")
        self.assertAligned()

    def test_settle_close_releases_pin_with_session(self):
        """夹具[关账减会话留钉桩]：关账成功，充电中格减、钉桩格同减、占用列同刷。"""
        r = self._open(self.p1, self.g1, "k1")
        sid = r["会话编号"]
        self.assertDual(1, 1)
        r2 = self._settle(sid, "close-1")
        self.assertEqual(r2["状态"], "已关账")
        self.assertEqual(r2["双计数"], {"钉桩桩数": 0, "充电中会话数": 0})
        self.assertDual(0, 0)
        self.assertEqual(self._pile_status(self.p1), "空闲")
        self.assertEqual(self._gun_status(self.g1), "可用")
        self.assertEqual(self._session_state(sid), "已关账")
        kinds = [e["类别"] for e in self._audit()]
        self.assertEqual(kinds, ["开充", "结算", "关账"])
        self.assertAligned()

    def test_timeout_interrupt_decrement_dashboard(self):
        """夹具[超时中断后仪表未减]：超时/中断收口后双格立减、占用列同刷。"""
        r1 = self._open(self.p1, self.g1, "k1")
        r2 = self._open(self.p2, self.g3, "k2")
        self.assertDual(2, 2)
        t1 = self._timeout(r1["会话编号"], "t1")
        self.assertEqual(t1["双计数"], {"钉桩桩数": 1, "充电中会话数": 1})
        self.assertDual(1, 1)
        self.assertEqual(self._pile_status(self.p1), "空闲")
        self.assertEqual(self._gun_status(self.g1), "可用")
        # 已超时即计数域终结：不可再标超时；可补关账（计价域），双计数不再动
        with self.assertRaises(HTTPException):
            self._timeout(r1["会话编号"], "t1-again")
        s1 = self._settle(r1["会话编号"], "s1")
        self.assertEqual(s1["状态"], "已关账")
        self.assertDual(1, 1)
        a2 = self._abort(r2["会话编号"], "急停", "a2")
        self.assertEqual(a2["双计数"], {"钉桩桩数": 0, "充电中会话数": 0})
        self.assertDual(0, 0)
        self.assertEqual(self._session_state(r2["会话编号"]), "已中断")
        # 充日未结会话数只计在充（充电中/结算中）
        with db_mod.db() as conn:
            self.assertEqual(dayseal_svc.get_day(conn)["未结会话数"], 0)
        self.assertAligned()

    def test_gun_pile_occupancy_dedup_and_release(self):
        """夹具[枪线占用与桩位占用同时漂数]：同桩双枪各钉一条，桩数去重为 1；逐枪释放。"""
        r1 = self._open(self.p1, self.g1, "k1")
        self._open(self.p1, self.g2, "k2")
        self.assertDual(1, 2)  # 臂内去重：桩按 DISTINCT 计
        self.assertEqual(self._pile_status(self.p1), "占用")
        self.assertEqual(self._gun_status(self.g1), "占用")
        self.assertEqual(self._gun_status(self.g2), "占用")
        self._settle(r1["会话编号"], "c1")
        self.assertDual(1, 1)  # 右枪仍钉桩一
        self.assertEqual(self._pile_status(self.p1), "占用")
        self.assertEqual(self._gun_status(self.g1), "可用")
        self.assertEqual(self._gun_status(self.g2), "占用")
        self.assertAligned()

    def test_ledger_charging_matches_dashboard_cells(self):
        """夹具[会话册充电中与仪表两格对不上]：两格 = 会话册集合按口径点计。"""
        self._open(self.p1, self.g1, "k1")
        self._open(self.p1, self.g2, "k2")
        self._open(self.p2, self.g3, "k3")
        o = self.overview()
        self.assertEqual((o["桩位占用"], o["充电中"]), (2, 3))
        self.assertEqual(o["双计数口径"], counters.PREDICATE_ID)
        self.assertEqual(o["拧花"], [])
        with db_mod.db() as conn:
            self.assertEqual(o["充电中"], len(counters.charging_session_ids(conn)))
            self.assertEqual(o["桩位占用"], len(counters.pinned_pile_ids(conn)))
        self.assertAligned()

    def test_open_validation_clean_rejections(self):
        """写口干净拒绝：不落数、不漂数。"""
        with self.assertRaises(HTTPException) as ctx:
            self._open(999, None, "v1")
        self.assertEqual(ctx.exception.status_code, 404)
        with self.assertRaises(HTTPException):  # 枪不属于该桩
            self._open(self.p2, self.g1, "v2")
        with db_mod.write_db() as conn:  # 维护桩不可开充
            svc.set_pile_status(conn, self.p3, "维护")
        with self.assertRaises(HTTPException):
            self._open(self.p3, self.g4, "v3")
        self._open(self.p1, self.g1, "v4")
        with self.assertRaises(HTTPException):  # 同枪再开
            self._open(self.p1, self.g1, "v5")
        with db_mod.write_db() as conn:  # 充日封印禁止新开充
            dayseal_svc.seal_day(conn)
        with self.assertRaises(HTTPException):
            self._open(self.p2, self.g3, "v6")
        with db_mod.write_db() as conn:
            dayseal_svc.unseal_day(conn)
        self.assertDual(1, 1)
        self.assertAligned()

    def test_arm_predicate_settling_pins_but_not_charging(self):
        """臂 A 口径：结算中会话仍钉桩、不计充电中（谓词直验，验后回滚）。"""
        r = self._open(self.p1, self.g1, "k1")

        class _Rollback(Exception):
            pass

        with self.assertRaises(_Rollback):
            with db_mod.write_db() as conn:
                conn.execute("UPDATE sessions SET status='结算中' WHERE id=?", (r["会话编号"],))
                dual = counters.replay_dual_counters(conn)
                self.assertEqual(dual, {"钉桩桩数": 1, "充电中会话数": 0})
                raise _Rollback()
        self.assertDual(1, 1)
        self.assertAligned()


class TestIdempotencyAndRollback(DualCounterBase):
    """半截回执幂等 + 半截回滚不漂不假齐。"""

    def test_half_receipt_retry_returns_same_receipt(self):
        """半截回执：提交成功但回执丢失，同键重试返回原回执、不重复落数。"""
        r1 = self._open(self.p1, self.g1, "K-半截")
        r2 = self._open(self.p1, self.g1, "K-半截")  # 客户端未收到回执，同键重试
        self.assertEqual(r1, r2)
        self.assertDual(1, 1)
        self.assertEqual(self._session_count(), 1)
        self.assertEqual([e["类别"] for e in self._audit()], ["开充"])
        with self.assertRaises(HTTPException) as ctx:  # 同键跨写口 → 409
            self._settle(r1["会话编号"], "K-半截")
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertAligned()

    def test_half_rollback_settle_leaves_no_divergence(self):
        """夹具[半截回滚后总览双格与会话册假齐]：关账半截崩溃整笔回滚，同键重试干净落账。"""
        r = self._open(self.p1, self.g1, "k1")
        sid = r["会话编号"]
        with mock.patch.object(
            counters, "refresh_projection", side_effect=FaultInjected("夹具注入：半截崩溃")
        ):
            with self.assertRaises(FaultInjected):
                self._settle(sid, "close-1")
        # 整笔回滚：会话仍充电中、双格未漂、占用列未动、审计无半截、回执未落
        self.assertDual(1, 1)
        self.assertEqual(self._session_state(sid), "充电中")
        self.assertEqual(self._pile_status(self.p1), "占用")
        self.assertEqual([e["类别"] for e in self._audit()], ["开充"])
        self.assertAligned()
        # 同键重试：干净落账一次
        r2 = self._settle(sid, "close-1")
        self.assertEqual(r2["状态"], "已关账")
        self.assertDual(0, 0)
        self.assertEqual([e["类别"] for e in self._audit()], ["开充", "结算", "关账"])
        self.assertAligned()

    def test_half_rollback_open_leaves_no_divergence(self):
        """开充半截崩溃：会话未落、占用未动、双格未漂；同键重试干净开充。"""
        with mock.patch.object(
            counters, "refresh_projection", side_effect=FaultInjected("夹具注入：半截崩溃")
        ):
            with self.assertRaises(FaultInjected):
                self._open(self.p1, self.g1, "open-1")
        self.assertDual(0, 0)
        self.assertEqual(self._session_count(), 0)
        self.assertEqual(self._audit(), [])
        r = self._open(self.p1, self.g1, "open-1")
        self.assertEqual(r["状态"], "充电中")
        self.assertDual(1, 1)
        self.assertEqual(self._session_count(), 1)
        self.assertAligned()


class TestManualAdjust(DualCounterBase):
    """夹具[手工改计假齐]：一律拒绝、留痕、不伪装、不拧动任何状态。"""

    def test_manual_adjust_never_fake_aligns(self):
        self._open(self.p1, self.g1, "k1")
        before = self._biz_state()
        resp = adjust_router.manual_adjust(
            adjust_router.AdjustIn(操作员="运维甲", 钉桩桩数=0, 充电中会话数=0, 备注="想刷齐", 幂等键="adj-1")
        )
        self.assertEqual(resp.status_code, 409)
        payload = json.loads(resp.body)
        self.assertEqual(payload["状态"], "已拒绝")  # 不得伪装成写口成功
        self.assertIn("ARM_A_SESSION_DERIVED", payload["拒因"])
        self.assertEqual(payload["双计数"], {"钉桩桩数": 1, "充电中会话数": 1})
        # 双格、册页、占用列零改动
        self.assertEqual(self._biz_state(), before)
        self.assertDual(1, 1)
        # 审计留痕：拒因与请求内容在案
        rejected = [e for e in self._audit() if e["类别"] == "手工改计被拒"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["明细"]["操作员"], "运维甲")
        self.assertEqual(rejected[0]["明细"]["请求"]["钉桩桩数"], 0)
        # 幂等重试：同键同回执，审计不重复
        resp2 = adjust_router.manual_adjust(
            adjust_router.AdjustIn(操作员="运维甲", 钉桩桩数=0, 充电中会话数=0, 幂等键="adj-1")
        )
        self.assertEqual(json.loads(resp2.body), payload)
        self.assertEqual(len([e for e in self._audit() if e["类别"] == "手工改计被拒"]), 1)
        # 对齐状态下改计同样被拒（拒绝与是否已对齐无关）
        resp3 = adjust_router.manual_adjust(
            adjust_router.AdjustIn(操作员="运维甲", 钉桩桩数=1, 充电中会话数=1, 幂等键="adj-2")
        )
        self.assertEqual(resp3.status_code, 409)
        self.assertAligned()


class TestPileStatusPort(DualCounterBase):
    """桩位状态口：手工钉桩被拒留痕；故障/维护不拧双计数。"""

    def test_manual_pin_rejected_and_audited(self):
        self._open(self.p1, self.g1, "k1")
        # 手工占用 = 手工钉桩 → 409 已拒绝 + 审计
        resp = piles_router.change_status(self.p2, piles_router.PileStatusIn(状态="占用", 操作员="运维甲"))
        self.assertEqual(resp.status_code, 409)
        payload = json.loads(resp.body)
        self.assertEqual(payload["状态"], "已拒绝")
        self.assertDual(1, 1)
        self.assertEqual(self._pile_status(self.p2), "空闲")
        # 有在充改故障 → 400
        with self.assertRaises(HTTPException) as ctx:
            piles_router.change_status(self.p1, piles_router.PileStatusIn(状态="故障"))
        self.assertEqual(ctx.exception.status_code, 400)
        # 维护（无在充桩）→ 应用，双格不动
        r = piles_router.change_status(self.p2, piles_router.PileStatusIn(状态="维护"))
        self.assertEqual(r["状态"], "维护")
        self.assertDual(1, 1)
        self.assertEqual(self.overview()["桩位维护"], 1)
        # 恢复空闲
        piles_router.change_status(self.p2, piles_router.PileStatusIn(状态="空闲"))
        self.assertEqual(self._pile_status(self.p2), "空闲")
        kinds = [e["类别"] for e in self._audit()]
        self.assertGreaterEqual(kinds.count("桩位状态"), 3)
        self.assertAligned()


class TestReplayRepair(DualCounterBase):
    """读路径重放纠正：占用列漂移按选定真源重放纠正并留痕。"""

    def test_replay_repairs_projection_drift(self):
        self._open(self.p1, self.g1, "k1")
        # 模拟历史遗留：绕过写口直改占用列（旧世界手工改计的副作用）
        with db_mod.write_db() as conn:
            conn.execute("UPDATE piles SET status='空闲' WHERE id=?", (self.p1,))
            conn.execute("UPDATE guns SET status='可用' WHERE id=?", (self.g1,))
        # 总览双格由真源推导，不受投影漂移影响
        self.assertDual(1, 1)
        # 但四面对照报拧花（桩位页/枪线占用列漂了）
        rep = self.report()
        self.assertFalse(rep["对齐"])
        self.assertTrue(any("桩位页" in v for v in rep["拧花"]))
        self.assertTrue(any("枪线占用列" in v for v in rep["拧花"]))
        # 重放修复
        out = dash_router.post_replay_repair()
        self.assertEqual(len(out["纠正"]), 2)
        self.assertTrue(out["对照"]["对齐"])
        self.assertEqual(len([e for e in self._audit() if e["类别"] == "重放纠正"]), 2)
        # 再修无事可纠
        self.assertEqual(dash_router.post_replay_repair()["纠正"], [])
        self.assertAligned()


class TestConcurrency(DualCounterBase):
    """并发漂数夹具：写口串行化 + 投影重算 + 幂等重试。"""

    def _run_threads(self, fns):
        errors, receipts = [], {}
        lock = threading.Lock()

        def work(tag, fn):
            try:
                r = fn()
                with lock:
                    receipts[tag] = r
            except Exception as exc:  # 收集后统一断言
                with lock:
                    errors.append((tag, exc))

        threads = [threading.Thread(target=work, args=(tag, fn)) for tag, fn in fns]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        return errors, receipts

    def test_concurrent_open_settle_no_drift(self):
        """夹具[开充关账并发漂数]：并发开充/关账/同键重试后，双格与重放一致。"""
        sids = [
            self._open(self.p1, self.g1, "pre-1")["会话编号"],
            self._open(self.p2, self.g3, "pre-2")["会话编号"],
            self._open(self.p3, self.g4, "pre-3")["会话编号"],
        ]
        self.assertDual(3, 3)
        fns = [(f"close-{sid}", (lambda sid=sid: self._settle(sid, f"close-{sid}"))) for sid in sids]
        fns.append(("close-retry-0", lambda: self._settle(sids[0], f"close-{sids[0]}")))  # 半截回执重试
        fns.append(("open-new", lambda: self._open(self.p1, self.g2, "open-new")))
        errors, receipts = self._run_threads(fns)
        self.assertEqual(errors, [])
        self.assertDual(1, 1)  # 仅剩桩一右枪在充
        self.assertAligned()
        # 同键重试回执一致，关账只落一次
        self.assertEqual(receipts[f"close-{sids[0]}"], receipts["close-retry-0"])
        kinds = [e["类别"] for e in self._audit()]
        self.assertEqual(kinds.count("开充"), 4)
        self.assertEqual(kinds.count("结算"), 3)
        self.assertEqual(kinds.count("关账"), 3)

    def test_concurrent_same_gun_single_pin(self):
        """同枪并发开充：恰好一成一败，不双钉。"""
        fns = [(f"open-{i}", (lambda i=i: self._open(self.p2, self.g3, f"same-gun-{i}"))) for i in range(2)]
        errors, receipts = self._run_threads(fns)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0][1], HTTPException)
        self.assertEqual(errors[0][1].status_code, 400)
        self.assertDual(1, 1)
        self.assertEqual(self._session_count(), 1)
        self.assertAligned()

    def test_concurrent_crash_retry_no_drift(self):
        """夹具[开充关账并发半截]：并发写口中途崩溃整笔回滚，同键重试后双格与重放一致。"""
        sids = [
            self._open(self.p1, self.g1, "pre-1")["会话编号"],
            self._open(self.p2, self.g3, "pre-2")["会话编号"],
            self._open(self.p3, self.g4, "pre-3")["会话编号"],
        ]
        real_refresh = counters.refresh_projection
        crashed = set()
        lock = threading.Lock()

        def flaky(conn, pile_id, gun_id=None):
            with lock:
                if pile_id == self.p1 and pile_id not in crashed:
                    crashed.add(pile_id)
                    raise FaultInjected("夹具注入：并发半截崩溃")
            return real_refresh(conn, pile_id, gun_id)

        def settle_with_retry(sid):
            key = f"close-{sid}"
            try:
                self._settle(sid, key)
            except FaultInjected:
                self._settle(sid, key)  # 半截崩溃后同键重试

        def open_with_retry():
            try:
                self._open(self.p1, self.g2, "open-new")
            except FaultInjected:
                self._open(self.p1, self.g2, "open-new")

        fns = [(f"close-{sid}", (lambda sid=sid: settle_with_retry(sid))) for sid in sids]
        fns.append(("open-new", open_with_retry))
        with mock.patch.object(counters, "refresh_projection", side_effect=flaky):
            errors, _ = self._run_threads(fns)
        self.assertEqual(errors, [])
        self.assertEqual(len(crashed), 1)  # 确实注入过一次崩溃
        self.assertDual(1, 1)
        self.assertAligned()
        kinds = [e["类别"] for e in self._audit()]
        self.assertEqual(kinds.count("开充"), 4)  # 崩溃笔已回滚，不留审计残迹
        self.assertEqual(kinds.count("结算"), 3)
        self.assertEqual(kinds.count("关账"), 3)


class TestAuditTrail(DualCounterBase):
    """审计流水：只增不改不删，逐条带双计数快照可对照重放。"""

    def test_audit_append_only_and_self_describing(self):
        r = self._open(self.p1, self.g1, "k1")
        self._settle(r["会话编号"], "c1")
        entries = self._audit()
        self.assertEqual([e["类别"] for e in entries], ["开充", "结算", "关账"])
        for e in entries:
            self.assertIn("双计数", e["明细"])
        self.assertEqual(entries[-1]["明细"]["双计数"], {"钉桩桩数": 0, "充电中会话数": 0})
        with db_mod.write_db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE audit_log SET kind='篡改' WHERE seq=1")
        with db_mod.write_db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM audit_log WHERE seq=1")
        self.assertAligned()


class TestLongTermAlignment(DualCounterBase):
    """夹具[桩位页与仪表长期拧花]：200 步随机写口+改计+桩态+故障注入，每步四面对照。"""

    def _free_guns(self):
        with db_mod.db() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    """SELECT g.id AS gun_id, p.id AS pile_id FROM guns g
                       JOIN piles p ON p.id=g.pile_id
                       WHERE g.status='可用' AND p.status NOT IN ('故障','维护') ORDER BY g.id"""
                ).fetchall()
            ]

    def _active_sessions(self):
        with db_mod.db() as conn:
            return [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM sessions WHERE status IN ('充电中','结算中') ORDER BY id"
                ).fetchall()
            ]

    def _timed_out_sessions(self):
        with db_mod.db() as conn:
            return [
                r["id"]
                for r in conn.execute("SELECT id FROM sessions WHERE status='已超时' ORDER BY id").fetchall()
            ]

    def _settable_piles(self):
        with db_mod.db() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    """SELECT id, status FROM piles p
                       WHERE status IN ('空闲','维护')
                         AND NOT EXISTS(SELECT 1 FROM sessions s
                                        WHERE s.pile_id=p.id AND s.status IN ('充电中','结算中'))
                       ORDER BY id"""
                ).fetchall()
            ]

    def _soak_op(self, rng, step):
        free = self._free_guns()
        active = self._active_sessions()
        timed_out = self._timed_out_sessions()
        settable = self._settable_piles()
        roll = rng.random()
        with db_mod.write_db() as conn:
            if roll < 0.40 and free:
                g = free[rng.randrange(len(free))]
                svc.open_session(conn, g["pile_id"], g["gun_id"], f"open-{step}")
            elif roll < 0.62 and active:
                svc.settle(conn, active[rng.randrange(len(active))], f"settle-{step}")
            elif roll < 0.72 and active:
                svc.mark_timeout(conn, active[rng.randrange(len(active))], f"timeout-{step}")
            elif roll < 0.82 and active:
                svc.abort_session(conn, active[rng.randrange(len(active))], "急停", f"abort-{step}")
            elif roll < 0.87 and timed_out:
                svc.settle(conn, timed_out[rng.randrange(len(timed_out))], f"settle-to-{step}")
            elif roll < 0.93:
                r = adjust_svc.manual_adjust(
                    conn, "运维甲", rng.randrange(4), rng.randrange(4), "想刷齐", f"adj-{step}"
                )
                self.assertEqual(r["状态"], "已拒绝")
            elif settable:
                p = settable[rng.randrange(len(settable))]
                svc.set_pile_status(conn, p["id"], "维护" if p["status"] == "空闲" else "空闲", "运维乙")

    def test_long_term_alignment_soak(self):
        rng = random.Random(20261124)
        for step in range(200):
            if rng.random() < 0.08:
                try:
                    with mock.patch.object(
                        counters,
                        "refresh_projection",
                        side_effect=FaultInjected("夹具注入：半截崩溃"),
                    ):
                        self._soak_op(rng, step)
                except FaultInjected:
                    pass  # 半截崩溃：整笔回滚，下面立刻对照
            else:
                self._soak_op(rng, step)
            self.assertAligned()
        # 长期运行后投影零漂移：重放修复无事可纠
        with db_mod.write_db() as conn:
            self.assertEqual(counters.replay_and_repair(conn), [])


if __name__ == "__main__":
    unittest.main()
