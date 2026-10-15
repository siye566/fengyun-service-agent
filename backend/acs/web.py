"""HTTP adapter for the domain engine, admin console and Feishu management.

Opaque HttpOnly cookies resolve to server-owned company bindings. Neither role,
scope nor model candidates are accepted from a customer browser. Admin cookies
are authenticated separately. No external LLM is used.
"""
import hashlib
import asyncio
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import psycopg
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .db import begin_write, connect
from .seed import seed
from .service import load_state, route_service_turn, trusted_session_key
from .tools import STATUS_TEXT, query_maintenance
from . import admin, feishu_channel

COOKIE = "acs_visitor"
TTL = 86400
WEB_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_visitors (
 token_hash TEXT PRIMARY KEY, scope_key TEXT UNIQUE NOT NULL,
 company_name TEXT UNIQUE NOT NULL, expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS web_messages (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 token_hash TEXT NOT NULL REFERENCES web_visitors(token_hash) ON DELETE CASCADE,
 event_id TEXT NOT NULL, request_hash TEXT NOT NULL, utterance TEXT NOT NULL,
 result_json TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(token_hash, event_id)
);
"""


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["message", "prepare_repair", "confirm_repair", "cancel_repair", "progress", "maintenance"]
    event_id: str = Field(min_length=16, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    utterance: str = Field(default="", max_length=4000)
    device_serial: str = Field(default="", max_length=80)
    symptom: str = Field(default="", max_length=500)


class BodyLimit:
    """Bound chunked as well as Content-Length bodies before JSON parsing."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 16384:
                return await JSONResponse({"detail": "请求内容过大"}, status_code=413)(scope, receive, send)
            if not message.get("more_body"):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def csrf(token):
    return hashlib.sha256(("acs-csrf:" + token).encode()).hexdigest()


def visitor(request):
    token = request.cookies.get(COOKIE, "")
    if not 30 <= len(token) <= 100:
        raise HTTPException(401, "体验会话已失效，请刷新页面")
    with connect() as conn:
        row = conn.execute("SELECT * FROM web_visitors WHERE token_hash=%s AND expires_at>now()",
                           (token_hash(token),)).fetchone()
    if not row:
        raise HTTPException(401, "体验会话已失效，请刷新页面")
    return token, row


def cleanup(conn):
    """Remove only expired adapter-owned synthetic tenants, never reset domain data."""
    rows = conn.execute("SELECT * FROM web_visitors WHERE expires_at<=now()").fetchall()
    for row in rows:
        key = trusted_session_key(conn, row["scope_key"], "browser")
        conn.execute("DELETE FROM service_turns WHERE session_key=%s", (key,))
        conn.execute("DELETE FROM service_sessions WHERE session_key=%s", (key,))
        conn.execute("DELETE FROM tickets WHERE company_name=%s", (row["company_name"],))
        conn.execute("DELETE FROM devices WHERE company_name=%s", (row["company_name"],))
        conn.execute("DELETE FROM company_bindings WHERE scope_key=%s", (row["scope_key"],))
        conn.execute("DELETE FROM web_visitors WHERE token_hash=%s", (row["token_hash"],))


def new_visitor():
    token = secrets.token_urlsafe(32)
    hashed = token_hash(token)
    scope, company = "web:guest:" + hashed, "体验企业-" + hashed[:12]
    serial = "DEMO-GR75-" + str(secrets.randbits(64))
    with connect() as conn:
        begin_write(conn)
        cleanup(conn)
        if conn.execute("SELECT count(*) AS n FROM web_visitors").fetchone()["n"] >= 500:
            raise HTTPException(503, "体验空间暂满，请稍后再试")
        conn.execute("INSERT INTO web_visitors VALUES (%s,%s,%s,now()+interval '24 hours')",
                     (hashed, scope, company))
        conn.execute("INSERT INTO company_bindings VALUES (%s,%s,'company',%s)",
                     (scope, company, date.today().isoformat()))
        conn.execute("""INSERT INTO devices(company_name,model,serial_no,installed_date,
                     last_maintenance_date,maintenance_interval_days) VALUES (%s,'GR-75',%s,%s,%s,90)""",
                     (company, serial, date.today().isoformat(), (date.today()-timedelta(days=85)).isoformat()))
    return token


def snapshot(row, token):
    with connect() as conn:
        devices = conn.execute("SELECT * FROM devices WHERE company_name=%s ORDER BY id",
                               (row["company_name"],)).fetchall()
        tickets = conn.execute("SELECT * FROM tickets WHERE company_name=%s ORDER BY id DESC LIMIT 100",
                               (row["company_name"],)).fetchall()
        state = load_state(conn, trusted_session_key(conn, row["scope_key"], "browser"))
        history = conn.execute("""SELECT utterance,result_json,created_at FROM web_messages
                     WHERE token_hash=%s AND result_json IS NOT NULL ORDER BY id DESC LIMIT 40""",
                               (row["token_hash"],)).fetchall()
    for device in devices:
        device["maintenance"] = query_maintenance(device["serial_no"], row["scope_key"])["data"]
    for ticket in tickets:
        ticket["status_text"] = STATUS_TEXT.get(ticket["status"], ticket["status"])
    return {"csrf": csrf(token), "company": row["company_name"], "devices": devices,
            "tickets": tickets, "state": state, "mode": "rule_baseline",
            "expires_at": row["expires_at"].isoformat(),
            "history": [{**h, "result": json.loads(h["result_json"]),
                         "created_at": h["created_at"].isoformat()} for h in reversed(history)]}


def create_app(origin=None, static_dir=None, start_connector=True):
    origin = (origin or os.getenv("ACS_WEB_ORIGIN", "http://127.0.0.1:8080")).rstrip("/")
    parsed_origin = urlsplit(origin)
    if parsed_origin.scheme not in ("http", "https") or not parsed_origin.hostname or parsed_origin.path:
        raise ValueError("ACS_WEB_ORIGIN must be an HTTP(S) origin without a path")

    @asynccontextmanager
    async def lifespan(_):
        seed()  # Idempotent, never seed(reset=True).
        with connect() as conn:
            conn.execute(WEB_SCHEMA)
            conn.execute(admin.SCHEMA)
            conn.execute(feishu_channel.SCHEMA)
        connector = asyncio.create_task(feishu_channel.supervise()) if start_connector else None
        try:
            yield
        finally:
            if connector:
                connector.cancel()
                try:
                    await connector
                except asyncio.CancelledError:
                    pass

    api = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    api.add_middleware(TrustedHostMiddleware, allowed_hosts=[parsed_origin.hostname, "localhost", "127.0.0.1", "testserver"])
    api.add_middleware(BodyLimit)
    windows = {}

    @api.middleware("http")
    async def protect(request, call_next):
        if request.url.path.startswith("/api/"):
            now = time.monotonic()
            # One process, no forwarded-header trust; buckets expire and remain bounded.
            for key in list(windows):
                if now - windows[key][0] > 60:
                    del windows[key]
            key = request.client.host if request.client else "unknown"
            if key not in windows:
                if len(windows) >= 1000:
                    return JSONResponse({"detail": "请稍后再试"}, status_code=429)
                windows[key] = [now, 0]
            windows[key][1] += 1
            if windows[key][1] > 120:
                return JSONResponse({"detail": "操作频繁，请一分钟后再试"}, status_code=429,
                                    headers={"Retry-After": "60"})
            if request.method == "POST" and request.headers.get("origin") != origin:
                return JSONResponse({"detail": "请求来源不匹配"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @api.exception_handler(psycopg.Error)
    async def database_error(_, exc):
        logging.warning("Database unavailable (%s)", type(exc).__name__)
        return JSONResponse({"detail": "数据库暂不可用，请稍后重试"}, status_code=503)

    @api.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        # Validation errors must not echo submitted passwords or app secrets.
        return JSONResponse({"detail": "输入未通过校验，请检查字段格式与长度"}, status_code=422)

    @api.get("/healthz")
    def health():
        with connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "storage": "postgresql", "mode": "rule_baseline"}

    @api.get("/api/session")
    def session(request: Request, response: Response):
        try:
            token, row = visitor(request)
        except HTTPException:
            token = new_visitor()
            response.set_cookie(COOKIE, token, max_age=TTL, httponly=True,
                                secure=parsed_origin.scheme == "https", samesite="lax", path="/")
            with connect() as conn:
                row = conn.execute("SELECT * FROM web_visitors WHERE token_hash=%s", (token_hash(token),)).fetchone()
        return snapshot(row, token)

    @api.post("/api/turn")
    def turn(body: Turn, request: Request):
        token, row = visitor(request)
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), csrf(token)):
            raise HTTPException(403, "会话校验失败，请刷新页面")
        candidates = None
        if body.action == "message":
            text = body.utterance.strip()
            if not text:
                raise HTTPException(422, "请输入售后需求")
        elif body.action == "prepare_repair":
            if not body.device_serial or not body.symptom.strip():
                raise HTTPException(422, "请补齐设备与故障")
            text = f"报修 {body.device_serial} {body.symptom.strip()}"
            candidates = {"intents": ["repair"], "device_serial": body.device_serial, "symptom": body.symptom.strip()}
        else:
            text = {"confirm_repair": "确认报修", "cancel_repair": "取消报修",
                    "progress": "查工单进度", "maintenance": "查询保养 " + body.device_serial}[body.action]
        payload_hash = token_hash(json.dumps(body.model_dump(), sort_keys=True, ensure_ascii=False))
        with connect() as conn:
            begin_write(conn)
            old = conn.execute("SELECT * FROM web_messages WHERE token_hash=%s AND event_id=%s",
                               (row["token_hash"], body.event_id)).fetchone()
            if old and old["request_hash"] != payload_hash:
                raise HTTPException(409, "相同事件编号不能用于不同请求")
            if not old:
                count = conn.execute("SELECT count(*) AS n FROM web_messages WHERE token_hash=%s",
                                     (row["token_hash"],)).fetchone()["n"]
                if count >= 200:
                    raise HTTPException(429, "当前体验空间已达到 200 次操作上限")
                conn.execute("INSERT INTO web_messages(token_hash,event_id,request_hash,utterance) VALUES (%s,%s,%s,%s)",
                             (row["token_hash"], body.event_id, payload_hash, text))
        result = json.loads(old["result_json"]) if old and old["result_json"] else route_service_turn(
            text, session_id="browser", event_id=body.event_id, scope_key=row["scope_key"], parsed=candidates)
        with connect() as conn:
            conn.execute("UPDATE web_messages SET result_json=%s WHERE token_hash=%s AND event_id=%s",
                         (json.dumps(result, ensure_ascii=False), row["token_hash"], body.event_id))
        return {"result": result, "snapshot": snapshot(row, token)}

    admin.attach_routes(api, secure=parsed_origin.scheme == "https")
    directory = Path(static_dir or os.getenv("ACS_STATIC_DIR", "apps/service-console/dist"))
    if directory.is_dir():
        @api.get("/experience")
        @api.get("/service-preview")
        def preview():
            return FileResponse(directory / "index.html")
        api.mount("/", StaticFiles(directory=directory, html=True), name="console")
    return api


app = create_app()
