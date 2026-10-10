# Disposable report execution with BoxLite

Status: **optional SDK integration spike**, not a production arbitrary-code service.
The service workflow remains unchanged. No model key or cloud account is needed.

## Why a sandbox here?

Future agents might generate ad hoc reporting or conversion code. Running that code in
the same process as the work-order database would expose credentials and host files.
This spike demonstrates a separate execution boundary with synthetic data, before
considering a model-facing code tool.

The current example accepts **only three fixed, small programs**. It does not accept
user scripts or model-generated programs. `SimpleBox.exec()` buffers output; clipping
returned strings is not a streaming memory limit. An arbitrary-code endpoint needs a
bounded streaming collector, workload quotas and stronger lifecycle reconciliation.

## Prerequisites

- Python 3.10+.
- Linux with accessible `/dev/kvm`, or Apple Silicon macOS per the pinned SDK docs.
- A virtual environment with `boxlite==0.10.5`.
- Host network access for the first OCI image pull (`python:3.12-slim`).

The SDK used here is the **local OSS runtime**, not BoxLite Cloud. The Cloud's image
aliases and account lifecycle are a different onboarding path. On Windows, use a
supported Linux environment and verify KVM access; do not assume any WSL2 instance
automatically supplies nested virtualization.

```sh
python -m venv .venv
# Activate the virtualenv using your shell's command.
python -m pip install -r requirements-sandbox.txt
python examples/boxlite_report.py --doctor
python examples/boxlite_report.py --scenario report
python examples/boxlite_report.py --scenario crash
python examples/boxlite_report.py --scenario timeout --timeout-seconds 1
```

`--doctor` is read-only: it does not pull an image, create a VM or call a cloud API.
Failure scenarios exit nonzero intentionally. Do not treat them as successful report runs.

## Data flow and policy

1. Run the existing repair-confirmation workflow using a disposable synthetic database.
2. Export only `is_demo`, workflow stage, created-ticket count and a human-review note.
3. Create a fresh box with one CPU, 256 MiB memory, no guest network, mounts, ports or secrets.
4. Execute Python directly (no shell interpolation), as UID/GID 65534 in `/tmp`.
5. Return JSON output as data. It cannot approve, edit or close a work order.
6. Stop the started box in `finally`; `auto_remove=True` requests SDK cleanup.

The guest never receives a database path, business credential, real customer document
or host workspace mount. The first image download happens on the host; disabled guest
networking is not a promise that the host runtime can operate offline on a cold cache.

## Result/error contract

The output includes `ok`, backend, scenario, exit code/output when available, stage
timings and cleanup status. Timings are per-run observations, **not a startup benchmark**.

| Code | Recovery |
| --- | --- |
| `PREREQUISITE_FAILED` | Fix the failed doctor check; never fall back to executing on the host. |
| `STARTUP_FAILED` / `STARTUP_TIMEOUT` | Check SDK installation, image access, native logs and virtualization. Startup deadline is 60 seconds; a cold image pull may exceed it. |
| `SCRIPT_EXIT_NONZERO` | Fix the report program and run a fresh box. |
| `EXECUTION_TIMEOUT` | Fix slow code; execution has SDK and host watchdog deadlines. |
| `EXECUTION_FAILED` | Inspect private native diagnostics. SDK-reported abnormal exits may use this code, including SDK timeout diagnostics. |
| `CLEANUP_FAILED` | Inspect the local runtime and remove remaining resources before retrying. |

If startup fails before `start()` returns, cleanup is `not_started`, **not proof that no
partial resource was allocated**. Inspect the runtime after an interrupted creation.
The demo is not resilient to a killed host process, and does not implement a reconciler,
multi-user admission limits, disk/output quotas, image digest pinning or escape testing.

## Verification levels

Normal CI runs test doubles for SDK options, argv, execution errors and cleanup.
It does not start a microVM. To verify on a supported host, save the SDK version,
doctor output, successful report, crash/timeout output and cleanup observations.
Do not claim hardware isolation or measured launch speed from passing mock tests.

## Product feedback to investigate

- Can users distinguish an image-pull failure from unavailable virtualization?
- Does an interrupted startup leave a resource that developers must reconcile?
- Do timeout results have a stable machine-readable code across SDK versions?
- Is first-run latency dominated by an uncached image? Separate cold and warm runs.

These are investigation questions, not confirmed upstream bugs. Use only synthetic
reproductions; no upstream issue is automatically filed by this demo.

API references: [BoxLite v0.10.5 Python SDK](https://github.com/boxlite-ai/boxlite/blob/v0.10.5/docs/reference/python/README.md),
[SimpleBox implementation](https://github.com/boxlite-ai/boxlite/blob/v0.10.5/sdks/python/boxlite/simplebox.py).
