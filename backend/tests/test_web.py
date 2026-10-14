import uuid

import pytest
from fastapi.testclient import TestClient

from acs.db import begin_write, connect
from acs.testing import temporary_database
from acs.web import COOKIE, cleanup, create_app


@pytest.fixture
def web(monkeypatch):
    with temporary_database() as url:
        monkeypatch.setenv("ACS_DATABASE_URL", url)
        monkeypatch.delenv("ACS_DB_SCHEMA", raising=False)
        app = create_app(origin="http://testserver")
        with TestClient(app) as client:
            initial = client.get("/api/session")
            assert "HttpOnly" in initial.headers["set-cookie"]
            assert "SameSite=lax" in initial.headers["set-cookie"]
            data = initial.json()
            yield client, data, app


def post(client, data, action, **fields):
    body = {"action": action, "event_id": uuid.uuid4().hex, **fields}
    response = client.post("/api/turn", json=body, headers={"Origin": "http://testserver", "X-CSRF-Token": data["csrf"]})
    return response, body


def test_real_workflow_survives_refresh_retry_and_adapter_restart(web):
    client, data, app = web
    serial = data["devices"][0]["serial_no"]
    result, _ = post(client, data, "prepare_repair", device_serial=serial, symptom="机器异响")
    assert result.json()["snapshot"]["state"]["stage"] == "awaiting_confirmation"
    assert not result.json()["snapshot"]["tickets"]
    result, _ = post(client, data, "progress")
    assert result.json()["snapshot"]["state"]["pending"]["device_serial"] == serial
    result, confirmation = post(client, data, "confirm_repair")
    assert result.json()["result"]["ok"]
    assert len(result.json()["snapshot"]["tickets"]) == 1
    retry = client.post("/api/turn", json=confirmation, headers={"Origin": "http://testserver", "X-CSRF-Token": data["csrf"]})
    assert retry.json()["result"] == result.json()["result"]
    assert len(retry.json()["snapshot"]["tickets"]) == 1
    cookies = dict(client.cookies)
    with TestClient(create_app(origin="http://testserver")) as restarted:
        restarted.cookies.update(cookies)
        saved = restarted.get("/api/session").json()
        assert saved["company"] == data["company"]
        assert len(saved["tickets"]) == 1
        assert saved["state"]["stage"] == "completed"
    with TestClient(app) as other:
        isolated = other.get("/api/session").json()
        assert isolated["company"] != data["company"]
        assert not isolated["tickets"] and not isolated["history"]
        denied, _ = post(other, isolated, "prepare_repair", device_serial=serial, symptom="机器异响")
        assert denied.json()["result"]["error"]["code"] == "cross_company_denied"


def test_auth_origin_csrf_and_client_scope_cannot_be_forged(web):
    client, data, _ = web
    body = {"action": "confirm_repair", "event_id": uuid.uuid4().hex}
    assert client.post("/api/turn", json=body).status_code == 403
    assert client.post("/api/turn", json=body, headers={"Origin": "http://testserver"}).status_code == 403
    headers = {"Origin": "http://testserver", "X-CSRF-Token": data["csrf"]}
    assert client.post("/api/turn", json={**body, "scope_key": "web:main"}, headers=headers).status_code == 422
    assert client.post("/api/turn", json={**body, "parsed": {"intents": ["repair"]}}, headers=headers).status_code == 422
    result = client.post("/api/turn", json=body, headers=headers)
    assert result.json()["result"]["error"]["code"] == "confirmation_not_ready"
    client.cookies.set(COOKIE, "a" * 43)
    assert client.post("/api/turn", json=body, headers=headers).status_code == 401


def test_event_collision_chunked_body_limit_cookie_and_quota(web):
    client, data, _ = web
    cookie = client.get("/api/session")
    assert cookie.headers["cache-control"] == "no-store"
    result, body = post(client, data, "progress")
    headers = {"Origin": "http://testserver", "X-CSRF-Token": data["csrf"]}
    assert client.post("/api/turn", json={**body, "action": "cancel_repair"}, headers=headers).status_code == 409
    headers["Content-Type"] = "application/json"
    chunks = (b"x" * 4096 for _ in range(6))
    assert client.post("/api/turn", content=chunks, headers=headers).status_code == 413
    assert client.get("/healthz").json()["storage"] == "postgresql"
    for _ in range(121):
        response = client.get("/api/session")
    assert response.status_code == 429


def test_expired_workspace_cleanup_does_not_reset_other_tenants(web):
    client, data, app = web
    expired_company = data["company"]
    post(client, data, "prepare_repair", device_serial=data["devices"][0]["serial_no"], symptom="机器异响")
    post(client, data, "confirm_repair")
    with TestClient(app) as other:
        active = other.get("/api/session").json()
        post(other, active, "prepare_repair", device_serial=active["devices"][0]["serial_no"], symptom="不出气")
        post(other, active, "confirm_repair")
        with connect() as conn:
            begin_write(conn)
            conn.execute("UPDATE web_visitors SET expires_at=now()-interval '1 minute' WHERE company_name=%s", (expired_company,))
            cleanup(conn)
        assert len(other.get("/api/session").json()["tickets"]) == 1
        # Deleting the first ticket must not make count-based numbering collide.
        post(other, active, "prepare_repair", device_serial=active["devices"][0]["serial_no"], symptom="机器异响")
        confirmed, _ = post(other, active, "confirm_repair")
        assert confirmed.json()["result"]["ok"]
        assert len(confirmed.json()["snapshot"]["tickets"]) == 2
    with connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM devices WHERE company_name=%s", (expired_company,)).fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM devices WHERE company_name='示例企业甲'").fetchone()["n"] == 1
