# GUI 与数据交换规范调查：数采设备时间统计、Windmill 与 Weft

|项|值|
| --- | --- |
|日期|2026-11-10|
|状态|调查报告，不是需求或架构真源；WebView2 与调试/结果工作区已由 T7.23/T7.24 实施|
|Weft 基线|当前工作树，版本 `0.4.0`；roadmap 仅剩 T7.10 未完成|
|调查对象|`C:\MyWork\数采设备时间统计`、用户提供的 Windmill 截图、Windmill 官方仓库与文档|
|约束|不替代 `01-prd.md` 至 `08-testing-strategy.md`；任何实施均须另拆 roadmap 任务并同步真源文档|

## 1. 结论先行

三个问题分别回答如下：

1. **是否参考 `数采设备时间统计` 制作 GUI：可以参考交互和任务组织，不应照搬技术实现，也不需要重做 Weft 的现有画布。**最值得借鉴的是“一键完成一组步骤”、步骤状态与过期传播、实时进度与日志、显式预览、结果入口，以及面向任务而非面向组件的界面组织。Weft 已有通用节点编辑器，应保留其左侧节点面板、中间画布、右侧检查器的主结构。
2. **是否先做通用数据交换规范：方法上应“先契约、后节点”，但 Weft 已经完成了这一轮通用定义，不应再建第二套规范。**现有 `Node`/`Port`、六类端口、`ValueRef`、Arrow IPC、运行快照、缓存策略和节点 JSON Schema 已覆盖通用交换层。下一步应通过真实工作流验证这些契约，而不是暂停节点实践去设计一个更抽象的 envelope。
3. **是否参考 Windmill：可以，而且其多项实践能验证 Weft 当前方向。**重点学习声明驱动 UI、测试到指定步骤、按 Run 聚合日志/结果、稳定步骤 ID、小型结果与大数据分离、运行历史与差异展示。不要引入它的 PostgreSQL 队列、多租户、部署体系、S3 依赖或动态 JavaScript 输入表达式。

一句话建议：

> **保留 Weft 当前架构，以参考项目作为 UX 与真实迁移案例，以 Windmill 作为成熟交互和对照架构；只补齐有实际证据的缺口，不重启 GUI 或数据协议。**

## 2. 调查范围与证据边界

本报告基于：

- Weft 的 PRD、架构、数据模型、roadmap，以及当前 SDK、端口、值引用和前端代码；
- `数采设备时间统计` 的 README、AGENTS 和 `gopro_stereo_sort.py` 相关实现；
- 用户提供的 Windmill Flow Editor 截图；
- Windmill 官方 OpenFlow、Flow Editor、Jobs、Worker、数据处理与仓库文档，链接见第 9 节。

未执行两个 GUI 的新一轮人工可用性测试，未做 Windmill 源码级性能审计，也未把参考项目迁移到 Weft。因此，文中的“已存在”是对当前代码和文档的静态核查；涉及体验的改进仍需真实用户操作验证。本调查不勾选任何 roadmap 任务。

## 3. Weft 已经具备的基础

### 3.1 GUI 不是空白起点

当前 `frontend/src/App.tsx` 已组合出完整的编辑器：

- 左侧应用栏和节点面板；
- 中间 React Flow 画布；
- 右侧由节点声明驱动的参数检查器；
- 保存、运行、停止、执行到此/从此/单节点；
- 日志、运行历史、端口预览、Agent 轨迹、审批和设置；
- 示例、导入、打包、聊天和 Metanode 导航。

这与截图中 Windmill 的“导航 + 中央流程 + 右侧设置”属于同一类信息架构。差异主要是 Weft 面向自由数据流图和端口数据，Windmill 更强调代码步骤、测试和部署。没有必要为了获得类似布局而重写前端。

此前 `docs/ref/dsh-gui-and-weft-improvements.md` 提出的结构化 API 错误、WS 重连恢复、App 编排拆分、统一对话框、配置状态边界和样式拆分，已分别由 T7.18–T7.22 落地。新的 GUI 工作不应重复这些旧建议。

### 3.2 通用交换层也已经存在

|契约层|当前定义|作用|
| --- | --- | --- |
|节点声明|`weft_sdk.Node`、版本、lane、缓存策略、工具能力|规定节点如何执行与被引用|
|端口|`Port`、`DynamicPortGroup`、`PortType`|规定连接名称、类型和兼容关系|
|参数|JSON Schema draft 2020-12、`ui_hints`|驱动后端校验和前端表单|
|运行时值|`ValueRef(table | json | none)`|统一 IPC、缓存和 Run 输出引用|
|大表|Arrow IPC 文件 + memory-map|避免把表格本体塞入 stdio JSON|
|运行记录|冻结图、节点 manifest、状态、错误、输出快照|保证历史可回看和结果可追踪|
|演进|`schema_version`、`node_version`、参数迁移|支持契约版本升级|

代码依据包括：

- `packages/weft-sdk/src/weft_sdk/nodes.py`；
- `packages/weft/src/weft/workflow/ports.py`；
- `packages/weft/src/weft/workflow/values.py`；
- `docs/03-architecture.md` §2–4；
- `docs/04-data-model.md` §2–6、§11。

因此，“先不考虑具体功能节点，先定义通用交换规范”作为项目早期顺序是正确的，但对当前 Weft 来说，这个阶段对应 T1.1–T1.3，已经完成。现在应做的是**维护契约一致性并用纵向场景检验它**。

## 4. `数采设备时间统计` 能提供的经验

### 4.1 它与 Weft 的 GUI 目标不同

参考项目是一个固定业务流水线：扫描目录 → 整理与补齐 → 自检 → 生成汇总与台账 → 可选上传。它的 GUI 是任务控制台；Weft 是通用工作流设计器加执行器。

所以不应把 Weft 画布替换成固定五步页面，但可以把“任务控制台”的清晰度带入设计器和运行视图。

### 4.2 值得借鉴的交互

1. **主任务只有一个明确入口。**“启动”按顺序运行必要步骤，未配置共享目录时跳过上传，失败后停止。对 Weft 的启示是示例和模板应提供清晰的默认运行路径，而不是让新用户先理解所有节点。
2. **步骤状态包含依赖过期。**上游变化后，下游标记为 `stale`，避免把旧成功误认为当前结果。Weft 已有更细的缓存与节点状态，可借鉴其面向用户的解释方式，但不能另建一套覆盖引擎状态的规则。
3. **进度、日志、取消围绕同一任务。**参考项目将子进程输出、两级进度、退出码和取消集中到一个 `WebJob`。Weft 已有 Run/WS/日志模型，应继续以 Run 为中心，不为不同面板建立平行任务状态。
4. **预览与副作用分开。**`--dry-run`、只重新统计、整理、上传是不同动作；网页不会通过隐式默认回答触发拷贝。Weft 应继续突出端口预览、资源预检和副作用确认。
5. **结果有直接出口。**汇总页、详细报告和 Excel 台账都可从对应步骤打开。Weft 可强化“运行成功后下一步做什么”：查看输出端口、打开生成文件、查看历史或打包，而不是只显示绿色节点。
6. **目录、报告、设置是不同信息层。**这避免所有内容挤进一张图。Weft 已有历史、端口、设置等面板，宜改善导航和可发现性，而非继续堆叠常驻面板。

### 4.3 值得借鉴的领域建模

参考项目的关键资产不是网页，而是厂家适配后形成的统一模型：

- `Material.layout = file | flat | tree` 统一表示单文件、平铺文件组和目录树；
- 厂家适配器只负责发现和读取时间；
- 命名、复制、报告、统计只消费统一模型，不再按厂家分支；
- 报告带 `schema_version`、相对路径和哈希/大小校验，兼顾迁移与旧版本读取；
- 读取旧产物失败时宁可不写，避免用空结果覆盖人工数据。

这与 Weft 的“节点声明与实现分离”“显式缓存输入”“路径相对 Root”“schema 迁移”方向一致。可迁移的是**先统一领域输入，再让通用执行层处理**的原则。

### 4.4 不应照搬的部分

- 单文件承载全部业务、CLI、HTTP 服务和 HTML；
- 内联 HTML/CSS/JS、轮询日志和会话内步骤状态；
- 无自动化测试的回归方式；
- 仅靠 Host/Origin 的本机安全边界；
- 把固定业务流程当成通用 DAG 引擎。

Weft 在模块化、认证、测试、历史快照和通用执行方面已经更强，不应退化。

## 5. Windmill 调查与可迁移经验

### 5.1 截图反映的设计

用户截图展示的是 Windmill Flow Editor，而非 `数采设备时间统计` 的界面。其主要结构为：

- 左侧全局导航：Runs、Variables、Resources、Assets、Triggers、Schedules 等；
- 中央流程：Triggers、Input、Result，以及 Test flow；
- 顶部设置、Error Handler、Test flow 和 Deploy；
- 右侧 Settings：Metadata、Runtime、Permissions，当前展示 Summary、Path、Description。

可借鉴的是**编辑、测试、流程级设置和错误处理入口清楚**。但 `Deploy` 和 `Permissions` 服务于 Windmill 的多用户、版本发布模型；Weft 是本地单用户、自包含目录，不应为视觉相似而复制这两个概念。

### 5.2 官方架构与数据流事实

Windmill 官方资料显示：

- OpenFlow 用带稳定 `id` 的模块组成 DAG，后续步骤可通过 `results.<id>` 引用前序结果；
- `input_transforms` 支持静态 JSON 或受限 JavaScript 表达式，将前序结果、变量和资源映射到脚本参数；
- 模块支持循环、分支、重试、超时、缓存、暂停/审批和错误处理；
- Flow Editor 支持自动保存草稿、测试整个流程、测试到指定步骤、单独测试、JSON/YAML 导出和版本 diff；
- 每个 Job 有独立 ID、参数、状态、日志、结果和元数据，Flow Job 负责编排子步骤 Job；
- 普通 Job 结果序列化为 JSON 并存数据库，官方明确建议结果保持小对象，大数据集放入对象存储，步骤间传递 `{"s3": "path/to/file"}` 这样的引用；
- Server 和 Worker 无状态，PostgreSQL 保存队列和全部应用状态，Worker 按 tag 拉取任务；
- 数据管道可使用 DuckDB 与外部存储，但计算仍按单个步骤在单节点执行，不等于每一步都分布式。

### 5.3 与 Weft 的对照

|Windmill 实践|Weft 当前对应物|建议|
| --- | --- | --- |
|稳定模块 ID 与 `results.<id>`|节点 ID、命名输出端口、图边|保留 Weft 的显式端口连接，不增加隐式全局结果总线|
|静态值/JS 输入转换|节点 params、`$var`、数据边|保留可校验模型；不引入任意 JS 表达式作为第二套数据流|
|声明生成参数 UI|Node JSON Schema + SchemaForm|已对齐，继续改善复杂字段和结果选择器即可|
|Test flow / Test up to / 单步测试|运行、执行到此、仅执行本节点|能力已有；可改进测试输入与结果入口的可发现性|
|Job 日志、结果、元数据与进度|Run、节点状态、日志、端口快照、WS|已对齐；保持同一 Run 契约|
|小 JSON 入数据库，大数据传对象引用|小 JSON inline，大 JSON/Table 落文件并传 ValueRef|已对齐，而且 Arrow 更适合表格数据流|
|流程 diff 和部署历史|冻结 Run 快照、revision/CAS|可评估设计稿 diff；不必引入独立部署生命周期|
|Flow group/subflow|Metanode、便签|已有对应能力，无需新增容器语义|
|重试、超时、暂停|取消、超时、确认；部分流程节点已有相应语义|只按具体 AC 增加；副作用节点禁止默认自动重试|
|Worker tag/group|三条 execution lane、独立 Worker pool|保留简单 lane；当前不需要分布式队列和标签系统|
|PostgreSQL 保存全部状态|`.weft` 目录和文件型 Run|维持本地文件真源，不引入数据库|

### 5.4 最值得吸收的 UX 细节

以下只是候选改进，不代表立即实施：

1. **前序输出选择器。**在参数或连线上下文中展示可连接的上游端口、类型和最近输出，降低用户寻找结果的成本；兼容判断仍由后端负责。
2. **测试运行抽屉。**集中展示触发输入、变量覆盖、执行范围和结果，复用现有 run API，不创建另一套“测试 Run”模型。
3. **流程级说明更可见。**将名称、用途、输入要求、输出物和外部资源以简洁摘要呈现，帮助交接；字段必须来自现有工作流契约。
4. **运行后结果页签。**把当前 Run 的状态、日志、输出、错误、审批和历史入口集中呈现，但保留现有数据模型。
5. **设计版本 diff。**若真实交接表明需要，再比较两个 workflow 快照；不要复制 Windmill 的 Deploy 权限体系。

## 6. 数据交换规范：应维护什么，不应新增什么

### 6.1 先区分三种“数据交换”

1. **设计时契约**：`workflow.json`、节点类型/版本、端口、params、变量绑定、位置与说明。
2. **运行时契约**：节点输入输出、`ValueRef`、Arrow/JSON 文件、哈希、取消、错误和 Run 快照。
3. **外部资源契约**：文件路径、Excel 描述符、目录、外部系统引用，以及它们的副作用和失效规则。

把三者都包成一个通用 JSON 消息并不会更简单，反而会丢失表格类型、副作用语义、缓存边界和 UI 预览能力。当前分层是正确的。

### 6.2 新增节点时应遵守的最小通用清单

无需先写新协议文档；每个新节点至少回答：

- 类型与 `node_version` 是什么；
- 输入/输出端口名和六类端口中的哪一类；
- 参数 JSON Schema 与变量绑定方式是什么；
- 在 `trusted_worker`、`trusted_service` 或 `sandboxed` 哪条 lane 执行；
- 是 `pure`、`volatile` 还是 `side_effect`；
- 哪些外部文件/目录需要内容哈希或资源预检；
- 输出如何进入 `ValueRef` 和 Run 快照，UI 如何预览；
- 失败、取消、版本迁移与打包行为是什么。

这就是当前通用定义的使用方式。新节点不应私自定义绕过这些规则的 IPC 格式。

### 6.3 对素材、目录树和大文件的约定

若将参考项目迁移到 Weft，建议：

- 视频、MCAP、H265、WAV 和目录本体**不进入 Arrow 表格，也不内联进 JSON**；
- 用 Table 表达素材清单、文件清单、时间区间、配对结果和报告记录；
- 用路径、相对 Root 路径、大小和内容哈希引用本体；
- 复制、改名、报告写入、上传都声明 `side_effect`，不得被缓存跳过；
- dry-run 只生成计划表或预览，不写目标；
- 只有在多个真实工作流都证明六类端口不足时，才讨论新的 `file`/`bundle` 端口；届时必须同时定义序列化、哈希、兼容矩阵、缓存、预览、安全和迁移，而不是只增加一个枚举值。

一个可行的纵向验证图如下，仅用于说明契约如何承载真实场景，不是节点实现承诺：

```text
Trigger / Variable(data_root)
  → 扫描为素材与文件 Table
  → 读取元数据并配对，仍为 Table
  → 生成改名/复制计划 Table
  → 端口预览（dry-run）
  → 显式执行复制（side_effect）
  → 生成报告/台账（side_effect）
  → 端口预览、Excel 或文件输出
```

这条链能同时检验 Table、Variable、外部文件哈希、局部执行、副作用、Run 快照和 GUI 结果入口，比脱离场景继续抽象协议更有价值。

## 7. 推荐推进顺序

1. **不重写、不新增第二套协议。**以当前 Weft `0.4.0` 为基线，先完成 T7.10 所需的真机、性能、双机和人工验收。
2. **做一次有脚本的 GUI 对照评估。**选“从零搭建 CSV 流程”“执行到失败节点并查看输入”“打开历史输出/生成文件”三个任务，对照参考项目和 Windmill 记录点击路径、误导点和结果可发现性。不要仅凭截图决定重构。
3. **只把已证实的问题拆成 roadmap 任务。**优先复用现有 Run、NodeTypeDecl、PortView、HistoryPanel 和 SchemaForm，避免新建平行状态或 API。
4. **把参考项目作为后续真实迁移试点。**先跑通一个只读/dry-run 纵向切片，再接入显式复制与报告副作用；用实际缺口推动通用契约演进。
5. **每次契约扩展都带兼容与测试成本。**同步 Pydantic/TS/API/文档、缓存键、历史读取、节点迁移和契约测试；不能只让当前节点跑通。

## 8. 最终取舍

|事项|决定建议|
| --- | --- |
|参考 `数采设备时间统计` 的 GUI|是，借鉴任务流、状态解释、日志/进度、预览与结果入口；保留 Weft 通用画布|
|参考其代码实现|否，不复制单文件 Web UI、轮询或无测试结构|
|重新制作通用数据交换规范|否，现有 Node/Port/ValueRef/Arrow/Run 契约就是通用层|
|先完全暂停节点开发|否，以真实纵向切片检验契约；发现共性缺口再扩展|
|参考 Windmill|是，重点参考声明驱动、测试体验、Run 可观测性和大结果引用|
|引入 Windmill 架构或代码|否，不引入 PostgreSQL、多租户、S3、部署权限体系或 AGPL 代码|
|新增 file/bundle 端口|暂不建议；先用路径引用和 Table 清单验证真实需求|

## 9. 参考来源

### Weft 与本地参考项目

- `docs/01-prd.md`、`docs/03-architecture.md`、`docs/04-data-model.md`、`docs/07-roadmap.md`；
- `docs/ref/dsh-gui-and-weft-improvements.md`；
- `frontend/src/App.tsx`；
- `packages/weft-sdk/src/weft_sdk/nodes.py`；
- `packages/weft/src/weft/workflow/ports.py`、`values.py`；
- `C:\MyWork\数采设备时间统计\README.md`、`AGENTS.md`、`gopro_stereo_sort.py`。

### Windmill 官方资料

- [Windmill GitHub 仓库：技术栈、架构与许可](https://github.com/windmill-labs/windmill)
- [OpenFlow Spec](https://www.windmill.dev/docs/openflow)
- [Flow editor](https://www.windmill.dev/docs/flows/flow_editor)
- [Flow editor components](https://www.windmill.dev/docs/flows/editor_components)
- [Jobs](https://www.windmill.dev/docs/core_concepts/jobs)
- [Workers and worker groups](https://www.windmill.dev/docs/core_concepts/worker_groups)
- [ETL and data processing](https://www.windmill.dev/docs/core_concepts/data_pipelines)
- [High availability and failover](https://www.windmill.dev/docs/advanced/high_availability)

许可补充：Windmill 仓库说明其开源部分采用 AGPLv3，API clients 与 OpenAPI spec 为 Apache 2.0，官方 Community Edition 还包含不同的产品许可边界。本报告只吸收公开设计经验；若未来复制代码、规范文本或分发其产物，必须另做许可证审查。
