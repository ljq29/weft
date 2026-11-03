# 06-engineering.md

# **Weft 工程规范**

|项|值|
| ------| ---------------------------------|
|版本|v0.1（草稿）|
|上游|`03-architecture.md`|
|读者|实现本项目的 agent 与人类贡献者|

---

## 1. 仓库结构（monorepo）

```
weft/
├── AGENTS.md                  # 通用 agent 入口索引
├── docs/                      # 本套文档（01–08）
├── pyproject.toml             # workspace 根（uv workspace）
├── packages/
│   ├── weft/                  # 主包：服务、引擎、CLI（见 03-architecture.md §1.2 分层）
│   │   ├── src/weft/
│   │   └── tests/
│   ├── weft-worker/           # Worker 入口、RPC、可信 Worker 内置节点实现
│   │   ├── src/weft_worker/
│   │   └── tests/
│   └── weft-sdk/              # weft_ctx + 节点声明协议（Worker 侧与用户工作流依赖）
│       ├── src/weft_sdk/
│       └── tests/
├── frontend/
│   ├── src/
│   │   ├── canvas/            # React Flow 封装、自定义节点/边组件
│   │   ├── panels/            # 参数表单、端口视图、聊天、审批、历史
│   │   ├── stores/            # zustand
│   │   ├── api/               # REST/WS 客户端（由 05-api.md 手写对应，勿自动生成后手改）
│   │   └── types/             # 与 04-data-model.md 对应的 TS 类型
│   └── tests/
└── e2e/                       # Playwright
```

规则：

- `weft-sdk` 不得依赖 `weft` 或 `weft-worker`；`weft` 与 `weft-worker` 均依赖 `weft-sdk`，主服务与工作流锁定的 `weft-worker` 必须同版本。
- 分层依赖方向违规（如 `engine` import `api`）由 `ruff` 的 `flake8-tidy-imports` banned-api 规则 + import-linter 检查，CI 强制。Engine 只暴露执行接口，trigger/agent 位于上层并调用接口，由组合根注入；Engine 不 import 具体 triggers/agent。
- 前端 `types/` 与后端 Pydantic 模型不自动同步，变更 `04-data-model.md` 时两侧手动更新。代码中的节点声明/JSON Schema 是参数真源，`09-nodes-v1.md` 由导出器生成且只读；用户故事仍是行为与 AC 真源。

## 2. 语言与工具链版本

|项|版本|说明|
| --------------| ----------------------------------------------------------------------------------------------------------------------------------------------------| ------------------------------|
|Python|3.12（`requires-python = ">=3.12"`）||
|包管理|uv（workspace 模式）|不用 pip/poetry|
|Node|22 LTS + pnpm||
|TypeScript|5.x，`strict: true`||
|后端主要依赖|fastapi, uvicorn, pydantic v2, polars, pyarrow, xlwings (win), pywin32 (win), apscheduler, watchdog, httpx, loguru, jinja2, simpleeval, send2trash|新增依赖须在 PR 描述说明理由|
|前端主要依赖|react 18, @xyflow/react 12, zustand, @tanstack/react-query, @tanstack/react-table, apache-arrow||

## 3. 代码风格

### Python

- 格式化 + lint：`ruff`（format + check，配置在根 `pyproject.toml`，line-length 100）。
- 类型：全量类型注解；`mypy --strict`（`tests/` 放宽到非 strict）。Windows-only 模块（`excel/xlwings_backend.py` 等）用 `sys.platform` guard，mypy 按 platform=win32 跑一遍、linux 跑一遍。
- 命名：模块/函数 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE`。节点类型字符串见 `04-data-model.md` §9。
- 禁止：裸 `except:`；`print`（用 loguru）；在 `engine/` 中 import `api/`；在非 ExcelWorker 线程触碰 COM 对象（debug 断言，`03-architecture.md` §5.2）。
- 异常：业务错误用 `weft.errors` 中的层级（`WeftError > NodeError > ExcelBusyError...`），API 层统一映射为错误响应（`05-api.md` 错误码表）。

### TypeScript

- `eslint` + `prettier`（默认规则 + `@typescript-eslint/strict`）。
- 组件函数式 + hooks；禁止 class 组件。
- 业务规则禁入前端（`03-architecture.md` A-08）：端口兼容性、校验等一律调后端接口。

### 通用

- 注释与文档字符串用英文；用户可见文案（UI、错误消息）v1 用中文。
- 每个节点类型的 `description` 与参数 `description` 必填（UI 与工具 schema 复用）。

## 4. 测试

|层|工具|标记|CI|
| --------------| ------------| -----------------------------------| ---------------------------------------------|
|Python 单元|pytest|默认|每 PR，Linux + Windows|
|Python 集成|pytest|`-m integration`|每 PR，Linux（Fake backends）+ Windows|
|Windows 真机|pytest|`-m win_real`（需真实 Excel/Sandboxie/pi）|自托管 runner 或发布前手动 `weft-test-win.ps1`|
|前端单元|vitest||每 PR|
|E2E|Playwright||每 PR（Linux，FakeExcelBackend + mock LLM）|

- AC 映射：测试函数 docstring 首行写 `US-XXX-NN/AC-M`。`scripts/coverage_matrix.py` 只检查 roadmap 中 `- [x]` 已完成任务卡的非 manual AC；引用不存在的 US/AC 直接报错。所有任务默认 `- [ ]`，文档编写完成不等于实现完成。
- 节点规格：代码声明/JSON Schema 为参数真源，T0.1 建导出器骨架，T1.3 首次生成只读 `docs/09-nodes-v1.md`；导出 diff 纳入 CI，禁止手改生成文件。
- mock LLM：`tests/fixtures/mock_llm/` 内置可脚本化的 OpenAI 兼容服务器（支持 stream 与 tool_calls 剧本）；真实模型响应录制为回放素材（`03-architecture.md` §12）。
- 覆盖率门禁与 `08-testing-strategy.md` §7.3 完全一致：`engine/`、`workflow/`、`agent/` 行覆盖 ≥85%；`nodes/`、`triggers/`、`sandbox/` ≥75%；`excel/xlwings_backend.py` 仅在 win_real 统计且 ≥70%；其余 ≥70%。不为凑数写无断言测试。

## 5. 常用命令

```bash
# 后端
uv sync                                   # 根 workspace 同步
uv run weft serve --no-browser            # 启动开发服务
uv run pytest                             # 单元
uv run pytest -m integration              # 集成
uv run ruff check . && uv run ruff format --check .
uv run mypy packages/weft/src

# 前端
pnpm -C frontend dev                      # Vite dev server（代理 /api → 7788）
pnpm -C frontend test
pnpm -C frontend lint && pnpm -C frontend typecheck

# E2E
pnpm -C e2e test

# 一键自检（提交前）
uv run poe check                          # = ruff + mypy + pytest + 前端 lint/test（poethepoet 任务）
```

## 6. Git 规范

- 分支：`main` 保护；功能分支 `feat/<topic>`、修复 `fix/<topic>`。
- 提交：Conventional Commits（`feat: / fix: / docs: / refactor: / test: / chore:`），一次提交一个逻辑变更；提交信息英文。
- PR：描述须含"关联的 US/AC 编号"与"文档是否需要更新"勾选项；CI 全绿才可合并。
- 文档即真源：行为变更必须同 PR 更新对应文档（PRD/US/数据模型/API）；审查时文档与代码不一致按文档为准打回。

## 7. 对 Coding Agent 的工作约定

1. **任务粒度**：一次只做 `07-roadmap.md` 中的一个任务；完成的定义 = 对应 AC 的测试通过 + `poe check` 全绿。
2. **先读后写**：动代码前先读该模块文档章节；发现文档与代码矛盾时停下来报告，不要擅自选边。
3. **不扩scope**：不实现任务未要求的功能（PRD Non-goals 列表优先级最高）；觉得该做的额外事，写进 PR 描述建议区。
4. **决策留痕**：任何偏离文档的实现决策，在 PR 描述中列出并给理由；重要的追加到 `03-architecture.md` §11 ADR 表。
5. **Windows 差异**：凡 COM/沙箱/路径相关代码，必须同时提供 Fake 实现与契约测试，保证 Linux CI 可测。
6. **错误信息面向用户**：节点错误消息要说"哪个节点、什么参数、怎么修"，不要裸抛内部异常。
7. **禁止引入**：LangChain/LangGraph（D-04）、ORM/数据库（v1 全文件存储）、新的前端状态库。

## 8. 发布

- 版本：SemVer。0.x 阶段 REST/WS 可破坏；1.0 起只新增。P0 表示完整 v1 必须，不等于首个公开版全交付：M0–M3 发布首个公开 MVP，M4–M6 为后续预览，M7 才形成完整 v1。具体版本号在对应里程碑发布前确定，不预写 M7=`0.1.0`。
- 主服务、`weft-worker` 与工作流锁定的 Worker 版本必须一致；`weft --version` 与 `/api/system/version` 一致。
- 打包：`uv build`；发布产物为 wheel + `pipx install weft` / `uv tool install weft` 指引。
- 发布前 checklist：`weft doctor` 真机全绿、`-m win_real` 测试通过、`e2e` 通过、docs 与 CHANGELOG 更新。Fake/Linux 绿灯不能替代 win_real。
