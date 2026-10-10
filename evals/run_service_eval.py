"""Offline end-to-end business contracts, real PostgreSQL, no provider credentials."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acs.bind import bind
from acs.db import connect
from acs.seed import seed
from acs.testing import temporary_database
from acs.service import route_service_turn


def evaluate():
    dataset = json.loads((ROOT / "evals/service_cases.json").read_text(encoding="utf-8"))
    results = []
    for case in dataset["cases"]:
        failures = []
        with temporary_database() as db:
            seed(db, reset=True)
            bind("web:demo-a", "示例企业甲", db_url=db)
            for index, turn in enumerate(case["turns"]):
                result = route_service_turn(turn["text"], case["id"], turn.get("event_id", str(index)),
                                            turn.get("parsed"), case.get("scope", "web:demo-a"), db)
                if "error" in turn:
                    if result.get("ok") or result.get("error", {}).get("code") != turn["error"]:
                        failures.append(f"turn {index}: wrong error")
                elif not result["ok"]: failures.append(f"turn {index}: {result['error']['code']}")
                else:
                    data = result["data"]
                    for field, expected in (("stage", turn["stage"]), ("intents", turn["intents"]),
                                            ("executed_tools", turn["allowed_tools"])):
                        if data[field] != expected: failures.append(f"turn {index}: wrong {field}")
                    if bool(data["clarification"]) != turn["clarify"]: failures.append(f"turn {index}: wrong clarification")
            conn = connect(db)
            count = conn.execute("SELECT COUNT(*) AS n FROM tickets").fetchone()["n"]
            conn.close()
            if count != case["tickets"]: failures.append(f"tickets {count}, expected {case['tickets']}")
        results.append({"id": case["id"], "passed": not failures, "failures": failures})
    return {"version": dataset["version"], "storage": "PostgreSQL", "scope": "offline business workflow; not model accuracy or channel delivery",
            "passed": sum(r["passed"] for r in results), "total": len(results), "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] == report["total"] else 1)
