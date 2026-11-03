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

async function request(path: string, method = "GET", body?: unknown) {
  const response = await fetch(`http://127.0.0.1:7788/api${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token()}`,
      "Content-Type": "application/json",
      "X-Weft-Client": "ui",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(
      `${method} ${path}: ${response.status} ${await response.text()}`,
    );
  return response.json();
}

test("US-DES-09/AC-1..4: collapse, edit child canvas and expand in browser", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("metanode");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  const workflows = await request("/workflows");
  const id = workflows.at(-1).id as string;
  const document = await request(`/workflows/${id}`);
  document.nodes = [
    {
      id: "n_00000001",
      type: "flow.trigger",
      node_version: 1,
      name: "Trigger",
      position: { x: 0, y: 0 },
      params: {},
    },
    {
      id: "n_00000002",
      type: "table.read_csv",
      node_version: 1,
      name: "Read CSV",
      position: { x: 200, y: 0 },
      params: { path: "data/input.csv" },
    },
    {
      id: "n_00000003",
      type: "table.row_filter",
      node_version: 1,
      name: "Row Filter",
      position: { x: 400, y: 0 },
      params: { column: "value", operator: ">", value: "1" },
    },
    {
      id: "n_00000004",
      type: "table.sorter",
      node_version: 1,
      name: "Sorter",
      position: { x: 600, y: 0 },
      params: { keys: [] },
    },
    {
      id: "n_00000005",
      type: "table.row_count",
      node_version: 1,
      name: "Row Count",
      position: { x: 800, y: 0 },
      params: {},
    },
  ];
  document.edges = [3, 4, 5].map((target, index) => ({
    id: `e_0000000${index + 1}`,
    source: `n_0000000${target - 1}`,
    sourcePort: "out",
    target: `n_0000000${target}`,
    targetPort: "in",
    order: 0,
  }));
  await request(`/workflows/${id}`, "PUT", document);
  const root = resolve(testInfo.outputPath(), "metanode.weft");
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
  await expect(page.locator(".weft-node")).toHaveCount(5);
  await page.keyboard.press("Shift+1");
  await page.keyboard.down("Control");
  for (const name of ["Read CSV", "Row Filter", "Sorter"])
    await page
      .locator(".weft-node")
      .filter({ hasText: name })
      .locator("strong")
      .click();
  await page.keyboard.up("Control");
  await page.getByRole("button", { name: "折叠为 Metanode" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(3);
  const meta = page.locator(".weft-node").filter({ hasText: "Metanode" });
  await meta.dblclick();
  await expect(page.locator(".weft-node")).toHaveCount(3);
  await expect(
    page.getByRole("navigation", { name: "Metanode 面包屑" }),
  ).toContainText("metanode > Metanode");
  await page.getByRole("button", { name: "返回上级" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(3);
  await meta.click({ button: "right" });
  await page.getByRole("button", { name: "展开 Metanode" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(5);
  await expect(
    page.locator(".weft-node").filter({ hasText: "Sorter" }),
  ).toHaveCount(1);
});
