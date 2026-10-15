import { test, expect } from "@playwright/test";

test("real PostgreSQL repair, read-only detour, reload persistence and visitor isolation", async ({
  page,
  browser,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/experience");
  await expect(page.getByLabel("报修设备")).toBeVisible();
  await page.getByLabel("故障现象").fill("机器异响");
  await page.getByRole("button", { name: "核对报修信息" }).click();
  await expect(
    page.getByRole("button", { name: "确认提交报修" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "查工单进度", exact: true }).click();
  await expect(
    page.getByRole("log").getByText("当前体验空间还没有工单。"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "确认提交报修" }),
  ).toBeEnabled();
  await page.screenshot({
    path: info.outputPath("postgres-web-confirmation.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(
    page.getByRole("button", { name: "确认提交报修" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "确认提交报修" }).click();
  await expect(page.getByText("报修已受理，可在工单页查看")).toBeVisible();
  await page.getByRole("button", { name: /报修工单/ }).click();
  await expect(page.locator(".live-ticket")).toHaveCount(1);
  await page.reload();
  await page.getByRole("button", { name: /报修工单/ }).click();
  await expect(page.locator(".live-ticket")).toHaveCount(1);
  await page.screenshot({
    path: info.outputPath("postgres-web-ticket.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const other = await browser.newContext();
  const second = await other.newPage();
  await second.goto(
    (process.env.ACS_LIVE_URL ?? "http://127.0.0.1:8080") + "/experience",
  );
  await second.getByRole("button", { name: /报修工单/ }).click();
  await expect(second.getByText("还没有工单", { exact: true })).toBeVisible();
  await other.close();
  expect(errors).toEqual([]);
});
