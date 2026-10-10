import { afterEach, expect, test, vi } from 'vitest';
import { randomUUID } from 'node:crypto';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import type { McpContext } from '../container/agent-runner/src/mcp-tools.js';

const schemas: { schema: string; python: string; engine: string }[] = [];
afterEach(() => {
  vi.unstubAllEnvs();
  for (const { schema, python, engine } of schemas.splice(0)) {
    execFileSync(python, ['-c', 'import sys,psycopg; from psycopg import sql; from acs.db import database_url; c=psycopg.connect(database_url(),autocommit=True); c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(sys.argv[1]))); c.close()', schema], {
      env: { ...process.env, PYTHONPATH: engine, PYTHONUTF8: '1' }, windowsHide: true,
    });
  }
});

test('trusted host text, mutable scope and stable receipts reach the real Python workflow', async () => {
  vi.resetModules();
  const engine = path.resolve('../../backend');
  const venv = path.resolve('../../.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const python = process.env.ACS_TEST_PYTHON || (existsSync(venv) ? venv : 'python');
  const schema = `acs_bridge_${randomUUID().replaceAll('-', '')}`;
  execFileSync(python, ['-c', 'import sys,psycopg; from psycopg import sql; from acs.db import database_url; c=psycopg.connect(database_url(),autocommit=True); c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(sys.argv[1]))); c.close()', schema], {
    env: { ...process.env, PYTHONPATH: engine, PYTHONUTF8: '1' }, windowsHide: true,
  });
  schemas.push({ schema, python, engine });
  vi.stubEnv('ACS_SERVICE_MODE', '1');
  vi.stubEnv('ACS_AGENT_PYTHON', python);
  vi.stubEnv('ACS_AGENT_ROOT', engine);
  vi.stubEnv('ACS_DB_SCHEMA', schema);
  execFileSync(python, ['-c', 'from acs.seed import seed; from acs.bind import bind; seed(); bind("web:demo-a", "示例企业甲")'], {
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
  const confirmed = await invoke();
  const replayed = await invoke();
  expect(confirmed.data.stage).toBe('completed');
  expect(replayed.data.results[0].data.ticket_no).toBe(confirmed.data.results[0].data.ticket_no);
  // Tools must read the current trusted identity, rather than capture construction-time scope.
  ctx.chatJid = 'web:unbound';
  ctx.currentInputTurnId = 'turn-3';
  expect((await invoke()).error.code).toBe('caller_unbound');
}, 20000);
