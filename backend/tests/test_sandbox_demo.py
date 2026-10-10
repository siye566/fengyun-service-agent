"""Contract tests with test doubles; these do not start or benchmark a microVM."""
import asyncio
from types import SimpleNamespace
import pytest
from examples.boxlite_report import run_report, synthetic_snapshot


class FakeBox:
    def __init__(self, outcome="success", stop_fails=False):
        self.outcome, self.stop_fails = outcome, stop_fails
        self.started = self.stopped = False
    async def start(self):
        if self.outcome == "startup": raise RuntimeError("private-path")
        self.started = True
    async def exec(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs
        if self.outcome == "timeout": raise asyncio.TimeoutError()
        if self.outcome == "execution": raise RuntimeError("secret")
        return SimpleNamespace(exit_code=1 if self.outcome == "crash" else 0,
                               stdout="{}", stderr="synthetic" if self.outcome == "crash" else "",
                               error_message="private SDK diagnostic" if self.outcome == "sdk_error" else None)
    async def stop(self):
        if self.stop_fails: raise RuntimeError("cleanup")
        self.stopped = True


def invoke(fake, scenario="report"):
    captured = {}
    def factory(**options):
        captured.update(options)
        return fake
    return asyncio.run(run_report(scenario, box_factory=factory)), captured


def test_snapshot_is_synthetic_and_read_only():
    snapshot = synthetic_snapshot()
    assert snapshot["is_demo"] and snapshot["workflow_stage"] == "completed"
    assert snapshot["created_tickets"] == 1
    assert set(snapshot) == {"is_demo", "workflow_stage", "created_tickets", "review_note"}


def test_success_has_explicit_policy_and_cleanup():
    fake = FakeBox()
    result, options = invoke(fake)
    assert result["ok"] and result["backend"] == "test_double"
    assert result["cleanup"] == "stopped" and fake.stopped
    assert options["network"] == {"mode": "disabled"}
    assert options["volumes"] == options["ports"] == options["secrets"] == []
    assert options["cpus"] == 1 and options["memory_mib"] == 256 and options["auto_remove"]
    assert fake.kwargs == {"user": "65534:65534", "cwd": "/tmp", "timeout": 5}
    assert fake.args[0] == "python" and fake.args[1] == "-c"


@pytest.mark.parametrize("outcome,code", [("crash", "SCRIPT_EXIT_NONZERO"), ("timeout", "EXECUTION_TIMEOUT"), ("execution", "EXECUTION_FAILED")])
def test_execution_failure_stops_box(outcome, code):
    fake = FakeBox(outcome)
    result, _ = invoke(fake)
    assert not result["ok"] and result["error"]["code"] == code
    assert fake.stopped
    assert "secret" not in str(result)


def test_startup_failure_is_not_claimed_cleaned():
    result, _ = invoke(FakeBox("startup"))
    assert result["cleanup"] == "not_started"
    assert result["error"]["code"] == "STARTUP_FAILED"
    assert "private-path" not in str(result)


def test_cleanup_failure_is_visible_not_success():
    result, _ = invoke(FakeBox(stop_fails=True))
    assert not result["ok"] and result["cleanup"] == "failed"
    assert result["error"]["code"] == "CLEANUP_FAILED"


def test_no_arbitrary_programs_or_unbounded_deadline():
    for scenario, deadline in [("shell", 5), ("report", 0), ("report", 31)]:
        with pytest.raises(ValueError): asyncio.run(run_report(scenario, deadline, box_factory=FakeBox))


def test_constructor_failure_returns_structured_error():
    def factory(**options): raise RuntimeError("private native install path")
    result = asyncio.run(run_report(box_factory=factory))
    assert not result["ok"] and result["error"]["code"] == "STARTUP_FAILED"
    assert "private native" not in str(result)


def test_sdk_diagnostic_is_not_misreported_as_success_or_leaked():
    fake = FakeBox("sdk_error")
    result, _ = invoke(fake)
    assert not result["ok"] and result["error"]["code"] == "EXECUTION_FAILED"
    assert fake.stopped and "private SDK diagnostic" not in str(result)
