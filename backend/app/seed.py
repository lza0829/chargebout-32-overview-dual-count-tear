from __future__ import annotations
from app.db import init_db, write_db
from app.services.core import set_setting, today


def seed_if_empty() -> None:
    init_db()
    with write_db() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM sites").fetchone()["c"]
        if n:
            return
        set_setting(conn, "超时分钟", "120")
        set_setting(conn, "会话序号", "1000")
        set_setting(conn, "脉冲默认电量", "1.5")
        conn.execute(
            "INSERT INTO rate_plans(name,peak_price,flat_price,valley_price) VALUES(?,?,?,?)",
            ("通用峰谷", 1.2, 0.9, 0.55),
        )
        conn.execute(
            "INSERT INTO rate_plans(name,peak_price,flat_price,valley_price) VALUES(?,?,?,?)",
            ("快充高峰", 1.6, 1.1, 0.7),
        )
        conn.execute(
            "INSERT INTO sites(name,address,active) VALUES(?,?,1)",
            ("河西路边站", "河西大道辅路"),
        )
        conn.execute(
            "INSERT INTO sites(name,address,active) VALUES(?,?,1)",
            ("城北场站", "城北物流园外侧"),
        )
        # 河西：慢充桩
        for i, name in enumerate(["河甲一号", "河甲二号", "河甲三号", "河甲四号"], start=1):
            cur = conn.execute(
                "INSERT INTO piles(site_id,name,rated_kw,status,rate_plan_id) VALUES(1,?,?, '空闲', 1)",
                (name, 7 if i < 4 else 11),
            )
            pid = cur.lastrowid
            conn.execute(
                "INSERT INTO guns(pile_id,name,status) VALUES(?,?, '可用')",
                (pid, "左枪"),
            )
            if i >= 3:
                conn.execute(
                    "INSERT INTO guns(pile_id,name,status) VALUES(?,?, '可用')",
                    (pid, "右枪"),
                )
        # 城北：快充
        for name in ["北乙一号", "北乙二号", "北乙三号"]:
            cur = conn.execute(
                "INSERT INTO piles(site_id,name,rated_kw,status,rate_plan_id) VALUES(2,?,?, '空闲', 2)",
                (name, 60),
            )
            pid = cur.lastrowid
            conn.execute(
                "INSERT INTO guns(pile_id,name,status) VALUES(?,?, '可用')",
                (pid, "单枪"),
            )
        # 一桩维护
        conn.execute("UPDATE piles SET status='维护' WHERE name='河甲四号'")
        conn.execute(
            "INSERT INTO day_seals(business_day,sealed,sealed_at,note) VALUES(?,?,NULL,'')",
            (today(), 0),
        )
