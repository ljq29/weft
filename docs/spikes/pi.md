# T0.4 pi 非交互模式与主机 LLMProxy Spike

## 当前结论

pi 1.4.0 已在本机通过最小主机 LLMProxy 调用 OpenAI Chat Completions 兼容 Mock，并收到预期文本 `WEFT_PROXY_OK`。原始假密钥只存在于主机运行时配置；pi 配置仅含环回代理地址、配置名和本地占位凭据。子进程环境、stdout 与 stderr 均未出现原始假密钥。

**T0.4 尚未完成**：Sandboxie 基础真实测试已验证默认外网阻断和环回代理例外，但真实 pi 在沙箱内经 LLMProxy 的完整场景尚未执行，不能用本机代理或网络探针替代该项验收。

## 环境与证据

- 日期：2026-11-03
- pi：`@earendil-works/pi-coding-agent` 1.4.0
- 脚本：`scripts/spikes/pi_llm_proxy.py`
- 命令：`uv run python scripts/spikes/pi_llm_proxy.py`
- 汇总报告：`.test-reports/pi-spike.json`
- 本次输出：`.test-reports/pi-8138933a/stdout.jsonl`、`stderr.log`
- 结果：pi 退出码 0；收到预期文本；Mock 确认上游 Authorization 由主机代理写入；`raw_key_in_child_env=false`；`raw_key_in_stdout_or_stderr=false`

## 固化命令行

```text
pi --provider weft-local --model spike-model --mode json --print \
  --no-session --no-tools --no-extensions --no-mcp --no-skills --no-context-files \
  "Reply with the configured test text only."
```

正式 Pi Agent 节点可按需开放工具，但必须保持非交互 `--print`、JSONL `--mode json`、独立配置/会话目录及显式资源开关。stdout 按 LF 解析 JSONL，stderr 用于诊断。

## 实现注意事项

1. 自定义 OpenAI 兼容端点可用 pi 的 `models.json`，provider 使用 `api: "openai-completions"`；本次代理 URL 为 `/v1/default`，由主机代理解析配置名并添加上游真实密钥。
2. 代理必须保留完整 `chat/completions` 两段路径；pi 流式 SSE 与 `stream_options` 可按实际端点兼容性配置。
3. pi 在助手响应 `stopReason: "error"` 时进程仍可能退出 0；正式节点必须同时检查 JSONL 终态与错误字段，不能只依赖退出码。
4. 沙箱默认外网阻断和指定环回 LLMProxy 例外已通过基础真实测试；真实 pi 沙箱场景及其他主机服务阻断仍属 T0.2/T0.4 待验收项。
