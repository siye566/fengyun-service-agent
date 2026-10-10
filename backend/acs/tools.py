"""第 1/2 轮的四个工具 + 第 3 轮回流补上的企业隔离（任务书第七节）。

工具是纯函数，不依赖 MCP / 模型 —— Mock 先行：
直接调用用于测试与冒烟；Miniclaw 里经 acs-tools.ts → acs.cli 驱动。

调用者身份：所有工具都要求 scope_key（Miniclaw chatJid），由 identity.py
按 company_bindings 绑定表解析，**默认拒绝**未绑定会话（fail-closed）。
诚实原则（任务书 4.2）：知识库未收录就明说，不编造诊断；
所有建议都带"最终以工程师现场确诊为准"的声明。
"""
from psycopg import Connection
from datetime import date, datetime, timedelta

from .db import connect, begin_write
from .identity import (
    ROLE_COMPANY,
    ROLE_INTERNAL,
    ROLE_UNBOUND,
    cross_company_error,
    resolve_caller,
    unbound_error,
)
from .results import err, ok

URGENCY_LEVELS = ("low", "normal", "high")
DUE_SOON_DAYS = 7  # 剩余天数 <= 7 视为临期

# 工单状态 → 给客户看的人话。审批流状态（第 4 轮）已并入：
# awaiting_finance（申领单待财务人工审批）/ parts_approved / parts_rejected
STATUS_TEXT = {
    "pending_dispatch": "已受理，待派工程师上门",
    "awaiting_finance": "现场确诊为零件问题，零件申领单待财务审批",
    "parts_approved": "零件已审批，安排发货/更换",
    "parts_rejected": "零件申领未通过审批",
}


def _device_by_serial(conn: Connection, serial_no: str):
    return conn.execute(
        "SELECT * FROM devices WHERE serial_no = %s", (serial_no,)
    ).fetchone()


def _guard(conn: Connection, scope_key: str | None) -> dict | None:
    """统一的前置闸门：未绑定直接拒绝；返回 None 表示放行。"""
    caller = resolve_caller(conn, scope_key)
    if caller["role"] == ROLE_UNBOUND:
        return unbound_error(caller["scope_key"])
    return None


def create_repair_ticket(
    company_name: str = "",
    device_serial: str = "",
    symptom: str = "",
    urgency: str = "normal",
    ticket_type: str = "repair",
    scope_key: str | None = None,
    db_url: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """报修：身份闸门 → 信息补全校验 → 台账校验 → 知识库检索 → 工单落库。

    企业角色建单强制落到绑定企业（company_name 可省略；传入不符时以绑定
    为准并附 note）；internal 角色必须提供企业名称，可代客建单。
    """
    conn = connect(db_url)
    try:
        begin_write(conn)
        caller = resolve_caller(conn, scope_key)
        if caller["role"] == ROLE_UNBOUND:
            return unbound_error(caller["scope_key"])

        if caller["role"] == ROLE_COMPANY:
            bound = caller["company_name"]
            note = None
            if str(company_name or "").strip() and company_name.strip() != bound:
                note = f"来单企业名与绑定身份不符，已按贵司绑定档案（{bound}）受理"
            company_name = bound
        else:
            note = None

        # 信息补全：缺什么一次列全（任务书 4.1"缺什么问什么"的确定性版本，
        # 自然语言的追问话术归第 2 轮的模型编排）
        missing = [
            name
            for name, value in (
                ("企业名称 company_name", company_name),
                ("设备序列号 device_serial", device_serial),
                ("故障现象 symptom", symptom),
            )
            if not str(value or "").strip()
        ]
        if missing:
            return err(
                "missing_info",
                "还缺以下信息：" + "、".join(missing),
                "请补齐后重新报修，一次最多再问两个澄清问题",
            )
        if urgency not in URGENCY_LEVELS:
            return err(
                "bad_urgency",
                f"紧急度只能是 {'/'.join(URGENCY_LEVELS)}，收到的是 {urgency!r}",
                "请改为 low、normal 或 high 后重试",
            )

        device = _device_by_serial(conn, device_serial.strip())
        if device is None:
            return err(
                "device_not_found",
                f"设备台账中查无序列号 {device_serial.strip()} 的设备",
                "请核对序列号；确认无误则联系管理员先把设备录入台账",
            )
        if (
            caller["role"] == ROLE_COMPANY
            and device["company_name"] != caller["company_name"]
        ):
            return cross_company_error("设备", device["serial_no"])

        if idempotency_key:
            existing = conn.execute(
                "SELECT ticket_no FROM tickets WHERE idempotency_key = %s AND company_name = %s",
                (idempotency_key, company_name.strip()),
            ).fetchone()
            if existing:
                conn.commit()
                return query_ticket_status(existing["ticket_no"], scope_key, db_url)

        # 知识库检索：按型号圈定范围，现象做包含匹配（"报 E3 故障"能命中"显示E3"）
        kb = conn.execute(
            "SELECT * FROM fault_kb WHERE model = %s AND symptom LIKE %s LIMIT 1",
            (device["model"], f"%{symptom.strip()}%"),
        ).fetchone()
        if kb:
            advice = (
                f"初步排查建议（仅供参考，最终以工程师现场确诊为准）："
                f"可能原因——{kb['possible_cause']}；"
                f"排查步骤——{kb['check_steps']}。"
                f"涉及零件：{kb['parts_involved'] or '无'}。"
            )
            kb_id: int | None = kb["id"]
        else:
            # 知识库未收录 → 不编造诊断，直接派单（任务书 4.2）
            advice = (
                "知识库未收录该故障现象，已受理并等待安排工程师，"
                "不提供猜测性诊断；现场确诊以工程师为准。"
            )
            kb_id = None

        today = date.today().isoformat()
        seq = conn.execute(
            "SELECT COUNT(*) AS n FROM tickets WHERE created_at LIKE %s",
            (f"{today}%",),
        ).fetchone()["n"]
        ticket_no = f"ACS-{today.replace('-', '')}-{seq + 1:03d}"
        conn.execute(
            "INSERT INTO tickets (ticket_no, company_name, device_serial, model,"
            " symptom, urgency, status, kb_id, advice, created_at, ticket_type, idempotency_key)"
            " VALUES (%s, %s, %s, %s, %s, %s, 'pending_dispatch', %s, %s, %s, %s, %s)",
            (
                ticket_no,
                company_name.strip(),
                device["serial_no"],
                device["model"],
                symptom.strip(),
                urgency,
                kb_id,
                advice,
                datetime.now().isoformat(timespec="seconds"),
                ticket_type,
                idempotency_key,
            ),
        )
        conn.commit()
        data = {
            "ticket_no": ticket_no,
            "company_name": company_name.strip(),
            "model": device["model"],
            "device_serial": device["serial_no"],
            "symptom": symptom.strip(),
            "urgency": urgency,
            "ticket_type": ticket_type,
            "status": "pending_dispatch",
            "advice": advice,
        }
        if note:
            data["note"] = note
        return ok(data)
    finally:
        conn.close()


def query_maintenance(
    device_serial: str, scope_key: str | None = None, db_url: str | None = None
) -> dict:
    """保养查询：身份闸门 → 台账 → 上次保养 + 周期 → 剩余天数与状态。"""
    if not str(device_serial or "").strip():
        return err(
            "missing_info",
            "还缺以下信息：设备序列号 device_serial",
            "请提供要查询的设备序列号",
        )

    conn = connect(db_url)
    try:
        caller = resolve_caller(conn, scope_key)
        if caller["role"] == ROLE_UNBOUND:
            return unbound_error(caller["scope_key"])

        device = _device_by_serial(conn, device_serial.strip())
        if device is None:
            return err(
                "device_not_found",
                f"设备台账中查无序列号 {device_serial.strip()} 的设备",
                "请核对序列号；确认无误则联系管理员先把设备录入台账",
            )
        if (
            caller["role"] == ROLE_COMPANY
            and device["company_name"] != caller["company_name"]
        ):
            return cross_company_error("设备", device["serial_no"])

        last = date.fromisoformat(device["last_maintenance_date"])
        interval = int(device["maintenance_interval_days"])
        next_due = last + timedelta(days=interval)
        days_left = (next_due - date.today()).days
        if days_left < 0:
            status = "overdue"
            hint = f"保养已过期 {-days_left} 天，建议尽快预约上门保养"
        elif days_left <= DUE_SOON_DAYS:
            status = "due_soon"
            hint = f"预计 {days_left} 天后到保养周期，请预约上门时间"
        else:
            status = "normal"
            hint = "设备保养状态正常，可由内部保养扫描检查临期情况"

        return ok(
            {
                "company_name": device["company_name"],
                "model": device["model"],
                "device_serial": device["serial_no"],
                "last_maintenance_date": device["last_maintenance_date"],
                "maintenance_interval_days": interval,
                "next_due_date": next_due.isoformat(),
                "days_left": days_left,
                "status": status,
                "hint": hint,
            }
        )
    finally:
        conn.close()


def query_ticket_status(
    ticket_no: str, scope_key: str | None = None, db_url: str | None = None
) -> dict:
    """进度查询（按工单号）：任务书第三节"进度类"意图的工具。"""
    if not str(ticket_no or "").strip():
        return err(
            "missing_info",
            "还缺以下信息：工单号 ticket_no",
            "报修成功后会返回 ACS- 开头的工单号；客户记不得时可改用企业名称查历史工单",
        )

    conn = connect(db_url)
    try:
        caller = resolve_caller(conn, scope_key)
        if caller["role"] == ROLE_UNBOUND:
            return unbound_error(caller["scope_key"])

        row = conn.execute(
            "SELECT * FROM tickets WHERE ticket_no = %s", (ticket_no.strip(),)
        ).fetchone()
        if row is None:
            return err(
                "ticket_not_found",
                f"查无工单号 {ticket_no.strip()}",
                "请核对工单号；客户记不得号码时可按企业名称查询历史工单",
            )
        if (
            caller["role"] == ROLE_COMPANY
            and row["company_name"] != caller["company_name"]
        ):
            return cross_company_error("工单", row["ticket_no"])
        return ok(
            {
                "ticket_no": row["ticket_no"],
                "company_name": row["company_name"],
                "model": row["model"],
                "device_serial": row["device_serial"],
                "symptom": row["symptom"],
                "urgency": row["urgency"],
                "ticket_type": row["ticket_type"] if "ticket_type" in row.keys() else "repair",
                "status": row["status"],
                "status_text": STATUS_TEXT.get(row["status"], row["status"]),
                "created_at": row["created_at"],
            }
        )
    finally:
        conn.close()


def list_company_tickets(
    company_name: str,
    scope_key: str | None = None,
    db_url: str | None = None,
    limit: int = 10,
) -> dict:
    """进度查询（按企业）："我上次报的工单怎么样了"时没有工单号的兜底。

    企业角色无视传入的 company_name，一律查绑定企业（按构造防越权枚举）；
    internal 角色按传入企业名查，支持包含匹配。
    """
    conn = connect(db_url)
    try:
        caller = resolve_caller(conn, scope_key)
        if caller["role"] == ROLE_UNBOUND:
            return unbound_error(caller["scope_key"])
        if caller["role"] == ROLE_COMPANY:
            target = caller["company_name"]
        else:
            if not str(company_name or "").strip():
                return err(
                    "missing_info",
                    "还缺以下信息：企业名称 company_name",
                    "请提供要查询的企业名称（或让客户报工单号）",
                )
            target = company_name.strip()

        rows = conn.execute(
            "SELECT * FROM tickets WHERE company_name LIKE %s"
            " ORDER BY created_at DESC, id DESC LIMIT %s",
            (f"%{target}%", int(limit)),
        ).fetchall()
        if not rows:
            return err(
                "no_tickets",
                f"企业 {target} 名下暂无报修工单",
                "确认企业名称是否与台账一致；确认无误则该企业还没有报过修",
            )
        return ok(
            {
                "count": len(rows),
                "tickets": [
                    {
                        "ticket_no": row["ticket_no"],
                        "symptom": row["symptom"],
                        "status": row["status"],
                        "status_text": STATUS_TEXT.get(row["status"], row["status"]),
                        "created_at": row["created_at"],
                    }
                    for row in rows
                ],
            }
        )
    finally:
        conn.close()


# ============ 第 4 轮：保养线（时间驱动）与零件申领审批流（人工闸门） ============

# 未完结的工单状态：保养扫描时，同一设备存在未完结保养单就不重复建
_OPEN_STATUSES = ("pending_dispatch", "awaiting_finance", "parts_approved")


def scan_maintenance_due(
    days_ahead: int = 7, scope_key: str | None = None, db_url: str | None = None
) -> dict:
    """保养台账扫描（任务书第五节，时间驱动主线）。

    internal 专用：找出临期/过期设备，按"型号-保养项目映射"生成保养工单
    （ticket_type=maintenance，建议=映射清单，模型不得即兴生成）。幂等：
    同一设备存在未完结保养单时跳过。
    """
    conn = connect(db_url)
    try:
        caller = resolve_caller(conn, scope_key)
        if caller["role"] != ROLE_INTERNAL:
            return err(
                "forbidden",
                "保养台账扫描是内部操作，仅限售后内部身份",
                "请用管理员绑定的会话（internal）执行",
            )
        devices = conn.execute("SELECT * FROM devices").fetchall()
        created, skipped = [], []
        for device in devices:
            last = date.fromisoformat(device["last_maintenance_date"])
            interval = int(device["maintenance_interval_days"])
            days_left = ((last + timedelta(days=interval)) - date.today()).days
            if days_left > days_ahead:
                continue  # 还没到临期线
            open_ticket = conn.execute(
                "SELECT ticket_no FROM tickets WHERE device_serial = %s"
                " AND ticket_type = 'maintenance' AND status IN (%s, %s, %s)"
                " ORDER BY id DESC LIMIT 1",
                (device["serial_no"], *_OPEN_STATUSES),
            ).fetchone()
            if open_ticket:
                skipped.append(
                    {"device_serial": device["serial_no"],
                     "ticket_no": open_ticket["ticket_no"]}
                )
                continue
            result = create_repair_ticket(
                company_name=device["company_name"],
                device_serial=device["serial_no"],
                symptom="定期保养（到期自动生成）",
                urgency="low",
                ticket_type="maintenance",
                scope_key=scope_key,
                db_url=db_url,
            )
            if result["ok"]:
                plan = conn.execute(
                    "SELECT items FROM maintenance_plans WHERE model = %s",
                    (device["model"],),
                ).fetchone()
                created.append({
                    "ticket_no": result["data"]["ticket_no"],
                    "company_name": device["company_name"],
                    "device_serial": device["serial_no"],
                    "model": device["model"],
                    "days_left": days_left,
                    "plan_items": (plan["items"] if plan else
                                   "（该型号暂无保养项目映射，请联系工程师补充）"),
                })
            else:
                skipped.append({"device_serial": device["serial_no"],
                                "reason": result["error"]["code"]})
        return ok({
            "scanned": len(devices),
            "created": created,
            "skipped": skipped,
            "summary": f"扫描 {len(devices)} 台：新保养单 {len(created)} 张，跳过 {len(skipped)} 台",
        })
    finally:
        conn.close()


def submit_part_request(
    ticket_no: str,
    part_no: str,
    quantity: int,
    scope_key: str | None = None,
    db_url: str | None = None,
) -> dict:
    """提交零件申领单（任务书第六节：工程师提交，无工单不受理）。internal 专用。"""
    if (not str(ticket_no or "").strip() or not str(part_no or "").strip()
            or int(quantity or 0) < 1):
        return err(
            "missing_info",
            "需要：关联工单号 ticket_no、零件编号 part_no、数量 quantity（≥1）",
            "申领单必须挂在一张真实工单下（无工单不受理）",
        )
    conn = connect(db_url)
    try:
        begin_write(conn)
        caller = resolve_caller(conn, scope_key)
        if caller["role"] != ROLE_INTERNAL:
            return err(
                "forbidden",
                "零件申领由现场工程师发起，企业客户可查询进度但不能提交",
                "如需零件，请联系为您服务的工程师",
            )
        ticket = conn.execute(
            "SELECT * FROM tickets WHERE ticket_no = %s", (ticket_no.strip(),)
        ).fetchone()
        if ticket is None:
            return err(
                "ticket_not_found",
                f"查无工单号 {ticket_no.strip()}",
                "申领单必须关联真实工单；请核对工单号",
            )
        part = conn.execute(
            "SELECT * FROM parts WHERE part_no = %s", (part_no.strip(),)
        ).fetchone()
        if part is None:
            return err(
                "part_not_found",
                f"零件库中查无编号 {part_no.strip()}",
                "请核对零件编号；确属新零件则联系管理员先入库",
            )
        if part["fit_models"] and ticket["model"] not in part["fit_models"]:
            return err(
                "part_not_compatible",
                f"零件 {part['name']} 适配型号（{part['fit_models']}）与工单设备型号"
                f" {ticket['model']} 不符",
                "请改用适配该型号的零件",
            )
        if int(quantity) > int(part["stock"]):
            return err(
                "insufficient_stock",
                f"零件 {part['name']} 库存 {part['stock']} 件，申领 {quantity} 件超出库存",
                "请减少数量或先走采购补库",
            )
        today = date.today().isoformat()
        seq = conn.execute(
            "SELECT COUNT(*) AS n FROM part_requests WHERE created_at LIKE %s",
            (f"{today}%",),
        ).fetchone()["n"]
        request_no = f"PR-{today.replace('-', '')}-{seq + 1:03d}"
        conn.execute(
            "INSERT INTO part_requests (request_no, ticket_no, part_no, part_name,"
            " quantity, requested_by, status, finance_comment, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, 'pending_approval', '', %s)",
            (request_no, ticket["ticket_no"], part["part_no"], part["name"],
             int(quantity), scope_key.strip(),
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.execute(
            "UPDATE tickets SET status = 'awaiting_finance' WHERE ticket_no = %s",
            (ticket["ticket_no"],),
        )
        conn.commit()
        return ok({
            "request_no": request_no,
            "ticket_no": ticket["ticket_no"],
            "part_no": part["part_no"],
            "part_name": part["name"],
            "quantity": int(quantity),
            "status": "pending_approval",
            "status_text": STATUS_TEXT["awaiting_finance"],
        })
    finally:
        conn.close()


def decide_part_request(
    request_no: str,
    decision: str,
    comment: str = "",
    scope_key: str | None = None,
    db_url: str | None = None,
) -> dict:
    """财务审批（人工闸门）：decision=approve/reject + 意见。internal 专用。

    智能体不代替财务决策——decision 必须来自人的明确指示，由系统提示词约束。
    通过 → 扣减库存并回写工单状态；拒绝 → 意见回传工单与企业会话。
    """
    if decision not in ("approve", "reject"):
        return err(
            "bad_decision",
            "decision 只能是 approve（通过）或 reject（拒绝）",
            "请明确审批结论和意见",
        )
    conn = connect(db_url)
    try:
        begin_write(conn)
        caller = resolve_caller(conn, scope_key)
        if caller["role"] != ROLE_INTERNAL:
            return err(
                "forbidden",
                "审批是财务的人工步骤，智能体与企业会话都不能代批",
                "请由财务在内部会话中明确给出通过/拒绝结论",
            )
        row = conn.execute(
            "SELECT * FROM part_requests WHERE request_no = %s", (request_no.strip(),)
        ).fetchone()
        if row is None:
            return err(
                "request_not_found",
                f"查无申领单号 {request_no.strip()}",
                "请核对 PR- 开头的申领单号",
            )
        if row["status"] != "pending_approval":
            return err(
                "already_decided",
                f"申领单 {row['request_no']} 已处理（{row['status']}）",
                "每张申领单只审批一次；如需变更请另开单",
            )
        new_status = "approved" if decision == "approve" else "rejected"
        if new_status == "approved":
            part = conn.execute(
                "SELECT * FROM parts WHERE part_no = %s", (row["part_no"],)
            ).fetchone()
            current = int(part["stock"]) if part else 0
            if current < int(row["quantity"]):
                return err(
                    "insufficient_stock",
                    f"审批时库存不足（当前 {current} 件，需 {row['quantity']} 件）",
                    "请先补库再批，或拒绝本单",
                )
            conn.execute(
                "UPDATE parts SET stock = stock - %s WHERE part_no = %s",
                (int(row["quantity"]), row["part_no"]),
            )
        conn.execute(
            "UPDATE part_requests SET status = %s, finance_comment = %s, decided_at = %s"
            " WHERE request_no = %s",
            (new_status, str(comment or "").strip(),
             datetime.now().isoformat(timespec="seconds"), row["request_no"]),
        )
        ticket_status = "parts_approved" if new_status == "approved" else "parts_rejected"
        conn.execute(
            "UPDATE tickets SET status = %s WHERE ticket_no = %s",
            (ticket_status, row["ticket_no"]),
        )
        conn.commit()
        return ok({
            "request_no": row["request_no"],
            "ticket_no": row["ticket_no"],
            "part_name": row["part_name"],
            "quantity": row["quantity"],
            "decision": new_status,
            "finance_comment": str(comment or "").strip(),
            "ticket_status_text": STATUS_TEXT[ticket_status],
        })
    finally:
        conn.close()


def query_part_requests(
    ticket_no: str, scope_key: str | None = None, db_url: str | None = None
) -> dict:
    """按工单查零件申领单（企业客户可查自己工单的审批进度，任务书 6.2）。"""
    if not str(ticket_no or "").strip():
        return err(
            "missing_info",
            "还缺以下信息：工单号 ticket_no",
            "请提供要查询的工单号",
        )
    conn = connect(db_url)
    try:
        caller = resolve_caller(conn, scope_key)
        if caller["role"] == ROLE_UNBOUND:
            return unbound_error(caller["scope_key"])
        ticket = conn.execute(
            "SELECT * FROM tickets WHERE ticket_no = %s", (ticket_no.strip(),)
        ).fetchone()
        if ticket is None:
            return err(
                "ticket_not_found",
                f"查无工单号 {ticket_no.strip()}",
                "请核对工单号",
            )
        if (caller["role"] == ROLE_COMPANY
                and ticket["company_name"] != caller["company_name"]):
            return cross_company_error("工单", ticket["ticket_no"])
        rows = conn.execute(
            "SELECT * FROM part_requests WHERE ticket_no = %s ORDER BY id DESC",
            (ticket["ticket_no"],),
        ).fetchall()
        status_text = {
            "pending_approval": "待财务审批",
            "approved": "已通过，安排发货",
            "rejected": "未通过",
        }
        return ok({
            "ticket_no": ticket["ticket_no"],
            "ticket_status_text": STATUS_TEXT.get(ticket["status"], ticket["status"]),
            "requests": [
                {
                    "request_no": r["request_no"],
                    "part_name": r["part_name"],
                    "quantity": r["quantity"],
                    "status": r["status"],
                    "status_text": status_text.get(r["status"], r["status"]),
                    "finance_comment": r["finance_comment"],
                }
                for r in rows
            ],
        })
    finally:
        conn.close()
