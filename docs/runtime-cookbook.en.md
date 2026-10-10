# Controlled tool runs, persistent sessions and failure recovery

This is an executable Agent Runtime / developer-experience example, not a sandbox SDK
integration, arbitrary-code endpoint or full security sandbox. The registered domain
tools run as trusted Python code, under the same OS user as the parent process.

## First run

Prerequisites: Node 22.18+ and Python 3.10+. From the repository root:

```sh
python examples/demo_service.py
node --experimental-strip-types examples/runtime_lab.mts
node --experimental-strip-types --test vendor/miniclaw/tests/acs-execution.test.mts
```

If needed, set `ACS_AGENT_PYTHON` (lab) or `ACS_TEST_PYTHON` (tests) to your Python
executable. The lab creates and deletes only its own temporary synthetic database.
No LLM, model key, container daemon, vendor account or external message is involved.

## Architecture

```text
Trusted host input / identity / event ID
  → Pi tool adapter (AbortSignal in handler extra)
  → service tool bridge
  → controlled execution helper (one ephemeral Run per call)
  → Python CLI → business checks → SQLite session / task / receipt
  ← validated JSON envelope + execution metadata
```

A Session is durable business state; a Run is a single execution attempt. Cancelling
a Run is not an instruction to delete the Session. Run events are currently in memory
and returned/logged as metadata; they are not a durable distributed execution ledger.

The lab reuses the same helper as the registered service bridge. Normal workflow calls
use real Python/SQLite. Timeout and cancellation use fixed host-only Node canaries to
inject failures deterministically. Those probes are not registered Agent tools and do
not prove a production crash occurred halfway through a database commit.

## Six observable lab outcomes

| Check | Expected result |
| --- | --- |
| Repair request | Business stage remains `awaiting_confirmation`. |
| Slow read | Run is `timed_out`; worker close is observed before `cleanup=exited`. |
| Cancelled read | AbortSignal stops the direct worker and reports `cancelled`. |
| Interrupted write probe | Return `acs_outcome_unknown`, not a safe automatic-retry suggestion. |
| Context after failed Runs | Original pending repair still exists. |
| Replayed confirmation | Same stable receipt; database contains one ticket. |

## Execution contract and defaults

- Registered tool names only; no shell command or user program parameter.
- Caller scope and database path are host options, not model-generated arguments.
- Direct argv invocation, `shell=false`, explicit backend working directory.
- Default deadline: 30 seconds. Default combined stdout/stderr budget: 64 KiB.
- Transport input budget: 16 KiB. Stdout is buffered only within the output budget.
- Minimal child environment rather than copying all parent variables. This avoids
  propagating parent model API keys but is **not a credential-security sandbox**: a
  same-user process still has OS filesystem/network permissions and can read files.
- Pi's AbortSignal is propagated through handler extra. An already-aborted call does
  not start a worker. A started worker is killed on timeout/cancellation/output excess.
- Completion waits for direct-worker `close`, or reports `cleanup=unconfirmed` after
  a bounded grace period. Do not infer that an unconfirmed process has exited.
- A valid envelope preserves domain `ok/data/error`; raw stderr is not model evidence.

Run states: `completed`, `failed`, `timed_out`, `cancelled`.
`completed` means this tool call returned a successful envelope, **not that the work
order is closed**. `outcome=unknown` means the bridge cannot certify a write's side
effect from its receipt. `known` on an interrupted read does not mean its query succeeded.

Metadata includes Run ID, tool, ordered event sequence, elapsed time, byte counts and
cleanup status. It excludes arguments, caller identity, raw stderr and business result
contents. Timings are observations, not a launch-performance benchmark.

## Failure and recovery

| Code | Developer action |
| --- | --- |
| `acs_tool_forbidden` | Select a registered domain tool. Do not turn this bridge into a shell endpoint. |
| `acs_bad_args` / `acs_bad_policy` | Fix the call contract or host policy before starting a process. |
| `acs_engine_unreachable` | Check host Python and backend paths. No worker startup is claimed. |
| `acs_timeout` / `acs_cancelled` | Inspect state and cleanup metadata. A read can be resumed intentionally. |
| `acs_output_limit` | Reduce the result or fix the tool; do not silently truncate JSON and infer success. |
| `acs_bad_output` / `acs_engine_exit` | Inspect private worker diagnostics. Invalid output is not evidence. |
| `acs_outcome_unknown` | First read the original task/receipt and current ticket state. Do not blindly create a new task or replay a write. |

The helper performs no automatic retry. It does **not** yet persist an uncertain-write
lock that blocks a later independent caller. A production controller should durably
freeze unresolved side effects and reconcile them before accepting further writes.
The current route's stable event/task keys protect the existing confirmation workflow,
but do not establish exactly-once behavior for every legacy write tool.

## Security and lifecycle boundaries

This change does not implement CPU/memory/disk quotas, network denial, a separate OS
user, container/microVM isolation, descendant-tree termination or sandbox escape tests.
A malicious Python worker is outside the threat model. Killing the parent process can
leave a child; there is no durable process reconciler yet. OS isolation for untrusted
code is a separate future boundary, not another name for these application controls.

## A 90-minute developer challenge approach

1. Define one user's success criterion and failure boundary before adding infrastructure.
2. Run the minimal workflow and reproduce one failure with a synthetic input.
3. Implement the smallest change in the real call chain, not a separate mock product.
4. Test normal, timeout, cancellation and ambiguous write outcomes.
5. Give a new developer exact commands, expected output and an actionable error.
6. End with demonstrated behavior, unverified assumptions and the next risk to address.

This is a preparation exercise based on a developer-oriented role, not a claim about
any company's actual interview question, user activation rate or production outcome.
