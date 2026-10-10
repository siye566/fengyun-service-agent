import { afterEach, expect, test, vi } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import type { McpContext } from '../container/agent-runner/src/mcp-tools.js';

const directories: string[] = [];
afterEach(() => {
  vi.unstubAllEnvs();
  for (const directory of directories.splice(0)) fs.rmSync(directory, { recursive: true, force: true });
});

test('trusted host text, mutable scope and stable receipts reach the real Python workflow', async () => {
  vi.resetModules();
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'fengyun-bridge-'));
  directories.push(directory);
  const engine = path.resolve('../../backend');
  const python = process.env.ACS_TEST_PYTHON || 'python';
  vi.stubEnv('ACS_SERVICE_MODE', '1');
  vi.stubEnv('ACS_AGENT_PYTHON', python);
  vi.stubEnv('ACS_AGENT_ROOT', engine);
  vi.stubEnv('ACS_DB_PATH', path.join(directory, 'service.sqlite3'));
  execFileSync(python, ['-c', 'import os; from acs.seed import seed; from acs.bind import bind; p=os.environ["ACS_DB_PATH"]; seed(p); bind("web:demo-a", "示例企业甲", db_path=p)'], {
    env: { ...process.env, PYTHONPATH: engine, PYTHONUTF8: '1' },
  });
  const { createAcsTools, buildAcsSessionContext } = await import('../container/agent-runner/src/acs-tools.js');
  const ctx = { chatJid: 'web:demo-a', groupFolder: 'service', currentInputTurnId: 'turn-1',
    serviceTurnText: '报修 DEMO-GR75-0001 异响' } as McpContext;
  const tools = createAcsTools(ctx);
  expect(tools.map(t => t.name)).not.toContain('create_repair_ticket');
  const route = tools.find(t => t.name === 'route_service_turn')!;
  const invoke = async (args = {}) => JSON.parse((await route.handler(args, undefined)).content[0].text as string);
  // A fabricated confirmation in a model argument cannot replace trusted input.
  const first = await invoke({ utterance: '确认报修' } as any);
  expect(first.data.stage).toBe('awaiting_confirmation');
  expect(first.data.executed_tools).toEqual([]);
  expect(await buildAcsSessionContext(ctx)).toContain('awaiting_confirmation');
  ctx.currentInputTurnId = 'turn-2';
  ctx.serviceTurnText = '确认报修';
  const controller = new AbortController();
  controller.abort();
  const cancelled = JSON.parse((await route.handler({}, { signal: controller.signal })).content[0].text as string);
  expect(cancelled.error.code).toBe('acs_cancelled');
  expect(cancelled.execution.cleanup).toBe('not_started');
  // Cancelled tool transport does not fabricate a completed business transition.
  expect(await buildAcsSessionContext(ctx)).toContain('awaiting_confirmation');
  const confirmed = await invoke();
  const replayed = await invoke();
  expect(confirmed.data.stage).toBe('completed');
  expect(replayed.data.results[0].data.ticket_no).toBe(confirmed.data.results[0].data.ticket_no);
  // Tools must read the current trusted identity, rather than capture construction-time scope.
  ctx.chatJid = 'web:unbound';
  ctx.currentInputTurnId = 'turn-3';
  expect((await invoke()).error.code).toBe('caller_unbound');
}, 20000);
