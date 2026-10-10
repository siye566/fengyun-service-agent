"""PostgreSQL migration regressions: rollback, isolation and concurrent writes."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from acs.db import connect, database_url, initialize
from acs.seed import seed
from acs.testing import temporary_database
from acs.tools import create_repair_ticket, decide_part_request, submit_part_request


def test_file_database_is_rejected():
    with pytest.raises(ValueError, match="PostgreSQL"):
        database_url("local.db")


def test_schema_isolation_and_initialization_are_repeatable():
    with temporary_database() as first, temporary_database() as second:
        seed(first)
        initialize(first)
        with connect(first) as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM devices").fetchone()["n"] == 3
        with connect(second) as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM devices").fetchone()["n"] == 0


def test_uncommitted_write_is_rolled_back_on_close():
    with temporary_database() as url:
        seed(url)
        conn = connect(url)
        conn.execute("UPDATE parts SET stock=0 WHERE part_no=%s", ("P-BELT-75",))
        conn.close()
        with connect(url) as reader:
            assert reader.execute("SELECT stock FROM parts WHERE part_no=%s", ("P-BELT-75",)).fetchone()["stock"] == 12


def test_concurrent_different_repairs_have_unique_ticket_numbers():
    with temporary_database() as url:
        seed(url)
        def create(number):
            return create_repair_ticket("示例企业甲", "DEMO-GR75-0001", "异响",
                                        scope_key="web:main", db_url=url,
                                        idempotency_key=f"parallel-{number}")
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(create, range(4)))
        assert all(result["ok"] for result in results)
        assert len({result["data"]["ticket_no"] for result in results}) == 4


def test_concurrent_approval_cannot_deduct_stock_twice():
    with temporary_database() as url:
        seed(url)
        ticket = create_repair_ticket("示例企业甲", "DEMO-GR75-0001", "异响", scope_key="web:main", db_url=url)
        request = submit_part_request(ticket["data"]["ticket_no"], "P-BELT-75", 2, scope_key="web:main", db_url=url)
        def approve(_):
            return decide_part_request(request["data"]["request_no"], "approve", scope_key="web:main", db_url=url)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(approve, range(2)))
        assert sum(result["ok"] for result in results) == 1
        assert next(result for result in results if not result["ok"])["error"]["code"] == "already_decided"
        with connect(url) as conn:
            assert conn.execute("SELECT stock FROM parts WHERE part_no=%s", ("P-BELT-75",)).fetchone()["stock"] == 10
