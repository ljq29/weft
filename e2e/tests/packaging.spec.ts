import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { appendFileSync, readFileSync, renameSync } from "node:fs";
import { resolve } from "node:path";

const config = resolve(
  import.meta.dirname,
  "../..",
  process.env.WEFT_E2E_CONFIG_DIR ?? ".test-reports/e2e-config",
  "session.json",
);
const projectRoot = resolve(import.meta.dirname, "../..");
const token = () => JSON.parse(readFileSync(config, "utf8")).token as string;
const apiUrl = process.env.WEFT_E2E_API_URL ?? "http://127.0.0.1:7788/api";

test("US-PKG-03/AC-1,4; US-PKG-04/AC-1,3,5: pack and import through the browser", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("handoff");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  const root = resolve(testInfo.outputPath(), "handoff.weft");
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
  await page.getByRole("button", { name: "打包工作流" }).click();
  await page
    .getByRole("dialog", { name: "打包数据目录" })
    .getByRole("button", { name: "保留 data", exact: true })
    .click();
  const completion = page.getByRole("dialog", { name: "打包完成" });
  await expect(completion).toBeVisible();
  const archive = (await completion.locator(".dialog-message").textContent())
    ?.replace("打包完成：", "")
    .trim();
  expect(archive).toContain("handoff-");
  await completion.getByRole("button", { name: "确定", exact: true }).click();
  renameSync(root, resolve(testInfo.outputPath(), "source.weft"));
  await page.getByRole("button", { name: "导入工作流" }).click();
  const importDialog = page.getByRole("dialog", { name: "导入工作流" });
  await importDialog.getByLabel("工作流 zip 路径").fill(archive ?? "");
  await importDialog.getByLabel("导入目标父目录").fill(testInfo.outputPath());
  const unpacked = page.waitForResponse(
    (response) => response.url().endsWith("/workflows/unpack") && response.ok(),
  );
  await importDialog.getByRole("button", { name: "导入", exact: true }).click();
  await unpacked;
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await expect(importDialog).toHaveCount(0);
  const response = await fetch(`${apiUrl}/workflows`, {
    headers: { Authorization: `Bearer ${token()}` },
  });
  const workflows = (await response.json()) as { path: string }[];
  expect(workflows.find((workflow) => workflow.path === root)).toBeDefined();
});
