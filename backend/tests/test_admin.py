"""Real PostgreSQL admin boundaries and channel persistence; no live credentials."""
import json
import uuid
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from acs.admin import COOKIE, digest
from acs.db import connect
from acs.feishu_channel import configuration, decrypt_secret, receive_message, record_message, process_message, runtime
from acs.feishu_worker import sdk_message
from acs.testing import temporary_database
from acs.web import create_app

PASSWORD = "ci-only-admin-password-long-enough"
ORIGIN = "http://testserver"


@pytest.fixture
def admin(monkeypatch):
    with temporary_database() as url:
        monkeypatch.setenv("ACS_DATABASE_URL", url)
        monkeypatch.delenv("ACS_DB_SCHEMA", raising=False)
        monkeypatch.setenv("ACS_ADMIN_PASSWORD", PASSWORD)
        monkeypatch.setenv("ACS_CHANNEL_KEY", "ab" * 32)
        app = create_app(origin=ORIGIN, start_connector=False)
        with TestClient(app) as client:
            response = client.post("/api/admin/login", json={"password": PASSWORD}, headers={"Origin": ORIGIN})
            assert response.status_code == 200
            assert "HttpOnly" in response.headers["set-cookie"]
            assert "SameSite=strict" in response.headers["set-cookie"]
            client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf"]})
            yield client, app


def test_admin_reads_all_customers_but_visitor_cookie_never_grants_admin(admin):
    client, app = admin
    companies = []
    for _ in range(2):
        with TestClient(app) as visitor:
            guest = visitor.get("/api/session").json()
            companies.append(guest["company"])
            assert visitor.get("/api/admin/overview").status_code == 401
            visitor.cookies.set(COOKIE, "a" * 43)
            assert visitor.get("/api/admin/conversations").status_code == 401
    response = client.get("/api/admin/conversations").json()
    assert {item["company"] for item in response["items"]} == set(companies)
    item = response["items"][0]
    assert client.get("/api/admin/conversations/" + item["id"]).status_code == 200
    assert client.get("/api/admin/devices").json()["items"]
    assert client.get("/api/admin/conversations", params={"q": companies[0]}).json()["items"][0]["company"] == companies[0]
    assert not client.get("/api/admin/conversations?channel=feishu").json()["items"]
    assert client.post("/api/admin/logout", json={}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post("/api/admin/logout", json={}).status_code == 200
    assert client.get("/api/admin/tickets").status_code == 401


def test_login_origin_bruteforce_expiry_and_password_rotation(admin, monkeypatch):
    client, app = admin
    assert client.post("/api/admin/login", json={"password": PASSWORD}, headers={"Origin": "https://elsewhere.example"}).status_code == 403
    with TestClient(app) as other:
        for _ in range(5):
            assert other.post("/api/admin/login", json={"password": "wrong"}, headers={"Origin": ORIGIN}).status_code == 401
        assert other.post("/api/admin/login", json={"password": PASSWORD}, headers={"Origin": ORIGIN}).status_code == 429
    with connect() as conn:
        conn.execute("UPDATE admin_sessions SET expires_at=now()-interval '1 minute'")
    assert client.get("/api/admin/overview").status_code == 401
    with connect() as conn:
        conn.execute("UPDATE admin_sessions SET expires_at=now()+interval '1 hour'")
    monkeypatch.setenv("ACS_ADMIN_PASSWORD", PASSWORD + "rotated")
    assert client.get("/api/admin/overview").status_code == 401


def test_encrypted_settings_mask_secret_validate_credentials_and_persist(admin, monkeypatch):
    client, app = admin
    body = {"app_id": "cli_ci123", "app_secret": "ci-only-app-secret", "enabled": False}
    response = client.post("/api/admin/feishu", json=body)
    assert response.status_code == 200
    assert "ci-only-app-secret" not in response.text
    assert "secret_cipher" not in response.text
    config = configuration()
    assert "ci-only-app-secret" not in config["secret_cipher"]
    assert decrypt_secret(config["secret_cipher"]) == body["app_secret"]
    assert client.post("/api/admin/feishu", json={**body, "app_secret": ""}).status_code == 200
    assert decrypt_secret(configuration()["secret_cipher"]) == body["app_secret"]
    assert client.post("/api/admin/feishu", json={**body, "app_id": "cli_changed", "app_secret": ""}).status_code == 422
    runtime("waiting_event", version=configuration()["version"])
    assert client.get("/api/admin/feishu").json()["runtime_state"] == "waiting_event"
    # Network boundary only: validate exact request without real account access.
    import httpx
    original_post = httpx.Client.post
    def verify(self, url, **kwargs):
        if not str(url).startswith("https://open.feishu.cn/"):
            return original_post(self, url, **kwargs)
        assert url == "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        assert kwargs["json"]["app_secret"] == body["app_secret"]
        return NS(status_code=200, json=lambda: {"code": 0, "tenant_access_token": "ci-only-never-return-token"})
    monkeypatch.setattr("httpx.Client.post", verify)
    checked = client.post("/api/admin/feishu/check", json={})
    assert checked.status_code == 200
    assert "ci-only-never-return-token" not in checked.text
    with TestClient(create_app(origin=ORIGIN, start_connector=False)) as restarted:
        restarted.cookies.update(dict(client.cookies))
        assert restarted.get("/api/admin/feishu").json()["has_secret"]


def test_feishu_unbound_then_company_binding_confirmation_retries_and_all_history(admin):
    client, _ = admin
    sent = []
    def message(text, event=None, sender="ou_ci_customer"):
        receive_message("cli_ci123", sender, "oc_ci_chat", event or "om_" + uuid.uuid4().hex, text,
                        lambda key, reply: sent.append((key, reply)))
    message("报修")
    item = client.get("/api/admin/conversations?channel=feishu").json()["items"][0]
    assert not item["company"] and "绑定" in sent[-1][1]
    assert client.post("/api/admin/bindings", json={"conversation_id": item["id"].split(":")[1], "company_name": "示例企业甲", "role": "internal"}).status_code == 422
    body = {"conversation_id": item["id"].split(":")[1], "company_name": "示例企业甲"}
    assert client.post("/api/admin/bindings", json=body).status_code == 200
    message("报修 DEMO-GR75-0002 机器异响")
    assert "不属于" in sent[-1][1]
    message("报修 DEMO-GR75-0001 机器异响")
    assert "确认报修" in sent[-1][1]
    assert not client.get("/api/admin/tickets").json()["items"]
    message("查工单进度")
    current = client.get("/api/admin/conversations/" + item["id"]).json()
    assert current["state"]["stage"] == "awaiting_confirmation"
    event = "om_" + uuid.uuid4().hex
    message("确认报修", event)
    delivered = len(sent)
    message("确认报修", event)
    assert len(sent) == delivered
    assert len(client.get("/api/admin/tickets").json()["items"]) == 1
    saved = client.get("/api/admin/conversations/" + item["id"]).json()
    assert len(saved["messages"]) == 5
    assert all(m["delivery"] == "sent" for m in saved["messages"])
    assert saved["state"]["stage"] == "completed"
    message("报修 DEMO-GR75-0001 机器异响")
    assert client.post("/api/admin/bindings", json={**body, "company_name": "示例企业乙"}).status_code == 200
    assert client.get("/api/admin/conversations/" + item["id"]).json()["state"]["pending"] is None
    message("确认报修")
    assert len(client.get("/api/admin/tickets").json()["items"]) == 1


def test_durable_received_and_failed_outbox_resumes_without_duplicate_ticket(admin):
    client, _ = admin
    row = record_message("cli_ci123", "ou_outbox", "oc_outbox", "om_inbox", "报修")
    with connect() as conn:
        assert conn.execute("SELECT delivery FROM feishu_messages WHERE id=%s", (row["id"],)).fetchone()["delivery"] == "received"
    def offline(*args):
        raise RuntimeError("ci-only simulated transport failure")
    scope = "feishu:cli_ci123:ou_outbox"
    process_message(row, scope, offline)
    with connect() as conn:
        pending = conn.execute("SELECT * FROM feishu_messages WHERE id=%s", (row["id"],)).fetchone()
    assert pending["delivery"] == "failed" and pending["attempts"] == 1
    delivered = []
    process_message(pending, scope, lambda key, text: delivered.append((key, text)))
    process_message({**pending, "delivery": "sent"}, scope, offline)
    assert len(delivered) == 1
    with connect() as conn:
        saved = conn.execute("SELECT * FROM feishu_messages WHERE id=%s", (row["id"],)).fetchone()
        assert saved["delivery"] == "sent" and saved["attempts"] == 2
    with pytest.raises(ValueError):
        record_message("cli_ci123", "ou_outbox", "oc_outbox", "om_inbox", "changed")


def test_sdk_handler_ignores_groups_and_non_user_messages_and_official_builders(admin):
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
    client, _ = admin
    msg = NS(chat_type="group", message_type="text", chat_id="oc_sdk", message_id="om_sdk", content=json.dumps({"text": "报修"}))
    sender = NS(sender_type="user", sender_id=NS(open_id="ou_sdk"))
    event = NS(event=NS(message=msg, sender=sender))
    sdk_message(event, "cli_sdk")
    assert not client.get("/api/admin/conversations?channel=feishu").json()["items"]
    msg.chat_type = "p2p"
    sender.sender_type = "app"
    sdk_message(event, "cli_sdk")
    assert not client.get("/api/admin/conversations?channel=feishu").json()["items"]
    sender.sender_type = "user"
    sdk_message(event, "cli_sdk")
    assert len(client.get("/api/admin/conversations?channel=feishu").json()["items"]) == 1
    # Import/build real pinned SDK models; transport is deliberately not invoked.
    lark.Client.builder().app_id("cli_sdk").app_secret("ci-only").timeout(12).build()
    body = CreateMessageRequestBody.builder().receive_id("oc_sdk").msg_type("text").content('{"text":"ci"}').uuid("a" * 40).build()
    assert CreateMessageRequest.builder().receive_id_type("chat_id").request_body(body).build().body.uuid == "a" * 40
