import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { appendFileSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const config = () =>
  resolve(
    import.meta.dirname,
    "../..",
    process.env.WEFT_E2E_CONFIG_DIR ?? ".test-reports/e2e-config",
    "session.json",
  );
const projectRoot = resolve(import.meta.dirname, "../..");
const token = () => JSON.parse(readFileSync(config(), "utf8")).token as string;

test("US-PKG-06/AC-1; US-PKG-07/AC-1,2: confirm missing resources and locate absolute path", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("resources");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Read CSV · 读取 CSV", exact: true })
    .dblclick();
  await expect(page.locator(".weft-node")).toHaveCount(2);
  await page
    .locator(".weft-node")
    .filter({ hasText: "Read CSV" })
    .locator("strong")
    .click();
  const external = resolve(testInfo.outputPath(), "external-missing.csv");
  await page.getByLabel("path *", { exact: true }).fill(external);
  const root = resolve(testInfo.outputPath(), "resources.weft");
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
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.locator(".toolbar")).not.toContainText("resources *");
  await page.getByRole("button", { name: "运行", exact: true }).click();
  const missingDialog = page.getByRole("dialog", { name: "外部资源缺失" });
  await expect(missingDialog).toBeVisible();
  await missingDialog
    .getByRole("button", { name: "取消", exact: true })
    .click();
  await expect(page.locator(".status-failed")).toHaveCount(0);
  await page.getByRole("button", { name: "运行", exact: true }).click();
  await missingDialog
    .getByRole("button", { name: "仍要运行", exact: true })
    .click();
  await expect(page.locator(".status-failed")).toHaveCount(1);
  await page.getByRole("button", { name: "打包工作流" }).click();
  await page
    .getByRole("dialog", { name: "打包警告" })
    .getByRole("button", { name: "继续打包", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "打包数据目录" })
    .getByRole("button", { name: "保留 data", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "打包完成" })
    .getByRole("button", { name: "确定", exact: true })
    .click();
  const locator = page.getByRole("button", { name: /定位 n_\w+\.path/ });
  await expect(locator).toBeVisible();
  await locator.click();
  await expect(page.getByLabel("path *", { exact: true })).toHaveValue(
    external,
  );
});
