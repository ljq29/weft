# T0.4 pi 非交互模式与主机 LLMProxy Spike

## 当前结论

**T0.4 已完成**。pi 的非交互参数、JSONL 输出、沙箱外 LLMProxy、Sandboxie 默认断网及环回例外均已通过真实验证；原始 API key 只存在用户级配置，未进入沙箱环境、stdout 或运行产物。

## 主机 Mock 证据

- 日期：2026-11-03；pi：`@earendil-works/pi-coding-agent` 1.4.0。
- 脚本：`scripts/spikes/pi_llm_proxy.py`；命令：`uv run python scripts/spikes/pi_llm_proxy.py`。
- 汇总报告：`.test-reports/pi-spike.json`；本次输出：`.test-reports/pi-8138933a/stdout.jsonl`、`stderr.log`。
- pi 退出码 0，收到 `WEFT_PROXY_OK`；Mock 确认上游 Authorization 由主机代理写入；`raw_key_in_child_env=false`、`raw_key_in_stdout_or_stderr=false`。

## 真实模型与 Sandboxie 证据

- 2026-11-04 使用本机用户级 `default` 配置和真实 `deepseek-v4.1-flash` 模型；API 地址与密钥不写入仓库。
- 主机 `LLMClient` 最小调用返回 `WEFT_REAL_OK`，token usage 正常。
- 真实 Agent Loop 完成两轮模型调用和一次参考表工具调用，流式事件、审计与最终分类正确。
- Pi 在 Sandboxie 内经环回代理返回 `WEFT_PI_OK`，退出码 0，解析到 19 个 JSONL 事件。
- Pi 启用 `read,write,edit,ls` 后创建 `organized/result.txt`；审批前真实文件不存在，经 `ChangeReviewStore` 应用后内容正确。运行产物未包含原始 API key。
- 配置发现依赖 `PI_CODING_AGENT_DIR` 和独立 session 目录；沙箱只传递这些非敏感变量以及 `PI_OFFLINE=1`、`PI_TELEMETRY=0`。

## 固化命令行

```text
pi --provider weft-local --model spike-model --mode json --print \
  --no-session --no-tools --no-extensions --no-mcp --no-skills --no-context-files \
  "Reply with the configured test text only."
```

正式 Pi Agent 节点可通过 `extra_args` 的 `--tools` 白名单按需开放工具，但必须保持非交互 `--print`、JSONL `--mode json`、独立配置/会话目录及显式资源开关。stdout 按 LF 解析 JSONL，stderr 用于诊断。

## 实现注意事项

1. 自定义 OpenAI 兼容端点使用 pi 的 `models.json`，provider 为 `api: "openai-completions"`；代理 URL 为 `/v1/<配置名>`，由主机代理解析配置名并添加上游真实密钥。
2. 代理保留完整 `chat/completions` 路径；模型兼容配置包含 `supportsUsageInStreaming: False`。
3. pi 在助手响应 `stopReason: "error"` 时进程仍可能退出 0；正式节点同时检查 JSONL 终态与错误字段，不能只依赖退出码。
4. T0.2/T5.2/T5.4 中任意命令的 Root 外硬拒绝及其他安全 AC 不因 T0.4 完成而自动完成。
