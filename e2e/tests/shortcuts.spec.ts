import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function token() {
  const configDir =
    process.env.WEFT_E2E_CONFIG_DIR ?? ".test-reports/e2e-config";
  const path = resolve(import.meta.dirname, "../..", configDir, "session.json");
  return JSON.parse(readFileSync(path, "utf8")).token as string;
}

async function createWorkflow(page: Page, name: string, parent: string) {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill(name);
  await page.getByLabel("父目录").fill(parent);
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
}

test("US-DES-08/AC-1: dialog focuses its field, closes on Escape and restores focus", async ({
  page,
}) => {
  await page.goto(`/?token=${token()}`);
  const openButton = page.getByRole("button", {
    name: "打开工作流",
    exact: true,
  });
  await openButton.click();
  const dialog = page.getByRole("dialog", { name: "打开工作流" });
  const input = dialog.getByLabel("工作流目录");
  await expect(input).toBeFocused();
  await input.fill("C:/flows/example.weft");
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(openButton).toBeFocused();
});

test("Escape dismisses demos, settings and port preview", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  const demosButton = page.getByRole("button", {
    name: "示例工作流",
    exact: true,
  });
  await demosButton.click();
  await expect(page.getByRole("dialog", { name: "示例工作流" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "示例工作流" })).toHaveCount(0);
  await expect(demosButton).toBeFocused();

  const settingsButton = page.getByRole("button", {
    name: "设置",
    exact: true,
  });
  await settingsButton.click();
  await expect(page.getByRole("dialog", { name: "设置" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "设置" })).toHaveCount(0);
  await expect(settingsButton).toBeFocused();

  await createWorkflow(page, "shortcut-preview", testInfo.outputPath());
  await page
    .locator(".weft-node")
    .getByRole("button", { name: "variable", exact: true })
    .click();
  await expect(page.getByRole("dialog", { name: "端口预览" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "端口预览" })).toHaveCount(0);
});

test("US-DES-08/AC-2,3: input Delete and Ctrl+C do not edit the canvas", async ({
  page,
}, testInfo) => {
  await createWorkflow(page, "shortcut-input", testInfo.outputPath());
  await page.locator(".weft-node strong").click();
  await expect(page.locator(".weft-node.selected")).toHaveCount(1);

  const input = page.getByLabel("工作流名称");
  await input.click();
  await input.press("Delete");
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await input.press("Control+c");
  await page
    .locator(".react-flow__pane")
    .click({ position: { x: 500, y: 80 } });
  await page.keyboard.press("Control+v");
  await expect(page.locator(".weft-node")).toHaveCount(1);
});

test("Escape closes the context menu before clearing node selection", async ({
  page,
}, testInfo) => {
  await createWorkflow(page, "shortcut-selection", testInfo.outputPath());
  const node = page.locator(".weft-node");
  await node.locator("strong").click();
  await expect(node).toHaveClass(/selected/);
  await node.click({ button: "right" });
  await expect(page.locator(".context-menu")).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.locator(".context-menu")).toHaveCount(0);
  await expect(node).toHaveClass(/selected/);
  await page.keyboard.press("Escape");
  await expect(page.locator(".weft-node.selected")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "选择一个节点" }),
  ).toBeVisible();
});

test("Escape leaves tool confirmation waiting for an explicit decision", async ({
  page,
}, testInfo) => {
  await createWorkflow(page, "shortcut-confirmation", testInfo.outputPath());
  await page.getByRole("button", { name: "运行", exact: true }).click();
  await expect(page.locator(".status-executed")).toHaveCount(1);
  await page.getByRole("button", { name: "历史", exact: true }).click();
  const history = page
    .locator(".history-panel button")
    .filter({ hasText: /r_\d/ });
  const text = await history.textContent();
  const runId = text?.match(/r_[A-Za-z0-9_]+/)?.[0];
  expect(runId).toBeTruthy();

  await page.evaluate((id) => {
    window.dispatchEvent(
      new CustomEvent("weft-chat", {
        detail: {
          event: "node.confirm_request",
          data: {
            run_id: id,
            request_id: "shortcut-confirm-request",
            node_id: "n_agent",
            tool: "write",
            args: { path: "output.txt" },
          },
        },
      }),
    );
  }, runId);
  const confirmation = page.getByRole("alertdialog", {
    name: "工具调用确认",
  });
  await expect(confirmation).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(confirmation).toBeVisible();
  await expect(
    confirmation.getByRole("button", { name: "批准", exact: true }),
  ).toBeVisible();
  await expect(
    confirmation.getByRole("button", { name: "拒绝", exact: true }),
  ).toBeVisible();
});
