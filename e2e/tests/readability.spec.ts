import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function token() {
  const configDir =
    process.env.WEFT_E2E_CONFIG_DIR ?? ".test-reports/e2e-config";
  const path = resolve(import.meta.dirname, "../..", configDir, "session.json");
  return JSON.parse(readFileSync(path, "utf8")).token as string;
}

test("US-SET-02/AC-2: primary UI is readable at 100 percent browser zoom", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("readable");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await page.locator(".weft-node strong").click();

  const fontSize = (locator: ReturnType<typeof page.locator>) =>
    locator.evaluate((element) =>
      Number.parseFloat(getComputedStyle(element).fontSize),
    );
  expect(await fontSize(page.locator("body"))).toBe(14);
  expect(await fontSize(page.locator(".node-heading strong"))).toBe(14);
  expect(await fontSize(page.locator(".node-search input").first())).toBe(14);
  await expect(page.locator(".weft-node")).toHaveCSS("width", "220px");
  expect(
    await page
      .locator(".node-search")
      .first()
      .evaluate((element) => {
        return element.getBoundingClientRect().height;
      }),
  ).toBeGreaterThanOrEqual(32);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
