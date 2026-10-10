"""Opt-in BoxLite SDK spike: disposable execution of fixed, synthetic report code.

This is NOT an arbitrary-code tool, an LLM demo, or a replacement for business ACLs.
SimpleBox buffers output, so only the small programs below are accepted. Unit tests
inject a test double; only the default CLI path starts a real microVM.
"""
import argparse
import asyncio
import importlib.metadata
import json
import os
import platform
import sys
import time
from pathlib import Path

SDK_VERSION = "0.10.5"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def doctor():
    """Read-only prerequisites check; does not install, pull an image or create a VM."""
    checks = [{"name": "python", "ok": sys.version_info >= (3, 10), "action": "Use Python 3.10+."}]
    supported = platform.system() == "Linux" or (platform.system() == "Darwin" and platform.machine() == "arm64")
    checks.append({"name": "host", "ok": supported,
                   "action": "Use Linux with accessible /dev/kvm or Apple Silicon macOS. On Windows, use a Linux environment with KVM; do not assume WSL2 exposes it."})
    if platform.system() == "Linux":
        checks.append({"name": "kvm", "ok": os.access("/dev/kvm", os.R_OK | os.W_OK),
                       "action": "Check virtualization support and permission to /dev/kvm."})
    try:
        version = importlib.metadata.version("boxlite")
        from boxlite import SimpleBox, NetworkSpec  # noqa: F401 - verify native SDK symbols
        sdk_ok = version == SDK_VERSION
    except (ImportError, importlib.metadata.PackageNotFoundError):
        version, sdk_ok = None, False
    checks.append({"name": "sdk", "ok": sdk_ok, "version": version,
                   "action": "In a supported environment, install requirements-sandbox.txt in a virtualenv."})
    return {"ok": all(c["ok"] for c in checks), "mode": "local", "checks": checks,
            "note": "Passing prerequisites is not proof that image pull or VM startup works. No cloud API is called."}


def synthetic_snapshot():
    """Exercise the real workflow, then export an allowlisted synthetic summary."""
    import tempfile
    from acs.seed import seed
    from acs.bind import bind
    from acs.service import route_service_turn
    with tempfile.TemporaryDirectory() as directory:
        db = str(Path(directory) / "demo.sqlite3")
        seed(db)
        bind("web:demo-a", "示例企业甲", db_path=db)
        for event, text in enumerate(["报修 DEMO-GR75-0001 异响", "确认报修"], 1):
            result = route_service_turn(text, "sandbox-demo", str(event), scope_key="web:demo-a", db_path=db)
            if not result["ok"]:
                raise RuntimeError("Synthetic workflow did not complete")
        return {"is_demo": True, "workflow_stage": result["data"]["stage"],
                "created_tickets": len(result["data"]["results"]),
                "review_note": "A human engineer must diagnose the machine. This report cannot approve or close a ticket."}


def program(scenario, snapshot):
    if scenario == "report":
        # JSON is an argv value, not interpolated into Python or a shell command.
        return "import json,sys; d=json.loads(sys.argv[1]); print(json.dumps({'report': d, 'authority': 'read_only_demo'}))"
    if scenario == "crash":
        return "raise RuntimeError('synthetic report failure')"
    if scenario == "timeout":
        return "import time; time.sleep(60)"
    raise ValueError("Only report, crash and timeout scenarios are supported")


async def run_report(scenario="report", timeout_seconds=5, box_factory=None):
    if scenario not in ("report", "crash", "timeout") or not 1 <= timeout_seconds <= 30:
        raise ValueError("Use an allowed scenario and a timeout from 1 to 30 seconds")
    backend = "test_double" if box_factory is not None else "boxlite"
    if box_factory is None:
        from boxlite import SimpleBox, NetworkSpec
        box_factory = SimpleBox
        network = NetworkSpec(mode="disabled")
    else:
        # Test representation, never passed to the native SDK.
        network = {"mode": "disabled"}
    snapshot = synthetic_snapshot()
    response = {"ok": False, "backend": backend, "scenario": scenario,
                "cleanup": "not_started", "timings_ms": {}}
    started, phase = False, "startup"
    tick = time.monotonic()
    try:
        box = box_factory(image="python:3.12-slim", cpus=1, memory_mib=256,
                          auto_remove=True, network=network, volumes=[], ports=[], secrets=[])
        await asyncio.wait_for(box.start(), timeout=60)
        started = True
        response["timings_ms"]["startup"] = round((time.monotonic() - tick) * 1000)
        phase, tick = "execution", time.monotonic()
        result = await asyncio.wait_for(
            box.exec("python", "-c", program(scenario, snapshot), json.dumps(snapshot),
                     user="65534:65534", cwd="/tmp", timeout=timeout_seconds),
            timeout=timeout_seconds + 2)
        response["timings_ms"]["execution"] = round((time.monotonic() - tick) * 1000)
        response.update(exit_code=result.exit_code, stdout=result.stdout[:8192], stderr=result.stderr[:8192])
        if result.error_message:
            response["error"] = {"code": "EXECUTION_FAILED", "action": "Inspect the SDK execution diagnostic locally; do not retry business writes."}
        elif result.exit_code != 0:
            response["error"] = {"code": "SCRIPT_EXIT_NONZERO", "action": "Fix the report program, then run it in a fresh box."}
        else:
            response["ok"] = True
    except (asyncio.TimeoutError, TimeoutError):
        response["error"] = {"code": "STARTUP_TIMEOUT" if phase == "startup" else "EXECUTION_TIMEOUT",
                             "action": "Check image cache/runtime for startup; fix slow report code for execution. No ticket writes are retried."}
    except Exception:
        # Do not include arbitrary exception strings: they may contain paths/secrets.
        response["error"] = {"code": "STARTUP_FAILED" if phase == "startup" else "EXECUTION_FAILED",
                             "action": "Run --doctor, then check the local SDK logs. No host-process fallback is allowed."}
    finally:
        if started:
            tick = time.monotonic()
            try:
                await asyncio.wait_for(box.stop(), timeout=10)
                response["cleanup"] = "stopped"
            except Exception:
                response["ok"] = False
                response["cleanup"] = "failed"
                response["error"] = {"code": "CLEANUP_FAILED", "action": "Inspect the local runtime and stop/remove the remaining box before retrying."}
            response["timings_ms"]["cleanup"] = round((time.monotonic() - tick) * 1000)
    return response


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--scenario", choices=["report", "crash", "timeout"], default="report")
    parser.add_argument("--timeout-seconds", type=int, choices=range(1, 31), default=5)
    args = parser.parse_args(argv)
    prerequisites = doctor()
    result = prerequisites if args.doctor else (
        asyncio.run(run_report(args.scenario, args.timeout_seconds)) if prerequisites["ok"] else
        {"ok": False, "error": {"code": "PREREQUISITE_FAILED", "action": "Resolve failed --doctor checks."}, "checks": prerequisites["checks"]})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
