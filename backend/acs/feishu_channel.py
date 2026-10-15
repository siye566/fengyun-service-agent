"""Private Feishu configuration, durable inbox and SDK process supervision.

Only the official SDK process calls receive_message; there is no public event
injection endpoint. Customer identity comes from the verified channel sender.
"""
import asyncio
import base64
import hashlib
import json
import os
import sys
import time

from Crypto.Cipher import AES

from .db import begin_write, connect
from .service import route_service_turn

SCHEMA = """
CREATE TABLE IF NOT EXISTS feishu_config (
 id INTEGER PRIMARY KEY CHECK(id=1), app_id TEXT NOT NULL,
 secret_cipher TEXT NOT NULL, enabled BOOLEAN NOT NULL DEFAULT false,
 version INTEGER NOT NULL DEFAULT 1,
 runtime_state TEXT NOT NULL DEFAULT 'disabled', last_error TEXT NOT NULL DEFAULT '',
 last_received_at TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS feishu_conversations (
 id TEXT PRIMARY KEY, app_id TEXT NOT NULL, open_id TEXT NOT NULL,
 scope_key TEXT UNIQUE NOT NULL, chat_id TEXT NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(app_id, open_id)
);
CREATE TABLE IF NOT EXISTS feishu_messages (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 conversation_id TEXT NOT NULL REFERENCES feishu_conversations(id),
 message_id TEXT NOT NULL, request_hash TEXT NOT NULL, utterance TEXT NOT NULL,
 company_name TEXT NOT NULL DEFAULT '', result_json TEXT, reply_text TEXT,
 delivery TEXT NOT NULL DEFAULT 'received', attempts INTEGER NOT NULL DEFAULT 0,
 retry_at TIMESTAMPTZ NOT NULL DEFAULT now(), delivery_error TEXT NOT NULL DEFAULT '',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(conversation_id,message_id)
);
CREATE INDEX IF NOT EXISTS feishu_message_history ON feishu_messages(conversation_id,id DESC);
"""


def channel_key():
    value = os.getenv("ACS_CHANNEL_KEY", "")
    try:
        key = bytes.fromhex(value)
    except ValueError:
        key = b""
    if len(key) != 32:
        raise ValueError("ACS_CHANNEL_KEY must contain 64 hex characters")
    return key


def encrypt_secret(secret):
    cipher = AES.new(channel_key(), AES.MODE_GCM)
    encrypted, tag = cipher.encrypt_and_digest(secret.encode())
    return base64.b64encode(cipher.nonce + tag + encrypted).decode()


def decrypt_secret(value):
    raw = base64.b64decode(value)
    return AES.new(channel_key(), AES.MODE_GCM, nonce=raw[:16]).decrypt_and_verify(raw[32:], raw[16:32]).decode()


def configuration():
    with connect() as conn:
        return conn.execute("SELECT * FROM feishu_config WHERE id=1").fetchone()


def public_configuration():
    row = configuration()
    if not row:
        return {"app_id": "", "has_secret": False, "enabled": False,
                "runtime_state": "unconfigured", "last_error": "", "last_received_at": None}
    return {key: row[key] for key in ("app_id", "enabled", "runtime_state", "last_error", "last_received_at")} | {"has_secret": bool(row["secret_cipher"])}


def runtime(state, error="", version=None):
    with connect() as conn:
        conn.execute("UPDATE feishu_config SET runtime_state=%s,last_error=%s WHERE id=1 AND (%s::integer IS NULL OR version=%s)",
                     (state, error, version, version))


def result_text(result):
    if not result.get("ok"):
        error = result.get("error", {})
        if error.get("code") == "caller_unbound":
            return "已收到你的消息，请联系售后管理员在工作台绑定所属企业。绑定后可发送设备序列号和故障现象报修。"
        return error.get("message", "暂时无法处理，请稍后再试")
    data = result.get("data", {})
    lines = list(data.get("clarification", []))
    pending = data.get("pending")
    if pending and pending.get("device_serial"):
        lines.insert(0, f"设备：{pending['device_serial']}\n故障：{pending.get('symptom') or '待补充'}")
    for item in data.get("results", []):
        if not item.get("ok"):
            lines.append(item.get("error", {}).get("message", "查询未完成"))
            continue
        value = item.get("data", {})
        if value.get("ticket_no"):
            lines.append(f"工单：{value['ticket_no']} · {value.get('status_text', '已受理')}")
        for key in ("advice", "hint"):
            if value.get(key):
                lines.append(str(value[key]))
        for ticket in value.get("tickets", []):
            lines.append(f"{ticket['ticket_no']} · {ticket.get('status_text', ticket.get('status', ''))}")
        if value.get("next_due_date"):
            lines.append(f"下次保养：{value['next_due_date']}")
        if value.get("items"):
            lines.append("保养项目：" + str(value["items"]))
    if data.get("stage") == "cancelled":
        lines.append("当前报修已取消。")
    return "\n".join(lines) or "已处理。请发送报修、保养或工单进度需求。"


def record_message(app_id, open_id, chat_id, message_id, text):
    """Durably acknowledge verified p2p text before doing business/API work."""
    if not all(isinstance(v, str) and 0 < len(v) <= 200 for v in (app_id, open_id, chat_id, message_id)):
        return
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return
    conversation_id = hashlib.sha256(json.dumps([app_id, open_id]).encode()).hexdigest()
    scope = f"feishu:{app_id}:{open_id}"
    request_hash = hashlib.sha256(json.dumps([open_id, chat_id, text]).encode()).hexdigest()
    with connect() as conn:
        begin_write(conn)
        conn.execute("""INSERT INTO feishu_conversations(id,app_id,open_id,scope_key,chat_id)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET updated_at=now(),chat_id=EXCLUDED.chat_id""",
                     (conversation_id, app_id, open_id, scope, chat_id))
        binding = conn.execute("SELECT company_name FROM company_bindings WHERE scope_key=%s", (scope,)).fetchone()
        conn.execute("""INSERT INTO feishu_messages(conversation_id,message_id,request_hash,utterance,company_name)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(conversation_id,message_id) DO NOTHING""",
                     (conversation_id, message_id, request_hash, text, binding["company_name"] if binding else ""))
        row = conn.execute("SELECT * FROM feishu_messages WHERE conversation_id=%s AND message_id=%s",
                           (conversation_id, message_id)).fetchone()
        if row["request_hash"] != request_hash:
            raise ValueError("channel event identity conflict")
        conn.execute("UPDATE feishu_config SET last_received_at=GREATEST(last_received_at,%s) WHERE id=1 AND app_id=%s", (row["created_at"], app_id))
    return row


def process_message(row, scope, send):
    if row["result_json"] is None:
        result = route_service_turn(row["utterance"], session_id="feishu-p2p", event_id=row["message_id"], scope_key=scope)
        reply = result_text(result)
        with connect() as conn:
            conn.execute("UPDATE feishu_messages SET result_json=%s,reply_text=%s,delivery='pending' WHERE id=%s",
                         (json.dumps(result, ensure_ascii=False), reply, row["id"]))
        row.update(reply_text=reply, delivery="pending")
    if row["delivery"] != "sent" and row["attempts"] < 5:
        deliver(row, send)


def receive_message(app_id, open_id, chat_id, message_id, text, send):
    """Integration entry point; production SDK journals then drains its inbox."""
    row = record_message(app_id, open_id, chat_id, message_id, text)
    if row:
        process_message(row, f"feishu:{app_id}:{open_id}", send)


def deliver(row, send):
    # Stable <=50-character UUID supported by Feishu create-message API.
    outbound_id = hashlib.sha256((row["conversation_id"] + ":" + row["message_id"]).encode()).hexdigest()[:40]
    with connect() as conn:
        conn.execute("UPDATE feishu_messages SET attempts=attempts+1,retry_at=now()+interval '1 minute' WHERE id=%s", (row["id"],))
    try:
        send(outbound_id, row["reply_text"])
    except Exception:
        with connect() as conn:
            conn.execute("UPDATE feishu_messages SET delivery='failed',delivery_error='发送失败，请检查应用权限及网络' WHERE id=%s", (row["id"],))
        return
    with connect() as conn:
        conn.execute("UPDATE feishu_messages SET delivery='sent',delivery_error='' WHERE id=%s", (row["id"],))


async def supervise():
    """One SDK subprocess keeps its event loop separate from uvicorn.

    Credential changes restart the subprocess; credentials never enter argv or
    stdout. The web server remains available while the channel is unavailable.
    """
    process, revision, retry_after = None, None, 0
    try:
        while True:
            try:
                config = await asyncio.to_thread(configuration)
                version = config["version"] if config else None
                enabled = bool(config and config["enabled"])
                if process and process.returncode is not None and version == revision:
                    await asyncio.to_thread(runtime, "error", "飞书接收进程退出，请检查凭证、应用配置及服务器网络", revision)
                    process = None
                    retry_after = time.monotonic() + 30
                if process and (version != revision or not enabled):
                    if process.returncode is None:
                        process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=10)
                    process = None
                if enabled and process is None and (version != revision or time.monotonic() >= retry_after):
                    revision = version
                    await asyncio.to_thread(runtime, "starting", "", revision)
                    process = await asyncio.create_subprocess_exec(
                        sys.executable, "-m", "acs.feishu_worker", str(revision),
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                if not enabled and config:
                    await asyncio.to_thread(runtime, "disabled", "", version)
            except Exception:
                # DB errors and subprocess setup failures cannot expose secrets.
                pass
            await asyncio.sleep(5)
    finally:
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
