import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
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

test("US-AGT-07/AC-1..5; US-TRG-03/AC-1,2: chat run, stable session and empty output", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("chat");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await expect(page.locator(".toolbar")).not.toContainText("chat *");
  const root = resolve(testInfo.outputPath(), "chat.weft");
  const list = await request("/workflows");
  const id = list.at(-1).id as string;
  const document = await request(`/workflows/${id}`);
  document.nodes.push({
    id: "n_00000002",
    type: "flow.chat_output",
    node_version: 1,
    name: "Chat Output",
    position: { x: 240, y: 0 },
    params: {},
  });
  document.nodes[0].params = { chat: { enabled: true } };
  document.edges = [
    {
      id: "e_00000001",
      source: "n_00000001",
      sourcePort: "message",
      target: "n_00000002",
      targetPort: "message",
      order: 0,
    },
  ];
  writeFileSync(
    resolve(root, "pyproject.toml"),
    `${readFileSync(resolve(root, "pyproject.toml"), "utf8")}\n[tool.uv.sources]\nweft-worker = { path = "${resolve(projectRoot, "packages/weft-worker").replaceAll("\\", "/")}" }\nweft-sdk = { path = "${resolve(projectRoot, "packages/weft-sdk").replaceAll("\\", "/")}" }\n`,
  );
  execFileSync("uv", ["sync"], {
    cwd: root,
    env: {
      ...process.env,
      UV_INDEX_URL: "https://pypi.tuna.tsinghua.edu.cn/simple",
    },
  });
  await saveDocument(id, document);
  page.once("dialog", (dialog) => void dialog.accept(root));
  const opened = page.waitForResponse(
    (response) => response.url().endsWith("/workflows/open") && response.ok(),
  );
  await page.getByRole("button", { name: "打开工作流" }).click();
  await opened;
  await expect(page.locator(".weft-node")).toHaveCount(2);
  await page.getByRole("button", { name: "聊天", exact: true }).click();
  await page.getByLabel("聊天内容").fill("你好聊天");
  const sent = page.waitForResponse((response) =>
    response.url().endsWith(`/workflows/${id}/chat`),
  );
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const runId = (await (await sent).json()).run_id as string;
  await expect(page.getByText("你好聊天", { exact: true })).toHaveCount(2);
  await expect(page.getByRole("button", { name: "新会话" })).toBeVisible();
  await expect
    .poll(async () => (await request(`/runs/${runId}`)).status)
    .toBe("succeeded");
  const latest = await request(`/workflows/${id}`);
  latest.nodes = latest.nodes.slice(0, 1);
  latest.edges = [];
  await saveDocument(id, latest);
  page.once("dialog", (dialog) => void dialog.accept(root));
  const reopened = page.waitForResponse(
    (response) => response.url().endsWith("/workflows/open") && response.ok(),
  );
  await page.getByRole("button", { name: "打开工作流" }).click();
  await reopened;
  await page.getByLabel("聊天内容").fill("无输出");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(
    page.getByText("运行完成（无输出）", { exact: true }),
  ).toBeVisible();
});
