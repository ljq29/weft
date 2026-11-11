# Weft Agent 工作指南

本文件面向首次接触仓库的 coding agent。命令均从仓库根目录执行；项目文档主要使用中文，源码注释和 docstring 使用英文。

## 1. 项目概览与当前状态

Weft 是**本地优先、仅支持 Windows** 的可视化工作流工具：用 KNIME 式节点图编排表格与文件处理，联动本机 Excel COM，并在受控沙箱中运行 AI agent 工具。产品形态是本机 Python 服务加同源 Web UI，可由浏览器或 WebView2 桌面窗口承载，不是多用户服务端平台。

- 当前三个 Python 包与前端版本均为 `0.5.1`；版本分散在各包 `pyproject.toml`、`__init__.py` 和 `frontend/package.json` 中，发布时必须同步。
- 主要能力包括 DAG/循环/Metanode、分类缓存、独立 Worker pool、表格/文件/Excel 节点、LLM 与 Agent Loop、授权 NodeTool、五类触发器、沙箱变更审批、运行历史和工作流打包。
- 工作流是 `<name>.weft/` 自包含目录；运行数据和配置以文件保存，**没有 ORM 或数据库**。
- M1–M7 的大多数任务卡已完成，`T7.10` 仍未完成；完整 v1 的双机交接、人工体验和采用门禁以 `docs/07-roadmap.md` 为准，不要把“已有发布”理解成所有人工验收均已完成。
- 只支持 Windows 10/11；WSL/Linux 不是目标运行环境。真实 Excel、Sandboxie-Plus 和可选的 Node.js/pi 是独立外部依赖。

## 2. 文档与真源

开始改动前先读相关文档。行为变更须同步对应文档；发现文档与代码矛盾时应报告，不要悄悄扩大任务范围。

| 文档 | 职责 |
| --- | --- |
| `docs/01-prd.md` | 产品范围、Non-goals、平台约束与 D-01..D-13 决策 |
| `docs/02-user-stories.md` | 用户故事和 Given/When/Then 验收标准，行为与 AC 真源 |
| `docs/03-architecture.md` | 进程拓扑、Engine、Worker、Excel、Agent、Sandbox、前端与 ADR |
| `docs/04-data-model.md` | `.weft` 目录、`workflow.json`、ValueRef、Run、审计和保留策略 |
| `docs/05-api.md` | REST、WebSocket、鉴权、revision/CAS 和错误码契约 |
| `docs/06-engineering.md` | 工程约定、测试和发布规范 |
| `docs/07-roadmap.md` | 任务卡及完成状态；只有 `- [x]` 表示完成 |
| `docs/08-testing-strategy.md` | 测试分层、契约测试、安全红线、性能和验收门禁 |
| `docs/09-nodes-v1.md` | 由节点声明生成的只读参数参考，禁止手改 |

补充规则：

- 节点参数以代码中的 `Node` 声明和 JSON Schema 为真源；`09-nodes-v1.md` 只是派生物，不覆盖用户故事。
- 依赖与可执行命令以当前 `pyproject.toml`、各 `package.json`、lockfile 和 CI workflow 为准；旧文档中的依赖举例可能已经漂移。
- 前端 TS 类型与后端 Pydantic 模型手工同步，不存在自动代码生成流程。
- `README.md` 提供面向用户的安装与启动入口，`CHANGELOG.md` 记录各版本实际验证范围。

## 3. 技术栈与运行时架构

### 技术栈

- **后端**：Python 3.12+、FastAPI、Uvicorn、Pydantic v2、jsonschema、Polars、PyArrow、httpx、Jinja2、simpleeval、APScheduler、watchdog、loguru；Windows 下使用 xlwings、pywin32 和 pywebview（WebView2 GUI）。
- **Worker**：独立 `weft-worker` 包，使用 Polars/PyArrow 和 send2trash；可信 Shell Command 也在 Worker 中执行。
- **SDK**：零第三方依赖的 `weft-sdk`，公开 `Node`、`Port`、执行 lane、缓存/工具能力声明及 `weft_ctx`。
- **前端**：React 18、TypeScript strict、Vite 6、React Flow 12（`@xyflow/react`）、Zustand、Apache Arrow JS、react-markdown。
- **工具链**：uv workspace、hatchling、Ruff、strict mypy、import-linter、pytest；Node.js 22、pnpm 11.9.0、ESLint、Prettier、Vitest、Playwright。

### 进程与数据流

1. 浏览器或 WebView2 通过 HTTP REST 和 WebSocket 连接 `127.0.0.1:7788`。FastAPI 既提供 `/api`，也在前端构建产物存在时提供 SPA；`weft serve --gui` 使用 pywebview edgechromium，关闭窗口停止本服务。
2. 主服务持有 WorkflowStore、Engine、RunCoordinator、TriggerManager、AgentRuntime、LLMProxy、SandboxManager 和 ExcelWorkerSupervisor。当前主要组合根是 `weft.api.app.create_app()` 与内嵌 CLI 的 `run_workflow()`；`weft/application/` 目前仅是包占位。
3. 每个 Run 在工作流自己的 `.venv` 中懒启动独立 Workflow Worker pool，默认 4 个真实子进程，Run 结束全部关闭。服务与 Worker 通过 stdio 上的逐行 JSON-RPC 通信；表格本体走 `.runs/<run_id>/ipc/` 下的 Arrow IPC 文件和 memory-map，不走 stdio。
4. 主服务与工作流声明的 `weft-worker==<service_version>` 必须精确同版本。Worker 启动时移除宿主 `PYTHONPATH`，不得依赖主服务源码的隐式复用。
5. Excel COM 不进入 Workflow Worker：独立 ExcelWorker 子进程中的单个 STA 线程串行执行，跨宿主使用 `Local\WeftExcelCOM` 互斥。可见 Excel 默认 attach；隐藏实例按 owned 身份和显式 save/discard 策略管理。
6. Agent 在主机服务侧编排。原始 LLM key 只由沙箱外 LLMProxy 读取；Sandboxie 中每个 Run 使用独立 box，文件变更先收集和审批，再应用到真实路径。
7. 每个工作流同一时刻最多一个活跃 Run。服务可用时 `weft run` 走服务 API；内嵌 CLI 与服务共用 `.runs/engine.lock` 跨进程锁。

节点分三条 lane：`trusted_worker`（表格、文件、用户 Python、可信 Shell）、`trusted_service`（流程、Excel、Agent 等）和 `sandboxed`（声明性工具）。缓存策略为 `pure | volatile | side_effect`，默认 `side_effect`；副作用不得因缓存而跳过，LLM 和实时 Excel Read 不得跨 Run 复用。

## 4. 仓库结构与模块分工

```text
packages/
  weft/                 主服务、引擎、CLI、服务侧节点与全部主包测试
  weft-worker/          Worker 入口/协议和可信 Worker 内置节点
  weft-sdk/             公共节点协议与 weft_ctx，不依赖另外两个包
frontend/               React SPA、Vitest 测试和生产构建
e2e/                    Playwright 浏览器测试
scripts/                AC 覆盖门禁、便携包构建与验收
packaging/weft.cmd      Windows 便携目录启动器
docs/                   需求、契约、架构、路线图和测试规范
.github/workflows/      Windows CI 与标签驱动 Release
```

主包 `packages/weft/src/weft/` 的关键目录：

| 模块 | 职责 |
| --- | --- |
| `api/` | FastAPI 路由、统一错误、REST/WS、会话与 Host/Origin 安全边界 |
| `engine/` | 调度、Run 队列、冻结快照、缓存、循环、执行锁与状态模型 |
| `workflow/` | Pydantic 模型、存储、校验、端口/ValueRef、迁移、Metanode、历史、资源预检和打包 |
| `nodes/` | 流程、Excel、Agent、Memory 节点，以及注册表和规格导出器 |
| `worker/` | 主服务侧工作流环境同步与 Worker pool 管理 |
| `excel/` | Backend 协议、Fake/Xlwings、ExcelWorker、监督器、目标与引用登记 |
| `agent/` | LLMProxy/Client、Agent Loop、工具、NodeTool、审计、确认、Pi、Memory 和设置 |
| `sandbox/` | Sandbox 接口、None/Sandboxie、helper、变更收集与审批 |
| `triggers/` | 手动协调器之上的 chat/schedule/watch/http 触发管理 |
| `demos/` | 三个内置 `.weft` 示例及其锁定依赖/资源 |
| `cli.py`、`doctor.py`、`operations.py`、`portable.py` | CLI、环境诊断/清理、结构化日志和便携运行时发现 |

其他重要位置：

- `packages/weft-worker/src/weft_worker/builtin*.py`：表格、文件等 Worker 节点；`runtime.py` 实现 Worker RPC 和 Arrow 序列化。
- `frontend/src/canvas/`、`panels/`、`components/`：画布、侧栏/弹窗面板和通用组件。
- `frontend/src/stores/`：workflow/run/connection 等 Zustand 状态；`hooks/` 拆分文档、命令、画布和 Overlay 编排。
- `frontend/src/api/`：轻量 fetch 客户端、结构化 `ApiError`、认证 WS、重连与 REST baseline 恢复。
- `frontend/src/types/workflow.ts`：手工维护的前端契约类型；`styles.css` 只汇总 `styles/` 下按区域拆分的 CSS。
- `packages/*/tests/`、`frontend/src/**/*.test.*`、`e2e/tests/`：对应层级测试。

## 5. 安装、启动与常用 CLI

开发前置条件：Windows、Python 3.12+、uv、Node.js 22、pnpm。可选真实验收依赖为桌面 Excel、Sandboxie-Plus 和 pi。

```bash
# 安装锁定依赖；镜像可按网络环境省略或覆盖
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uv sync --frozen
pnpm install --frozen-lockfile --registry=https://registry.npmmirror.com

# 完整应用：先构建 SPA，再由后端同源提供 UI
pnpm -C frontend build
uv run weft serve

# 前后端分离开发：两个终端分别执行
WEFT_DEV_ORIGIN=http://127.0.0.1:5173 uv run weft serve --no-browser
pnpm -C frontend dev
```

Vite 开发地址为 `127.0.0.1:5173`，将 `/api`（含 WS）代理到 `7788`。开发 Origin 必须通过后端的 `WEFT_DEV_ORIGIN` 显式允许。启动 URL 中的随机会话令牌被前端移入 `sessionStorage`；CLI 从用户会话文件读取它。

```bash
uv run weft serve --no-browser             # 不自动打开浏览器
uv run weft serve --gui                    # WebView2 桌面窗口
uv run weft serve --no-triggers            # 停用后台触发器
uv run weft run path/to/demo.weft --wait   # 执行工作流
uv run weft run path/to/demo.weft --var threshold=10 --wait
uv run weft pack path/to/demo.weft
uv run weft unpack demo.weft.zip -d D:/flows
uv run weft doctor --json
uv run weft doctor --cleanup               # 只清理 owned 且身份匹配的遗留资源
uv run weft --version
```

默认用户配置为 `%APPDATA%/weft/config.toml`，会话为同目录 `session.json`，服务日志在 `logs/`；测试可用 `WEFT_CONFIG_DIR` 隔离。非本机监听前必须配置 `server.global_token`。不要把真实令牌、会话文件或 LLM key 写入仓库。

## 6. 检查与测试

### 常用命令

```bash
uv run poe check                 # 提交前默认门禁
uv run poe lint                  # Ruff check/format、mypy win32、import-linter
uv run poe test                  # pytest：排除 integration 和 win_real
uv run poe integration           # pytest -m integration
uv run poe coverage              # US/AC 引用和已完成任务覆盖检查
uv run poe export-nodes-check    # 检查生成的节点文档是否漂移

pnpm -C frontend lint            # ESLint + Prettier check
pnpm -C frontend typecheck       # tsc --noEmit
pnpm -C frontend test            # Vitest run
pnpm -C frontend build           # typecheck + vite build

pnpm -C e2e exec playwright install chromium  # 首次安装浏览器
pnpm -C e2e test                 # 自动启动真实后端和 Vite，workers=1
```

`poe check` 的顺序是 `lint → 默认 pytest → frontend lint/typecheck/test → AC coverage → 节点导出漂移检查`。它**不包含** `integration`、Playwright E2E、真实 `win_real`、wheel/便携包验收；改动触及这些边界时必须另跑对应命令。默认 pytest 的表达式没有排除 `benchmark`，因此非真机基准也可能执行并写入 `.test-reports/`。

Windows 登录态桌面上的真实依赖与受控基准：

```bash
uv run pytest -m win_real -v
uv run pytest -m "win_real or benchmark" -v
```

`win_real` 需要真实 Excel/Sandboxie/pi，不在普通 hosted CI 中运行。未实际执行时必须明确标为未验证，不能用 Fake 结果替代。

### 测试分层与约定

- **Python 默认测试**：领域逻辑、Fake 契约和无需真实外部依赖的测试。
- **`integration`**：FastAPI/WS、文件系统、触发器、打包及真实 Workflow Worker 子进程；只允许在外部边界替换 Excel、Sandboxie 和远端 LLM，不得 mock 掉被测 Worker、缓存、RPC 或文件通道。
- **Vitest**：store、API/WS、表单、对话框和组件逻辑。
- **Playwright**：真实后端加浏览器交互；配置自动使用独立 `WEFT_CONFIG_DIR` 和开发 Origin。
- **契约测试**：Fake 与真实 Excel/Sandbox 应复用相同行为契约，避免 Fake 自成一套语义。
- **LLM**：自动化使用 `packages/weft/tests/fixtures/mock_llm.py` 的剧本式本地服务器；真实模型验收另行记录。

验证用户故事的 Python 测试 docstring 首行、TS 测试标题必须标注 `US-XXX-NN/AC-M`。`scripts/coverage_matrix.py` 会拒绝不存在的 US/AC，并检查 roadmap 已完成任务卡的非 manual AC 是否至少有测试引用。不要为凑覆盖写无断言测试，不要删除、skip、xfail 或弱化失败测试，也不要在生产代码中加入测试特判。

`docs/08-testing-strategy.md` 还规定了行覆盖目标：`engine/`、`workflow/`、`agent/` ≥85%，`nodes/`、`triggers/`、`sandbox/` ≥75%，真实 `xlwings_backend.py` ≥70%。当前 `poe coverage` 只检查 AC 追溯，并不计算这些行覆盖率。

## 7. 代码风格与修改约束

### Python

- Ruff：行宽 100、目标 Python 3.12，启用 `E/F/I/B/UP/TID`，忽略 `B008`；格式检查范围为 `packages` 和 `scripts`。
- mypy strict，统一按 `--platform win32` 检查三个包。模块/函数用 `snake_case`，类用 `PascalCase`，常量用 `UPPER_SNAKE`。
- 注释和 docstring 用英文；用户可见错误和 UI 文案用中文。服务日志使用 loguru，CLI 的用户输出可使用 `print`。
- Engine 不得 import API、具体 trigger 或 agent 实现；这些由上层和组合根协调。Ruff banned-api 与 import-linter 在 CI 强制边界。
- `weft-sdk` 不得依赖 `weft` 或 `weft-worker`。新增依赖要有必要性说明，并同步 manifest 与 lockfile。

### TypeScript / 前端

- TypeScript `strict`，启用未使用变量/参数检查；ESLint 使用 `strictTypeChecked` 和 react-hooks 规则，Prettier 负责格式。
- 使用函数组件与 hooks，不引入 class 组件或新的前端状态库。
- 业务规则只在后端。端口兼容、完整参数/图校验和执行状态以后端为准；前端本地 required 检查只提供 provisional 反馈，不得覆盖运行态。
- REST 使用现有 `api()` 和 `ApiError`，WS 遵循 authenticate ACK → subscribe → 断线重连 → REST baseline 的现有协议，不另建平行的数据获取层。

### 节点、工作流与范围

- 内置节点须填写英文 `name`、中文 `display_name`、描述、端口、lane、缓存策略及参数 schema。修改声明后重新生成并检查 `docs/09-nodes-v1.md`：

  ```bash
  uv run python -m weft.nodes.export --output docs/09-nodes-v1.md
  uv run poe export-nodes-check
  ```

- 自定义节点位于工作流 `nodes/*.py`，使用 SDK 的 `@node` 装饰器和 `user.*` 类型命名空间。
- 工作流路径默认相对 Root、采用 POSIX 风格；`.venv/`、`.runs/` 和密钥不进入打包产物。历史端口读取 Run 的 `outputs` 快照，不读临时 IPC 或当前全局缓存。
- 禁止引入 LangChain/LangGraph、ORM/数据库和新的前端状态库；不要实现 PRD Non-goals 中的远程 Runner、多用户、云同步或 agent 自主改图。
- 一次只完成 `docs/07-roadmap.md` 的一个任务卡。完成标准是对应 AC 测试通过、相关真机/人工门禁如实记录且 `poe check` 全绿；不能因文档写完就勾选实现任务。
- Git 使用 `feat/<topic>`、`fix/<topic>` 分支和英文 Conventional Commits；PR 应关联 US/AC 并说明文档更新与验证范围。

## 8. 安全红线

- 本机 API/WS 使用随机会话 Bearer token，并校验 Host/Origin；WS 未认证不能订阅。`X-Weft-Client: ui` 只是图修改操作标记，**不是鉴权替代品**。
- LLM key 仅存用户级配置，读取时掩码；不得进入工作流、打包文件、沙箱 env、stdout、trace 或日志。沙箱只获得本地 LLMProxy 地址和配置名。
- `NoneSandbox` 只提供受控影子目录文件工具；任意 bash、pi 和主机 spawn 必须拒绝，不能把它变成“无隔离直写模式”。
- Sandboxie 每 Run 独立 box，网络默认拒绝，仅开放受控环回 LLMProxy 例外。只清理本 Run 且身份匹配的 box/进程，不得误杀用户 Excel 或其他 Run。
- `workflow.json`、`pyproject.toml`、`uv.lock`、`.runs/**` 和用户配置属于 protected 变更，审批 apply 必须拒绝。真实目标哈希变化时返回 `CHANGE_CONFLICT`，未经重新查看 diff 和显式确认不得覆盖。
- NodeTool 只开放显式声明能力和参数白名单；Python/Shell/任意代码节点不可作为工具，副作用工具需要授权和确认，禁止递归 Agent。
- 打包必须保持 zip slip 防护、密钥扫描和错误阻断；Excel 公式写入默认关闭。安全相关改动应对照 `docs/08-testing-strategy.md` 的 SEC-01..SEC-13。

## 9. 构建、CI 与发布

### Wheel 与 Windows 便携目录

构建主包 wheel 前必须先有 `frontend/dist/index.html`；`packages/weft/build_hooks.py` 会把它复制为 wheel 内的 `weft/static`。Editable 安装不执行该复制。

```bash
pnpm -C frontend build
uv build --wheel --out-dir dist packages/weft-sdk
uv build --wheel --out-dir dist packages/weft-worker
uv build --wheel --out-dir dist packages/weft

# 默认会自行构建前端和三个 wheel；已构建时可加两个 skip 参数
uv run python scripts/build_portable.py
uv run python scripts/build_portable.py --skip-frontend-build --skip-wheel-build
uv run python scripts/verify_portable.py
```

产物为 `dist/*.whl`、`dist/weft-windows-x64/` 和 `dist/weft-windows-x64.zip`。便携目录只携带 CMD 启动器、PowerShell 源选择助手、uv、生产锁、manifest 和同版本 wheel，不携带 Python 或 Nuitka 主程序。首次运行通过内置 uv 在 `%LOCALAPPDATA%/Weft` 安装托管 CPython 3.12 和版本化应用环境；未显式指定包源时提示选择官方、已配置且可用的 pip 源或清华源。

```bat
weft.cmd serve
weft.cmd --china serve
weft.cmd --offline serve
weft.cmd --repair serve
weft.cmd --bootstrap-help
```

`verify_portable.py` 使用隔离的 PATH、`LOCALAPPDATA` 和配置目录，验证 manifest、无宿主 Python/uv 的已配置 pip 源交互下载、真实 CSV、缓存离线执行/repair、认证服务 API 和 SPA；首次验收需要网络。

### 自动化与发布流程

`.github/workflows/ci.yml` 在 main push 和 PR 上运行五个 **windows-latest** job：

1. `lint-and-type`：Python 与前端 lint/type；
2. `unit-and-integration`：默认 pytest、integration、AC coverage；
3. `frontend`：Vitest 与生产构建；
4. `e2e`：Chromium Playwright；
5. `build-packages`：三个 wheel、便携 ZIP 和干净 bootstrap/离线验收，上传构建产物。

发布不是部署到服务器，而是创建 GitHub Release。同步三个包及前端版本、更新文档和 CHANGELOG 后，推送匹配的 `v<version>` 标签；`.github/workflows/release.yml` 会检查标签与 `weft.__version__`，依次运行完整 `poe check`、integration、前端构建、E2E、wheel/便携包构建和便携验收，最后上传 wheel/ZIP 并创建 Release。该流程不包含真实桌面 `win_real` 和人工里程碑验收，发布前仍须按 roadmap 单独完成并记录。

## 10. 交付前检查清单

1. 确认只处理一个 roadmap 任务，并阅读对应 PRD/US/架构/数据/API 章节。
2. 修改契约时同步后端模型、前端类型、API/WS 客户端和相关文档；修改节点声明时重新生成 `09-nodes-v1.md`。
3. 先添加或更新带正确 US/AC 标记的行为测试，再实现；保持真实子进程与安全边界，不用 mock 绕过被测系统。
4. 运行 `uv run poe check`，再按影响范围运行 integration、E2E、前端 build、便携验收或 `win_real`。
5. 检查 git diff 和新生成文件，不提交 `.runs/`、`.test-reports/`、前端构建缓存、会话、密钥或用户工作流运行产物。
6. 在交付说明中列出实际运行的命令与结果；没有执行的真实 Excel/Sandboxie/pi、真实模型、双机或人工验收必须明确写“未验证”。
