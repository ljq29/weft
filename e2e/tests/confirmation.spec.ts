import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function token() {
  const path = resolve(
    import.meta.dirname,
    "../..",
    process.env.WEFT_E2E_CONFIG_DIR ?? ".test-reports/e2e-config",
    "session.json",
  );
  return JSON.parse(readFileSync(path, "utf8")).token as string;
}

test("US-AGT-12/AC-4: confirmation card shows tool, editable args and decisions", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("confirmation");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await page.getByRole("button", { name: "运行", exact: true }).click();
  await expect(page.locator(".status-executed")).toHaveCount(1);
  await page.getByRole("button", { name: "历史", exact: true }).click();
  const history = page
    .locator(".history-panel button")
    .filter({ hasText: /r_\d/ });
  const text = await history.textContent();
  const runId = text?.match(/r_[A-Za-z0-9_]+/)?.[0];
  expect(runId).toBeTruthy();

  await page.route("**/api/runs/*/confirm", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ resolved: true }),
    });
  });
  await page.evaluate((id) => {
    window.dispatchEvent(
      new CustomEvent("weft-chat", {
        detail: {
          event: "node.confirm_request",
          data: {
            event: "node.confirm_request",
            run_id: id,
            request_id: "request-e2e",
            node_id: "n_agent",
            tool: "write",
            args: { path: "original.txt", content: "safe" },
          },
        },
      }),
    );
  }, runId);

  const card = page.getByRole("alertdialog", { name: "工具调用确认" });
  await expect(card).toBeVisible();
  await expect(card.getByRole("heading")).toContainText("确认调用 write");
  await expect(card.getByRole("button", { name: "拒绝" })).toBeVisible();
  await card
    .getByLabel("确认参数")
    .fill(JSON.stringify({ path: "approved.txt", content: "safe" }));
  const request = page.waitForRequest((item) =>
    item.url().endsWith(`/api/runs/${runId}/confirm`),
  );
  await card.getByRole("button", { name: "批准" }).click();
  expect((await request).postDataJSON()).toEqual({
    request_id: "request-e2e",
    decision: "approve",
    modified_args: { path: "approved.txt", content: "safe" },
  });
  await expect(card).toHaveCount(0);
});
