"""把 acs.tools 的四个纯函数包成 MCP 服务器（stdio）。

注意调用者身份：MCP 协议不带 Miniclaw 会话身份，本服务器默认以"未绑定"
身份调工具（工具层 fail-closed 拒绝）。本地开发想放行，显式设环境变量
ACS_MCP_SCOPE（如 internal 调试）；正式链路走 Miniclaw runner 的
acs-tools.ts，那里带真实 chatJid。
"""
import os

from mcp.server.mcpserver import MCPServer  # mcp 2.x：FastMCP 已更名 MCPServer，API 同形

from . import tools

mcp = MCPServer("acs-after-sales")

_CALLER_SCOPE = os.environ.get("ACS_MCP_SCOPE") or None


@mcp.tool()
def create_repair_ticket(
    company_name: str, device_serial: str, symptom: str, urgency: str = "normal"
) -> dict:
    """创建空压机报修工单。

    需要：企业名称、设备序列号、故障现象；紧急度可选 low/normal/high。
    返回工单号与初步排查建议（仅供参考，最终以工程师现场确诊为准）；
    序列号在台账中查不到、或缺少必填信息时会返回缺什么/下一步怎么办。
    """
    return tools.create_repair_ticket(company_name, device_serial, symptom, urgency, scope_key=_CALLER_SCOPE)


@mcp.tool()
def query_maintenance(device_serial: str) -> dict:
    """查询某台空压机的保养状态。

    按设备序列号返回：上次保养日期、保养周期、下次到期日、剩余天数，
    以及状态（normal 正常 / due_soon 临期 / overdue 已过期）。
    """
    return tools.query_maintenance(device_serial, scope_key=_CALLER_SCOPE)


@mcp.tool()
def query_ticket_status(ticket_no: str) -> dict:
    """按工单号查询报修工单的处理进度。

    返回工单状态（已受理/待派单等）、报修内容与创建时间。
    客户记不得工单号时，可改用 list_company_tickets 按企业名称查询。
    """
    return tools.query_ticket_status(ticket_no, scope_key=_CALLER_SCOPE)


@mcp.tool()
def list_company_tickets(company_name: str, limit: int = 10) -> dict:
    """按企业名称查询该企业最近的报修工单列表。

    支持企业名称的包含匹配（如"示例企业甲"能匹配"示例企业甲"）。
    客户问"我上次报的工单怎么样了"但报不出工单号时用这个。
    """
    return tools.list_company_tickets(company_name, scope_key=_CALLER_SCOPE, limit=limit)


@mcp.tool()
def scan_maintenance_due(days_ahead: int = 7) -> dict:
    """保养台账扫描（内部角色专用）：找出临期/过期设备并生成保养工单。

    保养项目来自型号-保养项目映射；同一设备已有未完结保养单时跳过（幂等）。
    """
    return tools.scan_maintenance_due(days_ahead=days_ahead, scope_key=_CALLER_SCOPE)


@mcp.tool()
def submit_part_request(ticket_no: str, part_no: str, quantity: int) -> dict:
    """提交零件申领单（内部角色专用，无工单不受理）。

    申领单提交后工单进入"待财务审批"状态；需关联真实工单、零件适配设备型号、
    数量不超库存。
    """
    return tools.submit_part_request(ticket_no, part_no, quantity, scope_key=_CALLER_SCOPE)


@mcp.tool()
def decide_part_request(request_no: str, decision: str, comment: str = "") -> dict:
    """财务审批零件申领单（内部角色专用的人工闸门）。

    decision 只能是 approve 或 reject，必须附带审批意见；这是财务的人工决定，
    调用方不得代替决策。通过会扣减库存并回写工单状态。
    """
    return tools.decide_part_request(request_no, decision, comment, scope_key=_CALLER_SCOPE)


@mcp.tool()
def query_part_requests(ticket_no: str) -> dict:
    """按工单号查询零件申领单及审批进度（企业客户可查自己工单）。"""
    return tools.query_part_requests(ticket_no, scope_key=_CALLER_SCOPE)


if __name__ == "__main__":
    mcp.run()
