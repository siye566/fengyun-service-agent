import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/service-preview');
  await expect(
    page.getByRole('heading', { name: '与 Agent 一起处理售后需求' }),
  ).toBeVisible();
  await page.getByLabel('筛选演示企业').selectOption('all');
});

test('overview, scoped data and business navigation render without runtime errors', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.getByLabel('筛选演示企业').selectOption('示例企业乙');
  await page.screenshot({
    path: testInfo.outputPath('service-overview.png'),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByLabel('筛选演示企业').selectOption('示例企业丙');
  await expect(
    page.getByRole('heading', { name: '峰云售后 Agent' }),
  ).toBeVisible();
  await expect(
    page
      .getByText('示例企业甲', { exact: true })
      .filter({ visible: true }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: '设备台账', exact: true }).click();
  await expect(page.getByRole('heading', { name: '7 号空压机' })).toBeVisible();
  await page.getByRole('button', { name: '保养计划', exact: true }).click();
  await expect(page.getByText('161 天后到期')).toBeVisible();
  await expect(page.getByText('自动保养提醒 · 规划中')).toBeVisible();
  await page.getByRole('button', { name: '处理记录', exact: true }).click();
  await expect(
    page.getByText('示例处理结果：接头检修后恢复正常。'),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test('Agent separates compound tasks, preserves a waiting repair, and creates a linked ticket only after review', async ({
  page,
}, testInfo) => {
  const writes: string[] = [];
  page.on('request', (request) => {
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method()))
      writes.push(request.url());
  });
  await page.getByLabel('筛选演示企业').selectOption('示例企业乙');
  await page.getByRole('button', { name: /报修，同时查进度/ }).click();
  const tasks = page.getByRole('complementary', { name: 'Agent 当前任务' });
  await expect(tasks.getByText('2 项 · 1 项待确认')).toBeVisible();
  await expect(
    page.getByRole('log').getByText(/查询到 1 条示例记录/),
  ).toBeVisible();
  await page.getByRole('button', { name: '报修与工单', exact: true }).click();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByRole('button', { name: 'Agent 工作台', exact: true }).click();
  await page.getByLabel('Agent 设备选择').selectOption('DEMO-GR75-0002');
  await page.getByRole('button', { name: '确认设备', exact: true }).click();
  await page
    .getByLabel('Agent 故障补充')
    .fill('今天上午开始间歇性异响，无报警代码');
  // An independent query must not take the repair's device or fault fields.
  await page.getByLabel('发送给售后 Agent 的需求').fill('查一下现有工单进度');
  await page.getByRole('button', { name: '发送需求', exact: true }).click();
  await tasks.getByRole('button', { name: /故障报修/ }).click();
  await expect(page.getByLabel('Agent 故障补充')).toHaveValue(
    '今天上午开始间歇性异响，无报警代码',
  );
  await page
    .getByRole('button', { name: '生成报修确认信息', exact: true })
    .click();
  await expect(page.getByTestId('agent-action')).toContainText('DEMO-GR75-0002');
  await page.screenshot({
    path: testInfo.outputPath('agent-confirmation.png'),
    fullPage: true,
  });
  await page
    .getByRole('button', { name: '确认生成演示工单', exact: true })
    .click();
  await expect(tasks.getByText('3 项 · 0 项待确认')).toBeVisible();
  await expect(page.getByTestId('agent-action')).toHaveCount(0);
  await page
    .getByRole('log')
    .getByRole('button', { name: /今天上午开始间歇性异响/ })
    .click();
  await expect(
    page.getByRole('dialog').getByText('Agent 报修信息已确认（演示）'),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '报修与工单', exact: true }).click();
  await expect(page.locator('tbody tr')).toHaveCount(2);
  expect(writes).toEqual([]);
});

test('Agent handoff freezes only its task and maintenance returns a device-bound result', async ({
  page,
}) => {
  await page.getByLabel('筛选演示企业').selectOption('示例企业甲');
  await page.getByRole('button', { name: /报修，同时查进度/ }).click();
  await page.getByLabel('Agent 设备选择').selectOption('DEMO-GR75-0001');
  await page.getByRole('button', { name: '确认设备', exact: true }).click();
  await page.getByLabel('Agent 故障补充').fill('有间歇性异响，需要人工核实');
  await page.getByRole('button', { name: '转人工接手（演示）' }).click();
  const tasks = page.getByRole('complementary', { name: 'Agent 当前任务' });
  await expect(tasks.getByText('交接摘要', { exact: true })).toBeVisible();
  await expect(
    tasks.getByText('故障：有间歇性异响，需要人工核实', { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId('agent-action')).toHaveCount(0);
  await page.getByLabel('发送给售后 Agent 的需求').fill('查一下保养周期');
  await page.getByRole('button', { name: '发送需求', exact: true }).click();
  await page.getByLabel('Agent 设备选择').selectOption('DEMO-GR75-0001');
  await page.getByRole('button', { name: '确认设备', exact: true }).click();
  await expect(
    page.getByRole('log').getByText(/示例保养查询结果/),
  ).toContainText('5 天后到达保养周期');
  await tasks.getByRole('button', { name: /故障报修/ }).click();
  await expect(tasks.getByText('交接摘要', { exact: true })).toBeVisible();
  await expect(page.getByTestId('agent-action')).toHaveCount(0);
});

test('Agent scope changes reset the conversation and negated input never starts repair execution', async ({
  page,
}) => {
  await expect(
    page.getByRole('button', { name: '发送需求', exact: true }),
  ).toBeDisabled();
  await page.getByLabel('筛选演示企业').selectOption('示例企业乙');
  await page.getByRole('button', { name: /报修，同时查进度/ }).click();
  await page.getByLabel('Agent 设备选择').selectOption('DEMO-GR75-0002');
  await page.getByLabel('筛选演示企业').selectOption('示例企业丙');
  await expect(
    page.getByRole('log').getByText(/本地演示将这条消息/),
  ).toHaveCount(0);
  await expect(page.getByText('等待第一条需求', { exact: true })).toBeVisible();
  await page
    .getByLabel('发送给售后 Agent 的需求')
    .fill('不要报修，先找人工核实');
  await page.getByRole('button', { name: '发送需求', exact: true }).click();
  await expect(
    page.getByRole('log').getByText(/没有执行业务操作/),
  ).toBeVisible();
  await expect(page.getByLabel('Agent 设备选择')).toHaveCount(0);
  await page.getByRole('button', { name: '报修与工单', exact: true }).click();
  await expect(page.locator('tbody tr')).toHaveCount(1);
});

test('repair validation, detail, duplicate prevention and reset do not write to the backend', async ({
  page,
}) => {
  const writes: string[] = [];
  page.on('request', (request) => {
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method()))
      writes.push(request.url());
  });
  await page.getByRole('button', { name: '新建报修', exact: true }).click();
  const save = page.getByRole('button', { name: '生成演示报修' });
  await expect(save).toBeDisabled();
  await page.getByLabel('选择报修设备').selectOption('DEMO-GR75-0001');
  await page
    .getByLabel('故障描述', { exact: true })
    .fill('测试：运行时出现间歇性异响');
  await expect(save).toBeDisabled();
  await page.getByRole('checkbox').check();
  await save.click();
  await expect(
    page
      .getByRole('dialog')
      .getByRole('heading', { name: '测试：运行时出现间歇性异响' }),
  ).toBeVisible();
  await expect(
    page.getByRole('dialog').getByText('待处理', { exact: true }),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '新建报修', exact: true }).click();
  await page.getByLabel('选择报修设备').selectOption('DEMO-GR75-0001');
  await page
    .getByLabel('故障描述', { exact: true })
    .fill('测试：运行时出现间歇性异响');
  await page.getByRole('checkbox').check();
  await save.click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('status')).toContainText('已有相同的未完成报修');
  await page.getByRole('button', { name: '报修与工单', exact: true }).click();
  await page.getByLabel('搜索工单').fill('测试：运行时出现间歇性异响');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.reload();
  await page.getByRole('button', { name: '报修与工单', exact: true }).click();
  await page.getByLabel('搜索工单').fill('测试：运行时出现间歇性异响');
  await expect(page.getByText('没有找到匹配的工单')).toBeVisible();
  expect(writes).toEqual([]);
});

test('confirmation updates the intended record, and filters and device entry stay scoped', async ({
  page,
}) => {
  await page.getByRole('button', { name: '报修与工单', exact: true }).click();
  await page.getByLabel('工单状态', { exact: true }).selectOption('待确认');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page
    .getByRole('button', { name: '运行时出现异响，需要协助排查', exact: true })
    .click();
  await page.getByRole('button', { name: '确认是这台设备' }).click();
  await expect(
    page.getByRole('dialog').getByText('待处理', { exact: true }),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByText('没有找到匹配的工单')).toBeVisible();
  await page.getByRole('button', { name: '清除筛选' }).click();
  await expect(page.locator('tbody tr')).toHaveCount(4);
  await page.getByLabel('筛选演示企业').selectOption('示例企业乙');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByRole('button', { name: '设备台账', exact: true }).click();
  await page.getByRole('button', { name: '为此设备报修' }).click();
  await expect(page.getByLabel('选择报修设备')).toHaveValue('DEMO-GR75-0002');
  await expect(page.getByLabel('选择报修设备').locator('option')).toHaveCount(
    2,
  );
  await page.keyboard.press('Escape');
  await page.getByLabel('筛选演示企业').selectOption('示例企业丙');
  await page.getByRole('button', { name: '新建报修', exact: true }).click();
  await expect(page.getByLabel('选择报修设备')).toHaveValue('');
  await expect(page.getByRole('checkbox')).not.toBeChecked();
});
