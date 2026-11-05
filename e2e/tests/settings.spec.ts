import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function token() {
  const configDir =
    process.env.WEFT_E2E_CONFIG_DIR ?? ".test-reports/e2e-config";
  const path = resolve(import.meta.dirname, "../..", configDir, "session.json");
  return JSON.parse(readFileSync(path, "utf8")).token as string;
}

test("US-AGT-01/AC-1; US-SET-01/AC-2: structured settings save and reload", async ({
  page,
}) => {
  await page.goto(`/?token=${token()}`);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "设置" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("协议", { exact: true })).toHaveValue(
    "openai-chat-completions",
  );
  await expect(dialog.getByLabel("额外请求头（JSON）")).toHaveCount(0);
  await expect(dialog.getByLabel("运行与运维配置（JSON）")).toHaveCount(0);

  const retention = dialog.getByLabel("最近 Run 保留数", { exact: true });
  await retention.fill("51");
  await dialog.getByRole("button", { name: "保存设置" }).click();
  await expect(dialog.getByRole("status")).toContainText("设置已保存");
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);

  await page.getByRole("button", { name: "设置", exact: true }).click();
  const reopened = page.getByRole("dialog", { name: "设置" });
  await expect(
    reopened.getByLabel("最近 Run 保留数", { exact: true }),
  ).toHaveValue("51");
  await reopened.getByLabel("最近 Run 保留数", { exact: true }).fill("50");
  await reopened.getByRole("button", { name: "保存设置" }).click();
  await expect(reopened.getByRole("status")).toContainText("设置已保存");
});
