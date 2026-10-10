import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn, execFileSync, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { executeAcsTool, toolEnvironment, type AcsExecutionOptions } from '../container/agent-runner/src/acs-execution.ts';

const backendRoot = fileURLToPath(new URL('../../../backend', import.meta.url));
const python = process.env.ACS_TEST_PYTHON || 'python';
const base = { python, backendRoot, scope: 'web:demo-a', timeoutMs: 5000 };
const probe = (code: string): AcsExecutionOptions['spawnProcess'] => (_command, _argv, options) => spawn(process.execPath, ['-e', code], options) as ChildProcessWithoutNullStreams;

async function fixture(t: test.TestContext) {
  const root = await mkdtemp(join(tmpdir(), 'acs-execution-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const dbPath = join(root, 'service.sqlite3');
  execFileSync(python, ['-c', 'import os; from acs.seed import seed; from acs.bind import bind; p=os.environ["ACS_DB_PATH"]; seed(p); bind("web:demo-a", "示例企业甲", db_path=p); bind("web:demo-b", "示例企业乙", db_path=p)'], { env: toolEnvironment(backendRoot, dbPath) });
  return { ...base, dbPath };
}

test('registry and host-scope injection fail before any process is started', async () => {
  const never = () => { throw new Error('must not spawn'); };
  const forbidden = await executeAcsTool('shell', {}, { ...base, spawnProcess: never });
  assert.equal(forbidden.envelope.error?.code, 'acs_tool_forbidden');
  const forged = await executeAcsTool('query_maintenance', { scope_key: 'web:admin' }, { ...base, spawnProcess: never });
  assert.equal(forged.envelope.error?.code, 'acs_bad_args');
  assert.equal(forged.execution.cleanup, 'not_started');
});

test('real Python worker keeps pending session across a read-only detour', async t => {
  const options = await fixture(t);
  const first = await executeAcsTool('route_service_turn', { utterance: '报修 DEMO-GR75-0001 异响', session_id: 'demo', event_id: 'one' }, options);
  assert.equal(first.envelope.data?.stage, 'awaiting_confirmation');
  await executeAcsTool('list_company_tickets', {}, options);
  const context = await executeAcsTool('build_service_context', { session_id: 'demo' }, options);
  assert.equal(context.envelope.data?.phase, 'awaiting_confirmation');
  assert.equal(context.execution.state, 'completed');
  assert.equal(context.execution.cleanup, 'exited');
  assert.notEqual(context.execution.runId, first.execution.runId);
  assert.deepEqual(context.execution.events.map(e => e.seq), [1, 2, 3, 4]);
  assert.equal(context.execution.events.at(-1)?.type, 'completed');
});

test('stable receipt replay creates only one real ticket across new worker processes', async t => {
  const options = await fixture(t);
  await executeAcsTool('route_service_turn', { utterance: '报修 DEMO-GR75-0001 异响', session_id: 'demo', event_id: 'one' }, options);
  const input = { utterance: '确认报修', session_id: 'demo', event_id: 'confirm' };
  const first = await executeAcsTool('route_service_turn', input, options);
  const replay = await executeAcsTool('route_service_turn', input, options);
  assert.equal(first.envelope.data?.stage, 'completed');
  assert.deepEqual(replay.envelope, first.envelope);
  const count = execFileSync(python, ['-c', 'import os,sqlite3; c=sqlite3.connect(os.environ["ACS_DB_PATH"]); print(c.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]); c.close()'], { env: toolEnvironment(backendRoot, options.dbPath), encoding: 'utf8' });
  assert.equal(count.trim(), '1');
});

test('parallel company queries retain independent host scopes', async t => {
  const options = await fixture(t);
  const [own, other] = await Promise.all([
    executeAcsTool('query_maintenance', { device_serial: 'DEMO-GR75-0001' }, options),
    executeAcsTool('query_maintenance', { device_serial: 'DEMO-GR75-0001' }, { ...options, scope: 'web:demo-b' }),
  ]);
  assert.equal(own.envelope.ok, true);
  assert.equal(other.envelope.error?.code, 'cross_company_denied');
  assert.equal(other.execution.outcome, 'known');
});

test('fake parent secret is absent from worker environment and execution metadata', async () => {
  const old = process.env.ACS_FAKE_TEST_SECRET;
  process.env.ACS_FAKE_TEST_SECRET = 'synthetic-not-a-real-key';
  try {
    const run = await executeAcsTool('list_company_tickets', {}, { ...base, spawnProcess: probe('console.log(JSON.stringify({ok:true,data:{secretVisible:!!process.env.ACS_FAKE_TEST_SECRET}}))') });
    assert.equal(run.envelope.data?.secretVisible, false);
    assert.ok(!JSON.stringify(run.execution).includes('synthetic-not-a-real-key'));
    assert.ok(!JSON.stringify(run.execution).includes('web:demo-a'));
  } finally {
    if (old === undefined) delete process.env.ACS_FAKE_TEST_SECRET; else process.env.ACS_FAKE_TEST_SECRET = old;
  }
});

test('read timeout observes worker close before reporting cleanup', async () => {
  const result = await executeAcsTool('list_company_tickets', {}, { ...base, timeoutMs: 100, spawnProcess: probe('setTimeout(()=>{},60000)') });
  assert.equal(result.envelope.error?.code, 'acs_timeout');
  assert.equal(result.execution.state, 'timed_out');
  assert.equal(result.execution.cleanup, 'exited');
  assert.ok(result.execution.events.some(e => e.type === 'worker_closed'));
});

test('AbortSignal stops an active worker; pre-aborted calls never spawn', async () => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 100);
  try {
    const result = await executeAcsTool('list_company_tickets', {}, { ...base, signal: controller.signal, spawnProcess: probe('setTimeout(()=>{},60000)') });
    assert.equal(result.execution.state, 'cancelled');
    assert.equal(result.execution.cleanup, 'exited');
  } finally { clearTimeout(timer); }
  const early = new AbortController(); early.abort();
  const result = await executeAcsTool('list_company_tickets', {}, { ...base, signal: early.signal, spawnProcess: () => { throw new Error('must not spawn'); } });
  assert.equal(result.execution.cleanup, 'not_started');
});

test('interrupted write is unknown, never represented as a safe automatic retry', async () => {
  const result = await executeAcsTool('route_service_turn', {}, { ...base, timeoutMs: 100, spawnProcess: probe('setTimeout(()=>{},60000)') });
  assert.equal(result.envelope.error?.code, 'acs_outcome_unknown');
  assert.equal(result.execution.outcome, 'unknown');
  assert.match(result.envelope.error!.action, /Do not blindly retry/);
});

for (const [label, code, expected] of [
  ['output limit', 'process.stdout.write("x".repeat(4096)); setTimeout(()=>{},60000)', 'acs_output_limit'],
  ['malformed envelope', 'console.log("not-json")', 'acs_bad_output'],
  ['nonzero exit', 'process.exit(7)', 'acs_engine_exit'],
] as const) {
  test(`failure contract: ${label}`, async () => {
    const result = await executeAcsTool('list_company_tickets', {}, { ...base, outputLimitBytes: 1024, spawnProcess: probe(code) });
    assert.equal(result.envelope.error?.code, expected);
    assert.equal(result.execution.cleanup, 'exited');
    assert.equal(result.execution.state, 'failed');
  });
}

test('failure to observe cleanup is explicit and does not mutate a returned trace later', async t => {
  let actualKill: (() => boolean) | undefined;
  const launcher: AcsExecutionOptions['spawnProcess'] = (_command, _argv, options) => {
    const child = spawn(process.execPath, ['-e', 'setTimeout(()=>{},60000)'], options) as ChildProcessWithoutNullStreams;
    const kill = child.kill.bind(child);
    actualKill = () => kill('SIGKILL');
    child.kill = () => false;
    t.after(() => actualKill?.());
    return child;
  };
  const run = await executeAcsTool('list_company_tickets', {}, { ...base, timeoutMs: 100, cleanupGraceMs: 30, spawnProcess: launcher });
  assert.equal(run.execution.cleanup, 'unconfirmed');
  const trace = JSON.stringify(run.execution);
  actualKill?.();
  await new Promise(resolve => setTimeout(resolve, 50));
  assert.equal(JSON.stringify(run.execution), trace);
});

test('invalid policy, missing interpreter and oversized inputs fail visibly', async () => {
  const invalid = await executeAcsTool('list_company_tickets', {}, { ...base, timeoutMs: -1 });
  assert.equal(invalid.envelope.error?.code, 'acs_bad_policy');
  const missing = await executeAcsTool('list_company_tickets', {}, { ...base, python: 'missing-fengyun-interpreter-20261010' });
  assert.equal(missing.envelope.error?.code, 'acs_engine_unreachable');
  assert.equal(missing.execution.cleanup, 'not_started');
  const huge = await executeAcsTool('list_company_tickets', { text: 'x'.repeat(20000) }, base);
  assert.equal(huge.envelope.error?.code, 'acs_bad_args');
});
