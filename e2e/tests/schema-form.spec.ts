import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function token() {
  const configDir =
    process.env.WEFT_E2E_CONFIG_DIR ?? ".test-reports/e2e-config";
  const path = resolve(import.meta.dirname, "../..", configDir, "session.json");
  return JSON.parse(readFileSync(path, "utf8")).token as string;
}

test("US-DES-04/AC-1,3: trigger and aggregation parameters use structured controls", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("structured-form");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await page.locator(".weft-node strong").click();

  await expect(
    page.getByLabel("manual.enabled", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "添加schedule.schedules项" }).click();
  await page
    .getByLabel("schedule.schedules[0].cron", { exact: true })
    .fill("0 9 * * 1-5");
  await expect(
    page.getByLabel("schedule.schedules[0].cron", { exact: true }),
  ).toHaveValue("0 9 * * 1-5");

  await page.getByRole("button", { name: /^GroupBy/ }).dblclick();
  const groupBy = page.locator(".weft-node").filter({ hasText: "GroupBy" });
  const bounds = await groupBy.boundingBox();
  if (!bounds) throw new Error("GroupBy node is not visible");
  await page.mouse.move(bounds.x + 80, bounds.y + 20);
  await page.mouse.down();
  await page.mouse.move(bounds.x + 360, bounds.y + 20, { steps: 8 });
  await page.mouse.up();
  await groupBy.locator("strong").click();
  await page.getByRole("button", { name: "添加aggregations *项" }).click();
  await page
    .getByLabel("aggregations[0].column *", { exact: true })
    .fill("amount");
  await page
    .getByLabel("aggregations[0].agg *", { exact: true })
    .selectOption("sum");
  await page.getByLabel("aggregations[0].alias", { exact: true }).fill("total");
  await expect(
    page.getByLabel("aggregations[0].alias", { exact: true }),
  ).toHaveValue("total");
});
