// Reproduce documentation screenshots against the running local preview.
import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const output = path.join(root, 'docs/screenshots');
fs.mkdirSync(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
    : {}),
});
let page = await browser.newPage({ viewport: { width: 1440, height: 1120 }, deviceScaleFactor: 1 });
const errors = [];
const warnings = [];
page.on('pageerror', error => {
  // The UI-only preview does not run a backend WebSocket server.
  if (error.message === 'WebSocket closed without opened.') warnings.push(error.message);
  else errors.push(error.message);
});
const screenshot = async name => {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(output, name), fullPage: true, animations: 'disabled' });
};
try {
  await page.goto(`${process.env.SERVICE_PREVIEW_URL || 'http://127.0.0.1:5187'}/service-preview`);
  await page.getByRole('heading', { name: '与 Agent 一起处理售后需求' }).waitFor();
  await page.getByLabel('筛选演示企业').selectOption('示例企业乙');
  await screenshot('workbench.png');
  await page.getByRole('button', { name: /报修，同时查进度/ }).click();
  await page.getByLabel('Agent 设备选择').selectOption('DEMO-GR75-0002');
  await page.getByRole('button', { name: '确认设备', exact: true }).click();
  await page.getByLabel('Agent 故障补充').fill('今天上午开始间歇性异响，无报警代码');
  await page.getByRole('button', { name: '生成报修确认信息', exact: true }).click();
  await page.getByTestId('agent-action').waitFor();
  await page.setViewportSize({ width: 1440, height: 1320 });
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.querySelector('.fy-service')?.scrollTo(0, 0);
  });
  await screenshot('repair-confirmation.png');
  await page.getByLabel('筛选演示企业').selectOption('all');
  await page.getByRole('button', { name: '设备台账', exact: true }).click();
  await page.getByRole('heading', { name: '2 号空压机' }).waitFor();
  await page.setViewportSize({ width: 1440, height: 930 });
  await screenshot('device-maintenance.png');
  await page.getByRole('button', { name: '保养计划', exact: true }).click();
  await page.getByText('自动保养提醒 · 规划中').waitFor();
  await page.setViewportSize({ width: 1440, height: 1120 });
  await screenshot('maintenance-plan.png');

  // Present the actual CLI stdout in a clearly labelled documentation viewer.
  const stdout = execFileSync(process.env.ACS_CAPTURE_PYTHON || 'python', [
    path.join(root, 'acs-agent/scripts/demo_service.py'),
  ], { encoding: 'utf8', env: { ...process.env, PYTHONUTF8: '1' } });
  const runs = JSON.parse(`[${stdout.trim().replace(/\n}\s*\n{/g, '\n},{')}]`);
  const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
  const cards = runs.map((run, index) => {
    const data = run.result.data;
    const result = JSON.stringify({ stage: data.stage, executed_tools: data.executed_tools,
      clarification: data.clarification, results: data.results }, null, 2);
    return `<article><span class="step">0${index + 1}</span><h2>${escape(run.input)}</h2><span class="state">${escape(data.stage)}</span><pre>${escape(result)}</pre></article>`;
  }).join('');
  page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  await page.setContent(`<!doctype html><meta charset="utf-8"><style>
    *{box-sizing:border-box}body{margin:0;padding:52px;background:#f3f7fa;color:#182b36;font-family:"Microsoft YaHei",sans-serif}
    .eyebrow{font-size:14px;color:#187b70;letter-spacing:2px}h1{font-size:34px;margin:12px 0}p{color:#607483;font-size:16px;line-height:1.8}
    main{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:30px}article{background:white;border:1px solid #dce7ec;border-radius:16px;padding:24px}
    .step{font-size:26px;color:#187b70;font-weight:700}h2{font-size:18px;min-height:50px}.state{display:inline-block;border-radius:8px;background:#e3f3ed;padding:8px 12px;font-size:13px;color:#187b70}
    pre{font-family:Consolas,"Microsoft YaHei",monospace;font-size:12px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fa;border-radius:10px;padding:14px;color:#354b58}
    footer{margin-top:28px;font-size:13px;color:#617582}
  </style><div class="eyebrow">ACTUAL CLI EXECUTION · TEMPORARY SQLITE</div><h1>后端报修流程 · 实际运行记录</h1>
  <p>同一次真实 Python 演示运行的 stdout，整理为可读视图。等待确认 → 独立查询 → 确认建单。<br>未调用模型，未发送飞书消息；这是运行记录视图，不是后台产品界面。</p>
  <main>${cards}</main><footer>执行入口：python scripts/demo_service.py · 数据：示例企业与 DEMO 设备 · 临时数据库退出后清理</footer>`);
  await screenshot('backend-workflow.png');
  if (errors.length) throw new Error(errors.join('\n'));
  console.log(JSON.stringify({ screenshots: fs.readdirSync(output), browserErrors: errors.length, previewWarnings: warnings }));
} finally {
  await browser.close();
}
