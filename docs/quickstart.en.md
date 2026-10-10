# First service workflow, without an API key

This guide runs the real Python workflow against disposable synthetic SQLite data.
It does **not** start an LLM, send Feishu messages, connect the frontend, or start an OS sandbox.

## 1. Check your environment

Use Python 3.10+. Run all commands from the repository root.
On Windows, replace `python` with the path to your working interpreter if needed.

```sh
python --version
python examples/demo_service.py
```

No package installation is required for this first demo. It uses Python's standard library.
The temporary database is deleted when the demo exits.

## 2. Recognize the result

The demo prints three JSON turns:

| Input | Expected stage | Why |
| --- | --- | --- |
| Repair request for `DEMO-GR75-0001` | `awaiting_confirmation` | The workflow collects the target and symptom; it does not silently create a ticket. |
| Query ticket progress | `awaiting_confirmation` | A read-only detour preserves the pending repair. |
| Confirm repair | `completed` | The original confirmation text authorizes the pending request. |

Inspect `result.data.executed_tools`, `clarification` and `results` in the output.
This demonstrates the offline rule baseline, not measured model classification accuracy.

## 3. Verify the safety contracts

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python evals/run_service_eval.py
```

The synthetic benchmark checks business state and allowed tool calls, including duplicate
confirmation, missing fields, negated requests and company boundaries. Passing it is not
proof of production delivery, dispatch scheduling or field diagnosis accuracy.

## 4. Understand the execution boundary

```text
Trusted caller binding → session state → candidate intent/entity extraction
                      → program checks → confirmation → transactional ticket tool
Tool call → controlled Python worker → result envelope + execution record
```

The database retains the business session between worker processes. The execution helper
controls deadlines, cancellation and output buffering; caller ownership and confirmation
gates control business actions. Neither is an OS security boundary.

With Node 22.18+ and Python 3.10+, run the same helper used by the Pi service bridge:

```sh
node --experimental-strip-types examples/runtime_lab.mts
node --experimental-strip-types --test vendor/miniclaw/tests/acs-execution.test.mts
```

If `python` is not the correct interpreter, set `ACS_AGENT_PYTHON` for the lab and
`ACS_TEST_PYTHON` for the tests to its executable path. No npm install or model key is
required for these commands. Expected lab summary: six checks pass, with ordered Run
events. See the [runtime failure cookbook](runtime-cookbook.en.md) for boundaries.

## When you get stuck

| Symptom | Next step |
| --- | --- |
| `ModuleNotFoundError: pytest` | Install `requirements-dev.txt` with the same interpreter used to run the tests. |
| `unbound`/identity rejection | Check the host binding; do not add a caller identity to model-generated tool arguments. The demo creates its own synthetic binding. |
| Missing/ambiguous target | Supply the actual device serial or ask for clarification. Do not guess an asset. |
| Context budget exceeded | Inspect segment byte budgets and sources. Keep mandatory rules/state; shorten optional history. This is not precise token accounting. |
| Repeated confirmation | Reuse the stable event ID for delivery retries. Business writes have a separate task key. |

## Developer-experience measurement plan

For a usability session, record locally: environment check, first workflow result, first
failure understood, and regression run. Time these steps and label environment failures
separately from API-contract failures. Collect only redacted error codes and versions;
do not upload chats, ticket data or credentials. No activation rate or ten-minute success
rate has been measured by this repository.
