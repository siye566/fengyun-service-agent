/** Controlled tool subprocesses, not an OS sandbox or arbitrary-code endpoint. */
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';
import { performance } from 'node:perf_hooks';

export type AcsEnvelope = {
  ok: boolean;
  data?: Record<string, unknown>;
  error?: { code: string; message: string; action: string };
};
export type RunState = 'completed' | 'failed' | 'timed_out' | 'cancelled';
export type ExecutionEvent = { seq: number; type: string; elapsedMs: number };
export type ExecutionRecord = {
  runId: string; tool: string; state: RunState;
  outcome: 'known' | 'unknown'; cleanup: 'not_started' | 'exited' | 'unconfirmed';
  elapsedMs: number; stdoutBytes: number; stderrBytes: number;
  events: ExecutionEvent[];
};

const READ_TOOLS = new Set(['build_service_context', 'query_maintenance', 'query_ticket_status', 'list_company_tickets', 'query_part_requests']);
const WRITE_TOOLS = new Set(['route_service_turn', 'create_repair_ticket', 'scan_maintenance_due', 'submit_part_request', 'decide_part_request']);

export interface AcsExecutionOptions {
  python: string;
  backendRoot: string;
  scope: string;
  dbPath?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  outputLimitBytes?: number;
  cleanupGraceMs?: number;
  /** Host-only injection seam for deterministic fault tests; never a model argument. */
  spawnProcess?: (command: string, args: string[], options: Parameters<typeof spawn>[2]) => ChildProcessWithoutNullStreams;
}

function fail(code: string, message: string, action: string): AcsEnvelope {
  return { ok: false, error: { code, message, action } };
}
function validEnvelope(value: unknown): value is AcsEnvelope {
  if (!value || typeof value !== 'object') return false;
  const v = value as AcsEnvelope;
  if (v.ok === true) return !!v.data && typeof v.data === 'object' && !Array.isArray(v.data);
  return v.ok === false && !!v.error && ['code', 'message', 'action'].every(k => typeof (v.error as any)[k] === 'string');
}

/** No parent API keys, model config or credential-store paths are copied into the child env. */
export function toolEnvironment(root: string, dbPath?: string): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const key of ['PATH', 'Path', 'SystemRoot', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL']) {
    if (process.env[key]) env[key] = process.env[key];
  }
  env.PYTHONPATH = resolve(root);
  env.PYTHONUTF8 = '1';
  env.PYTHONIOENCODING = 'utf-8';
  if (dbPath) env.ACS_DB_PATH = resolve(dbPath);
  return env;
}

export async function executeAcsTool(tool: string, args: Record<string, unknown>, options: AcsExecutionOptions): Promise<{ envelope: AcsEnvelope; execution: ExecutionRecord }> {
  const startedAt = performance.now();
  const events: ExecutionEvent[] = [];
  const event = (type: string) => events.push({ seq: events.length + 1, type, elapsedMs: Math.round(performance.now() - startedAt) });
  const runId = randomUUID();
  event('requested');
  const immediate = (envelope: AcsEnvelope, state: RunState = 'failed') => {
    event(state);
    return { envelope, execution: { runId, tool, state, outcome: 'known' as const, cleanup: 'not_started' as const,
      elapsedMs: Math.round(performance.now() - startedAt), stdoutBytes: 0, stderrBytes: 0, events } };
  };
  if (!READ_TOOLS.has(tool) && !WRITE_TOOLS.has(tool)) return immediate(fail('acs_tool_forbidden', 'Tool is not in the service registry.', 'Use a registered domain tool; shell/code execution is not available.'));
  if (!args || typeof args !== 'object' || Array.isArray(args) || ['scope_key', 'db_path'].some(k => k in args)) return immediate(fail('acs_bad_args', 'Invalid arguments or injected host scope.', 'Caller identity and database location must be supplied by the host, not tool arguments.'));
  const timeoutMs = options.timeoutMs ?? 30_000;
  const outputLimit = options.outputLimitBytes ?? 65_536;
  const graceMs = options.cleanupGraceMs ?? 1_000;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || !Number.isInteger(outputLimit) || outputLimit < 128 || !Number.isFinite(graceMs) || graceMs <= 0) return immediate(fail('acs_bad_policy', 'Invalid execution policy.', 'Use positive deadlines and an output cap of at least 128 bytes.'));
  let input: string;
  try { input = JSON.stringify(args); }
  catch { return immediate(fail('acs_bad_args', 'Arguments cannot be encoded as JSON.', 'Use JSON-compatible tool arguments.')); }
  if (typeof input !== 'string') return immediate(fail('acs_bad_args', 'Arguments cannot be encoded as JSON.', 'Use a plain JSON argument object.'));
  if (Buffer.byteLength(input, 'utf8') > 16_384) return immediate(fail('acs_bad_args', 'Arguments exceed the transport budget.', 'Shorten tool input; do not send entire documents through this bridge.'));
  if (options.signal?.aborted) return immediate(fail('acs_cancelled', 'Cancelled before tool startup.', 'No process was started.'), 'cancelled');

  return new Promise(resolveResult => {
    let child: ChildProcessWithoutNullStreams;
    let settled = false, spawned = false;
    let stdoutBytes = 0, stderrBytes = 0;
    const stdout: Buffer[] = [];
    let reason: 'timeout' | 'cancel' | 'output' | 'stdin' | undefined;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    let cleanupDeadline: ReturnType<typeof setTimeout> | undefined;
    const elapsed = () => Math.round(performance.now() - startedAt);
    const finish = (envelope: AcsEnvelope, state: RunState, cleanup: ExecutionRecord['cleanup'], uncertain = false) => {
      if (settled) return;
      settled = true;
      clearTimeout(deadline); clearTimeout(cleanupDeadline);
      options.signal?.removeEventListener('abort', abort);
      event(state);
      resolveResult({ envelope, execution: { runId, tool, state, outcome: uncertain ? 'unknown' : 'known', cleanup,
        elapsedMs: elapsed(), stdoutBytes, stderrBytes, events } });
    };
    const interruption = (cleanup: ExecutionRecord['cleanup']) => {
      const state: RunState = reason === 'timeout' ? 'timed_out' : reason === 'cancel' ? 'cancelled' : 'failed';
      const uncertain = spawned && WRITE_TOOLS.has(tool);
      const code = uncertain ? 'acs_outcome_unknown' : reason === 'timeout' ? 'acs_timeout' : reason === 'cancel' ? 'acs_cancelled' : reason === 'output' ? 'acs_output_limit' : 'acs_input_failed';
      finish(fail(code, uncertain ? 'The process stopped without a definitive write receipt.' : 'Tool execution was interrupted.',
        uncertain ? 'Do not blindly retry. Read current task/ticket state and its stable receipt before resuming the original operation.' : 'Inspect the execution record. Retrying a read does not authorize a write.'), state, cleanup, uncertain);
    };
    const stop = (why: NonNullable<typeof reason>) => {
      if (settled || reason) return;
      reason = why;
      event('stop_requested:' + why);
      // Kill only this controlled worker. Descendant-tree termination is not promised.
      try { child.kill('SIGKILL'); } catch { /* The close event remains authoritative. */ }
      cleanupDeadline = setTimeout(() => interruption('unconfirmed'), graceMs);
    };
    const abort = () => stop('cancel');
    try {
      const launcher = options.spawnProcess ?? ((command, argv, settings) => spawn(command, argv, settings) as ChildProcessWithoutNullStreams);
      child = launcher(options.python, ['-m', 'acs.cli', tool, options.scope], {
        cwd: resolve(options.backendRoot), env: toolEnvironment(options.backendRoot, options.dbPath),
        stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true, shell: false,
      });
    } catch {
      finish(fail('acs_engine_unreachable', 'Could not start the service worker.', 'Check the host-configured Python interpreter and backend directory.'), 'failed', 'not_started');
      return;
    }
    child.once('spawn', () => { spawned = true; event('started'); });
    child.stdout.on('data', (chunk: Buffer) => {
      if (settled) return;
      stdoutBytes += chunk.length;
      if (stdoutBytes + stderrBytes > outputLimit) stop('output');
      else if (!reason) stdout.push(chunk);
    });
    child.stderr.on('data', (chunk: Buffer) => {
      if (settled) return;
      stderrBytes += chunk.length;
      if (stdoutBytes + stderrBytes > outputLimit) stop('output');
      // Count stderr, but never expose raw diagnostic text as tool evidence.
    });
    child.stdin.on('error', () => stop('stdin'));
    child.once('error', () => {
      if (spawned) { stop('stdin'); return; }
      finish(fail('acs_engine_unreachable', 'Could not start the service worker.', 'Check the host-configured Python interpreter and backend directory.'), 'failed', 'not_started');
    });
    child.once('close', code => {
      if (settled) return;
      event('worker_closed');
      if (reason) { interruption('exited'); return; }
      const uncertain = spawned && WRITE_TOOLS.has(tool);
      if (code !== 0) {
        finish(fail(uncertain ? 'acs_outcome_unknown' : 'acs_engine_exit', 'The worker exited without a successful protocol receipt.', uncertain ? 'Read the original task/receipt before any write retry.' : 'Inspect the worker and retry only the intended read.'), 'failed', 'exited', uncertain);
        return;
      }
      let parsed: unknown;
      try { parsed = JSON.parse(Buffer.concat(stdout).toString('utf8')); }
      catch { /* Invalid output is not trusted evidence. */ }
      if (!validEnvelope(parsed)) {
        finish(fail(uncertain ? 'acs_outcome_unknown' : 'acs_bad_output', 'The worker returned an invalid result envelope.', uncertain ? 'Read the original task/receipt before any write retry.' : 'Fix the tool protocol; do not infer success from stdout.'), 'failed', 'exited', uncertain);
        return;
      }
      finish(parsed, parsed.ok ? 'completed' : 'failed', 'exited');
    });
    options.signal?.addEventListener('abort', abort, { once: true });
    deadline = setTimeout(() => stop('timeout'), timeoutMs);
    if (options.signal?.aborted) abort();
    child.stdin.end(input);
  });
}
