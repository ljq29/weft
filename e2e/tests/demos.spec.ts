import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function token() {
  const configDir = process.env.WEFT_E2E_CONFIG_DIR ?? ".test-reports/e2e-config";
  const path = resolve(import.meta.dirname, "../..", configDir, "session.json");
  return JSON.parse(readFileSync(path, "utf8")).token as string;
}

async function createDemo(
  page: import("@playwright/test").Page,
  title: string,
  name: string,
  parent: string,
) {
  page.on("response", (response) => {
    if (response.status() >= 400)
      console.log("HTTP", response.status(), response.url());
  });
  page.on("pageerror", (error) => console.error(error));
  await page.goto(`/?token=${token()}`);
  await page.getByRole("button", { name: "示例工作流" }).click();
  const dialog = page.getByRole("dialog", { name: "示例工作流" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".demo-card")).toHaveCount(3);
  await dialog.getByRole("button", { name: new RegExp(title) }).click();
  await dialog.getByLabel("示例名称").fill(name);
  await dialog.getByLabel("示例父目录").fill(parent);
  await dialog.getByRole("button", { name: "创建并打开" }).click();
  await expect(dialog).toHaveCount(0);
}

test("US-DES-01/AC-4: CSV demo runs with bundled data and writes output", async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000);
  await createDemo(page, "CSV 销售汇总", "csv-demo", testInfo.outputPath());
  await expect(page.locator(".weft-node")).toHaveCount(5);
  await page.getByRole("button", { name: "运行", exact: true }).click();
  await expect(page.locator(".status-executed")).toHaveCount(5, {
    timeout: 90_000,
  });
  const output = readFileSync(
    resolve(testInfo.outputPath(), "csv-demo.weft/out/regional-sales.csv"),
    "utf8",
  );
  expect(output).toContain("region,total_amount");
  expect(output).toContain("华东");
  expect(output).toContain("华南");
});

test("US-DES-01/AC-4: table demo calculates and previews grouped results", async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000);
  await createDemo(page, "表格计算与预览", "table-demo", testInfo.outputPath());
  await expect(page.locator(".weft-node")).toHaveCount(5);
  await page.getByRole("button", { name: "运行", exact: true }).click();
  await expect(page.locator(".status-executed")).toHaveCount(5, {
    timeout: 90_000,
  });
  await page
    .locator(".weft-node")
    .filter({ hasText: "预览汇总结果" })
    .getByRole("button", { name: "out", exact: true })
    .click();
  const preview = page.getByRole("dialog", { name: "端口预览" });
  await expect(preview).toBeVisible();
  await expect(preview).toContainText("共 2 行");
  await expect(preview).toContainText("sales_total");
});

test("US-DES-01/AC-4: LLM demo contains setup placeholders and no secret", async ({
  page,
}, testInfo) => {
  await createDemo(page, "LLM 文本处理", "llm-demo", testInfo.outputPath());
  await expect(page.locator(".weft-node")).toHaveCount(2);
  await expect(page.locator(".canvas-note")).toContainText("<YOUR_API_KEY>");
  await expect(page.locator(".canvas-note")).toContainText("demo");
});
