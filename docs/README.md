# Weft 文档索引

Weft 是本地优先的 Windows 可视化工作流工具，融合表格数据流、Excel COM 实时联动和沙箱化 AI agent。当前处于设计阶段，仓库尚无实现代码。

## 阅读顺序

|文档|内容|主要用途|
| ------| ----------------------------------------------------| --------------------------------|
|[01-prd.md](01-prd.md)|产品定位、场景、功能需求、非目标与关键决策|判断做什么、不做什么|
|[02-user-stories.md](02-user-stories.md)|用户故事及 Given/When/Then 验收标准|行为与 AC 真源|
|[03-architecture.md](03-architecture.md)|进程、Engine、Worker、Excel、Agent、Sandbox 与 ADR|后端设计与技术约束|
|[04-data-model.md](04-data-model.md)|workflow.json、Run、ValueRef、事件、审计与配置字段|Pydantic/TS 数据契约|
|[05-api.md](05-api.md)|REST、WebSocket、错误码与版本兼容策略|UI/CLI/外部调用契约|
|[06-engineering.md](06-engineering.md)|monorepo、工具链、依赖规则、测试与发布规范|开发与自检|
|[07-roadmap.md](07-roadmap.md)|M0–M7 里程碑与未完成任务卡|实施顺序与完成追踪|
|[08-testing-strategy.md](08-testing-strategy.md)|测试分层、契约测试、安全红线、性能与 AC 门禁|验证策略|

## 真源与派生文档

- 需求范围以 `01-prd.md` 为准；行为和验收标准以 `02-user-stories.md` 为准。
- 数据字段与 API 分别以 `04-data-model.md`、`05-api.md` 为准；修改任一契约须同步相关文档。
- 节点参数以代码中的节点声明和 JSON Schema 为真源。规划的 `09-nodes-v1.md` 由导出器生成，是只读参考，不手写维护，也不覆盖用户故事的行为 AC。
- 根目录 `AGENTS.md` 是通用 agent 入口。

## 当前范围与验证状态

- P0 表示完整 v1 必须交付，不等于首个公开版全部交付。M0–M3 为首个公开 MVP，M4–M6 为后续预览，M7 才形成完整 v1。
- Sandboxie、Excel 多实例/COM 超时、pi 本地 LLM 代理等关键假设必须先通过 M0 Windows 真机 spike。
- `NoneSandbox` 的隔离语义仍待讨论；`X-Weft-Client: ui` 当前只是既定接口约束，暂不作为权限控制优化对象。
- 所有任务卡默认未完成，只有 `- [x]` 表示完成。Fake/Linux 测试不能替代 Windows 真机 `win_real` 验证。
