import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function token() {
  const configDir = process.env.WEFT_E2E_CONFIG_DIR ?? ".test-reports/e2e-config";
  const path = resolve(import.meta.dirname, "../..", configDir, "session.json");
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
  await expect(
    page.getByRole("button", { name: "Trigger", exact: true }),
  ).toBeVisible();
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
  await page
    .locator(".react-flow__pane")
    .click({ position: { x: 500, y: 80 } });
  await page.keyboard.press("Control+z");
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await page.keyboard.press("Control+y");
  await expect(page.locator(".weft-node")).toHaveCount(2);
  await page
    .locator(".weft-node")
    .filter({ hasText: "Read CSV" })
    .locator("strong")
    .click();
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

test("US-DES-08/AC-2, US-DES-11/AC-1: left drag selects nodes and middle drag pans", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("mouse-navigation");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await page.getByRole("button", { name: "Read CSV", exact: true }).dblclick();
  await expect(page.locator(".weft-node")).toHaveCount(2);
  await page.keyboard.press("Shift+1");

  const pane = page.locator(".react-flow__pane");
  const viewport = page.locator(".xyflow__viewport");
  const paneBox = await pane.boundingBox();
  if (!paneBox) throw new Error("Canvas pane is not visible");
  const viewportTransform = () =>
    viewport.evaluate((element) => getComputedStyle(element).transform);
  const beforePan = await viewportTransform();
  const panX = paneBox.x + paneBox.width - 100;
  const panY = paneBox.y + paneBox.height - 100;
  await page.mouse.move(panX, panY);
  await page.mouse.down({ button: "middle" });
  await page.mouse.move(panX - 120, panY - 60, { steps: 8 });
  await page.mouse.up({ button: "middle" });
  await expect.poll(viewportTransform).not.toBe(beforePan);

  await page.keyboard.press("Shift+1");
  await page.waitForTimeout(300);
  const nodes = page.locator(".weft-node");
  const first = await nodes.nth(0).boundingBox();
  const second = await nodes.nth(1).boundingBox();
  if (!first || !second) throw new Error("Canvas nodes are not visible");
  const left = Math.min(first.x, second.x) - 20;
  const top = Math.min(first.y, second.y) - 20;
  const right = Math.max(first.x + first.width, second.x + second.width) + 20;
  const bottom = Math.max(first.y + first.height, second.y + second.height) + 20;
  await page.mouse.move(left, top);
  await page.mouse.down();
  await page.mouse.move(right, bottom, { steps: 12 });
  await expect(page.locator(".react-flow__selection")).toBeVisible();
  await page.mouse.up();
  await expect(page.locator(".weft-node.selected")).toHaveCount(2);
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
