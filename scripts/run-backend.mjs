// Root commands work without activating a shell-specific Python environment.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const venv = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const python = process.env.ACS_AGENT_PYTHON || (existsSync(venv) ? venv : 'python');
const commands = {
  demo: ['examples/demo_service.py'],
  test: ['-m', 'pytest', '-q'],
  eval: ['evals/run_service_eval.py', '--output', 'evals/reports/service.json'],
};
const command = commands[process.argv[2]];
if (!command) {
  console.error('Usage: node scripts/run-backend.mjs demo|test|eval');
  process.exit(2);
}
const child = spawn(python, [...command, ...process.argv.slice(3)], {
  cwd: root,
  stdio: 'inherit',
  windowsHide: true,
  env: {
    ...process.env,
    PYTHONUTF8: '1',
    PYTHONPATH: [path.join(root, 'backend'), root, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
  },
});
child.on('error', error => {
  console.error(`无法启动 Python：${error.message}。请创建根目录 .venv 或设置 ACS_AGENT_PYTHON。`);
  process.exitCode = 1;
});
child.on('exit', code => { process.exitCode = code ?? 1; });
