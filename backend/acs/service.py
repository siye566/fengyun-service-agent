"""Thread-scoped workflow: model candidates are data, identity and writes are guarded."""
import hashlib
import json
import re
import uuid
from datetime import datetime

from .db import connect, begin_write
from .identity import resolve_caller, ROLE_UNBOUND, unbound_error, cross_company_error
from .results import ok, err
from . import tools

INTENTS = {"repair", "maintenance", "progress"}


def session_key(scope_key, session_id):
    return hashlib.sha256(json.dumps([scope_key, session_id], ensure_ascii=False).encode()).hexdigest()


def load_state(conn, key):
    row = conn.execute("SELECT state_json FROM service_sessions WHERE session_key=%s", (key,)).fetchone()
    return json.loads(row["state_json"]) if row else {"stage": "idle", "pending": None}


def parse_candidates(utterance, parsed=None):
    """Optional Pi structured extraction, or deterministic offline baseline. No confidence claim."""
    if parsed is not None:
        if not isinstance(parsed, dict) or set(parsed) - {"intents", "device_serial", "symptom", "ticket_no"}:
            raise ValueError("候选字段不符合 Schema")
        intents = parsed.get("intents", [])
        if not isinstance(intents, list) or any(i not in INTENTS for i in intents):
            raise ValueError("候选意图非法")
        for field in ("device_serial", "symptom", "ticket_no"):
            if field in parsed and (not isinstance(parsed[field], str) or len(parsed[field]) > 500):
                raise ValueError("候选实体非法")
        return {**parsed, "intents": list(dict.fromkeys(intents)), "source": "model_candidates"}
    intents = []
    if re.search(r"报修|异响|故障|报警|不出气", utterance): intents.append("repair")
    if "保养" in utterance: intents.append("maintenance")
    if re.search(r"进度|查.*工单|工单.*状态", utterance): intents.append("progress")
    serial = re.search(r"\bDEMO-[A-Z0-9]+-\d+\b", utterance)
    ticket = re.search(r"\bACS-\d{8}-\d+\b", utterance)
    symptom = next((s for s in ("机器异响", "异响", "不出气", "E3", "压力上不去") if s in utterance), "")
    return {"intents": intents, "device_serial": serial.group() if serial else "",
            "ticket_no": ticket.group() if ticket else "", "symptom": symptom, "source": "rule_baseline"}


def route_service_turn(utterance, session_id="default", event_id=None, parsed=None,
                       scope_key=None, db_url=None):
    if not isinstance(utterance, str) or not utterance.strip() or len(utterance) > 4000:
        return err("bad_utterance", "输入为空或过长", "输入不超过 4000 字符的售后需求")
    if not isinstance(session_id, str) or not session_id or len(session_id) > 200:
        return err("bad_session", "会话标识非法", "使用可信会话标识")
    if not isinstance(event_id, str) or not event_id or len(event_id) > 200:
        return err("missing_event_id", "缺少事件标识", "传入稳定消息 ID 以支持重试去重")
    conn = connect(db_url)
    key = session_key(scope_key, session_id)
    try:
        begin_write(conn)
        caller = resolve_caller(conn, scope_key)
        if caller["role"] == ROLE_UNBOUND: return unbound_error(scope_key)
        # Rebinding must not expose or resume a previous company's pending work.
        binding = hashlib.sha256(json.dumps(caller, sort_keys=True).encode()).hexdigest()
        key = session_key(key, binding)
        old = conn.execute("SELECT result_json FROM service_turns WHERE session_key=%s AND event_id=%s",
                           (key, event_id)).fetchone()
        if old: return json.loads(old["result_json"])
        state = load_state(conn, key)
        executed, results, clarification = [], [], []
        detected = []
        text = utterance.strip()
        pending = state.get("pending")
        if text in ("取消报修", "取消当前报修"):
            state = {"stage": "cancelled", "pending": None}
        elif text in ("确认报修", "确认提交"):
            detected = ["repair"]
            if not pending or state["stage"] not in ("awaiting_confirmation", "confirming"):
                return err("confirmation_not_ready", "尚无可确认的完整报修", "先补齐设备和故障信息")
            # Stable business key survives a crash between ticket creation and turn recording.
            state["stage"] = "confirming"
            conn.execute("INSERT INTO service_sessions VALUES(%s,%s,%s) ON CONFLICT (session_key) DO UPDATE SET state_json=EXCLUDED.state_json, updated_at=EXCLUDED.updated_at",
                         (key, json.dumps(state, ensure_ascii=False), datetime.now().isoformat()))
            conn.commit()
            result = tools.create_repair_ticket(
                pending["company_name"], pending["device_serial"], pending["symptom"],
                scope_key=scope_key, db_url=db_url, idempotency_key=pending["task_key"])
            executed.append("create_repair_ticket")
            results.append(result)
            if result["ok"]: state = {"stage": "completed", "pending": None}
            begin_write(conn)
        elif re.search(r"不要|不用|别|假如|如果", text):
            clarification = ["该输入包含否定或条件，请明确是否报修；不会执行写操作"]
        else:
            try: candidates = parse_candidates(text, parsed)
            except ValueError as exc: return err("invalid_candidates", str(exc), "按候选 Schema 重新解析")
            intents = candidates["intents"]
            detected = intents
            # A read-only detour never inherits or replaces the pending repair's device.
            serial = candidates.get("device_serial", "")
            device = conn.execute("SELECT * FROM devices WHERE serial_no=%s", (serial,)).fetchone() if serial else None
            if device and caller["role"] == "company" and device["company_name"] != caller["company_name"]:
                return cross_company_error("设备", serial)
            if "progress" in intents:
                ticket = candidates.get("ticket_no", "")
                name = "query_ticket_status" if ticket else "list_company_tickets"
                conn.commit()
                result = (tools.query_ticket_status(ticket, scope_key, db_url) if ticket else
                          tools.list_company_tickets(caller.get("company_name", ""), scope_key, db_url))
                begin_write(conn)
                state = load_state(conn, key); pending = state.get("pending")
                executed.append(name); results.append(result)
            if "maintenance" in intents:
                if device:
                    executed.append("query_maintenance")
                    conn.commit()
                    results.append(tools.query_maintenance(serial, scope_key, db_url))
                    begin_write(conn)
                    state = load_state(conn, key); pending = state.get("pending")
                else: clarification.append("请提供要查询保养的设备序列号")
            completing = pending and state["stage"] == "awaiting_details" and not intents
            if completing: detected = ["repair"]
            if "repair" in intents or completing:
                if state["stage"] == "confirming":
                    return err("task_busy", "报修正在提交或等待重试", "回复确认报修以恢复原任务，不要新建")
                # Changing an already selected device needs a fresh task, never silent overwrite.
                if pending and serial and pending.get("device_serial") and serial != pending["device_serial"]:
                    clarification.append("当前报修设备已选定；请取消当前报修后再切换设备")
                else:
                    pending = pending or {"task_key": uuid.uuid4().hex, "device_serial": "", "symptom": "", "company_name": ""}
                    if device: pending.update(device_serial=serial, company_name=device["company_name"])
                    elif serial: clarification.append("设备台账中未找到该序列号")
                    if candidates.get("symptom"): pending["symptom"] = candidates["symptom"]
                    missing = [f for f in ("device_serial", "symptom") if not pending.get(f)]
                    state = {"stage": "awaiting_details" if missing else "awaiting_confirmation", "pending": pending}
                    clarification.extend(["请补充：" + ", ".join(missing)] if missing else ["请核对设备和故障，然后回复“确认报修”"])
            elif not intents:
                clarification.append("请明确报修、保养或进度查询需求")
        data = {"route_version": "service-route-v1", "intents": detected,
                "stage": state["stage"], "pending": state.get("pending"), "clarification": clarification,
                "executed_tools": executed, "results": results}
        result = ok(data)
        replay = conn.execute("SELECT result_json FROM service_turns WHERE session_key=%s AND event_id=%s",
                              (key, event_id)).fetchone()
        if replay: return json.loads(replay["result_json"])
        conn.execute("INSERT INTO service_sessions VALUES(%s,%s,%s) ON CONFLICT (session_key) DO UPDATE SET state_json=EXCLUDED.state_json, updated_at=EXCLUDED.updated_at",
                     (key, json.dumps(state, ensure_ascii=False), datetime.now().isoformat()))
        conn.execute("INSERT INTO service_turns VALUES(%s,%s,%s)", (key, event_id, json.dumps(result, ensure_ascii=False)))
        conn.commit()
        return result
    finally: conn.close()


def trusted_session_key(conn, scope_key, session_id):
    caller = resolve_caller(conn, scope_key)
    binding = hashlib.sha256(json.dumps(caller, sort_keys=True).encode()).hexdigest()
    return session_key(session_key(scope_key, session_id), binding)
