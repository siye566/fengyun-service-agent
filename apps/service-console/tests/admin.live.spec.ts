import { test, expect } from "@playwright/test";

test("admin login, cross-customer history, Feishu settings and logout", async ({
  page,
  browser,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const guest = await browser.newContext();
  const customer = await guest.newPage();
  await customer.goto(
    (process.env.ACS_LIVE_URL ?? "http://127.0.0.1:8080") + "/experience",
  );
  await customer.getByLabel("故障现象").fill("机器异响");
  await customer.getByRole("button", { name: "核对报修信息" }).click();
  await expect(
    customer.getByRole("button", { name: "确认提交报修" }),
  ).toBeEnabled();
  const response = await guest.request.get(
    (process.env.ACS_LIVE_URL ?? "http://127.0.0.1:8080") + "/api/session",
  );
  const workspace = await response.json();
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "登录管理员工作台" }),
  ).toBeVisible();
  const denied = await page.request.get("/api/admin/conversations");
  expect(denied.status()).toBe(401);
  await page
    .getByLabel("管理员密码", { exact: true })
    .fill(process.env.ACS_ADMIN_TEST_PASSWORD!);
  await page.getByRole("button", { name: "进入管理工作台" }).click();
  await expect(
    page.getByRole("heading", { name: "客户会话", exact: true }),
  ).toBeVisible();
  await page.getByLabel("搜索客户会话").fill(workspace.company);
  await page.getByRole("button", { name: "提交搜索" }).click();
  await page
    .locator(".ops-conversation-item")
    .filter({ hasText: workspace.company })
    .click();
  await expect(page.getByRole("log", { name: "客户会话记录" })).toContainText(
    "机器异响",
  );
  await expect(page.locator(".ops-pending")).toContainText("等待客户确认");
  await page.screenshot({
    path: info.outputPath("admin-conversations.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "客户会话", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "飞书接入", exact: true }).click();
  await expect(page.getByLabel("App ID", { exact: true })).toBeVisible();
  await expect(page.getByLabel("App Secret", { exact: true })).toHaveAttribute(
    "type",
    "password",
  );
  await expect(
    page.getByRole("heading", { name: "让客户从飞书发起报修" }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("admin-feishu-settings.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  // Mobile has a compact header; logout stays accessible in a dedicated control.
  await page.getByRole("button", { name: "退出管理员" }).click();
  await expect(
    page.getByRole("heading", { name: "登录管理员工作台" }),
  ).toBeVisible();
  expect((await page.request.get("/api/admin/tickets")).status()).toBe(401);
  await guest.close();
  expect(errors).toEqual([]);
});
