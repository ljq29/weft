import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const config = resolve(
  import.meta.dirname,
  "../..",
  process.env.WEFT_E2E_CONFIG_DIR ?? ".test-reports/e2e-config",
  "session.json",
);
const apiUrl = process.env.WEFT_E2E_API_URL ?? "http://127.0.0.1:7788/api";
const token = () => JSON.parse(readFileSync(config, "utf8")).token as string;

async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token()}`,
      "Content-Type": "application/json",
      "X-Weft-Client": "ui",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(
      `${method} ${path}: ${response.status} ${await response.text()}`,
    );
  }
  return (await response.json()) as T;
}

test("US-EXE-07/AC-2: shows the backend code for an unauthorized request", async ({
  page,
}) => {
  await page.goto("/?token=invalid-token");
  await expect(page.locator(".error-banner")).toContainText("令牌缺失或无效");
  await expect(page.locator(".error-banner")).toContainText("UNAUTHORIZED");
});

test("US-DES-07/AC-4: reloads a conflict only after explicit confirmation", async ({
  page,
}, testInfo) => {
  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("api-conflict");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  await page.getByRole("button", { name: "新建工作流" }).click();
  await expect(page.locator(".weft-node")).toHaveCount(1);
  await page.locator(".weft-node strong").click();
  await page.getByLabel("节点注释").fill("本地未保存");

  const workflows = await request<{ id: string; name: string }[]>("/workflows");
  const id = workflows.find((workflow) => workflow.name === "api-conflict")?.id;
  expect(id).toBeTruthy();
  const current = await request<{
    id: string;
    revision: number;
    nodes: { comment?: string }[];
  }>(`/workflows/${id}`);
  current.nodes[0].comment = "服务端版本";
  await request(`/workflows/${id}`, "PUT", current);

  await page.getByRole("button", { name: "保存", exact: true }).click();
  const conflict = page.locator(".error-banner").filter({
    hasText: "REVISION_CONFLICT",
  });
  await expect(conflict).toBeVisible();
  await expect(page.getByLabel("节点注释")).toHaveValue("本地未保存");
  await expect(page.locator(".toolbar")).toContainText("api-conflict *");

  await conflict.getByRole("button", { name: "重新读取", exact: true }).click();
  await expect(page.getByLabel("节点注释")).toHaveValue("服务端版本");
  await expect(conflict).toHaveCount(0);
  await expect(page.locator(".toolbar")).not.toContainText("api-conflict *");
});
