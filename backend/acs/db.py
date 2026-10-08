"""SQLite 连接与建表。

任务书第二节的核心前提：先建表，再做 Agent。
三张前提表 = 设备台账 devices / 故障知识库 fault_kb / 零件库存 parts；
tickets（报修工单）是工具的产物表，第 2 轮编排会扩展它的状态机。
"""
import sqlite3
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "acs.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,               -- 所属企业
    model TEXT NOT NULL,                      -- 型号
    serial_no TEXT NOT NULL UNIQUE,           -- 序列号（设备唯一身份）
    installed_date TEXT NOT NULL,             -- 安装日期
    last_maintenance_date TEXT NOT NULL,      -- 上次保养日期
    maintenance_interval_days INTEGER NOT NULL -- 该型号保养周期（天）
);

CREATE TABLE IF NOT EXISTS fault_kb (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,                      -- 按型号组织
    symptom TEXT NOT NULL,                    -- 故障现象
    possible_cause TEXT NOT NULL,             -- 可能原因
    check_steps TEXT NOT NULL,                -- 排查步骤
    parts_involved TEXT NOT NULL DEFAULT ''   -- 涉及零件（顿号分隔）
);

CREATE TABLE IF NOT EXISTS parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_no TEXT NOT NULL UNIQUE,             -- 零件编号
    name TEXT NOT NULL,                       -- 零件名称
    fit_models TEXT NOT NULL,                 -- 适配型号（顿号分隔）
    stock INTEGER NOT NULL DEFAULT 0,         -- 库存数量
    price REAL NOT NULL DEFAULT 0             -- 价格
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_no TEXT NOT NULL UNIQUE,           -- 工单号 ACS-YYYYMMDD-NNN
    company_name TEXT NOT NULL,
    device_serial TEXT NOT NULL,
    model TEXT NOT NULL,
    symptom TEXT NOT NULL,
    urgency TEXT NOT NULL DEFAULT 'normal',   -- low / normal / high
    status TEXT NOT NULL DEFAULT 'pending_dispatch',
    kb_id INTEGER,                            -- 命中的知识库条目 id；NULL=知识库未收录
    advice TEXT NOT NULL DEFAULT '',          -- 给企业的初步排查建议
    created_at TEXT NOT NULL                  -- ISO 8601
);
CREATE TABLE IF NOT EXISTS company_bindings (
    scope_key TEXT PRIMARY KEY,               -- 调用者身份键（Miniclaw chatJid）
    company_name TEXT NOT NULL DEFAULT '',    -- 绑定企业（role=company 时有效）
    role TEXT NOT NULL DEFAULT 'company',     -- company（企业客户）/ internal（售后内部）
    bound_at TEXT NOT NULL                    -- ISO 8601
);

CREATE TABLE IF NOT EXISTS maintenance_plans (
    model TEXT PRIMARY KEY,                   -- 型号 → 保养项目映射（任务书第五节：清单来自映射，不许模型即兴生成）
    items TEXT NOT NULL,                      -- 保养项目（顿号分隔）
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS part_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_no TEXT NOT NULL UNIQUE,          -- 申领单号 PR-YYYYMMDD-NNN
    ticket_no TEXT NOT NULL,                  -- 关联工单（任务书第六节：无工单不受理）
    part_no TEXT NOT NULL,
    part_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    requested_by TEXT NOT NULL,               -- 申领人身份（scope_key）
    status TEXT NOT NULL DEFAULT 'pending_approval',  -- pending_approval / approved / rejected
    finance_comment TEXT NOT NULL DEFAULT '', -- 财务审批意见（人工闸门，智能体不代决）
    created_at TEXT NOT NULL,
    decided_at TEXT
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """幂等小迁移：老库补列。SQLite 无 IF NOT EXISTS 列语法，靠异常吞重。"""
    try:
        conn.execute(
            "ALTER TABLE tickets ADD COLUMN ticket_type TEXT NOT NULL DEFAULT 'repair'"
        )
    except sqlite3.OperationalError:
        pass  # 列已存在
    try:
        conn.execute("ALTER TABLE tickets ADD COLUMN idempotency_key TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ticket_idempotency ON tickets(idempotency_key)")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS service_sessions (
        session_key TEXT PRIMARY KEY,
        state_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS service_turns (
        session_key TEXT NOT NULL,
        event_id TEXT NOT NULL,
        result_json TEXT NOT NULL,
        PRIMARY KEY (session_key, event_id)
    );
    """)


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """打开连接并确保表存在。db_path 参数供测试用临时库，默认用 data/acs.sqlite3。"""
    path = Path(db_path or os.environ.get("ACS_DB_PATH") or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn
