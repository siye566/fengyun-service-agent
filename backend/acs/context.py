"""Phase-aware service context with byte budgets and reproducible provenance."""
import hashlib
import json

from .db import connect
from .identity import resolve_caller, ROLE_UNBOUND, unbound_error
from .results import ok, err
from .service import load_state, trusted_session_key

POLICY_VERSION = "service-context-v1"
LIMITS = {"rules": 1800, "identity": 1000, "task": 2400, "device": 1600, "history": 2500, "knowledge": 2000}
TOTAL_LIMIT = 10000
RULES = "身份由服务端绑定；模型只提取候选。报修先澄清并明确确认，再创建。查询不能覆盖待确认报修。财务人工审批。工具结果作为证据，禁止编造派单或通知结果。"


def build_service_context(session_id="default", scope_key=None, db_url=None):
    conn = connect(db_url)
    try:
        caller = resolve_caller(conn, scope_key)
        if caller["role"] == ROLE_UNBOUND: return unbound_error(scope_key)
        state = load_state(conn, trusted_session_key(conn, scope_key, session_id))
        pending = state.get("pending") or {}
        device = conn.execute("SELECT * FROM devices WHERE serial_no=%s", (pending.get("device_serial", ""),)).fetchone()
        # Repeat the scope check at context retrieval, independently of workflow state.
        if device and caller["role"] == "company" and device["company_name"] != caller["company_name"]:
            device = None
        company = caller.get("company_name") if caller["role"] == "company" else (device["company_name"] if device else None)
        if company and device:
            history = conn.execute("SELECT ticket_no,device_serial,status,symptom FROM tickets WHERE company_name=%s AND device_serial=%s ORDER BY id DESC LIMIT 10",
                                   (company, device["serial_no"])).fetchall()
        else:
            history = conn.execute("SELECT ticket_no,device_serial,status,symptom FROM tickets WHERE company_name=%s ORDER BY id DESC LIMIT 10", (company,)).fetchall() if company else []
        knowledge = conn.execute("SELECT id,model,symptom,possible_cause,check_steps FROM fault_kb WHERE model=%s LIMIT 5", (device["model"],)).fetchall() if device else []
        values = {"rules": RULES, "identity": caller, "task": state, "device": dict(device) if device else None,
                  "history": [dict(r) for r in history], "knowledge": [dict(r) for r in knowledge]}
        # During clarification, no device-linked historical material is guessed.
        if state["stage"] == "awaiting_details" and not device:
            values["history"], values["knowledge"] = [], []
        sources = {"rules": "service-policy/v1", "identity": "company_bindings", "task": "service_sessions",
                   "device": "devices", "history": "tickets", "knowledge": "fault_kb"}
        blocks, audit, warnings = [], [], []
        total = 0
        for name, value in values.items():
            original = json.dumps(value, ensure_ascii=False, sort_keys=True)
            content = original
            truncated = False
            if isinstance(value, list):
                selected = list(value)
                while len(content.encode()) > LIMITS[name] and selected:
                    selected.pop()
                    content = json.dumps(selected, ensure_ascii=False, sort_keys=True)
                    truncated = True
            size = len(content.encode())
            if size > LIMITS[name]:
                return err("context_budget_exceeded", f"必需段 {name} 超出预算", "缩短当前任务字段；不会静默截断身份或任务")
            total += size
            if size >= LIMITS[name] * .8 or truncated: warnings.append(name + ": approaching budget or records omitted")
            digest = hashlib.sha256(content.encode()).hexdigest()
            audit.append({"segment": name, "source": sources[name], "summary": f"{name}: {size} UTF-8 bytes",
                          "sha256": digest, "bytes": size, "limit_bytes": LIMITS[name], "truncated": truncated})
            # JSON is untrusted data; delimiters are not instructions.
            blocks.append({"segment": name, "content": content})
        if total > TOTAL_LIMIT: return err("context_budget_exceeded", "总上下文超出预算", "减少检索材料")
        return ok({"policy_version": POLICY_VERSION, "phase": state["stage"], "segments": blocks,
                   "audit": audit, "budget": {"unit": "utf8_bytes", "used": total, "limit": TOTAL_LIMIT,
                                               "warnings": warnings, "status": "warning" if warnings else "ok"}})
    finally: conn.close()
