import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const config = resolve(import.meta.dirname, "../../.test-reports/e2e-config/session.json");
const projectRoot = resolve(import.meta.dirname, "../..");
const token = () => JSON.parse(readFileSync(config, "utf8")).token as string;

async function request(path: string, method = "GET", body?: unknown) {
  const response = await fetch(`http://127.0.0.1:7788/api${path}`, {
    method,
    headers: { Authorization: `Bearer ${token()}`, "Content-Type": "application/json", "X-Weft-Client": "ui" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${method} ${path}: ${response.status} ${await response.text()}`);
  return response.json();
}
async function saveDocument(id: string, document: any) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await request(`/workflows/${id}`, "PUT", document);
    } catch (error) {
      if (!String(error).includes(" 409 ") || attempt === 2) throw error;
      const current = await request(`/workflows/${id}`);
      document.revision = current.revision;
    }
  }
}

test("US-EXE-01/AC-1, US-EXE-05/AC-4, US-EXE-06/AC-1,4,5: run and preview CSV in browser", async ({ page }, testInfo) => {
  page.on("response", (response) => {
    if (response.status() >= 400) console.log("HTTP", response.status(), response.url());
  });
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("execute");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  const root = resolve(testInfo.outputPath(), "execute.weft");
  writeFileSync(resolve(root, "data/input.csv"), "amount\n1\n3\n2\n");
  const document = await request(`/workflows/${(await request(`/workflows`)).at(-1).id}`);
  document.nodes = [
    { id: "n_00000001", type: "flow.trigger", node_version: 1, name: "Trigger", position: { x: 0, y: 0 }, params: {} },
    { id: "n_00000002", type: "table.read_csv", node_version: 1, name: "Read CSV", position: { x: 220, y: 0 }, params: { path: "data/input.csv" } },
    { id: "n_00000003", type: "table.row_filter", node_version: 1, name: "Row Filter", position: { x: 440, y: 0 }, params: { column: "amount", operator: ">", value: "1" } },
    { id: "n_00000004", type: "table.sorter", node_version: 1, name: "Sorter", position: { x: 660, y: 0 }, params: { keys: [{ column: "amount", descending: true }] } },
    { id: "n_00000005", type: "table.write_csv", node_version: 1, name: "Write CSV", position: { x: 880, y: 0 }, params: { path: "out/result.csv" } },
  ];
  document.edges = document.nodes.slice(2).map((node, index) => ({
    id: `e_0000000${index + 1}`,
    source: document.nodes[index + 1].id,
    sourcePort: "out",
    target: node.id,
    targetPort: "in",
    order: 0,
  }));
  writeFileSync(resolve(root, "pyproject.toml"), `${readFileSync(resolve(root, "pyproject.toml"), "utf8")}\n[tool.uv.sources]\nweft-worker = { path = "${resolve(projectRoot, "packages/weft-worker").replaceAll("\\", "/")}" }\nweft-sdk = { path = "${resolve(projectRoot, "packages/weft-sdk").replaceAll("\\", "/")}" }\n`);
  execFileSync("uv", ["sync"], { cwd: root, env: { ...process.env, UV_INDEX_URL: "https://pypi.tuna.tsinghua.edu.cn/simple" } });
  await saveDocument(document.id, document);
  page.once("dialog", (dialog) => void dialog.accept(root));
  await page.getByRole("button", { name: "打开工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(5);
  await page.getByRole("button", { name: "运行", exact: true }).click();
  await expect(page.locator(".status-executed")).toHaveCount(5, { timeout: 30_000 });
  await page.keyboard.press("Shift+1");
  await page.locator(".weft-node").filter({ hasText: "Read CSV" }).getByRole("button", { name: "out", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "端口预览" })).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("共 3 行");
  await expect(page.getByRole("dialog")).toContainText("amount");
  await expect(page.getByLabel("执行日志")).toBeVisible();
});
