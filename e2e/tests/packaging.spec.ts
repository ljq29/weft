import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { appendFileSync, readFileSync, renameSync } from "node:fs";
import { resolve } from "node:path";

const config = resolve(
  import.meta.dirname,
  "../../.test-reports/e2e-config/session.json",
);
const projectRoot = resolve(import.meta.dirname, "../..");
const token = () => JSON.parse(readFileSync(config, "utf8")).token as string;

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
  let archive = "";
  const packDialogs = (dialog: import("@playwright/test").Dialog) => {
    if (dialog.type() === "alert") {
      archive = dialog.message().replace("打包完成：", "");
      void dialog.accept();
    } else {
      void dialog.dismiss();
    }
  };
  page.on("dialog", packDialogs);
  await page.getByRole("button", { name: "打包工作流" }).click();
  await expect.poll(() => archive).toContain("handoff-");
  page.off("dialog", packDialogs);
  renameSync(root, resolve(testInfo.outputPath(), "source.weft"));
  let importStep = 0;
  const importDialogs = (dialog: import("@playwright/test").Dialog) => {
    const value = importStep++ === 0 ? archive : testInfo.outputPath();
    void dialog.accept(value);
  };
  page.on("dialog", importDialogs);
  await page.getByRole("button", { name: "导入工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await expect.poll(() => importStep).toBe(2);
  page.off("dialog", importDialogs);
  const response = await fetch("http://127.0.0.1:7788/api/workflows", {
    headers: { Authorization: `Bearer ${token()}` },
  });
  const workflows = (await response.json()) as { path: string }[];
  expect(workflows.find((workflow) => workflow.path === root)).toBeDefined();
});
