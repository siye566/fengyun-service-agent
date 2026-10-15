"""Authenticated operations console. Customer cookies never grant admin access."""
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .db import begin_write, connect
from .feishu_channel import channel_key, configuration, decrypt_secret, encrypt_secret, public_configuration, result_text
from .service import load_state, trusted_session_key
from .tools import STATUS_TEXT

COOKIE = "acs_admin"
SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_sessions (
 token_hash TEXT PRIMARY KEY, password_tag TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_audit (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, action TEXT NOT NULL,
 target TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: SecretStr = Field(max_length=256)


class FeishuSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(pattern=r"^cli_[a-zA-Z0-9]{3,100}$")
    app_secret: SecretStr = Field(default=SecretStr(""), max_length=256)
    enabled: bool


class Binding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    company_name: str = Field(default="", max_length=200)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password():
    value = os.getenv("ACS_ADMIN_PASSWORD", "")
    return value if len(value) >= 16 else ""


def require_admin(request):
    configured = password()
    token = request.cookies.get(COOKIE, "")
    if not configured or not 30 <= len(token) <= 100:
        raise HTTPException(401, "请先登录管理员账号")
    with connect() as conn:
        row = conn.execute("SELECT token_hash FROM admin_sessions WHERE token_hash=%s AND password_tag=%s AND expires_at>now()",
                           (digest(token), digest(configured))).fetchone()
    if not row:
        raise HTTPException(401, "管理员会话已失效，请重新登录")
    if request.method != "GET":
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), digest("acs-admin-csrf:" + token)):
            raise HTTPException(403, "管理员会话校验失败")
    return token


def audit(conn, action, target):
    conn.execute("INSERT INTO admin_audit(action,target) VALUES(%s,%s)", (action, target))


def attach_routes(app, secure):
    attempts = {}

    @app.get("/api/admin/session")
    def session(request: Request):
        try:
            token = require_admin(request)
            return {"authenticated": True, "configured": True, "csrf": digest("acs-admin-csrf:" + token)}
        except HTTPException:
            return {"authenticated": False, "configured": bool(password())}

    @app.post("/api/admin/login")
    def login(body: Login, request: Request, response: Response):
        expected = password()
        if not expected:
            raise HTTPException(503, "尚未配置管理员密码，请在服务器运行更新后的部署脚本")
        now = time.monotonic()
        for ip in list(attempts):
            if now - attempts[ip][0] > 300:
                del attempts[ip]
        ip = request.client.host if request.client else "unknown"
        if ip not in attempts:
            if len(attempts) >= 1000:
                raise HTTPException(429, "请稍后再试")
            attempts[ip] = [now, 0]
        if attempts[ip][1] >= 5:
            raise HTTPException(429, "登录尝试过多，请 5 分钟后重试")
        attempts[ip][1] += 1
        if not secrets.compare_digest(digest(body.password.get_secret_value()), digest(expected)):
            raise HTTPException(401, "管理员密码错误")
        token = secrets.token_urlsafe(32)
        with connect() as conn:
            conn.execute("DELETE FROM admin_sessions WHERE expires_at<=now() OR password_tag<>%s", (digest(expected),))
            old = request.cookies.get(COOKIE, "")
            conn.execute("DELETE FROM admin_sessions WHERE token_hash=%s", (digest(old),))
            conn.execute("INSERT INTO admin_sessions VALUES(%s,%s,now()+interval '12 hours')", (digest(token), digest(expected)))
            audit(conn, "admin_login", "admin")
        attempts.pop(ip, None)
        response.set_cookie(COOKIE, token, max_age=43200, httponly=True, secure=secure, samesite="strict", path="/")
        return {"authenticated": True, "configured": True, "csrf": digest("acs-admin-csrf:" + token)}

    @app.post("/api/admin/logout")
    def logout(request: Request, response: Response):
        token = require_admin(request)
        with connect() as conn:
            conn.execute("DELETE FROM admin_sessions WHERE token_hash=%s", (digest(token),))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/admin/overview")
    def overview(request: Request):
        require_admin(request)
        with connect() as conn:
            stats = conn.execute("""SELECT
                (SELECT count(*) FROM feishu_conversations) AS feishu_conversations,
                (SELECT count(*) FROM web_visitors WHERE expires_at>now()) AS web_conversations,
                (SELECT count(*) FROM tickets) AS tickets,
                (SELECT count(*) FROM tickets WHERE status='pending_dispatch') AS pending_tickets,
                (SELECT count(*) FROM feishu_conversations c LEFT JOIN company_bindings b ON b.scope_key=c.scope_key WHERE b.scope_key IS NULL) AS unbound,
                (SELECT count(*) FROM feishu_messages WHERE delivery='failed') AS failed_replies""").fetchone()
            companies = conn.execute("SELECT DISTINCT company_name FROM devices WHERE company_name NOT IN (SELECT company_name FROM web_visitors) ORDER BY company_name").fetchall()
        return {"stats": stats, "companies": [c["company_name"] for c in companies], "feishu": public_configuration(), "mode": "rule_baseline"}

    @app.get("/api/admin/conversations")
    def conversations(request: Request, channel: str = Query(default="all", pattern="^(all|feishu|web)$"),
                      q: str = Query(default="", max_length=100), offset: int = Query(default=0, ge=0)):
        require_admin(request)
        with connect() as conn:
            rows = conn.execute("""WITH conversations AS (
                SELECT 'feishu:'||c.id AS id,'feishu' AS channel,c.open_id AS customer,
                coalesce(b.company_name,'') AS company,c.updated_at,
                coalesce(m.utterance,'') AS last_message FROM feishu_conversations c
                LEFT JOIN company_bindings b ON b.scope_key=c.scope_key
                LEFT JOIN LATERAL(SELECT utterance FROM feishu_messages WHERE conversation_id=c.id ORDER BY id DESC LIMIT 1)m ON true
                UNION ALL
                SELECT 'web:'||v.token_hash,'web',v.company_name,v.company_name,
                coalesce(m.created_at,v.expires_at-interval '24 hours'),coalesce(m.utterance,'')
                FROM web_visitors v LEFT JOIN LATERAL(SELECT utterance,created_at FROM web_messages WHERE token_hash=v.token_hash ORDER BY id DESC LIMIT 1)m ON true
                WHERE v.expires_at>now()
            ) SELECT *,count(*) OVER() AS total FROM conversations
              WHERE (%s='all' OR channel=%s) AND (%s='' OR strpos(lower(customer||' '||company||' '||last_message),lower(%s))>0)
              ORDER BY updated_at DESC,id LIMIT 50 OFFSET %s""", (channel, channel, q, q, offset)).fetchall()
        return {"items": rows, "offset": offset, "has_more": bool(rows and rows[0]["total"] > offset + len(rows))}

    @app.get("/api/admin/conversations/{identifier}")
    def conversation(identifier: str, request: Request, before: int = Query(default=9223372036854775807, ge=1)):
        require_admin(request)
        channel, _, key = identifier.partition(":")
        if channel not in ("feishu", "web") or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise HTTPException(404, "会话不存在")
        with connect() as conn:
            if channel == "feishu":
                row = conn.execute("SELECT c.*,coalesce(b.company_name,'') AS company FROM feishu_conversations c LEFT JOIN company_bindings b ON b.scope_key=c.scope_key WHERE c.id=%s", (key,)).fetchone()
                if not row:
                    raise HTTPException(404, "会话不存在")
                messages = conn.execute("SELECT id,utterance,result_json,reply_text,delivery,delivery_error,created_at,company_name FROM feishu_messages WHERE conversation_id=%s AND id<%s ORDER BY id DESC LIMIT 100", (key, before)).fetchall()
                customer, company, scope, thread = row["open_id"], row["company"], row["scope_key"], "feishu-p2p"
            else:
                row = conn.execute("SELECT * FROM web_visitors WHERE token_hash=%s AND expires_at>now()", (key,)).fetchone()
                if not row:
                    raise HTTPException(404, "会话已过期或不存在")
                messages = conn.execute("SELECT id,utterance,result_json,created_at FROM web_messages WHERE token_hash=%s AND id<%s ORDER BY id DESC LIMIT 100", (key, before)).fetchall()
                customer = company = row["company_name"]
                scope, thread = row["scope_key"], "browser"
            state = load_state(conn, trusted_session_key(conn, scope, thread))
        for item in messages:
            result = json.loads(item.pop("result_json")) if item["result_json"] else None
            item["reply_text"] = item.get("reply_text") or (result_text(result) if result else "等待处理")
        return {"id": identifier, "channel": channel, "customer": customer, "company": company,
                "state": state, "messages": list(reversed(messages)), "older_cursor": messages[-1]["id"] if len(messages) == 100 else None}

    @app.post("/api/admin/bindings")
    def binding(body: Binding, request: Request):
        require_admin(request)
        with connect() as conn:
            begin_write(conn)
            row = conn.execute("SELECT scope_key FROM feishu_conversations WHERE id=%s", (body.conversation_id,)).fetchone()
            if not row:
                raise HTTPException(404, "请先让客户给机器人发送一条私聊消息")
            if body.company_name:
                existing = conn.execute("SELECT serial_no FROM devices WHERE company_name=%s AND company_name NOT IN (SELECT company_name FROM web_visitors) LIMIT 1", (body.company_name,)).fetchone()
                if not existing:
                    raise HTTPException(422, "请选择设备台账中的企业")
                conn.execute("""INSERT INTO company_bindings(scope_key,company_name,role,bound_at) VALUES(%s,%s,'company',%s)
                    ON CONFLICT(scope_key) DO UPDATE SET company_name=EXCLUDED.company_name,role='company',bound_at=EXCLUDED.bound_at""",
                             (row["scope_key"], body.company_name, datetime.now(timezone.utc).isoformat()))
            else:
                conn.execute("DELETE FROM company_bindings WHERE scope_key=%s", (row["scope_key"],))
            audit(conn, "bind_company" if body.company_name else "unbind_company", body.conversation_id)
        return {"ok": True}

    @app.get("/api/admin/tickets")
    def tickets(request: Request, offset: int = Query(default=0, ge=0)):
        require_admin(request)
        with connect() as conn:
            rows = conn.execute("SELECT *,count(*) OVER() AS total FROM tickets ORDER BY id DESC LIMIT 50 OFFSET %s", (offset,)).fetchall()
        for row in rows:
            row["status_text"] = STATUS_TEXT.get(row["status"], row["status"])
        return {"items": rows, "has_more": bool(rows and rows[0]["total"] > offset + len(rows))}

    @app.get("/api/admin/devices")
    def devices(request: Request, offset: int = Query(default=0, ge=0)):
        require_admin(request)
        with connect() as conn:
            rows = conn.execute("SELECT *,count(*) OVER() AS total FROM devices ORDER BY id LIMIT 50 OFFSET %s", (offset,)).fetchall()
        return {"items": rows, "has_more": bool(rows and rows[0]["total"] > offset + len(rows))}

    @app.get("/api/admin/feishu")
    def feishu(request: Request):
        require_admin(request)
        return public_configuration()

    @app.post("/api/admin/feishu")
    def save_feishu(body: FeishuSettings, request: Request):
        require_admin(request)
        try:
            channel_key()
        except ValueError:
            raise HTTPException(503, "尚未配置渠道加密密钥，请运行更新后的部署脚本") from None
        with connect() as conn:
            begin_write(conn)
            old = conn.execute("SELECT * FROM feishu_config WHERE id=1").fetchone()
            secret = body.app_secret.get_secret_value().strip()
            if not secret and (not old or old["app_id"] != body.app_id):
                raise HTTPException(422, "首次配置或更换 App ID 时需要填写 App Secret")
            encrypted = encrypt_secret(secret) if secret else old["secret_cipher"]
            conn.execute("""INSERT INTO feishu_config(id,app_id,secret_cipher,enabled,runtime_state) VALUES(1,%s,%s,%s,%s)
                ON CONFLICT(id) DO UPDATE SET app_id=EXCLUDED.app_id,secret_cipher=EXCLUDED.secret_cipher,
                enabled=EXCLUDED.enabled,version=feishu_config.version+1,runtime_state=EXCLUDED.runtime_state,
                last_error='',last_received_at=NULL,updated_at=now()""",
                         (body.app_id, encrypted, body.enabled, "starting" if body.enabled else "disabled"))
            audit(conn, "save_feishu", body.app_id)
        return public_configuration()

    @app.post("/api/admin/feishu/check")
    def check_feishu(request: Request):
        require_admin(request)
        config = configuration()
        if not config:
            raise HTTPException(422, "请先保存应用配置")
        try:
            secret = decrypt_secret(config["secret_cipher"])
            with httpx.Client(timeout=12) as client:
                response = client.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                                       json={"app_id": config["app_id"], "app_secret": secret})
                data = response.json()
            if response.status_code != 200 or data.get("code") != 0 or not data.get("tenant_access_token"):
                raise ValueError("invalid application credentials")
        except Exception:
            raise HTTPException(502, "凭证验证失败，请检查 App ID、App Secret 和服务器到飞书的网络") from None
        return {"ok": True, "message": "应用凭证有效；请继续验证事件订阅、机器人权限及实际收发。"}
