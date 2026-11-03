import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { appendFileSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const config = resolve(
  import.meta.dirname,
  "../../.test-reports/e2e-config/session.json",
);
const projectRoot = resolve(import.meta.dirname, "../..");
const token = () => JSON.parse(readFileSync(config, "utf8")).token as string;

test("US-EXE-09/AC-1..4: inspect a read-only historical Run in browser", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("history");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  const root = resolve(testInfo.outputPath(), "history.weft");
  appendFileSync(
    resolve(root, "pyproject.toml"),
    `\n[tool.uv.sources]\nweft-worker = { path = "${resolve(projectRoot, "packages/weft-worker").replaceAll("\\", "/")}" }\nweft-sdk = { path = "${resolve(projectRoot, "packages/weft-sdk").replaceAll("\\", "/")}" }\n`,
  );
  execFileSync("uv", ["sync"], {
    cwd: root,
    env: {
      ...process.env,
      UV_INDEX_URL: "https://pypi.tuna.tsinghua.edu.cn/simple",
    },
  });
  page.once("dialog", (dialog) => void dialog.accept(root));
  const opened = page.waitForResponse(
    (response) => response.url().endsWith("/workflows/open") && response.ok(),
  );
  await page.getByRole("button", { name: "打开工作流" }).click();
  await opened;
  await page.getByRole("button", { name: "运行", exact: true }).click();
  await expect(page.locator(".status-executed")).toHaveCount(1);
  await page.getByRole("button", { name: "历史", exact: true }).click();
  const item = page
    .locator(".history-panel button")
    .filter({ hasText: /r_\d/ });
  await expect(item).toHaveCount(1);
  await item.click();
  const detail = page.getByRole("region", { name: "历史运行详情" });
  await expect(detail).toContainText("succeeded");
  await expect(detail).toContainText("n_00000001");
  await expect(detail).toContainText("run.started");
  await detail.getByRole("button", { name: "查看轨迹" }).click();
  await expect(detail).toContainText("n_00000001 轨迹");
  await detail.getByRole("button", { name: "查看 variable" }).click();
  await expect(page.getByRole("dialog", { name: "端口预览" })).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("manual");
});
