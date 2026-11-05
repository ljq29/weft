import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { modelIdsFromResponse, SettingsPanel } from "./SettingsPanel";

describe("settings connections", () => {
  it("US-AGT-01/AC-1; US-SET-01/AC-2: renders connections and every structured setting", () => {
    const html = renderToStaticMarkup(
      <SettingsPanel onClose={() => undefined} />,
    );
    const labels = [
      "连接列表",
      "新增连接",
      "OpenAI Chat Completions",
      "服务商预设",
      "额外请求头",
      "添加请求头",
      "监听地址 server.host",
      "监听端口 server.port",
      "启动后打开浏览器",
      "非本机监听全局令牌",
      "默认沙箱",
      "允许 NoneSandbox",
      "沙箱网络",
      "Sandboxie Start.exe",
      "Sandboxie Box 前缀",
      "授权目录",
      "Excel 后端",
      "Excel 调用超时秒数",
      "Excel 超时后重启阈值",
      "pi 可执行文件路径",
      "Agent 审批超时秒数",
      "轨迹记录完整 Prompt",
      "Agent 轨迹保留天数",
      "HTTP Trigger 等待秒数",
      "日志级别",
      "日志保留天数",
      "缓存上限 MB",
      "最近 Run 保留数",
      "对话保留天数",
      "记忆保留天数",
    ];
    for (const label of labels) expect(html).toContain(label);
    expect(html).not.toContain("额外请求头（JSON）");
    expect(html).not.toContain("运行与运维配置（JSON）");
  });

  it("US-AGT-01/AC-2: extracts usable model ids for the editable model dropdown", () => {
    expect(
      modelIdsFromResponse([
        { id: "gpt-4o-mini" },
        { id: "deepseek-chat" },
        { id: 42 },
        { object: "model" },
      ]),
    ).toEqual(["gpt-4o-mini", "deepseek-chat"]);
  });
});
