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

test("US-DES-10/AC-1,2: edit comment and persist a styled Markdown note", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("notes");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await page.locator(".weft-node strong").click();
  await page.getByLabel("节点注释").fill("需要人工复核");
  await expect(page.locator(".weft-node p")).toHaveText("需要人工复核");
  await page
    .locator(".react-flow__pane")
    .click({ button: "right", position: { x: 500, y: 80 } });
  await expect(page.getByRole("region", { name: "画布便签" })).toBeVisible();
  await page.getByRole("button", { name: "编辑便签" }).click();
  await page.getByLabel("便签 Markdown").fill("# 交接说明\n\n**先检查输入**");
  await page.getByLabel("便签颜色").fill("#ffeeaa");
  await page.getByRole("button", { name: "预览便签" }).click();
  await expect(page.getByRole("heading", { name: "交接说明" })).toBeVisible();
  await expect(page.locator(".note-markdown strong")).toHaveText("先检查输入");
  await expect(page.getByRole("region", { name: "画布便签" })).toHaveCSS(
    "background-color",
    "rgb(255, 238, 170)",
  );
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.locator(".toolbar")).not.toContainText("notes *");
  const root = resolve(testInfo.outputPath(), "notes.weft");
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
  await expect(page.locator(".weft-node p")).toHaveText("需要人工复核");
  await expect(page.getByRole("heading", { name: "交接说明" })).toBeVisible();
  await expect(page.getByRole("region", { name: "画布便签" })).toHaveCSS(
    "background-color",
    "rgb(255, 238, 170)",
  );
});
