/** Credential-free lab using the same execution helper as the Pi service bridge. */
import { spawn, execFileSync, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { executeAcsTool, toolEnvironment, type AcsExecutionOptions } from '../vendor/miniclaw/container/agent-runner/src/acs-execution.ts';

const backendRoot = fileURLToPath(new URL('../backend', import.meta.url));
const python = process.env.ACS_AGENT_PYTHON || 'python';
const root = await mkdtemp(join(tmpdir(), 'fengyun-runtime-lab-'));
const dbPath = join(root, 'synthetic.sqlite3');
const options = { python, backendRoot, dbPath, scope: 'web:demo-a', timeoutMs: 5000 };
const reports: { name: string; pass: boolean; record?: unknown }[] = [];
const probe = (code: string): AcsExecutionOptions['spawnProcess'] => (_command, _args, settings) => spawn(process.execPath, ['-e', code], settings) as ChildProcessWithoutNullStreams;

try {
  execFileSync(python, ['-c', 'import os; from acs.seed import seed; from acs.bind import bind; p=os.environ["ACS_DB_PATH"]; seed(p); bind("web:demo-a", "示例企业甲", db_path=p)'], { env: toolEnvironment(backendRoot, dbPath) });
  const request = await executeAcsTool('route_service_turn', { utterance: '报修 DEMO-GR75-0001 异响', session_id: 'lab', event_id: 'request' }, options);
  reports.push({ name: 'repair_waits_for_confirmation', pass: request.envelope.data?.stage === 'awaiting_confirmation', record: request.execution });

  // Fixed host-only probes inject failures; these are not agent-selected shell tools.
  const timeout = await executeAcsTool('list_company_tickets', {}, { ...options, timeoutMs: 100, spawnProcess: probe('setTimeout(()=>{},60000)') });
  reports.push({ name: 'read_timeout_observes_worker_exit', pass: timeout.execution.state === 'timed_out' && timeout.execution.cleanup === 'exited', record: timeout.execution });
  const controller = new AbortController();
  const cancellation = setTimeout(() => controller.abort(), 100);
  const cancelled = await executeAcsTool('list_company_tickets', {}, { ...options, signal: controller.signal, spawnProcess: probe('setTimeout(()=>{},60000)') });
  clearTimeout(cancellation);
  reports.push({ name: 'cancellation_stops_worker', pass: cancelled.execution.state === 'cancelled' && cancelled.execution.cleanup === 'exited', record: cancelled.execution });

  const uncertain = await executeAcsTool('route_service_turn', {}, { ...options, timeoutMs: 100, spawnProcess: probe('setTimeout(()=>{},60000)') });
  reports.push({ name: 'write_interruption_is_not_safe_to_retry', pass: uncertain.envelope.error?.code === 'acs_outcome_unknown', record: uncertain.execution });
  const context = await executeAcsTool('build_service_context', { session_id: 'lab' }, options);
  reports.push({ name: 'pending_session_survives_failed_runs', pass: context.envelope.data?.phase === 'awaiting_confirmation', record: context.execution });

  const input = { utterance: '确认报修', session_id: 'lab', event_id: 'confirm' };
  const created = await executeAcsTool('route_service_turn', input, options);
  const replay = await executeAcsTool('route_service_turn', input, options);
  const count = execFileSync(python, ['-c', 'import os,sqlite3; c=sqlite3.connect(os.environ["ACS_DB_PATH"]); print(c.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]); c.close()'], { env: toolEnvironment(backendRoot, dbPath), encoding: 'utf8' }).trim();
  reports.push({ name: 'stable_receipt_prevents_duplicate_ticket', pass: created.envelope.data?.stage === 'completed' && JSON.stringify(created.envelope) === JSON.stringify(replay.envelope) && count === '1', record: replay.execution });
  console.log(JSON.stringify({ scope: 'Synthetic workflow and real controlled subprocesses; not an LLM or OS sandbox benchmark.', passed: reports.filter(r => r.pass).length, total: reports.length, reports }, null, 2));
  if (reports.some(r => !r.pass)) process.exitCode = 1;
} catch {
  console.error(JSON.stringify({ ok: false, error: 'LAB_SETUP_OR_EXECUTION_FAILED', action: 'Check Node 22.18+, Python 3.10+, ACS_AGENT_PYTHON and local filesystem permissions.' }));
  process.exitCode = 1;
} finally {
  // Only the exact synthetic directory created above is removed.
  await rm(root, { recursive: true, force: true });
}
