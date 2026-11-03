import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function token() {
  const path = resolve(
    import.meta.dirname,
    "../../.test-reports/e2e-config/session.json",
  );
  return JSON.parse(readFileSync(path, "utf8")).token as string;
}

test.beforeEach(({ page }) => {
  page.on("pageerror", (error) => console.error(error));
  page.on("console", (message) => {
    if (message.type() === "error") console.error(message.text());
  });
});

test("US-DES-01/AC-1,3, US-DES-02/AC-1,4, US-DES-07/AC-1,2: create and save a workflow", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("e2e");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.getByText("Trigger", { exact: true })).toBeVisible();
  await expect(page.getByText("e2e", { exact: true })).toBeVisible();
  await page.getByLabel("搜索节点").fill("read");
  await expect(
    page.getByRole("button", { name: "Read CSV", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Trigger", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Read CSV", exact: true }).dblclick();
  await expect(
    page.locator(".weft-node").filter({ hasText: "Read CSV" }),
  ).toBeVisible();
  await expect(page.getByText("e2e *", { exact: true })).toBeVisible();
  await expect(page.getByText("e2e *", { exact: true })).toHaveCount(0, {
    timeout: 10_000,
  });
  await page.getByRole("button", { name: "Read CSV", exact: true }).dblclick();
  await expect(page.getByText("e2e *", { exact: true })).toBeVisible();
  await page.keyboard.press("Control+s");
  await expect(page.getByText("e2e *", { exact: true })).toHaveCount(0);
});

test("US-DES-08/AC-1,2, US-DES-11/AC-1,2: history and view navigation work", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("history");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await page.getByRole("button", { name: "Read CSV", exact: true }).dblclick();
  await expect(page.locator(".weft-node")).toHaveCount(2);
  await page.keyboard.press("Control+z");
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await page.keyboard.press("Control+y");
  await expect(page.locator(".weft-node")).toHaveCount(2);
  await page.locator(".weft-node").filter({ hasText: "Read CSV" }).click();
  await page.keyboard.press("Control+c");
  await page.keyboard.press("Control+v");
  await expect(page.locator(".weft-node")).toHaveCount(3);
  await page.keyboard.press("Shift+1");
  await page.keyboard.press("Shift+2");
  await expect(page.locator(".xyflow__viewport")).toHaveCSS(
    "transform",
    /matrix\(/,
  );
  await expect(page.locator(".react-flow__minimap")).toBeVisible();
});

test("US-DES-07/AC-3: save failure preserves dirty state and shows an error", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("failure");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await page.route("**/api/workflows/*", (route) => {
    if (route.request().method() === "PUT") return route.abort();
    return route.continue();
  });
  await page.getByRole("button", { name: "Read CSV", exact: true }).dblclick();
  await expect(page.getByText("failure *", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("failure *", { exact: true })).toBeVisible();
});
