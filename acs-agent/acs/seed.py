"""冷启动种子数据（任务书第二节：每型号先人工整理 Top 常见故障）。

日期相对"今天"生成，保证三种保养状态（正常/临期/过期）在演示时永远各有一台。
用法：
    python -m acs.seed          # 空库时写入
    python -m acs.seed --reset  # 清空重写
"""
import os
import sys
from datetime import date, datetime, timedelta

from .db import connect

DEVICES = [
    # 企业, 型号, 序列号, 安装日期, 距今天数-上次保养, 周期(天)
    ("示例企业甲", "GR-75", "DEMO-GR75-0001", "2025-03-12", 85, 90),   # 5 天后到期 → 临期
    ("示例企业乙", "GR-75", "DEMO-GR75-0002", "2024-11-05", 107, 90),        # 17 天前已过期 → 过期
    ("示例企业丙", "EP-30", "DEMO-EP30-0007", "2025-08-01", 19, 180),      # 161 天后到期 → 正常
]

FAULT_KB = [
    ("GR-75", "机器异响",
     "皮带松动或主轴承磨损，也可能是主机内进入异物",
     "1.停机断电挂牌；2.检查皮带张紧度与磨损；3.盘车听诊轴承部位；4.检查主机进气口有无异物",
     "GR-75专用皮带、6208轴承"),
    ("GR-75", "不出气",
     "进气阀卡滞或空气滤芯堵塞",
     "1.检查进气阀动作是否到位；2.拆检空滤芯压差；3.检查最小压力阀",
     "进气阀维修包、空气滤芯"),
    ("GR-75", "E3",
     "排气温度过高报警，多为冷却器散热不良或油位偏低",
     "1.检查油位；2.吹扫冷却器翅片；3.检查温控阀",
     "冷却器"),
    ("GR-55", "压力上不去",
     "用气量超出额定排量，或管路接头泄漏",
     "1.核对当前用气负荷；2.肥皂水涂抹管路接头查泄漏",
     "密封垫套装"),
]

PARTS = [
    ("P-BELT-75", "GR-75 专用皮带", "GR-75", 12, 180.0),
    ("P-BRG-6208", "6208 轴承", "GR-75", 6, 260.0),
    ("P-FLT-AIR", "空气滤芯", "GR-75、GR-55", 20, 85.0),
    ("P-IV-KIT", "进气阀维修包", "GR-75", 4, 520.0),
    ("P-CLR-75", "冷却器", "GR-75", 2, 1350.0),
    ("P-SEAL-55", "密封垫套装", "GR-55", 10, 45.0),
]

# 型号 → 保养项目映射（任务书第五节：清单来自映射，不得由模型即兴生成）
MAINTENANCE_PLANS = [
    ("GR-75", "空滤芯检查更换、油滤芯更换、油气分离芯压差检查、皮带张紧与磨损检查、冷却器翅片吹扫、安全阀校验"),
    ("GR-55", "空滤芯检查更换、油滤芯更换、皮带张紧检查"),
    ("EP-30", "空滤芯检查更换、管路接头检漏"),
]


def seed(db_path: str | None = None, reset: bool = False) -> dict:
    conn = connect(db_path)
    try:
        existing = conn.execute("SELECT COUNT(*) AS n FROM devices").fetchone()["n"]
        if existing and not reset:
            return {"seeded": False, "reason": f"台账已有 {existing} 台设备，跳过（要重写请加 --reset）"}

        if reset:
            for table in ("service_turns", "service_sessions", "part_requests", "tickets", "maintenance_plans",
                          "fault_kb", "parts", "devices", "company_bindings"):
                conn.execute(f"DELETE FROM {table}")

        today = date.today()
        for company, model, serial, installed, days_ago, interval in DEVICES:
            last_maint = (today - timedelta(days=days_ago)).isoformat()
            conn.execute(
                "INSERT INTO devices (company_name, model, serial_no, installed_date,"
                " last_maintenance_date, maintenance_interval_days) VALUES (?, ?, ?, ?, ?, ?)",
                (company, model, serial, installed, last_maint, interval),
            )
        conn.executemany(
            "INSERT INTO fault_kb (model, symptom, possible_cause, check_steps, parts_involved)"
            " VALUES (?, ?, ?, ?, ?)",
            FAULT_KB,
        )
        conn.executemany(
            "INSERT INTO parts (part_no, name, fit_models, stock, price) VALUES (?, ?, ?, ?, ?)",
            PARTS,
        )
        conn.executemany(
            "INSERT INTO maintenance_plans (model, items, updated_at) VALUES (?, ?, ?)",
            [(model, items, datetime.now().isoformat(timespec="seconds"))
             for model, items in MAINTENANCE_PLANS],
        )
        # 管理员的会话绑成 internal（全量视图）；逗号分隔可用 ACS_INTERNAL_SCOPES 覆盖
        internal_scopes = os.environ.get("ACS_INTERNAL_SCOPES", "web:main").split(",")
        now = datetime.now().isoformat(timespec="seconds")
        conn.executemany(
            "INSERT OR REPLACE INTO company_bindings (scope_key, company_name, role, bound_at)"
            " VALUES (?, '', 'internal', ?)",
            [(scope.strip(), now) for scope in internal_scopes if scope.strip()],
        )
        conn.commit()
        return {
            "seeded": True,
            "devices": len(DEVICES),
            "fault_kb": len(FAULT_KB),
            "parts": len(PARTS),
            "internal_scopes": [s.strip() for s in internal_scopes if s.strip()],
        }
    finally:
        conn.close()


if __name__ == "__main__":
    counts = seed(reset="--reset" in sys.argv)
    print(counts)
