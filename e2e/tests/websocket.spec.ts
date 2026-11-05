import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const projectRoot = resolve(import.meta.dirname, "../..");
const config = resolve(
  projectRoot,
  process.env.WEFT_E2E_CONFIG_DIR ?? ".test-reports/e2e-config",
  "session.json",
);
const apiUrl = process.env.WEFT_E2E_API_URL ?? "http://127.0.0.1:7788/api";

function token(): string {
  return JSON.parse(readFileSync(config, "utf8")).token as string;
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    headers: { Authorization: `Bearer ${token()}` },
  });
  if (!response.ok)
    throw new Error(`GET ${path}: ${response.status} ${await response.text()}`);
  return (await response.json()) as T;
}

interface ClientCommand {
  connection: number;
  op: string;
  topics?: string[];
}
interface RunRecord {
  run_id: string;
  status: string;
  nodes: Record<string, { status: string }>;
}

test("US-EXE-05/AC-1,3,5: browser reconnects, reauthenticates and restores a completed run from REST", async ({
  page,
}, testInfo) => {
  let available = true;
  let connection = 0;
  let brokenConnection = 0;
  let disconnect: (() => Promise<void>) | undefined;
  const commands: ClientCommand[] = [];

  await page.routeWebSocket(/\/api\/ws$/, async (route) => {
    connection += 1;
    if (!available) {
      await route.close({ code: 1013, reason: "E2E backend unavailable" });
      return;
    }
    const currentConnection = connection;
    const server = route.connectToServer();
    disconnect = () =>
      route.close({ code: 1012, reason: "E2E recoverable restart" });
    route.onMessage((message) => {
      const command = JSON.parse(
        typeof message === "string" ? message : message.toString(),
      ) as { op?: unknown; topics?: unknown };
      if (typeof command.op === "string")
        commands.push({
          connection: currentConnection,
          op: command.op,
          topics: Array.isArray(command.topics)
            ? command.topics.filter(
                (topic): topic is string => typeof topic === "string",
              )
            : undefined,
        });
      server.send(message);
    });
    server.onMessage((message) => {
      route.send(message);
    });
  });

  await page.goto(`/?token=${token()}`);
  await page.getByLabel("工作流名称").fill("websocket-recovery");
  await page.getByLabel("父目录").fill(testInfo.outputPath());
  const createdResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/workflows",
  );
  await page.getByRole("button", { name: "新建工作流" }).click();
  const created = (await (await createdResponse).json()) as { id: string };
  const workflowId = created.id;
  const indicator = page.getByRole("status", { name: "连接状态" });
  await expect(indicator).toHaveClass(/\bready\b/);
  await expect(indicator).toContainText("已连接");

  await page
    .getByRole("button", { name: "Wait · 等待", exact: true })
    .dblclick();
  const waitNode = page.locator(".weft-node").filter({ hasText: "Wait" });
  await expect(waitNode).toHaveCount(1);
  await waitNode.locator("strong").click();
  await page.getByLabel("duration_seconds *", { exact: true }).fill("2");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.locator(".workflow-identity")).not.toContainText("*");

  const runResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === `/api/workflows/${workflowId}/runs`,
  );
  await page.getByRole("button", { name: "运行", exact: true }).click();
  const runId = (await (await runResponse).json()).run_id as string;
  await expect(waitNode).toHaveClass(/\bstatus-running\b/);

  available = false;
  brokenConnection = connection;
  if (!disconnect) throw new Error("No real WebSocket to disconnect");
  await disconnect();
  await expect(indicator).toHaveClass(/\b(?:disconnected|backoff)\b/);
  await expect(page.getByRole("button", { name: "立即重连" })).toBeVisible();

  await expect
    .poll(async () => (await request<RunRecord>(`/runs/${runId}`)).status, {
      timeout: 15_000,
    })
    .toBe("succeeded");
  await expect(waitNode).toHaveClass(/\bstatus-running\b/);

  const historyBaseline = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/workflows/${workflowId}/runs?limit=20`) &&
      response.ok(),
  );
  const runBaseline = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `/api/runs/${runId}` &&
      response.ok(),
  );
  const logBaseline = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `/api/runs/${runId}/log` &&
      response.ok(),
  );
  available = true;
  await expect(indicator).toHaveClass(/\bready\b/, { timeout: 15_000 });
  await expect(waitNode).toHaveClass(/\bstatus-executed\b/);

  const baseline = (await (await runBaseline).json()) as RunRecord;
  expect(baseline.status).toBe("succeeded");
  expect(Object.values(baseline.nodes)).toHaveLength(2);
  expect(
    Object.values(baseline.nodes).every((node) => node.status === "executed"),
  ).toBe(true);
  await historyBaseline;
  await logBaseline;

  const recoveredCommands = commands.filter(
    (command) => command.connection > brokenConnection,
  );
  const authenticate = recoveredCommands.findIndex(
    (command) => command.op === "authenticate",
  );
  expect(authenticate).toBeGreaterThanOrEqual(0);
  const subscriptions = recoveredCommands.slice(authenticate + 1);
  expect(
    subscriptions.some((command) =>
      command.topics?.includes(`workflow:${workflowId}`),
    ),
  ).toBe(true);
  expect(
    subscriptions.some((command) => command.topics?.includes(`run:${runId}`)),
  ).toBe(true);

  available = false;
  if (!disconnect) throw new Error("No recovered WebSocket to disconnect");
  await disconnect();
  await expect(indicator).toHaveClass(/\bbackoff\b/);
  await expect(indicator).toContainText(/第 [3-9]\d* 次/, {
    timeout: 15_000,
  });
  const beforeImmediateReconnect = commands.length;
  available = true;
  await page.getByRole("button", { name: "立即重连" }).click();
  await expect(indicator).toHaveClass(/\bready\b/, { timeout: 10_000 });
  await expect(waitNode).toHaveClass(/\bstatus-executed\b/);

  const immediateCommands = commands.slice(beforeImmediateReconnect);
  expect(immediateCommands[0]?.op).toBe("authenticate");
  expect(
    immediateCommands.some(
      (command) =>
        command.op === "subscribe" &&
        command.topics?.includes(`workflow:${workflowId}`),
    ),
  ).toBe(true);
  expect(
    immediateCommands.some(
      (command) =>
        command.op === "subscribe" && command.topics?.includes(`run:${runId}`),
    ),
  ).toBe(true);
});
