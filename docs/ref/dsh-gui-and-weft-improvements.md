# DSH GUI 借鉴结论与 Weft 前端改进建议

|项|值|
| ------| ------------------------------------------------------------|
|状态|参考文档，不是需求或验收真源|
|核查基线|DSH 官方仓库 `0.2.2-rc.1`、master `fcc0ad4`；Weft `0.3.0` 工作树（2026-11-05）|
|适用范围|DSH 官方 Web GUI / Electron Desktop；Weft `frontend/` 与相关 API/WS 契约|
|约束|不替代 `01-prd.md`、`02-user-stories.md`、`03-architecture.md`、`05-api.md`、`07-roadmap.md`。实施前必须拆成 roadmap 任务并同步对应文档|

---

## 1. 结论

### 1.1 核心判断

**DSH GUI 不是“单体 React 前端 + REST 后端”，而是“TypeScript 全栈 + Cordis 插件运行时 + React 18 渲染层 + 类型化 RPC/流协议”。**

它最值得学的不是基础设施规模，而是三个工程原则：

1. **边界**：谁拥有业务真相、谁只保存投影、谁负责渲染，必须清楚。
2. **契约**：数据、事件、UI 扩展点都有类型和生命周期约束，不靠约定俗成。
3. **可替换**：功能通过稳定接口组合，而不是互相 import 实现细节。

对 Weft 的直接含义：

> 学 DSH 的分层、契约和失败处理；不要照搬 Cordis、自定义模块加载器、完整 Slot 体系和自研 RPC 框架。

### 1.2 DSH 的整体技术栈

|层面|DSH 选择|
| ------| ------------------------------------------------------------|
|语言与运行时|TypeScript、ESM、Node.js `>=24.9`、pnpm workspace|
|浏览器框架|React 18.2 + React DOM，SPA，无 SSR|
|应用框架|Cordis 插件运行时，Web/Host 两侧都按插件组合|
|UI 组合|五类 Slot（single/list/keyed/chain/hoc）+ Component Factory|
|客户端状态|React-free Client Model；Zustand vanilla + Immer 快照 Store；React 侧用 `useSyncExternalStore`|
|样式|CSS Modules + `--dsw-*` 设计令牌；自研 `ui-primitives`|
|构建|Vite 6.4 + React 插件；Host 和客户端插件用 tsdown|
|插件加载|Host 注入 `window.__DSH_BOOT__`；浏览器用自研 lazy-CJS 模块系统加载 `/plugins`|
|请求|Typert 类型化 RPC；HTTP POST `/api`，JSON/multipart|
|实时流|WebSocket `/api/remote.mux`，多路逻辑流，支持取消、心跳、压缩和重连|
|开发期热更新|SSE `/plugins/events`，插件图和 bundle revision 变化|
|编辑器|Lexical，包含 slash command、引用 chip 和草稿恢复|
|长列表|TanStack Virtual|
|Markdown/代码|micromark + mdast + GFM + KaTeX + Shiki|
|官方桌面端|Electron 44，加载同一套 Web 应用，不另写原生 UI|

### 1.3 DSH 的一条数据路径

```text
Host 的 Session Log / Workspace / 业务服务
  → Typert Remote（HTTP 单次调用，WebSocket 流）
  → React-free Client Model
  → UI Adapter
  → Conversation 组装
  → Slot View
  → React 渲染
```

用户操作沿反向链路回到 Host。前端不拥有最终业务状态，也不复制一套业务规则。

### 1.4 值得学与不建议照搬

|值得学|不建议照搬|
| ------| ------------------------------------------------------------|
|Host 是唯一真相，前端只做可重放投影|Cordis “一切皆插件”|
|React-free 状态模型 + 薄渲染适配层|自研 lazy-CJS 模块加载器|
|先定义 API 契约，再写页面|五类 Slot 和 Factory 的完整实现|
|区分单次请求、持续流、事件通知|自研 Typert 代码生成和 RPC 协议|
|重连先取 baseline，再处理增量|完整插件生命周期/权限/热替换体系|
|设计令牌 + 基础组件集中维护|Electron 桌面壳（当前 Weft 规模不需要）|
|启动失败和降级要成为产品界面|把所有面板都做成可动态装卸的插件|

---

## 2. Weft 现状对照

### 2.1 已经对齐的部分

Weft 当前方向与 DSH 的可迁移原则有较高重合，不需要推翻：

- **React 18 + TypeScript + Vite**，技术栈与 DSH 的浏览器侧一致。
- **Zustand 管理编辑/运行状态**，适合当前规模；`runStore` 已由 WS 驱动。
- **后端是业务规则真源**，`03-architecture.md` A-08 明确“前端零业务规则”。
- **API 契约先于实现**，已有 `05-api.md`，包含 REST、WS、错误码和 CAS/revision 规则。
- **鉴权边界清楚**：UI 会话令牌、Bearer、WS authenticate、Host/Origin 校验都已定义。
- **测试分层完整**：pytest、Vitest、Playwright、`win_real` 分层明确。
- **已有失败显示**：启动版本警告、错误 banner、打包预检、运行审批等不是纯空白页。

这说明 Weft 不需要再引入一层“框架”，重点是收紧现有边界并减少耦合。

### 2.2 当前值得优先处理的问题

以下依据当前工作树观察，不代表已发布行为。

#### 问题 1：`App.tsx` 承担了过多编排职责

`frontend/src/App.tsx` 约 1142 行，同时负责：

- 画布和 React Flow 生命周期；
- 文档加载、保存、自动保存；
- 新建、打开、导入、打包、运行；
- WebSocket 连接；
- overlay 开关和焦点恢复；
- 上下文菜单；
- 全局错误与警告；
- 面包屑和 Metanode 导航；
- 右侧检查器组合。

这会让任何功能改动都触碰同一个文件，也让组件测试只能覆盖很浅的行为。

**判断：** 这是当前前端最高收益的重构点，但不需要重写，只需按职责拆出 controller/hook 和布局组件。

#### 问题 2：API 契约类型靠手写同步，错误只保留 message

`frontend/src/types/workflow.ts` 与后端 Pydantic 模型是手动同步；`05-api.md` 明确错误响应包含 `code`、`message`、`detail`，但 `frontend/src/api/client.ts` 在非 2xx 时只取 `error.message`，把 `code` 和 `detail` 丢掉，最终用 `String(reason)` 展示。

这会导致：

- 前端无法按稳定错误码分支，违反“不得匹配自然语言消息”的契约；
- `CHANGE_CONFLICT`、`RUN_QUEUE_FULL`、`PORT_NOT_EXECUTED` 等状态只能变成字符串提示；
- 前后端类型漂移无法在 CI 中暴露。

**判断：** 这是次高收益项，优先级高于继续增加页面功能。

#### 问题 3：WebSocket 没有连接代际和恢复机制

当前 `frontend/src/api/ws.ts`：

- 直接创建 `ws://`，没有按页面协议选择 `ws:`/`wss:`；
- `authenticate` 后立刻 `subscribe`，没有等待认证 ACK；
- 没有断线重连、退避、连接状态和手工重连；
- 没有“重连后重新用 REST 取 baseline”的统一入口；
- 只处理 `message`，没有 `error`/`close` 处理；
- `runId` 变化时才补订阅，可能错过启动初期的瞬时事件。

`05-api.md` 已明确“WS 无事件回放，重连后用 REST 补齐”，但实现层还没有把这条契约变成可靠状态机。

**判断：** 在网络抖动、休眠唤醒或服务重启时，这会造成运行状态缺失或界面停在旧状态。

#### 问题 4：前端存在本地业务判断的漂移风险

`frontend/src/stores/workflowStore.ts` 通过 `params_schema.required` 计算 `unconfigured/configured`，并在参数变化时沿下游传播状态。这个判断本身是 UI 展示逻辑，但它和 `04-data-model.md`、后端校验器是两套规则。

只要后端修改“什么算配置完整”或前端漏掉某个 schema 形态，就会出现：

- UI 显示已配置，运行却返回 400；
- UI 显示未配置，实际节点可运行；
- 多标签页/缓存恢复后状态不一致。

**判断：** 可以保留本地即时反馈，但必须明确它是“临时 UI 提示”，最终状态以服务端 validate/run 结果为准。不要把该规则扩展成更复杂的业务判断。

#### 问题 5：原生 `prompt/confirm/alert` 破坏交互一致性

当前仍使用：

- `window.prompt` 打开工作流、导入 zip、选择目标目录；
- `window.confirm` 处理打包警告、排除 data、资源缺失继续运行；
- `window.alert` 展示打包完成。

这些问题对当前功能可用性影响不大，但与 Weft 已有的 overlay 焦点恢复、E2E 可测性、错误展示体系不一致：

- 无法统一样式、键盘行为和焦点恢复；
- Playwright 处理原生对话框容易耦合；
- 错误和确认无法携带结构化 `code/detail`；
- 无法提供“查看详情/定位节点”等动作。

#### 问题 6：已安装 TanStack Query，但没有使用

`frontend/package.json` 声明了 `@tanstack/react-query`，但 `frontend/src/` 没有 `useQuery/useMutation/QueryClient` 使用。当前请求全部由 `api()` 和组件内 `useEffect` 手工管理。

这不一定要求立刻引入 Query；但必须二选一：

- **采用**：统一 server state 缓存、失效、重试和 loading/error 语义；
- **移除**：避免依赖清单表达错误的技术事实，并保留轻量 `api()`。

不建议在没有明确需要时同时维护两套请求习惯。

#### 问题 7：样式集中且存在设计令牌之外的硬编码

`frontend/src/styles.css` 约 2463 行。虽然 `:root` 已有颜色、间距、字号、阴影和面板尺寸令牌，但文件中仍存在较多直接色值和组件级布局规则。

Weft 没有 DSH 的第三方主题生态，不需要做完整 token 系统；但至少应：

- 保持颜色/字号/间距只从令牌取值；
- 按画布、检查器、面板、overlay 拆分样式文件；
- 把基础控件样式与业务布局分离。

否则新增面板会继续复制样式，深色主题或密度调整会变成全文件搜索。

---

## 3. 改进建议

### P0：先收紧契约和运行可靠性

#### P0-1 统一 API 契约和错误模型

目标：

- 后端 Pydantic/OpenAPI 或 JSON Schema 成为可导出的契约源；
- 前端类型只读生成或至少有 CI 契约快照检查，禁止随意手改生成物；
- 前端 `ApiError` 保留 `status`、`code`、`message`、`detail`；
- UI 分支只依赖 `code`，自然语言只用于展示。

最小落地：

1. 在 `frontend/src/api/client.ts` 定义并抛出结构化 `ApiError`。
2. 保留 `05-api.md` 的错误码目录，增加一个前端错误码映射表。
3. 先不做全量代码生成，先把 `WorkflowDocument`、`NodeTypeDecl`、`RunEvent`、错误响应四组契约用 schema 校验固定下来。
4. 后续再评估从 OpenAPI 生成只读 TS 类型/客户端。

验收：

- 409/CAS、409/QUEUE_FULL、404/PORT_NOT_EXECUTED、400/校验错误在 UI 中可按 `code` 分支；
- 错误详情不会在 `String(reason)` 中丢失；
- 前端类型与后端 schema 的漂移能被 CI 或契约测试发现。

#### P0-2 把 WebSocket 做成带代际的连接

目标：任何一次断线、服务重启、休眠唤醒后，UI 都能重新建立可信状态，而不是靠用户刷新。

建议状态机：

```text
idle → connecting → authenticating → subscribing → ready
                         ↘ failed → backoff → connecting
ready → disconnected → backoff → connecting
```

最小落地：

1. 按 `window.location.protocol` 选择 `ws:`/`wss:`。
2. 等待 authenticate ACK 后再 subscribe。
3. 断线后指数退避 + jitter，页面 `online`/`offline` 参与状态。
4. 每次重连后通过 REST 重新读取当前 workflow/run baseline，再继续接收增量。
5. 增加连接指示器和“立即重连”动作。
6. 事件处理按 topic + event 做显式 switch，避免未知事件静默污染 store。

验收：

- 手动 kill 服务或断网后，UI 显示 disconnected，恢复后自动回到 ready；
- 重连后节点状态、日志、审批请求从 baseline 恢复；
- 认证失败不进入订阅状态；
- 连接状态有组件/E2E 测试，不依赖控制台日志。

#### P0-3 拆分 `App.tsx` 的编排职责

不建议大改目录，先按现有结构做“提取”：

- `useWorkflowDocument`：加载、保存、自动保存、revision/CAS 错误；
- `useRunConnection`：WS、baseline、运行命令、取消、确认；
- `useWorkflowCommands`：新建、打开、导入、打包、预检；
- `EditorLayout`：rail、toolbar、canvas、inspector 的结构；
- `OverlayHost`：demo/chat/settings/preview 的开合与焦点恢复；
- `useCanvasInteractions`：React Flow 事件和 Metanode 导航。

约束：

- 继续使用现有 Zustand，不引入新状态库；
- 业务规则仍只由后端判定；
- 先提取纯编排，不改变用户行为；
- 每个提取步骤都可用现有 Vitest/Playwright 回归。

验收：

- `App.tsx` 只保留组合和少量本地 UI 状态；
- 新增一个 overlay 或一个运行命令不再需要改主画布组件；
- 组件测试可以直接测 controller/hook，而不是渲染整页。

#### P0-4 建立最小 UI 基础组件层

Weft 不需要 DSH 的 `ui-primitives` 规模，但需要统一的：

- `Dialog`/`ConfirmDialog`；
- `Toast`/`ErrorBanner`；
- `EmptyState`；
- `AsyncButton`（loading/disabled）；
- `Field`/`PathField`；
- `ConnectionIndicator`。

优先替换 `window.prompt/confirm/alert`，再逐步收拢按钮和表单样式。

验收：

- 代码中不再出现 `window.prompt/confirm/alert`；
- 所有 modal/alertdialog 有焦点进入、Escape、焦点恢复；
- Playwright 不依赖浏览器原生对话框；
- 确认动作能携带并展示结构化错误。

### P1：减少漂移，改善维护性

#### P1-1 明确本地配置状态的边界

保留即时反馈，但标记为 provisional：

- 本地只判断“字段是否为空/是否存在”用于即时提示；
- 最终可运行状态以 `/validate` 或 run 返回为准；
- 不在前端扩展复杂条件、端口兼容、Loop/Metanode 校验；
- 若某项状态会被运行、缓存或 API 使用，则应移到后端并进入共享契约。

#### P1-2 TanStack Query 二选一

若采用：

- 只管理 server state：workflow 文档、节点类型、运行历史、设置；
- WS 事件只做 invalidate 或局部 patch，不复制 Query 缓存；
- 明确 `staleTime`、重试和错误边界；
- 不把 Query 当作全局 UI 状态库。

若移除：

- 从 `package.json` 删除依赖；
- 把 `api()`、loading、error、取消和并发控制整理成一个小型请求层；
- 在 `03/06` 文档中同步技术事实。

不建议继续保留“安装了但不用”的状态。

#### P1-3 拆分样式但保留令牌

- 保留现有 `:root` 令牌，先把硬编码色值替换为语义变量；
- 按 `canvas/panels/overlays/layout` 拆分 CSS；
- 组件级样式优先靠近组件，避免一个 2463 行全局文件；
- 不引入 Tailwind 或新的 CSS-in-JS，不改变现有视觉方向。

#### P1-4 补上失败路径测试

现有 E2E 已覆盖画布、聊天、确认、执行、历史、Metanode、打包、资源、快捷键。建议补：

- WS 断线/重连/认证失败；
- 409 revision/CAS 冲突后重新读取；
- 401 会话过期；
- 运行中服务重启后的 baseline 恢复；
- 原生对话框替换后的 Escape/焦点/确认。

#### P1-5 修复文档与代码的事实漂移

当前观察到的漂移：

- `03-architecture.md` 前端层写了 `settingsStore`，实际只有 `workflowStore`、`runStore`、`metanodes`；
- `06-engineering.md` 把 TanStack Query 列为主要依赖，但前端未使用；
- 文档中的前端依赖与当前 `frontend/package.json` 版本需要对齐。

参考本文不等于立即修改真源文档。实施时应作为独立 docs 任务处理，按 `AGENTS.md` 同步对应章节。

### P2：等有明确收益再做

- **简单的 UI 区域注册表**：如果面板数量继续增长，可以做 typed `Record<Region, Component>`；不要做 DSH 五类 Slot。
- **流式 Markdown/虚拟化**：先用真实聊天和长日志测量；不要在数据量未到时复制 DSH 的增量 parser。
- **桌面壳**：Tauri/pywebview 可作为 v2 预留；当前 Web + 本地服务已满足产品边界。
- **运行时插件安装**：Weft 的节点扩展已有 `@weft.node` 和 workflow manifest；不需要复制 DSH 的客户端插件市场。

---

## 4. 不建议对 Weft 做的事

|不建议|原因|
| ------| ------------------------------------------------------------|
|引入 Cordis 或类似“一切皆插件”框架|Weft 是单一产品，没有第三方 UI 插件生态；收益低、调试成本高|
|自研浏览器模块加载器|Vite 产物 + 现有 monorepo 已足够；Weft 不需要运行时安装 UI|
|实现完整 Slot/Factory 体系|简单的区域注册和组件组合已能覆盖面板扩展|
|自研 RPC 代码生成器|FastAPI/OpenAPI/Pydantic 已能提供契约源；优先补运行时校验和错误模型|
|把所有 server state 塞进 Zustand|查询缓存、失效和并发应由 Query 或统一请求层处理|
|现在上 Electron/Tauri|发布、签名、自动更新和平台适配成本高；先把 Web 体验和可靠性做好|

---

## 5. 推荐实施顺序

|阶段|目标|完成信号|
| ------| ------------------------------------------------------------| ------------------------------------------------------------|
|1|API 错误模型 + 契约校验|UI 可按 `code` 分支，契约漂移有测试|
|2|WS 连接代际 + 重连 baseline|断线/服务重启后可自愈，状态指示可见|
|3|拆 `App.tsx` + 最小 UI 组件|主流程不再集中在一个文件，原生对话框归零|
|4|配置状态边界 + Query 二选一|前端不扩展业务规则，依赖清单不撒谎|
|5|CSS 拆分 + 失败路径 E2E|样式按区域维护，关键故障有回归|

每个阶段都应按 Weft 现有规则拆成独立 roadmap 任务，完成标准仍是“对应 AC 测试通过 + `poe check` 全绿”，不能因为本文档写了建议就勾掉实现任务。

---

## 6. 参考来源

DSH 官方资料：

- [DeepSeek Harness 仓库](https://github.com/deepseek-ai/deepseek-harness)
- [Web Client architecture](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/web-client.md)
- [Client 包地图](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/client/README.md)
- [Web boot kernel](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/client/web/README.md)
- [Client Modules](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/client/modules/README.md)
- [UI Slots](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/client/ui-slots/README.md)
- [UI Renderer](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/client/ui-renderer/README.md)
- [Connection](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/client/connection/README.md)
- [API Gateway](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/api/gateway/README.md)
- [Desktop](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/desktop/README.md)

Weft 内部依据：

- `docs/03-architecture.md` §9、A-08、A-11
- `docs/05-api.md` §11、§12
- `docs/06-engineering.md` §1、§2、§8
- `frontend/src/App.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/api/ws.ts`
- `frontend/src/stores/workflowStore.ts`
- `frontend/src/stores/runStore.ts`
- `frontend/src/styles.css`