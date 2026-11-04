# Weft Agent 工作指南

Weft 是本地优先的可视化工作流工具：KNIME 式表格数据流 + Excel COM 实时联动 + 沙箱化 AI agent 节点。仅支持 Windows，Python 后端 + React 前端；T0.1 仓库骨架与 GitHub Windows CI 均已通过，后续按 roadmap 推进。

## 文档索引（代码与文档冲突时以文档为准并报告）

|文档|内容|何时读|
| ------| ------------------------------------------------------------------| ----------------------------------|
|`docs/01-prd.md`|定位、场景、功能需求、Non-goals、决策 D-01..13|开始任何任务前；判断要不要做|
|`docs/02-user-stories.md`|用户故事与 AC，行为与验收真源|实现与写测试时|
|`docs/03-architecture.md`|进程拓扑、Engine、Worker pool、Excel/Agent/沙箱、ADR|写后端代码前|
|`docs/04-data-model.md`|workflow.json、Run 输出、ValueRef、TriggerEvent、审计与配置|定义/修改数据结构时|
|`docs/05-api.md`|REST + WS、revision/CAS、错误码、兼容策略|写 API 或前端 API 时|
|`docs/06-engineering.md`|monorepo、工具链、依赖规则、测试与发布|首次工作 + 提交前|
|`docs/07-roadmap.md`|M0–M7 与任务卡，唯一任务来源|领取任务时|
|`docs/08-testing-strategy.md`|测试分层、契约测试、安全红线、性能与 AC 门禁|写测试或提交自检前|

代码中的节点声明/JSON Schema 是参数真源；`docs/09-nodes-v1.md` 由导出器生成且只读，不覆盖行为 AC。`docs/README.md` 是文档索引。

## 常用命令（实现仓库建立后）

```bash
uv sync                          # 根 workspace 同步
uv run weft serve --no-browser   # T1.8 后：开发服务 127.0.0.1:7788
uv run poe check                 # 提交前自检：ruff + mypy + pytest + 前端 lint/test
uv run pytest -m integration     # Windows 集成测试（外部依赖用 Fake backends）
pnpm -C frontend dev             # 前端 dev server
```

## 硬性规则（违反即打回）

1. 一次只做 `docs/07-roadmap.md` 的一个任务；完成 = 对应 AC 测试通过 + `poe check` 全绿。任务卡统一 `- [ ]`，只有 `- [x]` 表示完成，不能凭文档编写完成而勾掉实现任务。
2. 不扩 scope：PRD Non-goals 优先；禁止 LangChain/LangGraph、ORM/数据库、新前端状态库。
3. Engine 只暴露执行接口，trigger/agent 在上层调用，由组合根注入；Engine 不 import 具体 triggers/agent。`weft-sdk` 不依赖 `weft`/`weft-worker`，主服务与 Worker 同版本，禁止主机 `PYTHONPATH` 隐式复用 Worker。
4. 项目仅支持 Windows，不支持 WSL/Linux；COM 只在 ExcelWorker 线程，沙箱/COM/路径相关代码必须带 Fake 实现与契约测试，但 Fake 绿灯不能替代 win_real。
5. 业务规则只在后端。副作用节点不得缓存执行；LLM 与实时 Excel Read 禁止跨 Run 复用；NodeTool 仅开放显式授权节点，原始 LLM key 只能由沙箱外代理读取。
6. 行为变更必须同步对应文档。`NoneSandbox` 仅提供受控影子目录文件工具，禁止任意 bash/pi；本机 UI/API/WS 使用随机会话令牌并校验 Host/Origin，`X-Weft-Client: ui` 不替代鉴权。
7. 测试 docstring 首行标注 `US-XXX-NN/AC-M`；不写无断言凑数测试，不覆盖不存在的 AC 引用。
