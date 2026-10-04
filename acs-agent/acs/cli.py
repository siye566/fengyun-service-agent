"""命令行桥：Miniclaw 运行时（Node）↔ acs Python 引擎。

约定：`python -m acs.cli <tool_name> [scope_key]`，参数 JSON 走 stdin，结果
信封 JSON 走 stdout（UTF-8）。scope_key = 调用者身份（Miniclaw chatJid），
由 identity.py 按绑定表解析，未绑定一律拒绝（fail-closed）。
Node 侧用环境变量 ACS_AGENT_PYTHON / ACS_AGENT_ROOT 定位解释器与项目，
ACS_DB_PATH 可重定向数据库（测试用）。

设计动机见 STAGES.md 决策记录：当前 Miniclaw 构建的 Pi 运行时不消费外部
MCP 服务器，领域工具以 runner 内置工具的身份注册，执行体仍是本 Python 包
——单一事实源不变，pytest 直接测到的逻辑就是模型调到的逻辑。
"""
import json
import os
import sys

from . import tools
from .service import route_service_turn
from .context import build_service_context

ROUTES = {
    "route_service_turn": route_service_turn,
    "build_service_context": build_service_context,
    "create_repair_ticket": tools.create_repair_ticket,
    "query_maintenance": tools.query_maintenance,
    "query_ticket_status": tools.query_ticket_status,
    "list_company_tickets": tools.list_company_tickets,
    "scan_maintenance_due": tools.scan_maintenance_due,
    "submit_part_request": tools.submit_part_request,
    "decide_part_request": tools.decide_part_request,
    "query_part_requests": tools.query_part_requests,
}

# 各工具在 ROUTES 函数签名里的参数顺序（不含 scope_key / db_path）
ARG_NAMES = {
    "route_service_turn": ("utterance", "session_id", "event_id", "parsed"),
    "build_service_context": ("session_id",),
    "create_repair_ticket": ("company_name", "device_serial", "symptom", "urgency"),
    "query_maintenance": ("device_serial",),
    "query_ticket_status": ("ticket_no",),
    "list_company_tickets": ("company_name",),
    "scan_maintenance_due": ("days_ahead",),
    "submit_part_request": ("ticket_no", "part_no", "quantity"),
    "decide_part_request": ("request_no", "decision", "comment"),
    "query_part_requests": ("ticket_no",),
}


def _envelope(code: str, message: str, action: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "action": action}}


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    tool_name = argv[1] if len(argv) > 1 else ""
    fn = ROUTES.get(tool_name)
    if fn is None:
        print(json.dumps(_envelope(
            "unknown_tool",
            f"未知工具 {tool_name!r}",
            "可用工具：" + "、".join(sorted(ROUTES)),
        ), ensure_ascii=False))
        return 2
    # 第 3 个位置参数 = 调用者身份（Miniclaw chatJid）；缺省视为未绑定 → 工具层拒绝
    scope_key = argv[2] if len(argv) > 2 else None
    try:
        args = json.loads(sys.stdin.read() or "{}")
        if not isinstance(args, dict):
            raise ValueError("参数必须是 JSON 对象")
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps(_envelope(
            "bad_args", f"参数不是合法 JSON 对象：{exc}", "检查调用方传参",
        ), ensure_ascii=False))
        return 2

    db_path = os.environ.get("ACS_DB_PATH") or None
    known = set(ARG_NAMES[tool_name])
    extra = {k: v for k, v in args.items() if k not in known}
    filtered = {k: args[k] for k in ARG_NAMES[tool_name] if k in args}
    if tool_name == "list_company_tickets":
        result = tools.list_company_tickets(
            filtered.get("company_name", ""),
            scope_key=scope_key,
            db_path=db_path,
            limit=extra.pop("limit", None) or 10,
        )
    else:
        result = fn(db_path=db_path, scope_key=scope_key, **filtered, **extra)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

