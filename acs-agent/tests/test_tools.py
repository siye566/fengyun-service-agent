"""第 1/2/3 轮工具测试：正常路径 + 失败路径 + 企业隔离（任务书第七节）。

每个测试用 tmp_path 下的临时库，互不污染；种子数据见 acs/seed.py
（seed 会把 "web:main" 绑成 internal 角色，现有用例借它拿全量视图）。
"""
import pytest

from acs.bind import bind
from acs.db import connect
from acs.seed import seed
from acs.tools import (
    create_repair_ticket,
    decide_part_request,
    list_company_tickets,
    query_maintenance,
    query_part_requests,
    query_ticket_status,
    scan_maintenance_due,
    submit_part_request,
)


def db_query(db_path, sql):
    conn = connect(db_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()

INTERNAL = "web:main"  # seed 默认绑成 internal 的 scope


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "test.sqlite3")
    seed(path, reset=True)
    return path


class TestCreateRepairTicket:
    def test_normal_path_hits_kb_and_persists(self, db):
        result = create_repair_ticket(
            "示例企业甲", "DEMO-GR75-0001", "机器异响", "high",
            scope_key=INTERNAL, db_path=db,
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["ticket_no"].startswith("ACS-")
        assert data["status"] == "pending_dispatch"
        assert data["model"] == "GR-75"
        # 命中知识库：建议来自故障库，且带诚实声明
        assert "皮带" in data["advice"]
        assert "最终以工程师现场确诊为准" in data["advice"]

    def test_ticket_numbers_increment_same_day(self, db):
        first = create_repair_ticket("示例企业乙", "DEMO-GR75-0002", "不出气",
                                     scope_key=INTERNAL, db_path=db)
        second = create_repair_ticket("示例企业乙", "DEMO-GR75-0002", "不出气",
                                      scope_key=INTERNAL, db_path=db)
        assert first["ok"] and second["ok"]
        assert first["data"]["ticket_no"] != second["data"]["ticket_no"]

    def test_kb_miss_creates_ticket_without_fabricated_diagnosis(self, db):
        result = create_repair_ticket(
            "示例企业丙", "DEMO-EP30-0007", "夜间自动停机",
            scope_key=INTERNAL, db_path=db,
        )
        # EP-30 没有任何知识库条目 → 工单照建，但明说未收录，不编造诊断
        assert result["ok"] is True
        assert "未收录" in result["data"]["advice"]

    def test_missing_info_lists_what_is_needed(self, db):
        result = create_repair_ticket("", "DEMO-GR75-0001", "",
                                      scope_key=INTERNAL, db_path=db)
        assert result["ok"] is False
        assert result["error"]["code"] == "missing_info"
        assert "企业名称" in result["error"]["message"]
        assert "故障现象" in result["error"]["message"]

    def test_unknown_device_is_rejected(self, db):
        result = create_repair_ticket("某公司", "AC-XXXX-9999", "异响",
                                      scope_key=INTERNAL, db_path=db)
        assert result["ok"] is False
        assert result["error"]["code"] == "device_not_found"
        assert result["error"]["action"]  # 下一步动作必须是"人话"

    def test_bad_urgency_is_rejected(self, db):
        result = create_repair_ticket(
            "示例企业乙", "DEMO-GR75-0002", "不出气", "马上来",
            scope_key=INTERNAL, db_path=db,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "bad_urgency"


class TestQueryMaintenance:
    def test_three_states_exist(self, db):
        # 种子数据按"距今天数"构造，三台设备必然分别落在三种状态
        statuses = {
            serial: query_maintenance(serial, scope_key=INTERNAL, db_path=db)
            for serial in ("DEMO-GR75-0001", "DEMO-GR75-0002", "DEMO-EP30-0007")
        }
        assert all(result["ok"] for result in statuses.values())
        found = {result["data"]["status"] for result in statuses.values()}
        assert found == {"normal", "due_soon", "overdue"}

    def test_overdue_device_reports_days_and_hint(self, db):
        result = query_maintenance("DEMO-GR75-0002", scope_key=INTERNAL, db_path=db)
        data = result["data"]
        assert data["status"] == "overdue"
        assert data["days_left"] < 0
        assert "过期" in data["hint"]

    def test_unknown_device_is_rejected(self, db):
        result = query_maintenance("NO-SUCH-DEVICE", scope_key=INTERNAL, db_path=db)
        assert result["ok"] is False
        assert result["error"]["code"] == "device_not_found"

    def test_missing_serial_is_rejected(self, db):
        result = query_maintenance("", scope_key=INTERNAL, db_path=db)
        assert result["ok"] is False
        assert result["error"]["code"] == "missing_info"


class TestQueryTicketStatus:
    def test_found_ticket_returns_human_status(self, db):
        created = create_repair_ticket(
            "示例企业甲", "DEMO-GR75-0001", "机器异响",
            scope_key=INTERNAL, db_path=db,
        )
        result = query_ticket_status(created["data"]["ticket_no"],
                                     scope_key=INTERNAL, db_path=db)
        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "pending_dispatch"
        assert "已受理" in data["status_text"]
        assert data["model"] == "GR-75"

    def test_unknown_ticket_no_is_rejected_with_next_step(self, db):
        result = query_ticket_status("ACS-20990101-999", scope_key=INTERNAL, db_path=db)
        assert result["ok"] is False
        assert result["error"]["code"] == "ticket_not_found"
        assert "企业名称" in result["error"]["action"]  # 指出兜底路径

    def test_missing_ticket_no_is_rejected(self, db):
        result = query_ticket_status("", scope_key=INTERNAL, db_path=db)
        assert result["ok"] is False
        assert result["error"]["code"] == "missing_info"


class TestListCompanyTickets:
    def test_fuzzy_company_match_lists_recent_first(self, db):
        create_repair_ticket("示例企业甲", "DEMO-GR75-0001", "机器异响",
                             scope_key=INTERNAL, db_path=db)
        create_repair_ticket("示例企业甲", "DEMO-GR75-0001", "不出气",
                             scope_key=INTERNAL, db_path=db)
        result = list_company_tickets("示例企业甲", scope_key=INTERNAL, db_path=db)
        assert result["ok"] is True
        assert result["data"]["count"] == 2
        symptoms = [t["symptom"] for t in result["data"]["tickets"]]
        assert symptoms == ["不出气", "机器异响"]  # 最新在前

    def test_company_without_tickets_is_reported_honestly(self, db):
        result = list_company_tickets("示例企业丙", scope_key=INTERNAL, db_path=db)
        assert result["ok"] is False
        assert result["error"]["code"] == "no_tickets"

    def test_missing_company_is_rejected(self, db):
        result = list_company_tickets("", scope_key=INTERNAL, db_path=db)
        assert result["ok"] is False
        assert result["error"]["code"] == "missing_info"


class TestCallerIsolation:
    """企业隔离（任务书第七节）：默认拒绝 + 跨企业不可见 + 建单强制落绑定企业。"""

    @pytest.fixture()
    def company_db(self, db):
        bound = bind("feishu:demo-company-b", "示例企业乙", db_path=db)
        assert bound["bound"] is True
        return db

    def test_unbound_caller_is_rejected_on_every_tool(self, db):
        results = [
            create_repair_ticket("示例企业乙", "DEMO-GR75-0002", "不出气", db_path=db),
            query_maintenance("DEMO-GR75-0002", db_path=db),
            query_ticket_status("ACS-20260913-001", db_path=db),
            list_company_tickets("示例企业乙", db_path=db),
        ]
        assert all(r["ok"] is False for r in results)
        assert all(r["error"]["code"] == "caller_unbound" for r in results)
        # 错误信息自带绑定指引（含 scope 标识），管理员照着执行即可
        assert "python -m acs.bind" in results[0]["error"]["action"]

    def test_company_can_query_own_device(self, company_db):
        result = query_maintenance("DEMO-GR75-0002", scope_key="feishu:demo-company-b",
                                   db_path=company_db)
        assert result["ok"] is True
        assert result["data"]["company_name"] == "示例企业乙"

    def test_company_cannot_query_other_company_device(self, company_db):
        result = query_maintenance("DEMO-GR75-0001", scope_key="feishu:demo-company-b",
                                   db_path=company_db)  # 示例企业甲的设备
        assert result["ok"] is False
        assert result["error"]["code"] == "cross_company_denied"

    def test_company_cannot_read_other_company_ticket(self, company_db):
        created = create_repair_ticket("示例企业甲", "DEMO-GR75-0001", "机器异响",
                                       scope_key=INTERNAL, db_path=company_db)
        result = query_ticket_status(created["data"]["ticket_no"],
                                     scope_key="feishu:demo-company-b", db_path=company_db)
        assert result["ok"] is False
        assert result["error"]["code"] == "cross_company_denied"

    def test_company_create_forces_bound_company(self, company_db):
        # 报他企设备 → 拒绝；报自己设备但企业名写歪 → 强制落绑定企业并注明
        rogue = create_repair_ticket("示例企业甲", "DEMO-GR75-0001", "异响",
                                     scope_key="feishu:demo-company-b", db_path=company_db)
        assert rogue["ok"] is False
        assert rogue["error"]["code"] == "cross_company_denied"

        sloppy = create_repair_ticket("宏泰机械公司", "DEMO-GR75-0002", "不出气",
                                      scope_key="feishu:demo-company-b", db_path=company_db)
        assert sloppy["ok"] is True
        assert sloppy["data"]["company_name"] == "示例企业乙"
        assert "绑定档案" in sloppy["data"]["note"]

    def test_company_list_ignores_passed_company_name(self, company_db):
        create_repair_ticket("示例企业乙", "DEMO-GR75-0002", "不出气",
                             scope_key=INTERNAL, db_path=company_db)
        result = list_company_tickets("示例企业甲",  # 想越权枚举别家
                                      scope_key="feishu:demo-company-b", db_path=company_db)
        # 不报错也不泄数：一律按绑定企业查
        assert result["ok"] is True
        assert all(t["ticket_no"].startswith("ACS-") for t in result["data"]["tickets"])

    def test_composite_conversation_jid_inherits_workspace_binding(self, company_db):
        # 两层身份：运行时 ctx.chatJid 是 chat#agent 复合键，应回退继承工作区绑定
        composite = "feishu:demo-company-b#agent:abc-123"
        result = query_maintenance("DEMO-GR75-0002", scope_key=composite,
                                   db_path=company_db)
        assert result["ok"] is True
        assert result["data"]["company_name"] == "示例企业乙"

    def test_exact_composite_binding_overrides_base(self, company_db):
        bind("feishu:demo-company-b#agent:special", "示例企业丙", db_path=company_db)
        result = query_maintenance("DEMO-EP30-0007",
                                   scope_key="feishu:demo-company-b#agent:special",
                                   db_path=company_db)
        assert result["ok"] is True  # 精确键优先：这个会话被单独绑到别家企业

    def test_unknown_base_stays_unbound(self, db):
        result = query_maintenance("DEMO-GR75-0002",
                                   scope_key="web:stranger#agent:x", db_path=db)
        assert result["ok"] is False
        assert result["error"]["code"] == "caller_unbound"

    def test_internal_role_keeps_full_view(self, company_db):
        result = query_maintenance("DEMO-GR75-0001", scope_key=INTERNAL,
                                   db_path=company_db)  # 别家设备，内部可查
        assert result["ok"] is True


class TestBindCommand:
    def test_bind_roundtrip_and_validation(self, db):
        assert bind("web:c1", "示例企业丙", db_path=db)["bound"] is True
        assert bind("web:c2", internal=True, db_path=db)["bound"] is True
        assert bind("web:c3", "  ", db_path=db)["bound"] is False  # 企业角色缺企业名
        assert bind("   ", "某公司", db_path=db)["bound"] is False  # scope 不能为空


class TestCliBridge:
    """python -m acs.cli：Miniclaw runner 的调用入口，信封语义必须与工具一致。"""

    def _run_cli(self, tmp_db, tool, args, scope=INTERNAL):
        import json
        import os
        import subprocess
        import sys
        from pathlib import Path

        project_root = Path(__file__).resolve().parents[1]
        env = {
            **os.environ,
            "ACS_DB_PATH": str(tmp_db),
            "PYTHONUTF8": "1",
            "PYTHONPATH": str(project_root),
        }
        argv = [sys.executable, "-m", "acs.cli", tool]
        if scope:
            argv.append(scope)
        return subprocess.run(
            argv,
            input=json.dumps(args, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=str(project_root),
            timeout=60,
        )

    def test_create_ticket_via_cli(self, db):
        import json

        proc = self._run_cli(db, "create_repair_ticket", {
            "company_name": "示例企业乙",
            "device_serial": "DEMO-GR75-0002",
            "symptom": "不出气",
            "urgency": "high",
        })
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["ok"] is True
        assert result["data"]["ticket_no"].startswith("ACS-")

    def test_cli_without_scope_is_rejected(self, db):
        import json

        proc = self._run_cli(db, "query_maintenance",
                             {"device_serial": "DEMO-GR75-0002"}, scope=None)
        assert proc.returncode == 0
        result = json.loads(proc.stdout)
        assert result["ok"] is False
        assert result["error"]["code"] == "caller_unbound"

    def test_unknown_tool_lists_available(self, db):
        proc = self._run_cli(db, "no_such_tool", {})
        assert proc.returncode == 2
        assert "未知工具" in proc.stdout

    def test_tool_error_keeps_envelope(self, db):
        import json

        proc = self._run_cli(db, "query_maintenance", {"device_serial": "NOPE"})
        assert proc.returncode == 0
        result = json.loads(proc.stdout)
        assert result["ok"] is False
        assert result["error"]["code"] == "device_not_found"


class TestScanMaintenance:
    """保养线（时间驱动）：internal 扫描 → 按型号映射生成保养单，幂等。"""

    def test_internal_scan_creates_due_tickets_with_plan_items(self, db):
        result = scan_maintenance_due(scope_key=INTERNAL, db_path=db)
        assert result["ok"] is True
        data = result["data"]
        # 种子：GR75-0001 临期(5天)、GR75-0002 过期(17天)、EP30 正常(161天)
        assert data["scanned"] == 3
        assert len(data["created"]) == 2
        serials = {c["device_serial"] for c in data["created"]}
        assert serials == {"DEMO-GR75-0001", "DEMO-GR75-0002"}
        for item in data["created"]:
            assert "皮带" in item["plan_items"]  # GR-75 保养映射清单
            status = query_ticket_status(item["ticket_no"],
                                         scope_key=INTERNAL, db_path=db)
            assert status["data"]["ticket_type"] == "maintenance"

    def test_scan_is_idempotent(self, db):
        scan_maintenance_due(scope_key=INTERNAL, db_path=db)
        again = scan_maintenance_due(scope_key=INTERNAL, db_path=db)
        assert again["data"]["created"] == []
        assert len(again["data"]["skipped"]) == 2  # 未完结保养单挡住重复建

    def test_scan_is_internal_only(self, db):
        result = scan_maintenance_due(scope_key="feishu:any-company", db_path=db)
        assert result["ok"] is False
        assert result["error"]["code"] == "forbidden"


class TestPartApproval:
    """零件申领审批流（任务书第六节）：无工单不受理、财务人工闸门、状态回写。"""

    def _make_ticket(self, db):
        created = create_repair_ticket(
            "示例企业乙", "DEMO-GR75-0002", "不出气",
            scope_key=INTERNAL, db_path=db,
        )
        return created["data"]["ticket_no"]

    def test_full_approval_flow_updates_stock_and_ticket(self, db):
        ticket_no = self._make_ticket(db)
        submitted = submit_part_request(ticket_no, "P-BRG-6208", 2,
                                        scope_key=INTERNAL, db_path=db)
        assert submitted["ok"] is True
        assert submitted["data"]["status"] == "pending_approval"
        status = query_ticket_status(ticket_no, scope_key=INTERNAL, db_path=db)
        assert status["data"]["status"] == "awaiting_finance"

        decided = decide_part_request(submitted["data"]["request_no"], "approve",
                                      "同意，按库存发货", scope_key=INTERNAL, db_path=db)
        assert decided["ok"] is True
        assert decided["data"]["ticket_status_text"].startswith("零件已审批")

        # 库存扣减：6208 轴承 6 → 4
        parts_now = db_query(db, "SELECT stock FROM parts WHERE part_no='P-BRG-6208'")
        assert parts_now[0]["stock"] == 4

        final = query_ticket_status(ticket_no, scope_key=INTERNAL, db_path=db)
        assert final["data"]["status"] == "parts_approved"

    def test_reject_flow_carries_comment(self, db):
        ticket_no = self._make_ticket(db)
        submitted = submit_part_request(ticket_no, "P-BRG-6208", 1,
                                        scope_key=INTERNAL, db_path=db)
        decided = decide_part_request(submitted["data"]["request_no"], "reject",
                                      "工单照片缺失，退回补充", scope_key=INTERNAL,
                                      db_path=db)
        assert decided["ok"] is True
        assert decided["data"]["decision"] == "rejected"
        assert "照片" in decided["data"]["finance_comment"]
        stock = db_query(db, "SELECT stock FROM parts WHERE part_no='P-BRG-6208'")
        assert stock[0]["stock"] == 6  # 拒绝不扣库存

    def test_submit_requires_real_ticket(self, db):
        result = submit_part_request("ACS-20990101-999", "P-BRG-6208", 1,
                                     scope_key=INTERNAL, db_path=db)
        assert result["error"]["code"] == "ticket_not_found"

    def test_submit_rejects_incompatible_part(self, db):
        ticket_no = self._make_ticket(db)
        result = submit_part_request(ticket_no, "P-SEAL-55", 1,
                                     scope_key=INTERNAL, db_path=db)
        assert result["error"]["code"] == "part_not_compatible"

    def test_submit_rejects_over_stock(self, db):
        ticket_no = self._make_ticket(db)
        result = submit_part_request(ticket_no, "P-BRG-6208", 99,
                                     scope_key=INTERNAL, db_path=db)
        assert result["error"]["code"] == "insufficient_stock"

    def test_decide_only_once(self, db):
        ticket_no = self._make_ticket(db)
        submitted = submit_part_request(ticket_no, "P-BRG-6208", 1,
                                        scope_key=INTERNAL, db_path=db)
        decide_part_request(submitted["data"]["request_no"], "approve",
                            scope_key=INTERNAL, db_path=db)
        again = decide_part_request(submitted["data"]["request_no"], "reject",
                                    "再想想", scope_key=INTERNAL, db_path=db)
        assert again["error"]["code"] == "already_decided"

    def test_company_scope_cannot_submit_or_decide(self, db):
        ticket_no = self._make_ticket(db)
        submit_forbidden = submit_part_request(ticket_no, "P-BRG-6208", 1,
                                               scope_key="feishu:demo-company-b", db_path=db)
        assert submit_forbidden["error"]["code"] == "forbidden"
        # 未提交也可验审批权限：随便编个单号，公司角色应先被 forbidden 拦住
        decide_forbidden = decide_part_request("PR-20260101-001", "approve",
                                               scope_key="feishu:demo-company-b", db_path=db)
        assert decide_forbidden["error"]["code"] == "forbidden"

    def test_company_can_view_own_request_progress(self, db):
        bind("feishu:demo-company-b", "示例企业乙", db_path=db)
        ticket_no = self._make_ticket(db)  # 示例企业乙的工单
        submitted = submit_part_request(ticket_no, "P-BRG-6208", 1,
                                        scope_key=INTERNAL, db_path=db)
        view = query_part_requests(ticket_no, scope_key="feishu:demo-company-b", db_path=db)
        assert view["ok"] is True
        assert view["data"]["requests"][0]["status"] == "pending_approval"

    def test_company_cannot_view_others_requests(self, db):
        bind("feishu:demo-company-b", "示例企业乙", db_path=db)
        created = create_repair_ticket("示例企业甲", "DEMO-GR75-0001", "机器异响",
                                       scope_key=INTERNAL, db_path=db)
        view = query_part_requests(created["data"]["ticket_no"],
                                   scope_key="feishu:demo-company-b", db_path=db)
        assert view["error"]["code"] == "cross_company_denied"
