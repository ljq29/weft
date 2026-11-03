# 02-user-stories.md

**Weft 用户故事与验收标准**

|项|值|
| ------| ----------------------------------------------|
|版本|v0.1（草稿）|
|状态|待确认|
|上游|`01-prd.md` §7 功能需求|
|下游|`06-nodes-v1.md`​（节点参数）、​`08-roadmap.md`（任务拆解）、测试代码|

---

## 0. 使用约定

### 0.1 本文档的用途

- 每个 PRD 需求（​`F-XXX-NN`​）至少对应一条用户故事；每条故事的验收标准（AC）是**可直接转写为测试用例**的 Given/When/Then。
- agent 实现任务时，以 AC 作为"完成"的客观定义；AC 未全部通过，任务不算完成。
- AC 中的具体数值、文件名、节点名均为**规范性**内容，实现必须与之一致（节点名以 ​`06-nodes-v1.md` 为准，本文若冲突以节点文档为准）。

### 0.2 格式

```
### US-<EPIC>-<NN> <标题>                       [优先级] [测试层级]
作为 <角色>，我想要 <能力>，以便 <价值>。
关联：F-XXX-NN, ...
AC-1  Given ... When ... Then ...
AC-2  ...
```

### 0.3 角色

|角色|含义|
| ------| -----------------------------------------------|
|**设计者**|在画布上搭建、调试工作流的人（v1 = 作者本人）|
|**运行者**|接收打包工作流并运行、改参数的人（同事）|
|**系统**|Weft 服务自身（用于描述自动行为）|
|**Agent**|工作流内的 LLM agent（作为受限主体出现）|

### 0.4 测试层级标签

|标签|含义|运行环境|
| ------| -----------------------------------------------| --------------------------------------------|
|`[unit]`|纯 Python 单元测试，无外部依赖|任意 OS、CI|
|`[int]`|集成测试：服务 + 引擎 + 文件系统，可 mock LLM|任意 OS、CI|
|`[int-win]`|需要真实 Excel / Sandboxie / pi|Windows 本机，手动或自托管 runner|
|`[e2e]`|浏览器端到端（Playwright）|CI（Linux，Excel 相关节点用 fake backend）|
|`[manual]`|需人工确认的体验类标准（时间、观感）|验收阶段手动|

### 0.5 通用前置条件（除非故事另有说明）

- Weft 服务已启动，监听 ​`127.0.0.1:7788`，浏览器已打开 UI。
- 存在一个已打开的工作流 ​`demo.weft/`​，Root 内 ​`data/`​ 含 ​`sales.csv`​（1000 行，列：​`date, region, product, amount, note`​）与 ​`ref.xlsx`。
- 用户级配置中已存在一个名为 ​`default` 的 LLM 配置，指向可用的 OpenAI 兼容端点（测试中以 mock 服务器替代）。
- Excel 相关故事：Windows 本机已安装桌面版 Excel，且用户已打开 ​`ref.xlsx`。

### 0.6 Epic 索引

|Epic|主题|故事数|
| ------| --------------| --------|
|DES|工作流设计|11|
|EXE|执行与调试|14|
|XLS|Excel 联动|12|
|TBL|表格与文件|10|
|AGT|Agent|12|
|SBX|沙箱与安全|9|
|TRG|触发器|8|
|PKG|可移植与打包|7|
|SET|设置与运维|5|

---

## 1. Epic DES：工作流设计

### US-DES-01 新建工作流 [P0] [int][e2e]

作为设计者，我想要新建一个工作流并指定其所在目录，以便从空白开始设计。  
关联：F-DES-07, F-PKG-01

- AC-1 Given UI 首页 When 点击"新建工作流"并输入名称 ​`weekly`​ 与父目录 ​`D:\flows`​ Then 系统创建 ​`D:\flows\weekly.weft\`​，内含 ​`workflow.json`​（schema 版本为当前版本、节点列表仅含一个 ​`Trigger`​）、​`pyproject.toml`​、​`data/`​、​`nodes/`​、​`prompts/`​、​`.gitignore`​（排除 ​`.runs/`​ 与 ​`.venv/`）。
- AC-2 Given 目标目录已存在同名 ​`.weft` When 新建 Then 系统拒绝并提示"目录已存在"，不覆盖任何文件。
- AC-3 Given 新建完成 When 查看画布 Then 画布显示一个 ​`Trigger` 节点，状态为"已配置"（黄）。

### US-DES-02 添加节点 [P0] [e2e]

作为设计者，我想要从节点面板把节点拖到画布上，以便组装工作流。  
关联：F-DES-01, F-DES-02

- AC-1 Given 画布 When 在节点面板搜索框输入 ​`read`​ Then 面板只显示名称或描述包含 ​`read`（不区分大小写）的节点，且按分类分组。
- AC-2 Given 面板中的 ​`Excel Read Range`​ When 拖到画布坐标 (300, 200) 释放 Then 画布出现该节点，​`workflow.json`​ 中新增节点记录含 ​`id`​（UUID）、​`type`​、​`position: {x: 300, y: 200}`​、​`params`（全部为默认值）。
- AC-3 Given 新添加的节点含必填参数未填 Then 节点显示"未配置"（红）状态。
- AC-4 Given 面板 When 双击某节点类型 Then 节点添加到画布当前视口中心。

### US-DES-03 连接端口 [P0] [unit][e2e]

作为设计者，我想要在节点端口之间拖出连线，且系统只允许类型兼容的连接，以便避免运行期才发现类型错误。  
关联：F-DES-03

- AC-1 Given ​`Read CSV`​ 的 Table 输出端口 When 拖到 ​`Row Filter`​ 的 Table 输入端口 Then 连线建立，​`workflow.json`​ 的 ​`edges`​ 新增记录含 ​`source, sourcePort, target, targetPort`。
- AC-2 Given ​`Read CSV`​ 的 Table 输出端口 When 拖到 ​`Excel Write Table` 的 Excel 输入端口 Then 连线被拒绝，目标端口显示红色高亮，画布顶部提示"Table 端口不能连接到 Excel 端口"。
- AC-3 Given 一个输入端口已有连线 When 再拖一条连线到该端口 Then 旧连线被替换（输入端口只允许一条入边），Tool 端口与 Variable 端口除外（允许多条）。
- AC-4 Given 连线会形成环路（非 Loop Start/End 对） When 释放 Then 连线被拒绝，提示"不允许形成循环，请使用 Loop 节点"。
- AC-5 ​`[unit]`​ 端口兼容性由后端 ​`ports.is_compatible(src_type, dst_type)` 决定，前端仅做展示；对 6 种类型的 36 种组合有完整的单元测试表。

### US-DES-04 编辑节点参数 [P0] [e2e][unit]

作为设计者，我想要在侧栏表单中编辑节点参数，表单由节点声明自动生成，以便不用记参数名。  
关联：F-DES-04

- AC-1 Given 选中 ​`Row Filter`​ 节点 Then 侧栏显示其参数表单：​`column`​（下拉，候选项来自上游表的列名；上游未执行则为自由文本）、​`operator`​（枚举）、​`value`（文本）。
- AC-2 Given 修改 ​`value`​ 为 ​`100`​ 并失焦 Then ​`workflow.json`​ 中该节点 ​`params.value`​ 更新为 ​`"100"`，节点状态从"已执行"退回"已配置"，其下游节点同样退回。
- AC-3 Given 必填参数留空 Then 表单该字段显示红色错误，节点状态为"未配置"。
- AC-4 ​`[unit]`​ 每个节点类型的参数 schema 为 JSON Schema（draft 2020-12），​`GET /api/nodes/types`​ 返回全部 schema；有测试确保所有内置节点的 schema 可被 ​`jsonschema` 校验器加载。
- AC-5 Given 参数类型为"路径" Then 表单提供文件选择器，选中的路径若在 Root 内则自动转为相对路径，若在 Root 外则保留绝对路径并显示黄色警告"绝对路径不可移植"。

### US-DES-05 节点状态指示 [P0] [e2e]

作为设计者，我想要一眼看出每个节点处于什么状态，以便知道工作流跑到哪了。  
关联：F-DES-05

- AC-1 节点底部有状态条，颜色与含义：红 = 未配置、黄 = 已配置未执行、绿 = 已执行、蓝色流动动画 = 执行中、红叉图标 = 错误、灰 = 已跳过（分支未命中）。
- AC-2 Given 工作流执行中 When 后端推送 ​`node.status` 事件 Then 对应节点状态在 200 ms 内更新。
- AC-3 Given 节点为错误态 When 悬停 Then 显示错误摘要（第一行）；点击则在侧栏显示完整 traceback。

### US-DES-06 绑定流变量到参数 [P0] [e2e][int]

作为设计者，我想要任何参数字段都能绑定一个流变量，以便路径、阈值等可以在运行时注入。  
关联：F-DES-06

- AC-1 Given ​`Excel Write Table`​ 的 ​`workbook` 参数 When 点击字段右侧的"变量"图标 Then 字段切换为变量选择模式，列出所有通过 Variable 端口到达本节点的变量名。
- AC-2 Given 选择变量 ​`target_wb`​ Then ​`workflow.json`​ 中该参数存为 ​`{"$var": "target_wb"}`，表单显示为变量标签。
- AC-3 ​`[int]`​ Given 运行时上游 ​`Variable`​ 节点产出 ​`target_wb = "汇总.xlsx"`​ Then ​`Excel Write Table`​ 实际收到的 ​`workbook`​ 参数为 ​`"汇总.xlsx"`。
- AC-4 Given 绑定的变量在运行时不存在 Then 节点执行失败，错误信息为 ​`Flow variable 'target_wb' not found`。

### US-DES-07 自动保存与脏标记 [P0] [e2e][int]

作为设计者，我想要修改自动保存，并且知道是否有未保存内容，以便不丢工作。  
关联：F-DES-07

- AC-1 Given 画布有任何修改 Then 标题栏显示 ​`*`​ 脏标记；2 秒无新修改后自动保存到 ​`workflow.json`，脏标记消失。
- AC-2 Given 按 ​`Ctrl+S` Then 立即保存。
- AC-3 Given 自动保存失败（磁盘只读） Then 脏标记保持并弹出错误提示，不丢失内存中的修改。
- AC-4 ​`[int]`​ 保存是原子的：先写 ​`workflow.json.tmp`​ 再 rename；中途进程被杀不会留下损坏的 ​`workflow.json`。

### US-DES-08 撤销/重做、复制/粘贴、框选 [P0] [e2e]

作为设计者，我想要常规编辑操作，以便高效调整图。  
关联：F-DES-01

- AC-1 ​`Ctrl+Z`​ / ​`Ctrl+Y` 对添加/删除节点、连线、移动、参数修改均有效，历史深度 ≥ 50。
- AC-2 框选多个节点后 ​`Ctrl+C`​ / ​`Ctrl+V`​ Then 粘贴的节点获得新 ​`id`，内部连线保留，与外部的连线不保留，位置整体偏移 (40, 40)。
- AC-3 ​`Delete` 删除选中节点及其所有连线。

### US-DES-09 Metanode 折叠与展开 [P1] [e2e][int]

作为设计者，我想要把一组节点折叠成一个复合节点，以便画布整洁并可复用。  
关联：F-DES-08

- AC-1 Given 框选 3 个相连节点 When 右键"折叠为 Metanode" Then 画布显示一个 Metanode，其输入/输出端口为原选区与外部的所有连线端口，连线自动重连。
- AC-2 Given 双击 Metanode Then 进入子画布编辑，面包屑显示 ​`demo > Metanode 1`。
- AC-3 ​`[int]`​ ​`workflow.json`​ 中 Metanode 存为 ​`type: "metanode"`​，​`params.graph` 内嵌子图（节点、边），执行语义与展开后等价。
- AC-4 右键"展开 Metanode"可逆操作，恢复原节点与连线。

### US-DES-10 节点注释与便签 [P1] [e2e]

作为设计者，我想要给节点加注释、在画布加便签，以便交接时别人看得懂。  
关联：F-DES-09

- AC-1 节点侧栏有"注释"字段，内容显示在节点下方（截断 60 字符，悬停全文）。
- AC-2 画布右键"添加便签"，便签支持 Markdown、可调大小、可改底色，存于 ​`workflow.json`​ 的 ​`notes` 数组。

### US-DES-11 节点面板与画布的基本导航 [P0] [e2e]

作为设计者，我想要缩放、平移、适应视图，以便处理大图。  
关联：F-DES-01

- AC-1 滚轮缩放（0.25x–2x），空格+拖拽或中键平移，​`Shift+1`​ 适应全图，​`Shift+2` 适应选中。
- AC-2 画布右下角有小地图。
- AC-3 视口位置与缩放存于 ​`workflow.json`​ 的 ​`viewport`，重新打开时恢复。

---

## 2. Epic EXE：执行与调试

### US-EXE-01 整体运行 [P0] [int][e2e]

作为设计者，我想要一键运行整个工作流，以便看到结果。  
关联：F-EXE-01

- AC-1 Given 一个 5 节点线性工作流（​`Trigger → Read CSV → Row Filter → GroupBy → Write CSV`​） When 点击"运行" Then 节点按拓扑顺序依次变为执行中、已执行；​`data/out.csv`​ 生成；运行状态为 ​`succeeded`。
- AC-2 ​`[int]` Given 两个无依赖的分支 Then 两分支节点并行执行（通过记录各节点 start/end 时间戳验证存在重叠）。
- AC-3 Given 工作流存在"未配置"节点 When 点击运行 Then 拒绝运行，列出未配置节点。
- AC-4 ​`[int]`​ ​`POST /api/workflows/{id}/runs`​ 返回 ​`{run_id}`​，状态码 202；运行完成后 ​`GET /api/runs/{run_id}`​ 返回 ​`status: succeeded` 与各节点状态。

### US-EXE-02 执行到此 [P0] [int][e2e]

作为设计者，我想要只执行到某个节点为止，以便调试时不跑整条链。  
关联：F-EXE-02

- AC-1 Given 右键 ​`GroupBy`​ 选择"执行到此" Then 只执行 ​`Trigger → Read CSV → Row Filter → GroupBy`​，​`Write CSV` 保持"已配置"状态。
- AC-2 Given ​`Read CSV`​ 与 ​`Row Filter`​ 已有有效缓存 Then 它们不重跑（节点日志无新条目），只执行 ​`GroupBy`。

### US-EXE-03 从此开始 / 仅执行本节点 / 重置 [P0] [int][e2e]

作为设计者，我想要更多局部执行操作，以便精准调试。  
关联：F-EXE-02

- AC-1 "从此开始"：Given 上游节点均已执行 When 对 ​`Row Filter`​ 选择"从此开始" Then 执行 ​`Row Filter` 及其全部下游。上游有未执行节点时拒绝并提示。
- AC-2 "仅执行本节点"：上游均已执行时只执行该节点，下游不执行且退回"已配置"。
- AC-3 "重置"：节点及其所有下游退回"已配置"，对应缓存文件删除。
- AC-4 "重置全部"：所有节点退回"已配置"，​`.runs/cache/` 清空。

### US-EXE-04 节点输出缓存 [P0] [unit][int]

作为系统，我要缓存节点输出并在输入与参数未变时复用，以便局部执行快速。  
关联：F-EXE-03

- AC-1 ​`[unit]`​ 缓存键 = ​`sha256(node_type + node_version + canonical_json(params) + 各输入端口的内容哈希)`；参数对象的键顺序不影响哈希。
- AC-2 ​`[int]`​ Given ​`Read CSV`​ 已执行 When 修改 ​`data/sales.csv`​ 内容 Then 下次运行 ​`Read CSV` 重跑（文件节点的输入哈希包含文件 mtime + size）。
- AC-3 ​`[int]`​ Table 输出缓存为 ​`.runs/cache/<node_id>/<port>.arrow`​；Variable/Message 为 ​`.json`​；Excel 引用为描述符 ​`.json`（见 Q1）。
- AC-4 Given 缓存文件损坏或版本不匹配 Then 视为未命中，重跑而非报错。
- AC-5 "打开工作流"时，已有缓存的节点显示为"已执行"状态。

### US-EXE-05 实时状态推送 [P0] [int][e2e]

作为设计者，我想要执行过程实时可见，以便不盲等。  
关联：F-EXE-04

- AC-1 ​`[int]`​ 连接 ​`WS /api/ws`​ 后，运行期间收到事件序列：​`run.started`​ → 若干 ​`node.started`​ / ​`node.progress`​ / ​`node.log`​ / ​`node.finished`​ / ​`node.failed`​ → ​`run.finished`​；每个事件含 ​`run_id, node_id, ts`。
- AC-2 ​`[int]`​ agent 节点运行时推送 ​`node.stream`​ 事件，​`delta` 字段为增量文本，顺序与 LLM 输出一致。
- AC-3 Given WebSocket 断线重连 Then 客户端通过 ​`GET /api/runs/{id}` 补齐状态，不丢最终结果。
- AC-4 ​`[e2e]` 底部日志面板按节点分组显示日志，支持筛选级别（INFO/WARN/ERROR）与按节点过滤。

### US-EXE-06 端口视图 [P0] [int][e2e]

作为设计者，我想要点击任何已执行的输出端口直接看数据，以便不用加调试节点。  
关联：F-EXE-05

- AC-1 Given ​`Row Filter` 已执行 When 点击其 Table 输出端口 Then 弹出表格预览：显示列名、类型、总行数，分页每页 100 行，可按列排序，可复制单元格。
- AC-2 Excel 端口显示描述符摘要：工作簿名、工作表、地址、行列数。
- AC-3 Message 端口显示消息列表（role、内容、tool call）；Variable 端口显示键值表。
- AC-4 ​`[int]`​ ​`GET /api/runs/{run_id}/nodes/{node_id}/ports/{port}?offset=0&limit=100`​ 返回 Arrow IPC 流（​`Content-Type: application/vnd.apache.arrow.stream`）或 JSON，依端口类型而定。
- AC-5 未执行的端口点击时提示"节点未执行"。

### US-EXE-07 错误处理与 Try/Catch [P0] [int][e2e]

作为设计者，我想要节点失败时信息清晰且不丢已完成结果，并能用 Try/Catch 兜底，以便工作流健壮。  
关联：F-EXE-06

- AC-1 Given ​`Row Filter`​ 引用了不存在的列 When 运行 Then ​`Row Filter`​ 为错误态，​`GroupBy`​ / ​`Write CSV`​ 保持"已配置"，​`Read CSV`​ 保持"已执行"且缓存可用；运行状态为 ​`failed`。
- AC-2 错误信息包含：节点名、异常类型、消息、完整 traceback、输入快照（Table 前 20 行）。
- AC-3 ​`[int]`​ Given ​`Try Start → 可能失败的节点 → Try End`​，且 ​`Try End`​ 的 ​`on_error`​ 分支已连接 Then 失败时执行 ​`on_error`​ 分支，运行状态为 ​`succeeded`​，​`Try End`​ 输出的 ​`error` 变量含错误信息。
- AC-4 用户 Python 节点抛出的异常，traceback 只显示用户代码部分，隐藏引擎内部帧。

### US-EXE-08 取消运行 [P0] [int][e2e]

作为设计者，我想要中止正在进行的运行，以便不等待错误的长任务。  
关联：F-EXE-07

- AC-1 Given 一个运行中的 ​`Wait`​ 节点（30 s） When 点击"停止" Then 运行在 2 s 内变为 ​`cancelled`​，​`Wait` 节点为"已取消"状态，下游不执行。
- AC-2 ​`[int]`​ 正在执行的 Python Script 子进程收到终止信号（Windows：​`CTRL_BREAK_EVENT`，3 s 后未退出则 kill）。
- AC-3 正在执行的 Agent Loop 在当前 LLM 调用返回后停止，不再发起新轮次；进行中的 HTTP 请求被取消。
- AC-4 已完成节点的缓存保留。

### US-EXE-09 运行历史 [P1] [int][e2e]

作为设计者，我想要回看过去的运行记录，以便排查问题。  
关联：F-EXE-08

- AC-1 ​`GET /api/workflows/{id}/runs?limit=20`​ 返回最近运行列表：​`run_id, trigger_source, started_at, finished_at, status`。
- AC-2 每次运行的元数据与日志存于 ​`.runs/<run_id>/`​（​`meta.json`​、​`log.jsonl`​、​`nodes/<node_id>.json`）。
- AC-3 UI "历史"面板列出运行，点击可查看各节点状态与日志（只读）。
- AC-4 保留策略：默认保留最近 50 次，超出按时间删除，可在设置中修改。

### US-EXE-10 循环：按行 [P0] [int]

作为设计者，我想要对表的每一行执行一段子图，以便逐项处理。  
关联：F-EXE-09

- AC-1 Given ​`Loop Start (Row)`​ 输入 10 行表，循环体为 ​`Variable → LLM Call → Table Creator`​，​`Loop End (Collect)`​ Then 循环体执行 10 次，每次 ​`Loop Start`​ 的 Variable 端口输出当前行各列为流变量，​`Loop End` 输出 10 行拼接表。
- AC-2 循环体内某次失败时整个循环失败（默认）；​`Loop End`​ 参数 ​`on_error: skip`​ 时跳过该次并在输出加 ​`_error` 列。
- AC-3 UI 上循环体节点显示当前迭代 ​`3 / 10`。
- AC-4 ​`[int]` 循环体内节点的缓存键包含迭代序号，不会跨迭代误命中。

### US-EXE-11 循环：按块与计数 [P0] [int]

作为设计者，我想要按固定行数分块或固定次数循环，以便批量调用。  
关联：F-EXE-09

- AC-1 ​`Loop Start (Chunk)`​，​`chunk_size: 100`，输入 1000 行 Then 循环 10 次，每次 Table 端口输出 100 行。
- AC-2 ​`Loop Start (Counting)`​，​`from: 0, to: 5, step: 1`​ Then 循环 5 次，Variable 端口输出 ​`i`。
- AC-3 ​`Loop End`​ 支持三种收集模式：​`concat`​（拼接表）、​`last`​（只保留最后一次）、​`variables`（收集变量为表）。
- AC-4 Loop Start 与 Loop End 必须成对且嵌套合法；保存时校验，非法时画布提示"Loop Start 无匹配 Loop End"。

### US-EXE-12 条件分支 [P0] [int]

作为设计者，我想要按条件走不同分支，以便处理多种情况。  
关联：F-EXE-10

- AC-1 ​`If`​ 节点参数 ​`condition`​ 为表达式（变量作用域内，语法为受限的 Python 表达式，由 ​`simpleeval`​ 求值），输出两个 Flow 端口 ​`true`​ / ​`false`；只有命中分支的下游执行，未命中分支的下游标记为"已跳过"（灰）。

- AC-2 ​`Switch`​ 节点参数 ​`variable`​ 与 ​`cases`​（值 → 端口名列表）及 ​`default` 端口；按变量值选择一个输出端口。
- AC-3 ​`[int]`​ 两个分支在下游 ​`Merge`​ 节点汇合时，​`Merge`​ 只接收命中分支的数据；两分支均未执行则 ​`Merge` 跳过。
- AC-4 表达式求值错误（引用不存在的变量、语法错）时 ​`If` 节点失败，错误信息含表达式原文与位置。
- AC-5 ​`[unit]`​ 表达式沙箱禁止 ​`import`​、属性访问 ​`__xxx__`、函数调用白名单外的函数；有对应的拒绝测试。

### US-EXE-13 运行互斥与排队 [P0] [int]

作为系统，我要保证同一工作流同一时刻只有一个活跃运行，以便避免 Excel 与缓存冲突。  
关联：F-EXE-11

- AC-1 Given 工作流 A 正在运行 When 再次触发 A Then 按工作流设置 ​`concurrency_policy`​：​`queue`​（默认）→ 新触发入队，当前运行结束后依次执行；​`drop`​ → 新触发被丢弃并记录日志；​`cancel_previous` → 取消当前运行后执行新触发。
- AC-2 队列长度上限 10，超出丢弃并记录 WARN。
- AC-3 不同工作流之间可并行运行，但 Excel 操作全局串行（见 US-XLS-11）。
- AC-4 ​`GET /api/workflows/{id}/runs?status=queued` 可查看队列。

### US-EXE-14 工作流独立执行环境 [P0] [int]

作为系统，我要在工作流自己的 venv 中执行节点代码，以便用户依赖不污染 Weft 本体。  
关联：F-EXE-12

- AC-1 Given 工作流 ​`pyproject.toml`​ 声明依赖 ​`requests`​ When 打开工作流 Then 系统在 ​`<root>/.venv/`​ 执行 ​`uv sync`，UI 显示进度；完成前运行按钮禁用。
- AC-2 ​`[int]`​ Python Script 节点中 ​`import requests`​ 成功；Weft 本体环境中无 ​`requests`。
- AC-3 ​`[int]`​ 节点执行进程（worker）由 ​`<root>/.venv/Scripts/python.exe`​ 启动；worker 与引擎通过 ​`03-architecture.md` 定义的 IPC 通信；一个 Run 复用同一个 worker 进程。
- AC-4 ​`uv sync` 失败（依赖冲突、网络）时，UI 显示 uv 的完整输出，工作流处于"环境异常"状态，可重试。
- AC-5 Weft 自带节点（Excel、表格等）所需的 ​`polars`​、​`pyarrow`​、​`xlwings`​ 由系统在创建工作流时写入 ​`pyproject.toml`​ 的 ​`[tool.weft.base-deps]`​ 并合并进 ​`dependencies`，用户不可删除。

---

## 3. Epic XLS：Excel 联动

> 本 Epic 的 ​`[int-win]`​ 测试需真实 Excel；CI 中以 ​`FakeExcelBackend`​（内存实现 ​`ExcelBackend`​ 接口）运行 ​`[int]` 标记的 AC。

### US-XLS-01 连接可见 Excel 实例 [P0] [int-win]

作为设计者，我想要工作流连接到我正在用的那个 Excel，以便实时联动。  
关联：F-XLS-01

- AC-1 Given 用户已打开 Excel（含 ​`ref.xlsx`​） When 执行 ​`Excel Connect`​（​`mode: attach_visible`​） Then 节点输出 Excel App 引用，描述符含 ​`pid`​、​`visible: true`​、​`workbooks: ["ref.xlsx"]`；用户的 Excel 窗口无任何闪烁或焦点变化。
- AC-2 Given 没有运行中的 Excel When 执行 Then 启动一个新的可见 Excel 实例并连接；​`Run`​ 结束后该实例**不**被关闭（用户可能要看）。
- AC-3 Given 多个 Excel 实例 Then 连接到最近活动的实例（​`GetActiveObject`​ 返回者），描述符注明 ​`pid`。

### US-XLS-02 启动独立隐藏实例 [P0] [int-win]

作为设计者，我想要可选地用一个隐藏的 Excel 实例，以便不干扰我手头的工作。  
关联：F-XLS-02

- AC-1 ​`Excel Connect`​（​`mode: new_hidden`​）启动新 Excel 进程，​`Visible=False`​，​`DisplayAlerts=False`​；描述符 ​`visible: false`。
- AC-2 Run 结束（成功/失败/取消）时该隐藏实例被关闭，未保存的工作簿按参数 ​`on_finish: discard | save`​ 处理，默认 ​`discard`。
- AC-3 Weft 服务异常退出时，隐藏实例由 ​`weft doctor --cleanup` 可发现并终止（按进程命令行标记识别）。

### US-XLS-03 引用、打开、新建工作簿 [P0] [int][int-win]

作为设计者，我想要以三种方式获得工作簿引用，以便覆盖已打开、文件、新建三种情况。  
关联：F-XLS-03

- AC-1 ​`Excel Workbook`​（​`mode: open_existing`​，​`name: "ref.xlsx"`）：Given 该工作簿已在连接的实例中打开 Then 输出 Workbook 引用；未打开则失败，错误信息列出当前已打开的工作簿名。
- AC-2 ​`Excel Workbook`​（​`mode: open_file`​，​`path: "data/ref.xlsx"`）：路径相对 Root 解析；若该文件已被同一实例打开则直接引用而非重复打开；文件不存在则失败。
- AC-3 ​`Excel Workbook`​（​`mode: new`​）：新建空白工作簿，描述符 ​`name: "Book1"`​（Excel 分配的名），​`saved: false`。
- AC-4 ​`[int]`​ 以上三种模式在 ​`FakeExcelBackend` 下行为一致（接口契约测试）。

### US-XLS-04 读取区域为表 [P0] [int][int-win]

作为设计者，我想要把工作表的一块区域读成表，以便进入数据流处理。  
关联：F-XLS-04

- AC-1 ​`Excel Read Range`​（​`sheet: "Sheet1"`​，​`range: "A1:E101"`​，​`header: true`）Then 输出 Table 100 行 5 列，列名来自第一行。
- AC-2 ​`range`​ 留空 → 读取 ​`UsedRange`​；​`range: "Table1"`​ → 读取同名表格对象（ListObject）；​`range: "MyNamed"` → 读取命名区域。
- AC-3 类型推断：整列为数字 → ​`Float64`​（整数则 ​`Int64`​）；Excel 日期序列号且单元格格式为日期 → ​`Datetime`​；混合 → ​`Utf8`；空单元格 → null。
- AC-4 ​`[int-win]`​ 读取 10 万单元格（1000×100）耗时 < 3 s（整块 ​`Range.Value` 一次读取，禁止逐格）。
- AC-5 工作表不存在 → 失败并列出可用工作表名。

### US-XLS-05 写表到区域 [P0] [int][int-win]

作为设计者，我想要把表写到工作表指定位置，并在用户 Excel 中立即可见，以便实时输出。  
关联：F-XLS-05

- AC-1 ​`Excel Write Table`​（​`sheet: "本周"`​，​`start: "A1"`​，​`mode: overwrite`​，​`header: true`）Then 从 A1 起写入表头与全部行；用户 Excel 窗口中该工作表立即显示数据；工作表不存在时自动创建。
- AC-2 ​`mode: append`​ → 从该工作表 ​`start` 列的最后非空行下一行开始写，不写表头。
- AC-3 ​`mode: overwrite`​ 且 ​`clear_below: true`​（默认）→ 写入前清空 ​`start` 以下、表宽以内的旧内容。
- AC-4 ​`autofit: true`​ → 写后自适应列宽；​`preserve_format: true`​ → 只写 ​`Value`，不改变目标格式。
- AC-5 ​`[int-win]` 写 10 万单元格 < 3 s（整块赋值）。
- AC-6 null 写为空单元格；​`Datetime`​ 写为 Excel 日期并保留原列格式；​`Utf8`​ 以 ​`=`​ 开头的值前缀 ​`'`​ 以防被解释为公式（参数 ​`escape_formula: true` 默认）。

### US-XLS-06 更新零散单元格 [P0] [int][int-win]

作为设计者，我想要更新若干不连续的单元格，以便做仪表盘式联动。  
关联：F-XLS-06

- AC-1 ​`Excel Cell Update`​ 参数 ​`cells`​ 为列表 ​`[{address: "B2", value: 42}, {address: "D5", value: "done"}]`​，或从输入 Table（列 ​`address, value`）读取；执行后对应单元格更新。
- AC-2 ​`value`​ 以 ​`=`​ 开头且参数 ​`allow_formula: true` 时写入公式。
- AC-3 地址非法时整节点失败且不写入任何单元格（先校验全部地址）。

### US-XLS-07 工作表管理 [P0] [int][int-win]

作为设计者，我想要列出、新建、删除、重命名工作表，以便组织输出。  
关联：F-XLS-07

- AC-1 ​`Excel Sheet Names`​ 输出 Table（列 ​`name, index, visible`）。
- AC-2 ​`Excel Sheet`​（​`action: create | delete | rename | clear`​）；​`delete` 时若为最后一张工作表则失败。
- AC-3 ​`delete`​ 不弹 Excel 确认框（临时设置 ​`DisplayAlerts=False` 并在操作后恢复）。

### US-XLS-08 显式保存 [P0] [int][int-win]

作为设计者，我想要显式控制保存，以便 Weft 不会悄悄覆盖我的文件。  
关联：F-XLS-08

- AC-1 ​`Excel Save`​（​`mode: save`​）：工作簿从未保存过（​`saved: false`​ 且无路径）时失败并提示用 ​`save_as`。
- AC-2 ​`Excel Save`​（​`mode: save_as`​，​`path: "out/result.xlsx"`​）：路径相对 Root；目录不存在则创建；文件已存在按参数 ​`overwrite: false` 默认失败。
- AC-3 Run 结束时 Weft 对可见实例中的工作簿**不**执行任何保存或关闭。
- AC-4 ​`format`​ 参数支持 ​`xlsx | xlsm | csv`​，映射到 ​`FileFormat` 常量。

### US-XLS-09 运行宏 [P1] [int-win]

作为设计者，我想要调用工作簿中的宏，以便复用已有 VBA。  
关联：F-XLS-09

- AC-1 ​`Excel Run Macro`​（​`macro: "Module1.Refresh"`​，​`args: [...]`​）调用 ​`Application.Run` 并将返回值输出为 Variable。
- AC-2 宏不存在或 VBA 抛错 → 节点失败，错误信息含 COM 错误描述。

### US-XLS-10 性能模式 [P1] [int-win]

作为设计者，我想要在批量写入时暂停重算与刷屏，以便更快。  
关联：F-XLS-10

- AC-1 ​`Excel Write Table`​ / ​`Excel Cell Update`​ / Loop 体内 Excel 节点在参数 ​`fast_mode: true`​（默认）下，执行前设置 ​`ScreenUpdating=False, Calculation=Manual, EnableEvents=False`，执行后无论成功失败均恢复原值。
- AC-2 ​`[int-win]` 1000 次 Cell Update 在 fast_mode 下总耗时 < 2 s。

### US-XLS-11 Excel 操作串行与连接共享 [P0] [unit][int]

作为系统，我要把所有 COM 调用放在专用 STA 线程串行执行，以便避免 COM 线程错误。  
关联：F-XLS-11

- AC-1 ​`[unit]`​ ​`ExcelWorker`​ 为单例线程，​`CoInitialize`​ 在该线程调用；所有 ​`ExcelBackend`​ 方法通过 ​`worker.submit(fn)`​ 投递并 ​`await` 结果；在其他线程直接调用 COM 对象的代码路径在 debug 模式下触发断言。
- AC-2 ​`[int]`​ 两个工作流同时运行且都含 Excel 节点时，COM 调用严格交错串行，无 ​`CoInitialize`/RPC_E_WRONG_THREAD 错误。
- AC-3 同一 Run 内多个 Excel 节点共享同一个 App 连接；Excel 引用通过端口传递的是描述符，worker 端维护 ​`描述符 → COM 对象` 的映射，Run 结束释放。
- AC-4 Excel 引用缓存（Q1）：缓存中只存描述符；"执行到此"命中缓存时，worker 按描述符重新解析（按名找工作簿、按名找工作表）；解析失败则缓存视为失效，重跑上游。

### US-XLS-12 Excel 不可用时的明确错误 [P0] [int][int-win]

作为设计者，我想要 Excel 出问题时得到明确提示而不是挂死，以便快速处理。  
关联：F-XLS-12

- AC-1 未安装 Excel（COM 注册表无 ​`Excel.Application`​）→ ​`Excel Connect`​ 在 1 s 内失败，错误 ​`Excel is not installed or not registered`。
- AC-2 Excel 被模态对话框阻塞（COM 调用返回 ​`RPC_E_CALL_REJECTED`​ / ​`0x800AC472`​）→ 自动重试 3 次（间隔 1 s），仍失败则节点失败，错误 ​`Excel is busy (modal dialog open?)`；UI 提示用户检查 Excel 窗口。
- AC-3 单次 COM 调用超时 ​`excel_call_timeout`（默认 60 s）→ 节点失败，worker 线程继续可用（超时不杀线程，但标记该调用结果为丢弃）。
- AC-4 ​`weft doctor` 报告 Excel 版本、是否可连接、Sandboxie 是否安装。

---

## 4. Epic TBL：表格与文件

### US-TBL-01 Arrow 传递与 Polars 计算 [P0] [unit][int]

作为系统，我要以 Arrow 作为节点间表格格式，以便零拷贝与跨进程。  
关联：F-TBL-01

- AC-1 ​`[unit]`​ 所有 Table 端口值在引擎内为 ​`pyarrow.Table`​；节点实现以 ​`polars.DataFrame`​ 接收并返回，由框架自动转换（​`pl.from_arrow`​ / ​`.to_arrow()`）。
- AC-2 ​`[int]` 10 万行 × 20 列表格从一个节点传到下一个节点（同一 worker 进程内）< 10 ms；跨进程（经 Arrow IPC 文件内存映射）< 100 ms。
- AC-3 列名重复、列名为空时节点失败，提示具体列。

### US-TBL-02 读写文件表格 [P0] [int]

作为设计者，我想要读写 CSV / Parquet / JSON / Excel 文件，以便与外部数据交换。  
关联：F-TBL-02

- AC-1 ​`Read CSV`​（​`path, encoding: auto, separator: auto, header: true, skip_rows: 0`​）→ 读 ​`data/sales.csv`​ 得 1000 行 5 列；​`encoding: auto`​ 依次尝试 ​`utf-8-sig, utf-8, gbk`。
- AC-2 ​`Read Parquet`​、​`Read JSON`​（lines 或 array 两种格式自动检测）、​`Read Excel File`​（​`sheet`​，经 ​`fastexcel`​/​`openpyxl`，不经 COM，可在 Excel 关闭时使用）。
- AC-3 ​`Write CSV`​（​`path, encoding: utf-8-sig, separator: ","`​）、​`Write Parquet`​、​`Write JSON`​、​`Write Excel File`​（​`sheet`​，用 ​`xlsxwriter`，整文件覆盖）。
- AC-4 写节点参数 ​`overwrite: true`​ 默认；​`false` 且文件存在则失败。
- AC-5 路径相对 Root；写入时自动创建父目录。

### US-TBL-03 基础变换节点 [P0] [unit][int]

作为设计者，我想要常用的单表变换节点，以便无代码清洗。  
关联：F-TBL-03

- AC-1 ​`Column Filter`​：​`mode: include | exclude`​，​`columns: [...]`​，支持通配符 ​`amount_*`。
- AC-2 ​`Row Filter`​：​`column, operator (==, !=, >, >=, <, <=, contains, starts_with, regex, is_null, is_not_null, in), value`​；多条件时用 ​`Row Filter`​ 串联或 ​`Rule Engine`。
- AC-3 ​`Sorter`​：​`keys: [{column, descending}]`，稳定排序。
- AC-4 ​`Column Rename`​：​`mapping: {old: new}`；目标名已存在则失败。
- AC-5 ​`Duplicate Filter`​：​`columns: [...]`​（空 = 全部），​`keep: first | last`。
- AC-6 ​`Missing Value`​：按列指定策略 ​`drop_row | fill_const | fill_mean | fill_prev`。
- AC-7 ​`Type Cast`​：​`mapping: {column: type}`​，type ∈ ​`int, float, str, bool, date, datetime`​；​`strict: false`​ 默认失败值转 null，​`true` 则节点失败。
- AC-8 ​`[unit]` 每个节点有基于固定小表的参数化测试，覆盖正常路径与至少一个错误路径。

### US-TBL-04 组合节点 [P0] [unit][int]

作为设计者，我想要多表组合节点，以便合并数据。  
关联：F-TBL-04

- AC-1 ​`Joiner`​：两个 Table 输入，​`how: inner | left | right | outer | cross | anti | semi`​，​`left_on, right_on`​，重名列后缀 ​`_right`。
- AC-2 ​`Concatenate`​：动态数量 Table 输入（≥ 2），​`how: vertical | horizontal | diagonal`（diagonal 允许列不一致，缺失填 null）。
- AC-3 ​`GroupBy`​：​`group_by: [...]`​，​`aggregations: [{column, agg: sum|mean|min|max|count|count_distinct|first|last|list|concat_str, alias}]`。
- AC-4 ​`Pivot`​：​`index, columns, values, agg`​；​`Unpivot`​：​`index, on, variable_name, value_name`。

### US-TBL-05 表达式与规则节点 [P0/P1] [unit][int]

作为设计者，我想要用表达式新增列或按规则赋值，以便处理无专用节点的场景。  
关联：F-TBL-05, F-TBL-06

- AC-1 ​`Polars Expression`​：​`expressions: [{alias, expr}]`​，​`expr`​ 为 Polars 表达式字符串（如 ​`pl.col("amount") * 1.1`​），在受限命名空间（仅 ​`pl`）中求值；错误时显示 Polars 原始错误信息。
- AC-2 ​`Math Formula`​：简化语法 ​`$amount$ * 1.1 + $tax$`​，​`$col$` 引用列，转为 Polars 表达式执行。
- AC-3 ​`String Manipulation`​：常用函数 ​`upper, lower, strip, replace, regex_replace, substr, concat, pad`，参数化。
- AC-4 ​`[P1]`​ ​`Rule Engine`​：有序规则列表 ​`[{condition, value}]`​ + ​`default`​，​`condition`​ 使用 Row Filter 相同的条件语法，首个命中生效，输出列 ​`alias`。
- AC-5 ​`[unit]`​ 表达式求值禁止访问 ​`__builtins__`、文件、网络；有拒绝测试。

### US-TBL-06 Table ↔ Variable [P0] [unit][int]

作为设计者，我想要表与流变量互转，以便把计算结果作为参数。  
关联：F-TBL-07

- AC-1 ​`Table to Variables`​：取第一行（或 ​`row_index`​），每列成为同名变量；​`mode: column_lists` 时每列成为列表变量。
- AC-2 ​`Variables to Table`：选中变量成为单行表。
- AC-3 ​`Table Row Count`​ 输出变量 ​`row_count`（常用于 If 判断）。
- AC-4 ​`Variable`​ 节点：手工定义 ​`[{name, type, value}]`​，type ∈ ​`str, int, float, bool, path, list`​；​`path` 类型相对 Root 解析为绝对路径后再输出。

### US-TBL-07 文件操作 [P0] [int]

作为设计者，我想要对文件系统做基本操作，以便搬运数据文件。  
关联：F-TBL-08

- AC-1 ​`List Files`​（​`path, pattern: "*.xlsx", recursive: false`​）→ Table 列 ​`path (相对Root), name, size, modified, is_dir`。
- AC-2 ​`File Copy / Move / Rename / Delete`​：输入 Table（列 ​`path`​）或参数单路径；​`Move`​/​`Rename`​ 目标存在时按 ​`overwrite`​ 处理；​`Delete`​ 默认移入回收站（​`send2trash`​），​`permanent: true` 才真删。
- AC-3 ​`Path Join`​：​`parts: [...]`​（可绑定变量）→ 变量 ​`path`，自动规范化分隔符。
- AC-4 Root 外的绝对路径操作允许，但节点显示黄色"不可移植"警告（设计期）。
- AC-5 所有文件节点拒绝解析为 Root 之外的 ​`..`​ 遍历？——**不**拒绝（用户可信车道），仅警告。

### US-TBL-08 Python Script 节点 [P0] [int]

作为设计者，我想要在节点里写 Python，以便处理任何特殊逻辑。  
关联：F-TBL-09

- AC-1 ​`Python Script`​ 节点参数：​`source: inline | file`​，​`code`​（inline 时）或 ​`path`​（相对 Root，通常在 ​`nodes/`​ 下），​`inputs: [{port, var}]`​，​`outputs: [{var, port, type}]`​。执行时每个输入 Table 端口绑定为同名 ​`polars.DataFrame`​ 变量，流变量以 ​`vars`​ 字典注入，用户代码结束后按 ​`outputs` 声明读取变量作为输出端口值。
- AC-2 代码可以是脚本体（直接执行）或定义 ​`def run(inputs: dict, vars: dict) -> dict:`；两种形式均支持，后者优先。
- AC-3 ​`[int]`​ 输出变量类型不符（声明 Table 但得到 ​`str`​）→ 节点失败，提示 ​`Output 'df' expected Table, got str`。
- AC-4 ​`print()` 输出作为 INFO 日志推送到 UI；未捕获异常的 traceback 仅显示用户代码帧（见 US-EXE-07 AC-4）。
- AC-5 inline 代码编辑器支持语法高亮与 ​`Ctrl+Enter`​ 执行到此；​`source: file` 时提供"在外部编辑器打开"按钮，文件变化后节点自动退回"已配置"。
- AC-6 ​`[int]`​ 用户代码运行在工作流 venv 的 worker 进程内（US-EXE-14），可 ​`import`​ 工作流依赖；可通过 ​`weft_ctx.root`​ 获得 Root 绝对路径，​`weft_ctx.log(...)`​ 写日志，​`weft_ctx.progress(0.5)` 上报进度。
- AC-7 ​`[int]`​ 用户代码抛出 ​`weft_ctx.Cancelled` 或收到取消信号时节点状态为"已取消"。

### US-TBL-09 Shell Command 节点 [P1] [int]

作为设计者，我想要在可信车道执行一条命令，以便调用外部工具（非 agent 使用）。  
关联：F-TBL-10

- AC-1 ​`Shell Command`​（​`command`​，​`cwd`​ 默认 Root，​`shell: powershell | cmd`​，​`timeout`​，​`env`​）→ 输出变量 ​`stdout, stderr, exit_code`​；​`fail_on_nonzero: true` 默认。
- AC-2 命令中可用 ​`{var}` 插值流变量，插值时自动引号转义。
- AC-3 输出实时流式推送到日志面板。

### US-TBL-10 Table View 与 Table Creator [P0] [e2e][int]

作为设计者，我想要在画布上固定展示一张表，或手工创建一张小表，以便做参考与测试。  
关联：F-EXE-05, F-TBL-07

- AC-1 ​`Table View` 节点：输入 Table，执行后节点体内嵌显示前 N 行（默认 10），可展开为完整端口视图。
- AC-2 ​`Table Creator`​ 节点：侧栏提供可编辑网格，列可指定类型，内容存于 ​`params.rows`；输出 Table。

---

## 5. Epic AGT：Agent

> LLM 相关 ​`[int]`​ 测试使用本地 mock OpenAI 兼容服务器（固定脚本应答，支持 ​`stream`​ 与 ​`tool_calls`​）；​`[manual]` 用真实模型验收。

### US-AGT-01 LLM 配置 [P0] [int][e2e]

作为设计者，我想要在全局设置中管理多个 LLM 端点配置，以便节点按名引用。  
关联：F-AGT-01

- AC-1 设置页"LLM 配置"可增删改：​`name, base_url, api_key, model, extra_headers, timeout`​；​`api_key`​ 以掩码显示，存于用户级 ​`config.toml`（见 F-SBX-08）。
- AC-2 "测试连接"按钮调用 ​`GET {base_url}/models` 或发送最小补全请求，3 s 内显示成功/失败与错误体。
- AC-3 所有 agent 类节点的 ​`llm`​ 参数为下拉，选项来自配置名；配置不存在时节点运行失败 ​`LLM config 'xxx' not found`。
- AC-4 ​`[int]`​ 请求按 OpenAI Chat Completions 规范构造；​`base_url`​ 末尾 ​`/v1` 有无均可。

### US-AGT-02 LLM Call 节点 [P0] [int]

作为设计者，我想要做一次 LLM 调用，以便处理文本任务。  
关联：F-AGT-02

- AC-1 ​`LLM Call`​ 参数：​`llm, system_prompt, user_prompt（支持 {var} 与 {table:port_name} 插值）, temperature, max_tokens, output: text | json, json_schema（可选）`​；输入 Message（可选，作为历史）与 Variable；输出 Message 端口（完整历史 + 本次回复）与 Variable 端口（​`response` 文本或解析后的 JSON）。
- AC-2 ​`output: json`​ 时请求带 ​`response_format`；解析失败则重试 1 次（追加"请只输出合法 JSON"），仍失败则节点失败并附原始文本。
- AC-3 ​`{table:in}`​ 插值把输入表渲染为 Markdown（前 ​`table_max_rows` 行，默认 50）。
- AC-4 ​`[int]`​ 流式输出通过 ​`node.stream`​ 事件推送；节点日志记录 ​`prompt_tokens, completion_tokens, latency_ms`。
- AC-5 HTTP 错误按状态码处理：429/5xx 指数退避重试 3 次；4xx 其他直接失败并附响应体。

### US-AGT-03 Agent Loop 节点 [P0] [unit][int][manual]

作为设计者，我想要一个 ReAct 循环节点，工具由端口注入，以便 agent 自主完成多步任务。  
关联：F-AGT-03

- AC-1 ​`Agent Loop`​ 参数：​`llm, system_prompt, task（支持插值）, max_turns（默认 20）, stop_on_text（可选正则）, tool_choice: auto | required`​；输入端口：Message（历史，可选）、Variable、Tool（多条）、Table（可选，渲染进 task）；输出端口：Message（最终回复）、Message（完整轨迹）、Variable（​`final_text`​, ​`turns`​, ​`tool_calls_count`）。
- AC-2 ​`[unit]`​ 循环逻辑：调用 LLM → 若回复含 ​`tool_calls`​ 则逐个执行并以 ​`role: tool`​ 消息回填 → 再调用 → 直至回复无 tool_calls 或达到 ​`max_turns`​；达到上限时节点状态"已执行"但 ​`Variable.stopped_by = "max_turns"` 并记 WARN。
- AC-3 ​`[unit]`​ 工具 schema 来自 Tool 端口对象的 ​`name, description, parameters (JSON Schema)`；同名工具冲突时节点在运行前失败。
- AC-4 ​`[int]` 工具执行异常不终止循环：错误文本作为 tool 结果回填，agent 可自行修正；连续 3 次同一工具失败则终止。
- AC-5 每轮推送 ​`node.stream`​（文本增量）与 ​`node.tool_call`​（​`tool, args, result_summary, duration_ms`）事件；UI 在节点侧栏以时间线展示。
- AC-6 ​`[manual]` 用真实模型完成场景 B（分类备注列），结果列正确率人工抽查可接受。

### US-AGT-04 Node as Tool [P0] [unit][int]

作为设计者，我想要把任一节点包装成工具给 agent，以便 agent 复用确定性能力且受控。  
关联：F-AGT-04, F-SBX-07

- AC-1 ​`Node as Tool`​ 节点参数：​`target_node`​（画布上任一节点，下拉）、​`tool_name`​（默认节点名 snake_case）、​`description`​、​`exposed_params: [...]`​（哪些参数由 agent 填，其余固定）、​`result_format: table_markdown | json | text`；输出 Tool 端口。
- AC-2 ​`[unit]`​ 工具 ​`parameters`​ schema = 目标节点参数 schema 中 ​`exposed_params` 子集；非暴露参数取目标节点当前值。
- AC-3 ​`[int]`​ agent 调用工具时，目标节点在可信车道以 agent 提供的参数执行一次（独立于其画布状态，不改变其缓存），输出按 ​`result_format`​ 转为字符串回填；执行受 ​`tool_timeout`（默认 120 s）约束。
- AC-4 ​`[int]`​ 目标节点需要输入端口数据时，取其画布上已缓存的上游输出；上游未执行则工具调用返回错误文本 ​`Upstream of 'X' not executed`。
- AC-5 每次调用写入审计日志 ​`.runs/<run_id>/audit.jsonl`​：​`ts, run_id, agent_node, tool, args, status, duration_ms, result_hash`。
- AC-6 ​`target_node` 不能是 Agent 类节点自身或其祖先（防递归）；保存时校验。
- AC-7 Excel 类节点作为工具时，COM 调用仍经 ExcelWorker 串行（US-XLS-11）。

### US-AGT-05 Sandboxed Tools [P0] [int][int-win]

作为设计者，我想要给 agent 一组沙箱内的基础工具，以便它能自由读写文件与执行命令。  
关联：F-AGT-05, F-SBX-02

- AC-1 ​`Sandboxed Tools`​ 节点参数：​`tools: [read, write, edit, list, bash]`​（多选）、​`cwd`​（默认 Root）、​`sandbox: inherit | none | sandboxie`​（默认 inherit 自全局）、​`bash_timeout`；输出 Tool 端口（一个端口承载多个工具）。
- AC-2 工具语义与 pi 一致：​`read(path, offset?, limit?)`​、​`write(path, content)`​、​`edit(path, old_string, new_string)`​（old_string 必须唯一匹配）、​`list(path, pattern?)`​、​`bash(command, timeout?)`。
- AC-3 ​`[int-win]`​ ​`sandbox: sandboxie`​ 下，​`write`​ 的文件出现在 ​`C:\Sandbox\<user>\<box>\drive\<盘>\...`​ 而非真实路径；​`read`​ 可读真实文件；​`bash`​ 进程由 ​`Start.exe /box:<box> /wait /silent` 启动。
- AC-4 ​`[int]`​ ​`sandbox: none`​ 需在节点上显式选择且全局设置 ​`allow_unsandboxed: true`​，否则运行前失败 ​`Unsandboxed tools are disabled in settings`。
- AC-5 ​`bash`​ 输出截断至 ​`max_output_chars`（默认 20000），尾部注明截断。
- AC-6 工具调用记入审计日志（同 US-AGT-04 AC-5）。

### US-AGT-06 Pi Agent 节点 [P0] [int-win][manual]

作为设计者，我想要直接调用原版 pi coding agent 作为一个节点，以便复用其成熟能力。  
关联：F-AGT-06

- AC-1 ​`Pi Agent`​ 参数：​`task`​（支持插值）、​`cwd`​（默认 Root）、​`pi_path`​（默认取全局设置）、​`model`​（传给 pi 的模型参数，可选）、​`sandbox`​、​`timeout`​、​`extra_args`​；输入 Variable/Message；输出 Variable（​`final_text, exit_code`）与 Message（轨迹）。
- AC-2 ​`[int-win]`​ 以子进程运行 pi 的非交互模式（​`pi -p "<task>"`​ 或其 JSON 输出模式，具体命令行在 ​`06-nodes-v1.md`​ 固定），​`cwd` 为指定目录，stdout 流式推送到 UI。
- AC-3 pi 未安装（​`pi_path` 不可执行）→ 运行前失败并链接到"安装指引"。
- AC-4 ​`sandbox: sandboxie`​ 时 pi 进程在沙箱内，其 API key 通过环境变量注入；​`weft doctor` 验证沙箱内进程能访问网络。
- AC-5 ​`[manual]`​ 完成场景 C（整理 ​`raw/` 目录），变更列表正确反映 pi 的重命名/移动。

### US-AGT-07 Chat Input / Output 与聊天面板 [P0] [int][e2e]

作为设计者，我想要通过聊天触发工作流并看到回复，以便对话式使用。  
关联：F-AGT-07, F-TRG-03

- AC-1 UI 右侧"聊天"面板，绑定当前工作流；发送消息 → 触发一次 Run，​`Trigger`​ 节点的 Message 端口输出 ​`[{role: user, content}]`​，Variable 端口输出 ​`chat_message, session_id`。
- AC-2 ​`Chat Output`​ 节点：输入 Message 或 Variable，执行后内容显示为聊天面板中的助手消息；一次 Run 内多个 ​`Chat Output` 按执行顺序显示。
- AC-3 ​`[int]`​ 流式：​`Chat Output`​ 的上游为 agent 节点时，面板实时显示增量（复用 ​`node.stream`）。
- AC-4 ​`session_id`​ 在面板"新会话"前保持不变；历史消息由 ​`Memory` 节点（US-AGT-08）或工作流自行维护，面板本身只显示本会话。
- AC-5 工作流无 ​`Chat Output` 时，Run 结束后面板显示"运行完成（无输出）"。

### US-AGT-08 Memory 节点 [P1] [int]

作为设计者，我想要按会话保存与读取历史消息，以便多轮对话。  
关联：F-AGT-08

- AC-1 ​`Memory Load`​（​`session_id`​，​`max_messages`​）→ Message 端口；​`Memory Save`​（​`session_id`​，输入 Message）追加写入 ​`.runs/memory/<session_id>.jsonl`。
- AC-2 ​`max_messages`​ 截断保留最新；​`Memory Clear` 节点清空会话。
- AC-3 memory 目录不随打包分发（在 ​`.runs/` 下）。

### US-AGT-09 Prompt Template 节点 [P0] [unit][int]

作为设计者，我想要用模板组合 prompt，以便引用变量与表格。  
关联：F-AGT-09

- AC-1 ​`Prompt Template`​ 参数：​`template`​（Jinja2 子集：变量、if、for、filters ​`upper/lower/truncate/json`​）、​`role: system | user`​、​`table_max_rows`​；输入 Variable/Table；输出 Message 与 Variable（​`text`）。
- AC-2 模板可从 ​`prompts/*.md`​ 文件加载（​`source: file`），文件变化后节点退回"已配置"。
- AC-3 ​`[unit]`​ 未定义变量渲染时失败（​`StrictUndefined`），错误含变量名与行号。
- AC-4 ​`[unit]`​ Jinja2 沙箱环境（​`SandboxedEnvironment`​），禁止属性遍历到 ​`__class__` 等。

### US-AGT-10 用量与轨迹可见 [P1] [int][e2e]

作为设计者，我想要看到每次调用的 token、耗时、工具调用，以便控制成本与排查。  
关联：F-AGT-10

- AC-1 agent 类节点侧栏"轨迹"标签页：按轮次列出 LLM 请求摘要、回复、工具调用（参数折叠可展开）、​`prompt_tokens / completion_tokens / latency_ms`。
- AC-2 Run 级汇总：​`GET /api/runs/{id}`​ 含 ​`usage: {prompt_tokens, completion_tokens, llm_calls, tool_calls}`。
- AC-3 轨迹持久化于 ​`.runs/<run_id>/nodes/<node_id>.trace.jsonl`，可从历史面板回看。

### US-AGT-11 agent 不能修改工作流图 [P0] [unit][int]

作为系统，我要确保 agent 无法增删节点或连线，以便可控。  
关联：F-AGT-11

- AC-1 ​`[unit]`​ Tool 端口可承载的工具类型只有 ​`NodeTool`​ 与 ​`SandboxedTool`；不存在任何修改图结构的内置工具。
- AC-2 ​`[int]`​ 工作流修改 API（​`PUT /api/workflows/{id}`​）要求请求头 ​`X-Weft-Client: ui`，且运行期间（Run 活跃）拒绝修改图结构（返回 409）。
- AC-3 沙箱内进程对 ​`workflow.json` 的写入落在沙箱副本，默认在变更审批中被标记为"受保护文件"，不可勾选应用（US-SBX-05）。

### US-AGT-12 人工介入确认 [P1] [int][e2e]

作为设计者，我想要在 agent 调用某些工具前要求我确认，以便关键操作不失控。  
关联：F-AGT-12

- AC-1 ​`Node as Tool`​ / ​`Sandboxed Tools`​ 有 ​`require_confirmation: true | false`​ 参数（Sandboxed Tools 可按工具单独设置，默认 ​`write/edit/bash` 为 true）。
- AC-2 ​`[int]`​ 需确认的调用触发 ​`node.confirm_request`​ 事件（含 ​`tool, args`​），Run 进入 ​`waiting`​ 状态；​`POST /api/runs/{id}/confirm`​ 提交 ​`approve | reject`​（可附修改后的 args）；​`reject` 作为工具错误回填给 agent。
- AC-3 ​`confirm_timeout`​（默认 10 min）超时按 ​`reject` 处理。
- AC-4 ​`[e2e]` UI 弹出确认卡片，显示工具名、参数（可编辑）、批准/拒绝按钮。

---

## 6. Epic SBX：沙箱与安全

### US-SBX-01 沙箱接口可插拔 [P0] [unit]

作为系统，我要定义统一的沙箱接口，以便替换实现。  
关联：F-SBX-01

- AC-1 ​`Sandbox`​ 抽象接口：​`spawn(cmd, cwd, env, timeout) -> Process`​、​`read_file(path)`​、​`write_file(path, content)`​、​`list_dir(path)`​、​`collect_changes() -> list[Change]`​、​`apply(changes)`​、​`discard()`​；实现 ​`NoneSandbox`​ 与 ​`SandboxieSandbox`。
- AC-2 ​`[unit]`​ 接口契约测试套件对两种实现运行（​`NoneSandbox` 在临时目录下以"写入到影子目录"方式模拟，使 CI 可测审批流）。
- AC-3 全局设置 ​`sandbox.default: sandboxie | none`​，​`sandbox.allow_unsandboxed: false` 默认。

### US-SBX-02 Sandboxie 实现 [P0] [int-win]

作为系统，我要通过 Sandboxie-Plus 启动 agent 工具进程，以便隔离。  
关联：F-SBX-02, F-SBX-03

- AC-1 设置 ​`sandbox.sandboxie.start_exe`​（默认 ​`C:\Program Files\Sandboxie-Plus\Start.exe`​）、​`sandbox.sandboxie.box`​（默认 ​`WeftBox`​）、​`sandbox.sandboxie.root`​（默认 ​`C:\Sandbox\%USER%\WeftBox`）。
- AC-2 ​`weft doctor`​ 检查 ​`Start.exe`​ 存在、box 存在（​`Start.exe /box:WeftBox /listpids`​ 可执行）、沙箱内 ​`python -c "print(1)"` 可运行且能访问网络。
- AC-3 每个 Run 使用独立子目录标记（环境变量 ​`WEFT_RUN_ID`​），同一 box 内并发 Run 的变更按进程写入时间与路径归属区分；v1 简化：**同一时刻只允许一个使用沙箱的 Run**，第二个排队。
- AC-4 Run 结束后沙箱内残留进程被终止（​`Start.exe /box:WeftBox /terminate`）。

### US-SBX-03 沙箱内读真实文件、写入重定向 [P0] [int-win]

作为 Agent，我可以读取真实文件系统但写入不会影响真实文件，以便安全探索。  
关联：F-SBX-03

- AC-1 沙箱内 ​`read("D:\flows\demo.weft\data\sales.csv")` 成功返回真实内容。
- AC-2 沙箱内 ​`write("D:\flows\demo.weft\out\a.txt", ...)`​ 后，真实路径不存在该文件，​`<sandbox root>\drive\D\flows\demo.weft\out\a.txt` 存在。
- AC-3 沙箱内删除真实文件后，真实文件仍在（Sandboxie 以删除标记记录），​`collect_changes()`​ 报告 ​`deleted`。

### US-SBX-04 变更列表与 diff [P0] [int][int-win]

作为设计者，我想要在 Run 结束后看到 agent 做了哪些文件变更，以便审批。  
关联：F-SBX-04

- AC-1 Run 结束（成功/失败/取消）后，系统调用 ​`collect_changes()`​，产出 ​`.runs/<run_id>/changes.json`​：​`[{path, kind: created | modified | deleted | renamed, size, is_text, protected}]`。
- AC-2 UI 弹出"变更审批"面板：按目录树展示，Root 内与 Root 外分组；文本文件（≤ 1 MB，UTF-8 可解码）可展开行级 diff；二进制只显示大小变化。
- AC-3 ​`[int]`​ ​`GET /api/runs/{id}/changes`​ 与 ​`GET /api/runs/{id}/changes/diff?path=...` 返回对应数据。
- AC-4 无变更时不弹面板，日志记一条 INFO。

### US-SBX-05 应用 / 丢弃变更 [P0] [int][int-win]

作为设计者，我想要勾选变更并应用到真实位置或丢弃，以便我掌控最终结果。  
关联：F-SBX-05

- AC-1 ​`POST /api/runs/{id}/changes/apply`​ 请求体 ​`{paths: [...]}`​ → 对应文件从沙箱副本复制到真实路径（​`deleted` 则删除真实文件，先移入回收站）；应用结果逐项返回成功/失败。
- AC-2 ​`POST /api/runs/{id}/changes/discard` → 清空本 Run 的沙箱副本。
- AC-3 工作流设置 ​`sandbox.auto_apply_in_root: false`​ 默认；为 ​`true` 时 Root 内非受保护变更自动应用，Root 外仍需审批。
- AC-4 受保护文件（​`workflow.json`​、​`pyproject.toml`​、​`uv.lock`​、​`.runs/**`​、用户级 ​`config.toml`​）在变更列表中标记 ​`protected: true`​，UI 中灰显不可勾选，​`apply` API 收到其路径时整体拒绝（400）。

- AC-5 应用后变更面板标记"已应用"；同一 Run 的变更只能应用一次（幂等：重复请求返回已应用状态）。

### US-SBX-06 沙箱内无 COM 访问 [P0] [int-win]

作为系统，我要确认沙箱内进程无法驱动主机 Excel，以便隔离边界成立。  
关联：F-SBX-06

- AC-1 沙箱内执行 ​`python -c "import win32com.client; win32com.client.GetActiveObject('Excel.Application')"` 失败（找不到活动对象或 COM 被拒绝）。
- AC-2 文档与 UI 提示：agent 需操作 Excel 时使用 Node as Tool；​`Sandboxed Tools` 的描述中注明此限制。

### US-SBX-07 审计日志 [P0] [unit][int]

作为设计者，我想要所有 agent 工具调用有统一审计记录，以便事后追查。  
关联：F-SBX-07

- AC-1 ​`[unit]`​ 审计记录 schema：​`{ts, run_id, node_id, agent_kind: agent_loop | pi, lane: trusted | sandboxed, tool, args_redacted, status: ok | error | rejected, duration_ms, result_hash}`​；​`args_redacted`​ 对含 ​`key/token/password/secret` 的字段打码。
- AC-2 写入 ​`.runs/<run_id>/audit.jsonl`，追加式、每行一条 JSON。
- AC-3 UI 历史面板的 Run 详情含"审计"标签页，可按工具/状态过滤。

### US-SBX-08 密钥不入工作流目录 [P0] [unit][int]

作为系统，我要保证密钥只存在用户级配置中，以便打包不泄密。  
关联：F-SBX-08

- AC-1 ​`[unit]`​ ​`workflow.json` 的 JSON Schema 中不存在任何密钥字段；节点参数引用 LLM 仅按配置名。
- AC-2 ​`[int]`​ 打包产物 zip 内任何文件均不含 ​`config.toml`​ 中的 ​`api_key` 值（打包流程中全文扫描断言，命中则打包失败并提示来源文件）。
- AC-3 Python Script 代码中硬编码形如 API key 的高熵字符串时，打包时 WARN（不阻断）。

### US-SBX-09 服务仅本机监听与 HTTP token [P0] [int]

作为系统，我要默认只监听本机并对触发端点鉴权，以便不暴露风险面。  
关联：F-SBX-09

- AC-1 默认绑定 ​`127.0.0.1:7788`​；设置改为 ​`0.0.0.0` 时启动日志打 WARN 且 UI 顶栏常驻提示。
- AC-2 ​`POST /api/workflows/{id}/trigger`​ 要求 ​`Authorization: Bearer <token>`，token 在该工作流触发器配置中生成/轮换；错误 token 返回 401 并限速（同 IP 每分钟 ≤ 10 次失败）。
- AC-3 其余 ​`/api/*` 在监听非本机地址时也要求全局 token（设置中生成）。

---

## 7. Epic TRG：触发器

### US-TRG-01 统一触发事件 [P0] [unit][int]

作为系统，我要把所有触发源统一为同一事件结构，以便下游节点无需区分来源。  
关联：F-TRG-01

- AC-1 ​`[unit]`​ 事件结构：​`{source: manual | chat | schedule | file | http, ts, payload: dict, session_id?}`​；​`Trigger`​ 节点输出端口：Variable（​`source, ts` 及 payload 平铺）、Message（仅 chat 时非空）、Table（file 触发时的文件清单，其他为空表）。
- AC-2 ​`Trigger` 节点侧栏按 5 种来源分区配置，每种可独立启用/禁用（F-TRG-07）。
- AC-3 ​`[int]`​ Run 的 ​`meta.json` 记录完整触发事件。

### US-TRG-02 手动触发 [P0] [int][e2e]

作为设计者，我想要点按钮或用 CLI 运行工作流，以便即时执行。  
关联：F-TRG-02

- AC-1 UI "运行"按钮 → ​`source: manual`​，payload 为空对象；可在运行对话框中临时覆盖流变量（​`payload.overrides`）。
- AC-2 ​`weft run <path-to-workflow> [--var k=v ...] [--wait]`​ 退出码：成功 0、失败 1、取消 2；​`--wait` 时输出各节点状态行；服务未启动时 CLI 以内嵌模式直接执行（不依赖服务进程）。

### US-TRG-03 聊天触发 [P0] [int][e2e]

（主体见 US-AGT-07）  
关联：F-TRG-03

- AC-1 聊天面板发送 → ​`source: chat`​，​`payload: {message, history_len}`​，​`session_id` 稳定。
- AC-2 Trigger 未启用 chat 来源时，聊天面板显示"该工作流未启用聊天触发"。

### US-TRG-04 定时触发 [P0] [int]

作为设计者，我想要 cron 或固定间隔自动运行，以便无人值守。  
关联：F-TRG-04

- AC-1 配置 ​`schedules: [{cron: "0 9 * * 1-5"} | {interval_seconds: 3600}]`，多条可并存；cron 为 5 段标准格式，时区为本机时区。
- AC-2 ​`[int]`​ 到点产生 ​`source: schedule`​ 事件，payload 含 ​`schedule_id, scheduled_at`；错过的触发（服务未运行）不补跑。
- AC-3 UI 显示每条 schedule 的下次触发时间；非法 cron 表达式在保存时报错。
- AC-4 工作流关闭或服务停止后不再触发（F-TRG-07）。

### US-TRG-05 文件监听触发 [P0] [int]

作为设计者，我想要文件夹变化自动触发，以便"丢文件即处理"。  
关联：F-TRG-05

- AC-1 配置 ​`watch: [{path, pattern: "*.xlsx", events: [created, modified, deleted], debounce_ms: 2000, recursive: false}]`​；​`path` 相对 Root 或绝对。
- AC-2 ​`[int]`​ 在防抖窗口内的多个事件合并为一次触发；payload 含 ​`events: [{path, kind, ts}]`，Trigger 的 Table 端口输出同内容表。
- AC-3 忽略 ​`.runs/`​、​`.venv/`​、临时文件（​`~$*`​, ​`*.tmp`​, ​`.~lock*`）。
- AC-4 监听路径不存在时触发器状态为"异常"（UI 红点），不影响其他来源。
- AC-5 由本工作流自身写入的文件（Run 活跃期间引擎写出的路径）不触发，防自激循环。

### US-TRG-06 HTTP 触发 [P0] [int]

作为外部系统，我想要 POST 一个端点触发工作流，以便集成。  
关联：F-TRG-06

- AC-1 ​`POST /api/workflows/{id}/trigger`​，Bearer token（US-SBX-09），body 任意 JSON → ​`source: http`​，​`payload.body`​ 为请求体；响应 202 ​`{run_id}`。
- AC-2 ​`?wait=true`​ 时阻塞至 Run 结束（上限 ​`http_trigger_wait_timeout`​ 默认 300 s），返回 ​`{run_id, status, outputs}`​，​`outputs`​ 为工作流中 ​`HTTP Response` 节点（P1，若无则为空）设置的内容。
- AC-3 触发器未启用 http 来源 → 404（不泄露工作流存在性差异：统一 404）。

### US-TRG-07 来源独立开关与生命周期 [P0] [int]

作为设计者，我想要每种触发源独立启停，且随工作流/服务生命周期生效，以便可控。  
关联：F-TRG-07

- AC-1 任一来源开关变更即时生效（无需重启服务）；Trigger 节点上显示各来源小图标（启用亮/禁用灰/异常红）。
- AC-2 ​`[int]`​ 服务启动时恢复所有已打开工作流的 schedule 与 watch；​`weft serve --no-triggers` 启动则全部不激活（调试用）。

### US-TRG-08 Excel 事件触发（占位） [P2]

关联：F-TRG-08。v2 经 xlOil 伴侣插件实现 SheetChange / Ribbon 触发，本版本仅在文档中保留事件结构兼容性：​`source: excel`​，payload 含 ​`workbook, sheet, address`。无 AC。

---

## 8. Epic PKG：可移植与打包

### US-PKG-01 工作流目录自包含 [P0] [unit][int]

作为系统，我要保证工作流的全部定义都在目录内，以便拷走即完整。  
关联：F-PKG-01

- AC-1 ​`[unit]`​ ​`workflow.json`​ schema 校验器拒绝任何绝对路径出现在"可移植参数"（标记为 ​`format: weft-path`​ 的字段）中——允许保存，但 ​`weft pack` 时收集为警告清单（F-PKG-06）。
- AC-2 ​`[int]`​ 把 ​`demo.weft/` 整体复制到另一路径后打开，所有相对路径节点无需修改即可运行。

### US-PKG-02 依赖声明与自动同步 [P0] [int]

（主体见 US-EXE-14）  
关联：F-PKG-02

- AC-1 UI "依赖"面板可增删 ​`pyproject.toml`​ 的 ​`dependencies`​，保存后提示并执行 ​`uv sync`​，​`uv.lock` 更新。
- AC-2 打开工作流时若 ​`.venv`​ 缺失或 ​`uv.lock`​ 与 venv 不一致（​`uv sync --check` 非零）→ 自动同步。

### US-PKG-03 打包 [P0] [int][e2e]

作为设计者，我想要一键导出 zip，以便发给同事。  
关联：F-PKG-03

- AC-1 UI "打包"对话框：默认排除 ​`.runs/`​、​`.venv/`​、​`__pycache__`​；​`data/`​ 可勾选排除；显示预计体积；产物命名 ​`<name>-<yyyymmdd>.weft.zip`。
- AC-2 ​`weft pack <workflow-dir> [-o out.zip] [--exclude-data]` 等价。
- AC-3 ​`[int]`​ 产物 zip 根为 ​`<name>.weft/`​ 单目录；含 ​`workflow.json, pyproject.toml, uv.lock, nodes/, prompts/`；密钥扫描通过（US-SBX-08 AC-2）。
- AC-4 打包前执行校验：schema 合法、绝对路径警告清单、Loop 配对、未配置节点清单；有 ERROR 级问题时需确认才继续。

### US-PKG-04 导入 [P0] [int][e2e]

作为运行者，我想要导入 zip 并直接可跑，以便接收交接。  
关联：F-PKG-04

- AC-1 UI "导入" → 选 zip 与目标父目录 → 解压、schema 版本检查、​`uv sync`、打开画布；全程进度可见。
- AC-2 ​`weft unpack a.weft.zip -d D:\flows` 等价。
- AC-3 zip 内含 Root 外路径（zip slip）→ 拒绝导入。
- AC-4 ​`[int]`​ 端到端：机器 A ​`pack`​ → 机器 B（干净环境，仅装 Weft + uv）​`unpack`​ → ​`weft run` 成功（CI 中以两个独立临时目录 + 清空缓存模拟）。

### US-PKG-05 schema 版本与迁移 [P0] [unit]

作为系统，我要给 ​`workflow.json` 版本号并向后兼容，以便升级不破坏旧工作流。  
关联：F-PKG-05

- AC-1 ​`workflow.json`​ 顶层 ​`schema_version: 1`；打开高于当前支持版本的文件 → 明确报错"请升级 Weft"。
- AC-2 ​`[unit]`​ 迁移框架：​`migrations/v1_to_v2.py`​ 形式注册，打开旧版本时逐级迁移，迁移前自动备份 ​`workflow.json.bak.v1`。
- AC-3 节点级版本：每个节点类型有 ​`node_version`，节点实现可提供参数迁移函数；未知节点类型以"占位节点"显示（保留参数，不可执行），不丢数据。

### US-PKG-06 绝对路径检测 [P1] [unit]

关联：F-PKG-06

- AC-1 ​`weft pack`​ 与 UI 打包对话框列出所有含绝对路径的 ​`(节点, 参数, 值)`；用户可逐条跳转修改。

### US-PKG-07 运行前资源预检 [P1] [int]

作为运行者，我想要运行前一次性知道缺什么外部资源，以便不被逐节点报错折磨。  
关联：F-PKG-07

- AC-1 运行前对声明了"外部资源"的参数（工作簿名、绝对路径、LLM 配置名、pi 路径）做存在性检查，汇总为一份报告；有缺失时询问"仍要运行？"。
- AC-2 检查不执行任何写操作，总耗时 < 2 s（Excel 检查仅查已打开工作簿列表）。

---

## 9. Epic SET：设置与运维

### US-SET-01 用户级配置 [P0] [unit][int]

关联：F-SET-01

- AC-1 ​`%APPDATA%\weft\config.toml`​，首次启动生成带注释的默认文件；结构：​`[server] [llm.<name>] [sandbox] [excel] [logging]`。
- AC-2 设置页修改后写回文件并即时生效（监听端口除外，提示需重启）。
- AC-3 ​`[unit]` 配置加载有 schema 校验与默认值合并；非法值报具体字段错误。

### US-SET-02 服务启动与 UI [P0] [int][e2e][manual]

关联：F-SET-02

- AC-1 ​`weft serve`​ 启动后 2 s 内监听就绪；默认自动打开浏览器（​`--no-browser` 关闭）。
- AC-2 ​`[manual]` 冷启动到 UI 可交互 < 5 s（PRD §9.3）。
- AC-3 端口被占用时报错并提示 ​`--port`。

### US-SET-03 日志 [P0] [int]

关联：F-SET-03

- AC-1 服务日志 ​`%APPDATA%\weft\logs\weft-<date>.log`，JSON lines，按天轮转，默认保留 14 天。
- AC-2 Run 日志独立于服务日志（​`.runs/<run_id>/log.jsonl`​）；两者均含 ​`trace_id` 可关联。
- AC-3 日志级别可在设置中调整，​`DEBUG` 级别记录每次 COM 调用与 LLM 请求摘要（不含密钥与完整 prompt，完整 prompt 仅在 trace 文件中）。

### US-SET-04 CLI 与 doctor [P0] [int][int-win]

关联：F-SET-04

- AC-1 ​`weft --help`​ 列出 ​`serve run pack unpack doctor`​；全部命令支持 ​`--json` 输出。
- AC-2 ​`weft doctor`​ 检查并逐项报告 OK/WARN/FAIL：Python 版本、uv、Excel 可连接性、Sandboxie、pi、端口占用、​`%APPDATA%` 可写；退出码 = FAIL 项数。
- AC-3 ​`weft doctor --cleanup` 清理孤儿隐藏 Excel 实例（US-XLS-02 AC-3）与沙箱残留进程。

### US-SET-05 托盘（占位） [P2]

关联：F-SET-05。无 AC。

---

## 10. 覆盖矩阵

|PRD 需求|故事|
| --------------| ---------------------------------------------|
|F-DES-01..10|US-DES-01..11|
|F-EXE-01..12|US-EXE-01..14|
|F-XLS-01..12|US-XLS-01..12（F-XLS-13 → US-TRG-08 占位）|
|F-TBL-01..10|US-TBL-01..10|
|F-AGT-01..12|US-AGT-01..12|
|F-SBX-01..09|US-SBX-01..09|
|F-TRG-01..08|US-TRG-01..08|
|F-PKG-01..07|US-PKG-01..07|
|F-SET-01..05|US-SET-01..05|

维护规则：PRD 新增/变更需求时，必须同步本矩阵；AC 与 ​`06-nodes-v1.md` 冲突时以节点文档为准并回改本文。
