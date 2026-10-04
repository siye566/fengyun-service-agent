import json
import pytest
from acs.bind import bind
from acs.db import connect
from acs.seed import seed
from acs.service import route_service_turn, trusted_session_key
from acs.context import build_service_context


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "service.sqlite3")
    seed(path, reset=True)
    bind("web:demo-a", "示例企业甲", db_path=path)
    return path


def test_business_benchmark_contracts():
    from evals.run_service_eval import evaluate
    report = evaluate()
    assert report["passed"] == report["total"], report


def test_state_restored_and_query_does_not_replace_repair(db):
    first = route_service_turn("报修 DEMO-GR75-0001 异响", "s", "1", scope_key="web:demo-a", db_path=db)
    second = route_service_turn("查工单进度", "s", "2", scope_key="web:demo-a", db_path=db)
    assert second["data"]["pending"] == first["data"]["pending"]
    context = build_service_context("s", "web:demo-a", db)
    assert context["data"]["phase"] == "awaiting_confirmation"
    assert all(segment["sha256"] for segment in context["data"]["audit"])
    assert "示例企业乙" not in json.dumps(context, ensure_ascii=False)


def test_rebinding_cannot_resume_or_retrieve_old_task(db):
    route_service_turn("报修 DEMO-GR75-0001 异响", "s", "1", scope_key="web:demo-a", db_path=db)
    bind("web:demo-a", "示例企业乙", db_path=db)
    result = route_service_turn("确认报修", "s", "2", scope_key="web:demo-a", db_path=db)
    assert result["error"]["code"] == "confirmation_not_ready"
    context = build_service_context("s", "web:demo-a", db)
    assert "DEMO-GR75-0001" not in json.dumps(context, ensure_ascii=False)


def test_essential_context_hard_limit_blocks(db):
    conn = connect(db)
    key = trusted_session_key(conn, "web:demo-a", "s")
    state = {"stage": "awaiting_confirmation", "pending": {"symptom": "异响" * 2000}}
    conn.execute("INSERT INTO service_sessions VALUES(?,?,?)", (key, json.dumps(state), "demo"))
    conn.commit(); conn.close()
    result = build_service_context("s", "web:demo-a", db)
    assert result["error"]["code"] == "context_budget_exceeded"


def test_crash_recovery_uses_stable_business_key(db):
    from acs.tools import create_repair_ticket
    first = route_service_turn("报修 DEMO-GR75-0001 异响", "s", "1", scope_key="web:demo-a", db_path=db)
    pending = first["data"]["pending"]
    # Simulate the ticket committed but the workflow receipt was not yet saved.
    created = create_repair_ticket("示例企业甲", pending["device_serial"], pending["symptom"],
                                  scope_key="web:demo-a", db_path=db, idempotency_key=pending["task_key"])
    restored = route_service_turn("确认报修", "s", "2", scope_key="web:demo-a", db_path=db)
    assert restored["data"]["results"][0]["data"]["ticket_no"] == created["data"]["ticket_no"]
    conn = connect(db)
    assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 1
    conn.close()


def test_concurrent_duplicate_confirmation_creates_one_ticket(db):
    from concurrent.futures import ThreadPoolExecutor
    route_service_turn("报修 DEMO-GR75-0001 异响", "s", "1", scope_key="web:demo-a", db_path=db)
    def confirm():
        return route_service_turn("确认报修", "s", "2", scope_key="web:demo-a", db_path=db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: confirm(), range(2)))
    assert all(r["ok"] for r in results)
    assert results[0] == results[1]
    conn = connect(db)
    assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 1
    conn.close()


def test_model_cannot_supply_scope_and_missing_receipt_fails_closed(db):
    invalid = route_service_turn("报修", "s", "1", {"intents": ["repair"], "scope_key": "web:main"}, "web:demo-a", db)
    assert invalid["error"]["code"] == "invalid_candidates"
    missing = route_service_turn("报修", scope_key="web:demo-a", db_path=db)
    assert missing["error"]["code"] == "missing_event_id"
