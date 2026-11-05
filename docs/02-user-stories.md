# 02-user-stories.md

**Weft 用户故事与验收标准**

|项|值|
| ------| ----------------------------------------------|
|版本|v0.1（草稿）|
|状态|待确认|
|上游|`01-prd.md` §7 功能需求|
|下游|`09-nodes-v1.md`（节点参数，规划）、`07-roadmap.md`（任务拆解）、测试代码|

---

## 0. 使用约定

### 0.1 本文档的用途

- 每个 PRD 需求（`F-XXX-NN`）至少对应一条用户故事；每条故事的验收标准（AC）是**可直接转写为测试用例**的 Given/When/Then。
- agent 实现任务时，以 AC 作为"完成"的客观定义；AC 未全部通过，任务不算完成。
- AC 中的具体数值、文件名、节点名为规范性内容，但受控性能基准除外。代码中的节点声明/JSON Schema 是参数真源，`09-nodes-v1.md` 是自动导出的只读参考；本文始终是行为与 AC 真源，参考文档不得覆盖 AC。

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
|`[unit]`|纯 Python 单元测试，无外部依赖|Windows CI|
|`[int]`|集成测试：服务 + 引擎 + 文件系统，可 mock LLM|Windows CI|
|`[int-win]`|需要真实 Excel / Sandboxie / pi|Windows 本机，手动或自托管 runner|
|`[e2e]`|浏览器端到端（Playwright）|Windows CI（Excel 相关节点用 fake backend）|
|`[manual]`|需人工确认的体验类标准（时间、观感）|验收阶段手动|

### 0.5 通用前置条件（除非故事另有说明）

- Weft 服务已启动，监听 `127.0.0.1:7788`，浏览器已打开 UI。
- 存在一个已打开的工作流 `demo.weft/`，Root 内 `data/` 含 `sales.csv`（1000 行，列：`date, region, product, amount, note`）与 `ref.xlsx`。
- 用户级配置中已存在一个名为 `default` 的 LLM 配置，指向可用的 OpenAI 兼容端点（测试中以 mock 服务器替代）。
- Excel 相关故事：Windows 本机已安装桌面版 Excel，且用户已打开 `ref.xlsx`。

### 0.6 Epic 索引

|Epic|主题|故事数|
| ------| --------------| --------|
|DES|工作流设计|12|
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

- AC-1 Given UI 首页 When 点击"新建工作流"并输入名称 `weekly` 与父目录 `D:\flows` Then 系统创建 `D:\flows\weekly.weft\`，内含 `workflow.json`（schema 版本为当前版本、节点列表仅含一个 `Trigger`）、`pyproject.toml`、`data/`、`nodes/`、`prompts/`、`.gitignore`（排除 `.runs/`、`.venv/` 与 `__pycache__/`）。
- AC-2 Given 目标目录已存在同名 `.weft` When 新建 Then 系统拒绝并提示"目录已存在"，不覆盖任何文件。
- AC-3 Given 新建完成 When 查看画布 Then 画布显示一个 `Trigger` 节点，状态为"已配置"（黄）。
- AC-4 Given UI 示例库 When 选择内置 CSV、表格或 LLM 示例并指定名称与父目录 Then 系统复制完整 `.weft` 目录、生成新的工作流 ID 并打开独立副本；CSV 与表格示例包含可直接运行的资源，LLM 示例仅引用命名配置并以 `<YOUR_API_KEY>` 等占位符说明设置方法，不保存真实密钥；同名同来源示例再次创建时经临时目录与环境同步后自动替换并打开，其他目标目录冲突仍拒绝覆盖。

### US-DES-02 添加节点 [P0] [e2e]

作为设计者，我想要从节点面板把节点拖到画布上，以便组装工作流。  
关联：F-DES-01, F-DES-02

- AC-1 Given 画布 When 在节点面板搜索框输入 `read` Then 面板只显示名称或描述包含 `read`（不区分大小写）的节点，且按分类分组。
- AC-2 Given 面板中的 `Excel Read Range` When 拖到画布坐标 (300, 200) 释放 Then 画布出现该节点，`workflow.json` 中新增节点记录含 `id`（`n_` + 8 hex）、`type`、`position: {x: 300, y: 200}`、`params`（全部为默认值）。
- AC-3 Given 新添加的节点含必填参数未填 Then 节点显示“未配置”（红）状态。
- AC-4 Given 面板 When 双击某节点类型 Then 节点添加到画布当前视口中心。

### US-DES-03 连接端口 [P0] [unit][e2e]

作为设计者，我想要在节点端口之间拖出连线，且系统只允许类型兼容的连接，以便避免运行期才发现类型错误。  
关联：F-DES-03

- AC-1 Given `Read CSV` 的 Table 输出端口 When 拖到 `Row Filter` 的 Table 输入端口 Then 连线建立，`workflow.json` 的 `edges` 新增记录含 `id, source, sourcePort, target, targetPort, order`；`id` 唯一且匹配 `^e_[0-9a-f]{8}$`，同一 Variable 输入按 order 合并。
- AC-2 Given `Read CSV` 的 Table 输出端口 When 拖到 `Excel Write Table` 的 Excel 输入端口 Then 连线被拒绝，目标端口显示红色高亮，画布顶部提示"Table 端口不能连接到 Excel 端口"。
- AC-3 Given 一个输入端口已有连线 When 再拖一条连线到该端口 Then 旧连线被替换（输入端口只允许一条入边），Tool 端口与 Variable 端口除外（允许多条）。
- AC-4 Given 连线会形成环路（非 Loop Start/End 对） When 释放 Then 连线被拒绝，提示"不允许形成循环，请使用 Loop 节点"。
- AC-5 `[unit]` 端口兼容性由后端 `ports.is_compatible(src_type, dst_type)` 决定，前端仅做展示；对 6 种类型的 36 种组合有完整的单元测试表。
- AC-6 `[unit]` 动态输入通过多个命名端口实例化，每个端口仍最多一条入边；Concatenate 声明 `in_1...in_N`（N ≥ 2），Merge 固定两个命名输入并允许部分 skipped，不得借 Tool/Variable 例外绕过普通端口基数约束。

### US-DES-04 编辑节点参数 [P0] [e2e][unit]

作为设计者，我想要在侧栏表单中编辑节点参数，表单由节点声明自动生成，以便不用记参数名。  
关联：F-DES-04

- AC-1 Given 选中 `Row Filter` 节点 Then 侧栏显示其参数表单：`column`（下拉，候选项来自上游表的列名；上游未执行则为自由文本）、`operator`（枚举）、`value`（文本）。
- AC-2 Given 修改 `value` 为 `100` 并失焦 Then `workflow.json` 中该节点 `params.value` 更新为 `"100"`，节点状态从"已执行"退回"已配置"，其下游节点同样退回。
- AC-3 Given 必填参数留空 Then 表单该字段显示红色错误，节点状态为"未配置"。
- AC-4 `[unit]` 每个节点类型的参数 schema 为 JSON Schema（draft 2020-12），`GET /api/nodes/types` 返回全部 schema；有测试确保所有内置节点的 schema 可被 `jsonschema` 校验器加载。
- AC-5 Given 参数类型为"路径" Then 表单提供文件选择器，选中的路径若在 Root 内则自动转为相对路径，若在 Root 外则保留绝对路径并显示黄色警告"绝对路径不可移植"。

### US-DES-05 节点状态指示 [P0] [e2e]

作为设计者，我想要一眼看出每个节点处于什么状态，以便知道工作流跑到哪了。  
关联：F-DES-05

- AC-1 节点底部有状态条，颜色与含义：红 = 未配置、黄 = 已配置未执行、绿 = 已执行、蓝色流动动画 = 执行中、红叉图标 = 错误、灰 = 已跳过（仅分支未命中 `skipped_branch`）。`out_of_scope` 与失败后的 `skipped_upstream` 显示已配置（黄），不得显示为灰色分支跳过。
- AC-2 Given 工作流执行中 When 后端推送 `node.status` 事件 Then 对应节点状态在 200 ms 内更新。
- AC-3 Given 节点为错误态 When 悬停 Then 显示错误摘要（第一行）；点击则在侧栏显示完整 traceback。

### US-DES-06 绑定流变量到参数 [P0] [e2e][int]

作为设计者，我想要任何参数字段都能绑定一个流变量，以便路径、阈值等可以在运行时注入。  
关联：F-DES-06

- AC-1 Given `Excel Write Table` 的 `workbook` 参数 When 点击字段右侧的"变量"图标 Then 字段切换为变量选择模式，列出所有通过 Variable 端口到达本节点的变量名。
- AC-2 Given 选择变量 `target_wb` Then `workflow.json` 中该参数存为 `{"$var": "target_wb"}`，表单显示为变量标签。
- AC-3 `[int]` Given 运行时上游 `Variable` 节点产出 `target_wb = "汇总.xlsx"` Then `Excel Write Table` 实际收到的 `workbook` 参数为 `"汇总.xlsx"`。
- AC-4 Given 绑定的变量在运行时不存在 Then 节点执行失败，错误信息为 `Flow variable 'target_wb' not found`。

### US-DES-07 自动保存与脏标记 [P0] [e2e][int]

作为设计者，我想要修改自动保存，并且知道是否有未保存内容，以便不丢工作。  
关联：F-DES-07

- AC-1 Given 画布有任何修改 Then 标题栏显示 `*` 脏标记；2 秒无新修改后自动保存到 `workflow.json`，脏标记消失。
- AC-2 Given 按 `Ctrl+S` Then 立即保存。
- AC-3 Given 自动保存失败（磁盘只读） Then 脏标记保持并弹出错误提示，不丢失内存中的修改。
- AC-4 `[int]` 保存是原子的：先写 `workflow.json.tmp` 再 rename；每次成功保存递增整数 `revision`，请求携带读取时 revision 做 CAS，冲突返回 409 且不覆盖他人修改；活跃 Run 仍用冻结快照。
- AC-5 `[int]` 活跃 Run 中增删节点/连线返回 409；位置、注释等非结构修改允许保存但只影响下一 Run。

### US-DES-08 撤销/重做、复制/粘贴、框选 [P0] [e2e]

作为设计者，我想要常规编辑操作，以便高效调整图。  
关联：F-DES-01

- AC-1 `Ctrl+Z` / `Ctrl+Y` 对添加/删除节点、连线、移动、参数修改均有效，历史深度 ≥ 50。
- AC-2 框选多个节点后 `Ctrl+C` / `Ctrl+V` Then 粘贴的节点获得新 `id`，内部连线保留，与外部的连线不保留，位置整体偏移 (40, 40)。
- AC-3 `Delete` 删除选中节点及其所有连线。

### US-DES-09 Metanode 折叠与展开 [P1] [e2e][int]

作为设计者，我想要把一组节点折叠成一个复合节点，以便画布整洁并可复用。  
关联：F-DES-08

- AC-1 Given 框选 3 个相连节点 When 右键"折叠为 Metanode" Then 画布显示一个 Metanode，其输入/输出端口为原选区与外部的所有连线端口，连线自动重连。
- AC-2 Given 双击 Metanode Then 进入子画布编辑，面包屑显示 `demo > Metanode 1`。
- AC-3 `[int]` `workflow.json` 中 Metanode 存为 `type: "flow.metanode"`，`params.graph` 内嵌子图（节点、边），`params.interface.inputs/outputs` 将每个外部端口名映射到 `{node, port}`；外部端口名唯一、类型与被映射内部端口一致，执行语义与展开后等价。`meta_<id>/` 仅用于展开后的内部执行 ID，不改变持久化节点 ID 规则。
- AC-4 右键"展开 Metanode"可逆操作，恢复原节点与连线。

### US-DES-10 节点注释与便签 [P1] [e2e]

作为设计者，我想要给节点加注释、在画布加便签，以便交接时别人看得懂。  
关联：F-DES-09

- AC-1 节点侧栏有"注释"字段，内容显示在节点下方（截断 60 字符，悬停全文）。
- AC-2 画布右键"添加便签"，便签支持 Markdown、可调大小、可改底色，存于 `workflow.json` 的 `notes` 数组。

### US-DES-11 节点面板与画布的基本导航 [P0] [e2e]

作为设计者，我想要缩放、平移、适应视图，以便处理大图。  
关联：F-DES-01

- AC-1 滚轮缩放（0.25x–2x），空格+拖拽或中键平移，`Shift+1` 适应全图，`Shift+2` 适应选中。
- AC-2 画布右下角有小地图。
- AC-3 视口位置与缩放存于 `workflow.json` 的 `viewport`，重新打开时恢复。

### US-DES-12 Metanode 模板导出（占位） [P2]

关联：F-DES-10。v2 支持将 Metanode 导出为可复用模板；v1 仅保留需求追踪，不排实现任务，暂无 AC。

---

## 2. Epic EXE：执行与调试

### US-EXE-01 整体运行 [P0] [int][e2e]

作为设计者，我想要一键运行整个工作流，以便看到结果。  
关联：F-EXE-01

- AC-1 Given 一个 5 节点线性工作流（`Trigger → Read CSV → Row Filter → Sorter → Write CSV`） When 点击"运行" Then 节点按拓扑顺序依次变为执行中、已执行；`data/out.csv` 生成；运行状态为 `succeeded`。
- AC-2 `[int]` Given 两个无依赖的分支 Then 两分支节点并行执行（通过记录各节点 start/end 时间戳验证存在重叠）。
- AC-3 Given 工作流存在"未配置"节点 When 点击运行 Then 拒绝运行，列出未配置节点。
- AC-4 `[int]` `POST /api/workflows/{id}/runs` 返回 `{run_id, disposition}`，状态码 202；运行完成后 `GET /api/runs/{run_id}` 返回 `status: succeeded` 与各节点状态。

### US-EXE-02 执行到此 [P0] [int][e2e]

作为设计者，我想要只执行到某个节点为止，以便调试时不跑整条链。  
关联：F-EXE-02

- AC-1 Given 右键 `Sorter` 选择"执行到此" Then 只执行 `Trigger → Read CSV → Row Filter → Sorter`，`Write CSV` 保持"已配置"状态。
- AC-2 Given `Read CSV` 与 `Row Filter` 已有有效缓存 Then 它们不重跑（节点日志无新条目），只执行 `Sorter`。

### US-EXE-03 从此开始 / 仅执行本节点 / 重置 [P0] [int][e2e]

作为设计者，我想要更多局部执行操作，以便精准调试。  
关联：F-EXE-02

- AC-1 "从此开始"：Given 上游节点均已执行 When 对 `Row Filter` 选择"从此开始" Then 执行 `Row Filter` 及其全部下游。上游有未执行节点时拒绝并提示。
- AC-2 "仅执行本节点"：上游均已执行时只执行该节点，下游不执行且退回"已配置"。
- AC-3 "重置"：节点及其所有下游退回"已配置"，对应缓存文件删除。
- AC-4 "重置全部"：所有节点退回"已配置"，`.runs/cache/` 清空。

### US-EXE-04 节点输出缓存 [P0] [unit][int]

作为系统，我要只复用语义安全且输入未变的节点输出，以便局部执行快速且不跳过副作用。
关联：F-EXE-03

- AC-1 `[unit]` 每个节点声明 `cache_policy: pure | volatile | side_effect`，默认 `side_effect`。`pure` 的结果仅由声明输入决定，可命中缓存；`volatile` 的结果依赖实时外部状态或具有非确定性，禁止跨 Run 复用；`side_effect` 产生需要每次执行的外部效果，禁止缓存跳过。工具授权由 `tool_capability` 独立判断。
- AC-2 `[unit]` 缓存键 = `sha256(node_type + node_version + implementation_hash + canonical_json(resolved_params) + 按端口名排序的(port_name, content_hash) + 按名称排序的(external_input_name, content_hash) + user_code_hash + uv_lock_hash + iteration_index)`；参数对象键顺序不影响哈希，循环外迭代号为 null。只有节点通过 `cache_inputs` 显式声明的 `file | directory` 参数才额外读取外部状态。
- AC-3 `[int]` Given `Read CSV` 已执行 When 仅改变 `data/sales.csv` 内容且保持 mtime 与 size 不变 Then 下次运行仍重跑，因为其 `path` 声明为 `cache_inputs: file` 并使用内容 SHA-256。
- AC-4 `[int]` Given `Write CSV` 已有输出 When 再次运行 Then 节点实际执行并重新写入目标文件，体现 `side_effect`，即使输入与参数未变化也不得被缓存跳过。
- AC-5 `[int]` Table 输出缓存为 `.runs/cache/<node_id>/<port>.arrow`，Variable/Message/Excel 描述符为 `.json`；`meta.json` 另存 outputs 与可选 `activated_ports`。缓存损坏或版本不匹配视为未命中并重跑。打开工作流时只有有效 `pure` 缓存使节点显示"已执行"。
- AC-6 `[int]` 每个 Run 入队时冻结图、参数、变量和节点 manifest 到 `.runs/<run_id>/workflow.json`；活跃 Run 中允许的非结构修改仅影响下一 Run，NodeTool 的固定参数也取该冻结快照。
- AC-7 `[int]` 每个已执行端口在 `meta.json` 的 `outputs: {port: ValueRef}` 记录不可变值；≤256 KB 的 JSON 可内联，Table 与大 JSON 写入 `.runs/<run_id>/outputs/<node_id>/<port>`。缓存命中时也复制文件值到本 Run outputs 并复用已有哈希，缓存重置或 LRU 删除后历史快照仍可读。历史端口 API 不读临时 IPC 或当前全局缓存，默认随最近 50 次 Run 保留。
- AC-8 `[unit]` 每个 `workflow.json` 含整数 `revision`；保存携带读取时 revision，CAS 不一致返回 409。运行中结构修改拒绝，非结构修改允许且递增 revision。
- AC-9 `[int]` `List Files` 的 `path` 声明为 `cache_inputs: directory`；按相同 path/pattern/recursive 规则生成排序后的 `{path,name,size,modified,is_dir}` 指纹，任一条目变化都使缓存失效，未声明参数不得触发隐式文件读取。
- AC-10 `[int]` Given 实时 `Excel Read Range` 或 `LLM Call` 已有输出 When 再次运行 Then 节点实际执行，体现 `volatile`，不得跨 Run 复用结果。Excel App/Workbook 描述符可在重新 `resolve()` 成功后复用，但不得据此复用 Excel Read 的表格内容。
- AC-11 `[unit]` 节点注册表测试逐项核对内置节点的预期缓存策略：`Read CSV`、`Row Filter`、`Sorter` 与纯表格变换为 `pure`；实时 `Excel Read Range`、`LLM Call` 为 `volatile`；文件/Excel 写入为 `side_effect`。新增节点必须同步更新预期矩阵，不得依赖缺省值隐式分类。
- AC-12 `[int]` If/Switch 的 `activated_ports` 与 outputs 一同缓存并写入 Run 记录；第二次运行缓存命中时重放同一分支决策，下游执行路径与首次一致。

### US-EXE-05 实时状态推送 [P0] [int][e2e]

作为设计者，我想要执行过程实时可见，以便不盲等。  
关联：F-EXE-04

- AC-1 `[int]` 连接 `WS /api/ws` 并完成 authenticate 与 subscribe 后，运行期间收到事件序列：`run.started` → 若干 `node.started` / `node.progress` / `node.log` / `node.finished` / `node.failed` → `run.finished`；每个事件含 `run_id, node_id, ts`。
- AC-2 `[int]` agent 节点运行时推送 `node.stream` 事件，`delta` 字段为增量文本，顺序与 LLM 输出一致。
- AC-3 Given WebSocket 断线重连 Then 客户端显示连接状态，以带退避的新连接代际重新 authenticate，等待认证 ACK 后 subscribe，并通过 `GET /api/runs/{id}` 等 REST baseline 补齐状态；旧代际事件不得污染状态，不丢最终结果，用户可手工立即重连。
- AC-4 `[e2e]` 底部日志面板按节点分组显示日志，支持筛选级别（INFO/WARN/ERROR）与按节点过滤。
- AC-5 `[int]` 未认证或令牌无效的 WS 连接不得订阅或接收事件；认证成功前发送 subscribe 返回认证错误并关闭连接。

### US-EXE-06 端口视图 [P0] [int][e2e]

作为设计者，我想要点击任何已执行的输出端口直接看数据，以便不用加调试节点。  
关联：F-EXE-05

- AC-1 Given `Row Filter` 已执行 When 点击其 Table 输出端口 Then 弹出表格预览：显示列名、类型、总行数，分页每页 100 行，可按列排序，可复制单元格。
- AC-2 Excel 端口显示描述符摘要：工作簿名、工作表、地址、行列数。
- AC-3 Message 端口显示消息列表（role、内容、tool call）；Variable 端口显示键值表。
- AC-4 `[int]` `GET /api/runs/{run_id}/nodes/{node_id}/ports/{port}?offset=0&limit=100` 返回 Arrow IPC 流（`Content-Type: application/vnd.apache.arrow.stream`）或 JSON，依端口类型而定。
- AC-5 未执行的端口点击时提示"节点未执行"。

### US-EXE-07 错误处理与 Try Start/Try End [P0] [int][e2e]

作为设计者，我想要节点失败时信息清晰且不丢已完成结果，并能用 Try Start/Try End 兜底，以便工作流健壮。
关联：F-EXE-06

- AC-1 Given `Row Filter` 引用了不存在的列 When 运行 Then `Row Filter` 为错误态，`Sorter` / `Write CSV` 保持"已配置"，`Read CSV` 保持"已执行"且缓存可用；运行状态为 `failed`。
- AC-2 错误信息包含：节点名、异常类型、消息、完整 traceback、输入快照（Table 前 20 行）。
- AC-3 `[int]` Given `Try Start → 可能失败的节点 → Try End`，且 `Try End` 的 `on_error` 分支已连接 Then 失败时执行 `on_error` 分支，运行状态为 `succeeded`，`Try End` 输出的 `error` 变量含错误信息。
- AC-4 用户 Python 节点抛出的异常，traceback 只显示用户代码部分，隐藏引擎内部帧。

### US-EXE-08 取消运行 [P0] [int][e2e]

作为设计者，我想要中止正在进行的运行，以便不等待错误的长任务。  
关联：F-EXE-07, F-EXE-13

- AC-1 Given 一个运行中的 `Wait` 节点（`duration_seconds: 30`） When 点击"停止" Then 运行在 2 s 内变为 `cancelled`，`Wait` 节点为"已取消"状态，下游不执行。
- AC-2 `[int]` 正在执行的 Python Script 子进程收到终止信号（Windows：`CTRL_BREAK_EVENT`，3 s 后未退出则 kill）。
- AC-3 正在执行的 Agent Loop 立即取消在途 HTTP 请求，当前 LLM 调用以取消结束，不等待正常响应，也不再发起新一轮；正在执行或排队的工具调用继承同一 Run 取消上下文。
- AC-4 已完成节点的缓存保留。
- AC-5 `[int]` Given `Wait`（`duration_seconds: 0.1`）连接下游探针 When 正常运行 Then Wait 在不少于 0.1 s 后成功结束，下游仅在此后执行一次；未收到取消时不得提前放行下游。

### US-EXE-09 运行历史 [P1] [int][e2e]

作为设计者，我想要回看过去的运行记录，以便排查问题。  
关联：F-EXE-08

- AC-1 `GET /api/workflows/{id}/runs?limit=20` 返回最近运行列表：`run_id, trigger_source, started_at, finished_at, status`。
- AC-2 每次运行存 `.runs/<run_id>/meta.json`（状态、错误与端口 ValueRef）、`log.jsonl`（Run 日志）与可选的 `nodes/<node_id>.trace.jsonl`（agent 轨迹）；不生成 `nodes/<node_id>.json`。
- AC-3 UI "历史"面板列出运行，点击可查看各节点状态与日志（只读）。
- AC-4 保留策略：默认保留最近 50 次，超出按时间删除，可在设置中修改。

### US-EXE-10 循环：按行 [P0] [int]

作为设计者，我想要对表的每一行执行一段子图，以便逐项处理。  
关联：F-EXE-09

- AC-1 Given `Loop Start (Row)` 输入 10 行表，循环体为 `Variable → LLM Call → Table Creator`，`Loop End (Collect)` Then 循环体执行 10 次，每次 `Loop Start` 的 Variable 端口输出当前行各列为流变量，`Loop End` 输出 10 行拼接表。
- AC-2 循环体内某次失败时整个循环失败（默认）；`Loop End` 参数 `on_error: skip` 时跳过该次并在输出加 `_error` 列。
- AC-3 UI 上循环体节点显示当前迭代 `3 / 10`。
- AC-4 `[int]` 循环体内节点的缓存键包含迭代序号，不会跨迭代误命中。

### US-EXE-11 循环：按块与计数 [P0] [int]

作为设计者，我想要按固定行数分块或固定次数循环，以便批量调用。  
关联：F-EXE-09

- AC-1 `Loop Start (Chunk)`，`chunk_size: 100`，输入 1000 行 Then 循环 10 次，每次 Table 端口输出 100 行。
- AC-2 `Loop Start (Counting)`，`from: 0, to: 5, step: 1` Then 循环 5 次，`i` 依次为 0、1、2、3、4；`to` 为上界且排他，负 step 时按同一半开区间规则向反方向迭代，step=0 拒绝。
- AC-3 `Loop End` 支持三种收集模式：`concat`（拼接表）、`last`（只保留最后一次）、`variables`（收集变量为表）。
- AC-4 Loop Start 与 Loop End 必须成对且嵌套合法；保存时校验，非法时画布提示"Loop Start 无匹配 Loop End"。

### US-EXE-12 条件分支 [P0] [int]

作为设计者，我想要按条件走不同分支，以便处理多种情况。  
关联：F-EXE-10

- AC-1 `If` 节点参数 `condition` 为表达式（变量作用域内，语法为受限的 Python 表达式，由 `simpleeval` 求值），输出两个 Flow 端口 `true` / `false`；只有命中分支的下游执行，未命中分支的下游标记为"已跳过"（灰）。

- AC-2 `Switch` 节点参数 `variable` 与 `cases`（值 → 端口名列表）及 `default` 端口；按变量值选择一个输出端口。
- AC-3 `[int]` `Merge` 固定两个命名 Table 输入 `left/right`，每端口最多一条入边，并声明 `accepts_partial_inputs=true`；仅命中一侧时接收该侧数据并执行，两侧均 skipped 时 Merge 也 skipped。
- AC-4 表达式求值错误（引用不存在的变量、语法错）时 `If` 节点失败，错误信息含表达式原文与位置。
- AC-5 `[unit]` 表达式沙箱禁止 `import`、属性访问 `__xxx__`、函数调用白名单外的函数；有对应的拒绝测试。
- AC-6 `[int]` 菱形 `If → A/B → Merge` 分别命中 true、false 时，未命中侧传播 `skipped_branch`，Merge 等待两侧输入均到终态后执行；双侧 skipped 时 Merge 跳过并继续传播。所有节点最终进入终态，不重复执行；与 ExecScope 相交时 scope 外节点记录 `out_of_scope` 且 UI 保持已配置。

### US-EXE-13 运行互斥与排队 [P0] [int]

作为系统，我要保证同一工作流同一时刻只有一个活跃运行，以便避免 Excel 与缓存冲突。  
关联：F-EXE-11

- AC-1 Given 工作流 A 正在运行 When 再次触发 A Then 按工作流设置 `concurrency_policy`：`queue`（默认）→ 新触发入队，当前运行结束后依次执行；`drop` → 新触发被丢弃并记录日志，不创建 Run；`cancel_previous` → 取消当前运行后执行新触发。
- AC-2 队列长度上限 10，超出请求返回 409 `RUN_QUEUE_FULL` 并记录 WARN，不创建 Run。
- AC-3 不同工作流之间可并行运行，但 Excel 操作全局串行（见 US-XLS-11）。
- AC-4 `GET /api/workflows/{id}/runs?status=queued` 可查看队列。
- AC-5 `[int]` 立即执行/入队返回 202 `{run_id, disposition: started|queued}`；策略 drop 返回 200 `{run_id: null, disposition: dropped}`；手动、聊天和 HTTP 触发使用同一规则。
- AC-6 `[int]` 服务运行时 `weft run` 只调用服务 API；服务未运行时内嵌 CLI 与服务模式共用每工作流跨进程执行锁，锁记录 PID、进程创建时间与 Run ID，缓存访问受同锁保护。服务与 CLI、两个内嵌 CLI 同时触发时不得产生两个活跃 Run；不同进程中的 Excel 调用仍经 Windows `Local\WeftExcelCOM` 互斥串行，异常退出按进程身份回收 stale 锁。

### US-EXE-14 工作流独立执行环境 [P0] [int]

作为系统，我要在工作流自己的 venv 中执行节点代码，以便用户依赖不污染 Weft 本体。  
关联：F-EXE-12

- AC-1 Given 工作流 `pyproject.toml` 声明依赖 `requests` When 打开工作流 Then 系统在 `<root>/.venv/` 执行 `uv sync`，UI 显示进度；完成前运行按钮禁用。
- AC-2 `[int]` Python Script 节点中 `import requests` 成功；Weft 本体环境中无 `requests`。
- AC-3 `[int]` Worker 由 `<root>/.venv/Scripts/python.exe` 启动，执行已安装的 `weft-worker` 入口且不依赖主机 `PYTHONPATH`；每 Run 懒启动独立 Worker pool（默认并行度 4），每个 Worker 同时只处理一个 `execute`。测试用两个真实子进程的重叠执行证明并行，Run 结束后 pool 全部退出且下一 Run 不继承全局变量。
- AC-4 `uv sync` 失败（依赖冲突、网络）时，UI 显示 uv 的完整输出，工作流处于"环境异常"状态，可重试。
- AC-5 创建工作流时，生成器将 `weft-worker==<service_version>` 及用户依赖写入标准 `pyproject.toml` 的 `dependencies` 并锁入 `uv.lock`；主服务与 Worker 版本不一致时拒绝运行。`[tool.weft]` 仅存 Weft 元数据，不声明 uv 会自动合并的自定义依赖段。
- AC-6 `[unit]` monorepo 中 `weft-worker` 包含 Worker 入口、RPC 与可信 Worker 内置节点实现并依赖 `weft-sdk`；Excel COM 的 xlwings/pywin32 只由主服务环境安装，不要求每个 Worker 安装。
- AC-7 `[int]` v1 不承诺 Worker 跨版本兼容；服务升级后打开旧工作流时提示更新 `weft-worker==<service_version>`，经用户确认后重锁并 `uv sync`，版本仍不一致则拒绝运行，不隐式修改 lock。

---

## 3. Epic XLS：Excel 联动

> 本 Epic 的 `[int-win]` 测试需真实 Excel；CI 中以 `FakeExcelBackend`（内存实现 `ExcelBackend` 接口）运行 `[int]` 标记的 AC。

### US-XLS-01 连接可见 Excel 实例 [P0] [int-win]

作为设计者，我想要工作流连接到我正在用的那个 Excel，以便实时联动。  
关联：F-XLS-01

- AC-1 Given 用户已打开 Excel（含 `ref.xlsx`） When 执行 `Excel Connect`（`mode: attach_visible`） Then 节点输出 Excel App 引用，描述符含 `pid`、`visible: true`、`workbooks: ["ref.xlsx"]`；用户的 Excel 窗口无闪烁或焦点变化。
- AC-2 Given 没有运行中的 Excel When 执行 Then 启动一个新的可见 Excel 实例并连接；Run 结束后该实例不被关闭（用户可能要看）。
- AC-3 Given 多个 Excel 实例 Then UI/参数提供实例列表，用户按 PID、窗口标题或已打开工作簿明确选择；工作流只保存工作簿名/路径等稳定目标，最近 PID/窗口选择按 `(workflow_id, node_id)` 存入 `%APPDATA%/weft/excel-targets.toml` 且不进入打包产物；不得假定 `GetActiveObject` 返回“最近活动实例”，该行为须在 M0 实测。
- AC-4 `[int]` Given schedule/watch/http 等无人值守 Run When 已保存目标无法解析或匹配多个实例 Then 运行前失败并列出原因，不随机 attach，也不自动改用隐藏实例；PID 变化后仅在已选工作簿等稳定身份能唯一匹配时重新解析。

### US-XLS-02 启动独立隐藏实例 [P0] [int-win]

作为设计者，我想要可选地用一个隐藏的 Excel 实例，以便不干扰我手头的工作。  
关联：F-XLS-02

- AC-1 `Excel Connect`（`mode: new_hidden`）启动新 Excel 进程，`Visible=False`，`DisplayAlerts=False`；描述符 `visible: false`，登记 owned PID、进程创建时间、Run 与心跳。
- AC-2 Run 结束（成功/失败/取消）时关闭该隐藏实例；`on_finish: save | discard` 无默认值，用户必须在运行前显式选择，未保存工作簿逐个列入结果报告，不得静默丢弃。
- AC-3 Weft 服务异常退出时，`weft doctor --cleanup` 仅依据 Weft 登记且 PID+创建时间+Run/心跳匹配的 owned 隐藏实例进行清理；无法验证归属则不终止并提示人工处理，不依赖未经验证的命令行标记。

### US-XLS-03 引用、打开、新建工作簿 [P0] [int][int-win]

作为设计者，我想要以三种方式获得工作簿引用，以便覆盖已打开、文件、新建三种情况。  
关联：F-XLS-03

- AC-1 `Excel Workbook`（`mode: open_existing`，`name: "ref.xlsx"`）：Given 该工作簿已在连接的实例中打开 Then 输出 Workbook 引用；未打开则失败，错误信息列出当前已打开的工作簿名。
- AC-2 `Excel Workbook`（`mode: open_file`，`path: "data/ref.xlsx"`）：路径相对 Root 解析；若该文件已被同一实例打开则直接引用而非重复打开；文件不存在则失败。
- AC-3 `Excel Workbook`（`mode: new`）：新建空白工作簿，描述符 `name: "Book1"`（Excel 分配的名），`saved: false`。
- AC-4 `[int]` 以上三种模式在 `FakeExcelBackend` 下行为一致（接口契约测试）。

### US-XLS-04 读取区域为表 [P0] [int][int-win]

作为设计者，我想要把工作表的一块区域读成表，以便进入数据流处理。  
关联：F-XLS-04

- AC-1 `Excel Read Range`（`sheet: "Sheet1"`，`range: "A1:E101"`，`header: true`）Then 输出 Table 100 行 5 列，列名来自第一行。
- AC-2 `range` 留空 → 读取 `UsedRange`；`range: "Table1"` → 读取同名表格对象（ListObject）；`range: "MyNamed"` → 读取命名区域。
- AC-3 类型推断：整列为数字 → `Float64`（整数则 `Int64`）；Excel 日期序列号且单元格格式为日期 → `Datetime`；混合 → `Utf8`；空单元格 → null。
- AC-4 `[int-win]` 在固定基准机上以整块 `Range.Value` 一次读取 10 万单元格（1000×100），记录受控基准结果，目标 < 3 s；该数值不是任意机器的硬性 AC，测试禁止逐格读取。
- AC-5 工作表不存在 → 失败并列出可用工作表名。
- AC-6 `[int]` `Excel Read Range` 为 `volatile`；两次 Run 之间即使用户只修改一个单元格且其他输入描述符不变，也必须重新读取新值，禁止跨 Run 复用表格内容。

### US-XLS-05 写表到区域 [P0] [int][int-win]

作为设计者，我想要把表写到工作表指定位置，并在用户 Excel 中立即可见，以便实时输出。  
关联：F-XLS-05

- AC-1 `Excel Write Table`（`sheet: "本周"`，`start: "A1"`，`mode: overwrite`，`header: true`）Then 从 A1 起写入表头与全部行；可见实例默认模式（`fast_mode: false`）下窗口立即显示数据，工作表不存在时自动创建。
- AC-2 `mode: append` → 从该工作表 `start` 列的最后非空行下一行开始写，不写表头。
- AC-3 `mode: overwrite` 且 `clear_below: true`（默认）→ 写入前清空 `start` 以下、表宽以内的旧内容。
- AC-4 `autofit: true` → 写后自适应列宽；`preserve_format: true` → 只写 `Value`，不改变目标格式。
- AC-5 `[int-win]` 在固定基准机上整块写入 10 万单元格并记录结果，目标 < 3 s；不作为任意机器硬 AC。
- AC-6 null 写为空单元格；`Datetime` 写为 Excel 日期并保留原列格式；`allow_formula: false`（默认）时，`Utf8` 以 `=` 开头的值前缀 `'` 以防被解释为公式；`allow_formula: true` 时才作为公式写入。

### US-XLS-06 更新零散单元格 [P0] [int][int-win]

作为设计者，我想要更新若干不连续的单元格，以便做仪表盘式联动。  
关联：F-XLS-06

- AC-1 `Excel Cell Update` 参数 `cells` 为列表 `[{address: "B2", value: 42}, {address: "D5", value: "done"}]`，或从输入 Table（列 `address, value`）读取；执行后对应单元格更新。
- AC-2 `allow_formula: false`（默认）时，`value` 以 `=` 开头也按普通文本写入；仅 `allow_formula: true` 时写入公式。
- AC-3 地址非法时整节点失败且不写入任何单元格（先校验全部地址）。

### US-XLS-07 工作表管理 [P0] [int][int-win]

作为设计者，我想要列出、新建、删除、重命名工作表，以便组织输出。  
关联：F-XLS-07

- AC-1 `Excel Sheet Names` 输出 Table（列 `name, index, visible`）。
- AC-2 `Excel Sheet`（`action: create | delete | rename | clear`）；`delete` 时若为最后一张工作表则失败。
- AC-3 `delete` 不弹 Excel 确认框（临时设置 `DisplayAlerts=False` 并在操作后恢复）。

### US-XLS-08 显式保存 [P0] [int][int-win]

作为设计者，我想要显式控制保存，以便 Weft 不会悄悄覆盖我的文件。  
关联：F-XLS-08

- AC-1 `Excel Save`（`mode: save`）：工作簿从未保存过（`saved: false` 且无路径）时失败并提示用 `save_as`。
- AC-2 `Excel Save`（`mode: save_as`，`path: "out/result.xlsx"`）：路径相对 Root；目录不存在则创建；文件已存在按参数 `overwrite: false` 默认失败。
- AC-3 Run 结束时 Weft 对可见实例中的工作簿**不**执行任何保存或关闭。
- AC-4 `format` 参数支持 `xlsx | xlsm | csv`，映射到 `FileFormat` 常量。

### US-XLS-09 运行宏 [P1] [int-win]

作为设计者，我想要调用工作簿中的宏，以便复用已有 VBA。  
关联：F-XLS-09

- AC-1 `Excel Run Macro`（`macro: "Module1.Refresh"`，`args: [...]`）调用 `Application.Run` 并将返回值输出为 Variable。
- AC-2 宏不存在或 VBA 抛错 → 节点失败，错误信息含 COM 错误描述。

### US-XLS-10 性能模式 [P1] [int-win]

作为设计者，我想要在批量写入时暂停重算与刷屏，以便更快。  
关联：F-XLS-10

- AC-1 `fast_mode` 在可见实例默认 false、隐藏实例默认 true；显式开启时执行前设置 `ScreenUpdating=False, Calculation=Manual, EnableEvents=False`，执行后无论成功失败均恢复原值，尤其必须恢复屏幕刷新。
- AC-2 `[int-win]` 在固定基准机上分别测量 1000 次逐格 Cell Update 与批量合并调用，记录对比结果；逐格 < 2 s 仅作受控优化目标，不作为任意机器硬 AC。

### US-XLS-11 Excel 操作串行与连接共享 [P0] [unit][int]

作为系统，我要把所有 COM 调用放在专用 STA 线程串行执行，以便避免 COM 线程错误。  
关联：F-XLS-11

- AC-1 `[unit]` 服务或内嵌 CLI 通过监督器管理独立 `ExcelWorker` 子进程；COM 只在子进程的单 STA 线程执行并在该线程调用 `CoInitialize`，所有 `ExcelBackend` 方法通过 `worker.submit(fn)` 投递并 await 结果；在其他线程直接调用 COM 对象的代码路径在 debug 模式下触发断言。
- AC-2 `[int]` 两个工作流同时运行且都含 Excel 节点时，COM 调用严格串行，无 `CoInitialize`/`RPC_E_WRONG_THREAD` 错误；服务与内嵌 CLI、多个内嵌 CLI 之间通过 Windows `Local\WeftExcelCOM` 互斥锁保持同样的全局串行。
- AC-3 同一 Run 内多个 Excel 节点共享同一个 App 连接；Excel 引用通过端口传递描述符，worker 端维护 `描述符 → COM 对象` 映射，Run 结束释放。
- AC-4 Excel App/Workbook 描述符可在 `resolve()` 成功后复用；工作簿或工作表解析失败则重跑连接上游。实时 Excel Read 是 volatile，每次 Run 都重新读取单元格，不因描述符有效而复用表格内容。
- AC-5 `[int]` 连续超时达到 `excel.restart_after_timeouts`（默认 3）或监督心跳确认进程失效时，监督器终止并重建 ExcelWorker；后续新请求可恢复，排队请求以 `EXCEL_WORKER_RESTARTED` 明确失败，不自动重放，服务与其他非 Excel 节点保持运行。

### US-XLS-12 Excel 不可用时的明确错误 [P0] [int][int-win]

作为设计者，我想要 Excel 出问题时得到明确提示而不是挂死，以便快速处理。  
关联：F-XLS-12

- AC-1 未安装 Excel（COM 注册表无 `Excel.Application`）→ `Excel Connect` 在 1 s 内失败，错误 `Excel is not installed or not registered`。
- AC-2 Excel 被模态对话框阻塞（`RPC_E_CALL_REJECTED` / `0x800AC472`）→ 自动重试 3 次（间隔 1 s），仍失败则节点失败，错误 `Excel is busy (modal dialog open?)`；UI 提示用户检查 Excel 窗口。
- AC-3 单次 COM 调用超过 `excel.call_timeout`（默认 60 s）→ 本次请求失败/结果被丢弃，但 ExcelWorker 仍被旧调用占用，后续 Excel 操作排队且 UI 显示繁忙；达到恢复阈值后按 US-XLS-11 AC-5 重建，不宣称超时后立即可处理下一项。
- AC-4 `weft doctor` 报告 Excel 版本、可连接实例列表、Sandboxie 动态 box 与网络默认拒绝检查。
- AC-5 `[int-win]` 注入不可中断的 COM 调用使 ExcelWorker wedged 后，系统能按阈值重建 Worker 并恢复新请求；超时写请求和重建时排队请求均报告结果未知/失败，不自动重放，不 kill 用户可见 Excel。

---

## 4. Epic TBL：表格与文件

### US-TBL-01 Arrow 传递与 Polars 计算 [P0] [unit][int]

作为系统，我要以 Arrow IPC 文件作为跨进程表格格式，以便统一传输并减少不必要复制。
关联：F-TBL-01

- AC-1 `[unit]` Table 端口在引擎内为 `pyarrow.Table`；节点实现以 `polars.DataFrame` 接收并返回，由框架转换。v1 只支持内存内数据，不以 Polars lazy 暗示超内存能力。
- AC-2 `[int]` 跨 Worker 通过 Arrow IPC 文件 + memory-map 读取，记录 10 万行 × 20 列在固定基准机上的结果，目标 < 100 ms；分别测序列化、写盘、哈希、映射和 DataFrame 转换，不宣称全链路零拷贝。
- AC-3 列名重复、列名为空时节点失败，提示具体列。

### US-TBL-02 读写文件表格 [P0] [int]

作为设计者，我想要读写 CSV / Parquet / JSON / Excel 文件，以便与外部数据交换。  
关联：F-TBL-02

- AC-1 `Read CSV`（`path, encoding: auto, separator: auto, header: true, skip_rows: 0`）→ 读 `data/sales.csv` 得 1000 行 5 列；`encoding: auto` 依次尝试 `utf-8-sig, utf-8, gbk`。
- AC-2 `Read Parquet`、`Read JSON`（lines 或 array 两种格式自动检测）、`Read Excel File`（`sheet`，经 `fastexcel`，不经 COM，可在 Excel 关闭时使用）。
- AC-3 `Write CSV`（`path, encoding: utf-8-sig, separator: ","`）、`Write Parquet`、`Write JSON`、`Write Excel File`（`sheet`，用 `xlsxwriter`，整文件覆盖）。
- AC-4 写节点参数 `overwrite: true` 默认；`false` 且文件存在则失败。
- AC-5 路径相对 Root；写入时自动创建父目录。

### US-TBL-03 基础变换节点 [P0] [unit][int]

作为设计者，我想要常用的单表变换节点，以便无代码清洗。  
关联：F-TBL-03

- AC-1 `Column Filter`：`mode: include | exclude`，`columns: [...]`，支持通配符 `amount_*`。
- AC-2 `Row Filter`：`column, operator (==, !=, >, >=, <, <=, contains, starts_with, regex, is_null, is_not_null, in), value`；多条件时用 `Row Filter` 串联或 `Rule Engine`。
- AC-3 `Sorter`：`keys: [{column, descending}]`，稳定排序。
- AC-4 `Column Rename`：`mapping: {old: new}`；目标名已存在则失败。
- AC-5 `Duplicate Filter`：`columns: [...]`（空 = 全部），`keep: first | last`。
- AC-6 `Missing Value`：按列指定策略 `drop_row | fill_const | fill_mean | fill_prev`。
- AC-7 `Type Cast`：`mapping: {column: type}`，type ∈ `int, float, str, bool, date, datetime`；`strict: false` 默认失败值转 null，`true` 则节点失败。
- AC-8 `[unit]` 每个节点有基于固定小表的参数化测试，覆盖正常路径与至少一个错误路径。

### US-TBL-04 组合节点 [P0] [unit][int]

作为设计者，我想要多表组合节点，以便合并数据。  
关联：F-TBL-04

- AC-1 `Joiner`：两个 Table 输入，`how: inner | left | right | outer | cross | anti | semi`，`left_on, right_on`，重名列后缀 `_right`。
- AC-2 `Concatenate`：通过 `DynamicPortGroup` 实例化 `in_1...in_N` 命名 Table 输入（N ≥ 2，每端口一条入边，按端口序号排序），`how: vertical | horizontal | diagonal`（diagonal 允许列不一致，缺失填 null）。
- AC-3 `GroupBy`：`group_by: [...]`，`aggregations: [{column, agg: sum|mean|min|max|count|count_distinct|first|last|list|concat_str, alias}]`。
- AC-4 `Pivot`：`index, columns, values, agg`；`Unpivot`：`index, on, variable_name, value_name`。

### US-TBL-05 表达式与规则节点 [P0/P1] [unit][int]

作为设计者，我想要用表达式新增列或按规则赋值，以便处理无专用节点的场景。  
关联：F-TBL-05, F-TBL-06

- AC-1 `Polars Expression`：`expressions: [{alias, expr}]`，expr 使用 Python 风格 AST 白名单表达列引用、字面量、运算符和白名单函数（如 `col("amount") * 1.1`），编译为 Polars 表达式；禁止 Python `eval`，错误显示位置与原因。
- AC-2 `Math Formula`：简化语法 `$amount$ * 1.1 + $tax$`，`$col$` 引用列，转为 Polars 表达式执行。
- AC-3 `String Manipulation`：常用函数 `upper, lower, strip, replace, regex_replace, substr, concat, pad`，参数化。
- AC-4 `[P1]` `Rule Engine`：有序规则列表 `[{condition, value}]` + `default`，`condition` 使用 Row Filter 相同的条件语法，首个命中生效，输出列 `alias`。
- AC-5 `[unit]` AST 白名单拒绝属性访问、import、任意调用、`__builtins__`、文件和网络；If 仍由 simpleeval 求值并遵守函数白名单，不与行条件语法混用。

### US-TBL-06 Table ↔ Variable [P0] [unit][int]

作为设计者，我想要表与流变量互转，以便把计算结果作为参数。  
关联：F-TBL-07

- AC-1 `Table to Variables`：取第一行（或 `row_index`），每列成为同名变量；`mode: column_lists` 时每列成为列表变量。
- AC-2 `Variables to Table`：选中变量成为单行表。
- AC-3 `Table Row Count` 输出变量 `row_count`（常用于 If 判断）。
- AC-4 `Variable` 节点：手工定义 `[{name, type, value}]`，type ∈ `str, int, float, bool, path, list`；`path` 类型相对 Root 解析为绝对路径后再输出。

### US-TBL-07 文件操作 [P0] [int]

作为设计者，我想要对文件系统做基本操作，以便搬运数据文件。  
关联：F-TBL-08

- AC-1 `List Files`（`path, pattern: "*.xlsx", recursive: false`）→ Table 列 `path (相对Root), name, size, modified, is_dir`；`path` 声明为 directory 类型缓存输入，目录指纹按 US-EXE-04 AC-9 计算。
- AC-2 `File Copy / Move / Rename / Delete`：输入 Table（列 `path`）或参数单路径；`Move`/`Rename` 目标存在时按 `overwrite` 处理；`Delete` 默认移入回收站（`send2trash`），`permanent: true` 才真删。
- AC-3 `Path Join`：`parts: [...]`（可绑定变量）→ 变量 `path`，自动规范化分隔符。
- AC-4 Root 外的绝对路径操作允许，但节点显示黄色"不可移植"警告（设计期）。
- AC-5 所有文件节点允许解析到 Root 之外的 `..` 路径（用户可信车道），不因此拒绝操作，但显示不可移植警告。

### US-TBL-08 Python Script 节点 [P0] [int]

作为设计者，我想要在节点里写 Python，以便处理任何特殊逻辑。  
关联：F-TBL-09

- AC-1 `Python Script` 节点参数：`source: inline | file`，`code`（inline 时）或 `path`（相对 Root，通常在 `nodes/` 下），`inputs: [{port, var}]`，`outputs: [{var, port, type}]`。这些参数是 `DynamicPortGroup` 的配置来源，保存时实例化并校验端口唯一性；端口改名/删除使对应连线失效，实例化清单进入节点 manifest 与缓存键。执行时每个输入 Table 端口绑定为同名 `polars.DataFrame` 变量，流变量以 `vars` 字典注入，用户代码结束后按 `outputs` 声明读取变量作为输出端口值。
- AC-2 代码可以是脚本体（直接执行）或定义 `def run(inputs: dict, vars: dict) -> dict:`；两种形式均支持，后者优先。
- AC-3 `[int]` 输出变量类型不符（声明 Table 但得到 `str`）→ 节点失败，提示 `Output 'df' expected Table, got str`。
- AC-4 `print()` 输出作为 INFO 日志推送到 UI；未捕获异常的 traceback 仅显示用户代码帧（见 US-EXE-07 AC-4）。
- AC-5 inline 代码编辑器支持语法高亮与 `Ctrl+Enter` 执行到此；`source: file` 时提供"在外部编辑器打开"按钮，文件变化后节点自动退回"已配置"。
- AC-6 `[int]` 用户代码运行在工作流 venv 的 worker 进程内（US-EXE-14），可 `import` 工作流依赖；可通过 `weft_ctx.root` 获得 Root 绝对路径，`weft_ctx.log(...)` 写日志，`weft_ctx.progress(0.5)` 上报进度。
- AC-7 `[int]` 用户代码抛出 `weft_ctx.Cancelled` 或收到取消信号时节点状态为"已取消"。

### US-TBL-09 Shell Command 节点 [P1] [int]

作为设计者，我想要在可信车道执行一条命令，以便调用外部工具（非 agent 使用）。  
关联：F-TBL-10

- AC-1 `Shell Command`（`command`，`cwd` 默认 Root，`shell: powershell | cmd`，`timeout`，`env`）→ 输出变量 `stdout, stderr, exit_code`；`fail_on_nonzero: true` 默认。
- AC-2 命令中可用 `{var}` 插值流变量，但 PowerShell 与 cmd 必须使用各自独立、经测试的转义器，不得共用所谓通用引号规则；值无法安全表示为单个字面量时节点失败。两种 shell 均测试空格、单双引号、换行及 `$`、反引号、`%`、`&`、`|`、`>` 等元字符，插值不得改变命令结构或产生额外命令。
- AC-3 输出实时流式推送到日志面板。

### US-TBL-10 Table View 与 Table Creator [P0] [e2e][int]

作为设计者，我想要在画布上固定展示一张表，或手工创建一张小表，以便做参考与测试。  
关联：F-EXE-05, F-TBL-07

- AC-1 `Table View` 节点：输入 Table，执行后节点体内嵌显示前 N 行（默认 10），可展开为完整端口视图。
- AC-2 `Table Creator` 节点：侧栏提供可编辑网格，列可指定类型，内容存于 `params.rows`；输出 Table。

---

## 5. Epic AGT：Agent

> LLM 相关 `[int]` 测试使用本地 mock OpenAI 兼容服务器（固定脚本应答，支持 `stream` 与 `tool_calls`）；`[manual]` 用真实模型验收。

### US-AGT-01 LLM 配置 [P0] [int][e2e]

作为设计者，我想要在全局设置中管理多个 LLM 端点配置，以便节点按名引用。  
关联：F-AGT-01

- AC-1 设置页"LLM 配置"可增删改：`name, base_url, api_key, model, extra_headers, timeout`；`api_key` 以掩码显示，存于用户级 `config.toml`（见 F-SBX-08）。
- AC-2 "测试连接"按钮调用 `GET {base_url}/models` 或发送最小补全请求，3 s 内显示成功/失败与错误体。
- AC-3 所有 agent 类节点的 `llm` 参数为下拉，选项来自配置名；配置不存在时节点运行失败 `LLM config 'xxx' not found`。
- AC-4 `[int]` 请求按 OpenAI Chat Completions 规范构造；`base_url` 末尾 `/v1` 有无均可。

### US-AGT-02 LLM Call 节点 [P0] [int]

作为设计者，我想要做一次 LLM 调用，以便处理文本任务。  
关联：F-AGT-02

- AC-1 `LLM Call` 参数：`llm, system_prompt, user_prompt, table_max_rows（默认 50）, temperature, max_tokens, output: text | json, json_schema（可选）`；两个 prompt 均使用与 Prompt Template 相同的 Jinja2 沙箱子集，流变量写作 `{{ var }}`；输入 Message（可选，作为历史）、Variable 与可选 Table；输出 Message 端口（完整历史 + 本次回复）与 Variable 端口（`response` 文本或解析后的 JSON）。
- AC-2 `output: json` 时请求带 `response_format`；解析失败则重试 1 次（追加"请只输出合法 JSON"），仍失败则节点失败并附原始文本。
- AC-3 输入表通过 `tables.<port>` 暴露，`{{ tables.in | table }}` 渲染为 Markdown（前 `table_max_rows` 行）；`table` 是专用只读 filter，不允许访问任意对象属性。
- AC-4 `[int]` 流式输出通过 `node.stream` 事件推送；节点日志记录 `prompt_tokens, completion_tokens, latency_ms`。
- AC-5 HTTP 错误按状态码处理：429/5xx 指数退避重试 3 次；4xx 其他直接失败并附响应体。

### US-AGT-03 Agent Loop 节点 [P0] [unit][int][manual]

作为设计者，我想要一个 ReAct 循环节点，工具由端口注入，以便 agent 自主完成多步任务。  
关联：F-AGT-03

- AC-1 `Agent Loop` 参数：`llm, system_prompt, task（使用统一 Jinja2 沙箱子集）, max_turns（默认 20）, on_max_turns: fail | return_partial（默认 fail）, stop_on_text（可选正则）, tool_choice: auto | required`；输入端口：Message（历史，可选）、Variable、Tool（多条）、Table（可选，渲染进 task）；输出端口：Message（最终回复）、Message（完整轨迹）、Variable（`final_text`, `turns`, `tool_calls_count`, `stopped_by`, `partial`）。
- AC-2 `[unit]` 每轮先检查 `stop_on_text`，命中即停止；未命中且回复含 `tool_calls` 时逐个执行并回填，无 tool calls 时正常返回。达到 `max_turns` 默认节点失败；仅 `on_max_turns: return_partial` 时允许返回且必须 `partial: true, stopped_by: "max_turns"` 并记 WARN。
- AC-3 `[unit]` 工具 schema 来自 Tool 端口对象的 `name, description, parameters (JSON Schema)`；同名工具冲突时节点在运行前失败。
- AC-4 `[int]` 工具执行异常不终止循环：错误文本作为 tool 结果回填，agent 可自行修正；连续 3 次同一工具失败则终止。
- AC-5 每轮推送 `node.stream`（文本增量）与 `node.tool_call`（`tool, args_redacted, result_summary, duration_ms`）事件；UI 在节点侧栏以时间线展示。
- AC-6 `[manual]` 用真实模型完成场景 B（分类备注列），结果列正确率人工抽查可接受。

### US-AGT-04 Node as Tool [P0] [unit][int]

作为设计者，我想要把受控节点包装成工具给 agent，以便 agent 复用确定性能力而不获得任意主机执行权限。
关联：F-AGT-04, F-SBX-07

- AC-1 `Node as Tool` 参数：`target_node, tool_name, description, exposed_params, result_format: table_markdown | json | text`；下拉仅列出声明 `tool_capability` 的节点，且 `exposed_params` 必须是节点 `tool_exposed_params` 白名单子集。
- AC-2 `[unit]` 默认仅只读/纯计算节点可包装；Python Script、Shell Command、用户任意代码节点和 Agent 节点一律拒绝。写文件、Excel 写等副作用节点需设计者与调用时双重显式授权，默认逐次确认。
- AC-3 `[unit]` 工具 parameters schema 是允许暴露参数的子集；非暴露参数取当前 Run 的冻结 `workflow.json`，而非实时画布值。
- AC-4 `[int]` 调用以 ephemeral 方式执行，不写全局缓存、不改画布状态；需要上游输入时取本 Run 已物化的输入快照，缺失则返回 `Upstream of 'X' not executed`。Worker 调用占用本 Run pool 槽位，service 调用占用对应 lane 并发额度，池满时排队；调用继承 Run 取消上下文且受 `tool_timeout`（默认 120 s）约束，不另开绕过上限的执行通道。
- AC-5 每次调用写入 `.runs/<run_id>/audit.jsonl`：`ts, run_id, agent_node, tool, args_redacted, status, duration_ms, result_hash`；不得因审计记录原始 key 或敏感 URL。
- AC-6 `target_node` 不能是 Agent 类节点自身或其祖先（防递归）；保存时校验。Excel 类只读工具仍经 ExcelWorker 串行，副作用 Excel 工具遵守 AC-2。
- AC-7 `[int]` 构造未声明工具能力或试图暴露非白名单参数的节点，保存和直接调用均拒绝，不能借 NodeTool 绕过沙箱。

### US-AGT-05 Sandboxed Tools [P0] [int][int-win]

作为设计者，我想要给 agent 一组沙箱内的基础工具，以便它能自由读写文件与执行命令。  
关联：F-AGT-05, F-SBX-02

- AC-1 `Sandboxed Tools` 节点参数：`tools: [read, write, edit, list, bash]`（多选）、`cwd`（默认 Root）、`sandbox: inherit | none | sandboxie`（默认 inherit 自全局）、`bash_timeout`；输出 Tool 端口（一个端口承载多个工具）。
- AC-2 工具语义与 pi 一致：`read(path, offset?, limit?)`、`write(path, content)`、`edit(path, old_string, new_string)`（old_string 必须唯一匹配）、`list(path, pattern?)`、`bash(command, timeout?)`；bash 仅可用于 Sandboxie。
- AC-3 `[int-win]` `sandbox: sandboxie` 下，`write` 的文件出现在 `C:\Sandbox\<user>\<box>\drive\<盘>\...` 而非真实路径；`read` 可读真实文件；`bash` 进程由 `Start.exe /box:<box> /wait /silent /env:WEFT_RUN_ID=<id>` 启动。
- AC-4 `[int]` `sandbox: none` 需在节点上显式选择且全局设置 `sandbox.allow_none_sandbox: true`，否则运行前失败 `NoneSandbox is disabled in settings`；none 仅开放受控影子目录 read/write/edit/list，选择 bash 时运行前失败 `bash requires sandboxie`，不得启动直接主机子进程。
- AC-5 `bash` 输出截断至 `max_output_chars`（默认 20000），尾部注明截断。
- AC-6 工具调用记入审计日志（同 US-AGT-04 AC-5）。

### US-AGT-06 Pi Agent 节点 [P0] [int-win][manual]

作为设计者，我想要直接调用原版 pi coding agent 作为一个节点，以便复用其成熟能力。  
关联：F-AGT-06

- AC-1 `Pi Agent` 参数：`task`（使用统一 Jinja2 沙箱子集）、`cwd`（默认 Root）、`pi_path`（默认取全局设置）、`llm`（命名配置）、`sandbox`、`timeout`、`extra_args`；输入 Variable/Message；输出 Variable（`final_text, exit_code`）与 Message（轨迹）。
- AC-2 `[int-win]` 以子进程运行 pi 的非交互模式，具体命令行由 M0 实测并固定到节点声明/自动导出参考；`cwd` 为指定目录，stdout 流式推送到 UI。
- AC-3 pi 未安装（`pi_path` 不可执行）→ 运行前失败并链接到“安装指引”。
- AC-4 `[int-win]` pi 在沙箱内只获得本地 `LLMProxy` 地址和 LLM 配置名，由沙箱外代理读取原始 key 并请求允许的 LLM 端点；网络默认拒绝，唯一内置例外是该环回代理，直接外网与其他主机服务默认拒绝；沙箱 env、stdout、trace 均无原始 key。M0 必须先验证 pi 支持该 OpenAI 兼容本地代理。
- AC-5 `[manual]` 完成场景 C（整理 `raw/` 目录），变更列表正确反映 pi 的重命名/移动；无法可靠判定时降级为删除+创建并提示。
- AC-6 `[unit]` `sandbox: none` 时 Pi Agent 运行前失败 `Pi Agent requires sandboxie`，不得以直接子进程方式绕过审批与隔离。

### US-AGT-07 聊天触发 / Chat Output 与聊天面板 [P0] [int][e2e]

作为设计者，我想要通过聊天触发工作流并看到回复，以便对话式使用。  
关联：F-AGT-07, F-TRG-03

- AC-1 UI 发送固定调用 REST `POST /api/workflows/{id}/chat`，经 ChatSource 触发 Run；WS 只推送。Trigger Variable 输出 `{source, ts, session_id, payload}`，聊天文本位于 `payload.message`，Message 端口输出 `[{role: user, content: payload.message}]`。
- AC-2 `Chat Output` 输入 Message 或 Variable，执行后显示助手消息；一次 Run 多个 Chat Output 按执行顺序显示，事件含 `run_id, session_id, source_node_id, message_id`。
- AC-3 `[int]` 上游 agent 的 `node.stream` 通过相同 run/session/source/message 映射实时更新；最终 `chat.message` 替换同一消息而非重复追加。
- AC-4 `session_id` 在“新会话”前保持稳定；UI 会话独立存 `.runs/chat/<session_id>.jsonl`，可供面板恢复，不等于 P1 Memory。默认按 `cache.chat_retention_days: 30` 清理，0 表示不自动清理。需要模型历史时仍显式使用 Memory 或工作流维护。
- AC-5 工作流无 `Chat Output` 时，Run 结束后面板显示“运行完成（无输出）”。

### US-AGT-08 Memory 节点 [P1] [int]

作为设计者，我想要按会话保存与读取历史消息，以便多轮对话。  
关联：F-AGT-08

- AC-1 `Memory Load`（`session_id`，`max_messages`）→ Message 端口；`Memory Save`（`session_id`，输入 Message）追加写入 `.runs/memory/<session_id>.jsonl`。
- AC-2 `max_messages` 截断保留最新；`Memory Clear` 节点清空会话。
- AC-3 memory 目录不随打包分发（在 `.runs/` 下），默认按 `cache.memory_retention_days: 30` 清理，0 表示不自动清理。

### US-AGT-09 Prompt Template 节点 [P0] [unit][int]

作为设计者，我想要用模板组合 prompt，以便引用变量与表格。  
关联：F-AGT-09

- AC-1 `Prompt Template` 参数：`template`（Jinja2 子集：变量、if、for、filters `upper/lower/truncate/json`）、`role: system | user`、`table_max_rows`；输入 Variable/Table；输出 Message 与 Variable（`text`）。
- AC-2 模板可从 `prompts/*.md` 文件加载（`source: file`），文件变化后节点退回"已配置"。
- AC-3 `[unit]` 未定义变量渲染时失败（`StrictUndefined`），错误含变量名与行号。
- AC-4 `[unit]` Jinja2 沙箱环境（`SandboxedEnvironment`），禁止属性遍历到 `__class__` 等。

### US-AGT-10 用量与轨迹可见 [P1] [int][e2e]

作为设计者，我想要看到每次调用的 token、耗时、工具调用，以便控制成本与排查。  
关联：F-AGT-10

- AC-1 agent 类节点侧栏"轨迹"标签页：按轮次列出 LLM 请求摘要、回复、工具调用（参数折叠可展开）、`prompt_tokens / completion_tokens / latency_ms`。
- AC-2 Run 级汇总：`GET /api/runs/{id}` 含 `usage: {prompt_tokens, completion_tokens, llm_calls, tool_calls}`。
- AC-3 轨迹持久化于 `.runs/<run_id>/nodes/<node_id>.trace.jsonl`，可从历史面板回看。

### US-AGT-11 agent 不能修改工作流图 [P0] [unit][int]

作为系统，我要确保 agent 无法增删节点或连线，以便可控。  
关联：F-AGT-11

- AC-1 `[unit]` Tool 端口可承载的工具类型只有 `NodeTool` 与 `SandboxedTool`；不存在任何修改图结构的内置工具。
- AC-2 `[int]` 工作流修改 API（`PUT /api/workflows/{id}`）要求有效 UI 会话令牌和请求头 `X-Weft-Client: ui`；令牌缺失/无效返回 401，缺少 header 返回 403，运行期间（Run 活跃）拒绝修改图结构返回 409。该自定义头仅区分 UI 操作、减少误调用，不替代鉴权，也不构成 agent 不得改图的安全边界。
- AC-3 沙箱内进程对 `workflow.json` 的写入落在沙箱副本，默认在变更审批中被标记为"受保护文件"，不可勾选应用（US-SBX-05）。

### US-AGT-12 人工介入确认 [P1] [int][e2e]

作为设计者，我想要在 agent 调用某些工具前要求我确认，以便关键操作不失控。  
关联：F-AGT-12

- AC-1 `Node as Tool` / `Sandboxed Tools` 有 `require_confirmation: true | false` 参数（Sandboxed Tools 可按工具单独设置，默认 `write/edit/bash` 为 true）。
- AC-2 `[int]` 需确认的调用触发 `node.confirm_request` 事件（含 `tool, args`），Run 进入 `waiting` 状态；`POST /api/runs/{id}/confirm` 提交 `approve | reject`（可附修改后的 args）；`reject` 作为工具错误回填给 agent。
- AC-3 `agent.confirm_timeout_s`（默认 600 s）超时按 `reject` 处理。
- AC-4 `[e2e]` UI 弹出确认卡片，显示工具名、参数（可编辑）、批准/拒绝按钮。

---

## 6. Epic SBX：沙箱与安全

### US-SBX-01 沙箱接口可插拔 [P0] [unit]

作为系统，我要定义统一的沙箱接口，以便替换实现。
关联：F-SBX-01

- AC-1 `Sandbox` 抽象接口：`spawn(cmd, cwd, env, timeout) -> Process`、`read_file(path)`、`write_file(path, content)`、`list_dir(path)`、`collect_changes() -> list[Change]`、`apply(changes)`、`discard()`；实现 `NoneSandbox` 与 `SandboxieSandbox`。`NoneSandbox.spawn` 仅供受控 helper 内部使用，不向 bash/pi 暴露。
- AC-2 `[unit]` 接口契约测试套件对两种实现运行（`NoneSandbox` 在临时目录下以"写入到影子目录"方式模拟，使 CI 可测审批流）；对 NoneSandbox 任意 bash/pi 请求必须拒绝。
- AC-3 全局设置 `sandbox.default: sandboxie | none`，`sandbox.allow_none_sandbox: false` 默认；该开关只允许模拟语义，不允许直写真实路径。

### US-SBX-02 Sandboxie 实现 [P0] [int-win]

作为系统，我要通过 Sandboxie-Plus 启动 agent 工具进程，以便隔离并精确归属每个 Run。
关联：F-SBX-02, F-SBX-03

- AC-1 设置 `sandbox.sandboxie.start_exe`（默认 `C:\Program Files\Sandboxie-Plus\Start.exe`）；每个 Run 创建独立 box `WeftBox-<run_id>` 并登记 `{run_id, box, root, owned_pids, process_created_at}`，不靠时间或路径猜测归属。动态 box 创建、删除、列举与终止能力必须先通过 M0 spike。
- AC-2 `weft doctor` 检查 `Start.exe`、动态 box 生命周期、沙箱内 `python -c "print(1)"` 与网络默认拒绝；显式开启网络时还要验证白名单/防火墙确实生效，不能只检查“能访问网络”。
- AC-3 不同 Run 可拥有不同 box；终止、清理与变更收集只操作当前 Run 登记的 box/进程树，绝不终止其他 Run 或用户已有 box。
- AC-4 Run 结束后只终止本 Run box 及其拥有的残留进程树，再按用户审批结果保留或删除 box；异常退出后的清理由登记信息识别，不匹配则不操作。

### US-SBX-03 沙箱内读真实文件、写入重定向 [P0] [int-win]

作为 Agent，我可以读取真实文件但写入不会影响真实文件，以便安全探索。
关联：F-SBX-03

- AC-1 沙箱内 `read("D:\flows\demo.weft\data\sales.csv")` 成功返回真实内容；文件工具的写入限定 Root 与显式授权目录，任意命令的越权写入按 AC-4 的遏制与审计语义处理。
- AC-2 沙箱内 `write("D:\flows\demo.weft\out\a.txt", ...)` 后，真实路径不存在该文件，`<sandbox root>\drive\D\flows\demo.weft\out\a.txt` 存在。
- AC-3 沙箱内删除真实文件后，真实文件仍在，`collect_changes()` 报告 `deleted`。
- AC-4 `[int-win]` 经真实 Sandboxie 验证后，v1 对任意命令的越权写入采用明确降级：真实路径保持不变，外部变更标记 `protected` 且禁止 apply，`changes.json` 必须 `audit_complete: false` 并在 UI 显示“审计不完整”；访问外网仍必须被拒绝。不得把子进程退出码 0 或单纯重定向宣称为硬拒绝。

### US-SBX-04 变更列表与 diff [P0] [int][int-win]

作为设计者，我想要在 Run 结束后看到 agent 做了哪些文件变更，以便审批。
关联：F-SBX-04

- AC-1 Run 开始前记录审计范围内真实文件存在性与内容 SHA-256 基线；结束后产出 `.runs/<run_id>/changes.json`，每项含 `{path, kind, size, is_text, protected, baseline_hash, state}`，kind 支持 `created | modified | deleted | renamed`，renamed 另含 `old_path/new_path`，state 为 `pending | applied | conflict | failed | discarded`。
- AC-2 `[int]` 重命名优先按删除与创建的内容哈希匹配；无法可靠判断时降级为删除+创建并明确提示，不得把复制误报为重命名。
- AC-3 UI 按目录树展示 Root 内外分组；文本文件（≤ 1 MB，UTF-8 可解码）可展开行级 diff，二进制显示大小与哈希变化；`GET /changes` 与 `/changes/diff` 返回相同事实与 `audit_complete`。
- AC-4 无变更且审计完整时不弹面板并记 INFO；审计不完整时即使未识别到文件变更也必须提示。

### US-SBX-05 应用 / 丢弃变更 [P0] [int][int-win]

作为设计者，我想要勾选变更并安全应用到真实位置或丢弃，以便我掌控最终结果。
关联：F-SBX-05

- AC-1 `POST /changes/apply` 请求 `{paths, overwrite_conflicts?: bool}`；应用前重新计算真实目标哈希，与基线不同则该项状态为 `conflict`，不覆盖。用户查看新 diff 后必须显式 `overwrite_conflicts: true` 才能覆盖。
- AC-2 覆盖或删除前备份原文件（删除可移入回收站），创建/修改采用临时文件+rename；请求已处理即返回 200 `{results: [...]}`，逐项返回 `applied | conflict | failed`，冲突项的错误码为 `CHANGE_CONFLICT`，普通路径不因其他项失败而回滚，不承诺多文件事务全原子。
- AC-3 `POST /changes/discard` 清空本 Run 未应用沙箱副本并标记 discarded；`sandbox.auto_apply_in_root` 默认 false，开启时也只自动应用 Root 内非受保护且无冲突变更。
- AC-4 受保护文件（`workflow.json`、`pyproject.toml`、`uv.lock`、`.runs/**`、用户级 `config.toml`）灰显不可勾选；请求含任一 protected 路径则整体 400 且无任何应用。
- AC-5 已应用项重复请求幂等返回 applied；冲突项须重新确认，失败项可重试，全部状态持久化到 `changes.json`。

### US-SBX-06 沙箱内无 COM 访问 [P0] [int-win]

作为系统，我要确认沙箱内进程无法驱动主机 Excel，以便隔离边界成立。
关联：F-SBX-06

- AC-1 沙箱内执行 `python -c "import win32com.client; win32com.client.GetActiveObject('Excel.Application')"` 失败（找不到活动对象或 COM 被拒绝）。
- AC-2 文档与 UI 提示：agent 需操作 Excel 时使用 Node as Tool；`Sandboxed Tools` 的描述中注明此限制。

### US-SBX-07 审计日志 [P0] [unit][int]

作为设计者，我想要所有 agent 工具调用有统一审计记录，以便事后追查。
关联：F-SBX-07

- AC-1 `[unit]` 审计记录 schema：`{ts, run_id, node_id, agent_kind: agent_loop | pi, lane: trusted | sandboxed, tool, args_redacted, status: ok | error | rejected, duration_ms, result_hash}`；除 `key/token/password/secret` 字段外，Authorization 认证头、URL userinfo 和敏感 query 参数也必须打码。
- AC-2 写入 `.runs/<run_id>/audit.jsonl`，追加式、每行一条 JSON；完整 prompt 默认不写 trace，显式开启时必须配置保留期限。
- AC-3 UI 历史面板含“审计”标签页，可按工具/状态过滤；测试断言原始 API key 不出现在沙箱 env、stdout、audit 或 trace。

### US-SBX-08 密钥不入工作流目录 [P0] [unit][int]

作为系统，我要保证密钥只存在用户级配置中，以便打包不泄密。
关联：F-SBX-08

- AC-1 `[unit]` `workflow.json` 的 JSON Schema 中不存在任何密钥字段；节点参数引用 LLM 仅按配置名。
- AC-2 `[int]` 打包产物 zip 内任何文件均不含 `config.toml` 中的 `api_key` 值（打包流程中全文扫描断言，命中则打包失败并提示来源文件）。
- AC-3 Python Script 代码中硬编码形如 API key 的高熵字符串时，打包时 WARN（不阻断）。

### US-SBX-09 本机服务、浏览器边界与 HTTP token [P0] [int]

作为系统，我要默认只监听本机并校验 UI 与触发端点身份，以便不暴露风险面。
关联：F-SBX-09

- AC-1 默认绑定 `127.0.0.1:7788`；设置改为 `0.0.0.0` 时启动日志打 WARN 且 UI 顶栏常驻提示。
- AC-2 `POST /api/workflows/{id}/trigger` 要求 `Authorization: Bearer <token>`，token 在该工作流触发器配置中生成/轮换；错误 token 返回 401 并限速（同 IP 每分钟 ≤ 10 次失败）。
- AC-3 监听非本机地址时，其余 `/api/*` 要求全局 token（设置中生成）。
- AC-4 `[int]` 本机服务启动时生成随机 UI 会话令牌；除工作流 `/trigger` 外，其余 API 均要求 `Authorization: Bearer <ui_session_token>`，WS 先 authenticate 再订阅。令牌只经启动 URL 和仅当前用户可读的会话文件分发，不写入工作流、日志或 trace。
- AC-5 `[int]` 所有请求校验 Host；带 Origin 的浏览器请求仅接受当前 UI 同源地址，失败返回 403。无 Origin 的非浏览器请求也必须持有对应 Bearer token；`X-Weft-Client` 不得代替会话令牌。

---

## 7. Epic TRG：触发器

### US-TRG-01 统一触发事件 [P0] [unit][int]

作为系统，我要把所有触发源统一为同一事件结构，以便下游节点无需区分来源。  
关联：F-TRG-01

- AC-1 `[unit]` 事件结构：`{source: manual | chat | schedule | file | http | excel, ts, session_id?, payload: dict}`；excel 仅预留，v1 不接受运行。Trigger Variable 输出 `{source, ts, session_id?, payload}`，不 flatten；Message 仅 chat 非空，Table 为 file 清单。
- AC-2 Trigger 节点侧栏按 5 种 v1 来源分区配置，每种独立启停；params 是唯一真源，TriggerManager 派生运行视图，不保存顶层影子 trigger。
- AC-3 `[int]` Run 的 `meta.json` 记录完整触发事件，聊天文本通过 `payload.message` 读取。

### US-TRG-02 手动触发 [P0] [int][e2e]

作为设计者，我想要点按钮或用 CLI 运行工作流，以便即时执行。  
关联：F-TRG-02

- AC-1 UI "运行"按钮 → `source: manual`，payload 为空对象；可在运行对话框中临时覆盖流变量（`payload.overrides`）。
- AC-2 `weft run <path-to-workflow> [--var k=v ...] [--wait]` 退出码：成功 0、失败 1、取消 2；`--wait` 时输出各节点状态行。服务可用时 CLI 只调用服务 API；服务未启动时以内嵌模式直接执行，并按 US-EXE-13 AC-6 获取共享跨进程执行锁，不得绕过单活跃 Run 或全局 Excel 串行。

### US-TRG-03 聊天触发 [P0] [int][e2e]

（主体见 US-AGT-07）  
关联：F-TRG-03

- AC-1 聊天面板发送 → `source: chat`，`payload: {message, history_len}`，`session_id` 稳定。
- AC-2 Trigger 未启用 chat 来源时，聊天面板显示"该工作流未启用聊天触发"。

### US-TRG-04 定时触发 [P0] [int]

作为设计者，我想要 cron 或固定间隔自动运行，以便无人值守。  
关联：F-TRG-04

- AC-1 配置 `schedules: [{cron: "0 9 * * 1-5"} | {interval_seconds: 3600}]`，多条可并存；cron 为 5 段标准格式，时区为本机时区。
- AC-2 `[int]` 到点产生 `source: schedule` 事件，payload 含 `schedule_id, scheduled_at`；错过的触发（服务未运行）不补跑。
- AC-3 UI 显示每条 schedule 的下次触发时间；非法 cron 表达式在保存时报错。
- AC-4 工作流关闭或服务停止后不再触发（F-TRG-07）。

### US-TRG-05 文件监听触发 [P0] [int]

作为设计者，我想要文件夹变化自动触发，以便"丢文件即处理"。  
关联：F-TRG-05

- AC-1 配置 `watch: {enabled: true, watches: [{path, pattern: "*.xlsx", events: [created, modified, deleted], debounce_ms: 2000, recursive: false}]}`；`path` 相对 Root 或绝对。
- AC-2 `[int]` 在防抖窗口内的多个事件合并为一次触发；payload 含 `events: [{path, kind, ts}]`，Trigger 的 Table 端口输出同内容表。
- AC-3 忽略 `.runs/`、`.venv/`、临时文件（`~$*`, `*.tmp`, `.~lock*`）。
- AC-4 监听路径不存在时触发器状态为"异常"（UI 红点），不影响其他来源。
- AC-5 由本工作流自身写入的文件（Run 活跃期间引擎写出的路径）不触发，防自激循环。

### US-TRG-06 HTTP 触发 [P0] [int]

作为外部系统，我想要 POST 一个端点触发工作流，以便集成。  
关联：F-TRG-06, F-TRG-09

- AC-1 `POST /api/workflows/{id}/trigger`，Bearer token（US-SBX-09），body 任意 JSON → `source: http`，`payload.body` 为请求体；立即执行/入队返回 202 `{run_id, disposition}`，队列满返回 409。drop 无论是否携带 `wait=true` 都返回 200 `{run_id: null, disposition: dropped}`，不返回 status/outputs。
- AC-2 `?wait=true` 时阻塞至 Run 结束（上限 `trigger.http_wait_timeout_s` 默认 300 s），返回 `{run_id, status, outputs}`；唯一已执行的 `HTTP Response` 提供 `outputs: {status_code, headers, body}`，未配置或未执行时 outputs 为 `{}`。超时且 Run 仍 queued/running 时返回 202 `{run_id, status, outputs: {}, wait_timed_out: true}`，Run 继续执行，客户端可轮询。上述行为在 T6.1 与 HTTP 触发一起交付。
- AC-3 触发器未启用 http 来源 → 404（不泄露工作流存在性差异：统一 404）。
- AC-4 `[int]` `HTTP Response` 参数为 `status_code`（默认 200）、`headers`（对象）与 `body`（文本或 JSON）；每个 Run 最多执行一个，执行多个时运行失败，异步触发不等待该节点。

### US-TRG-07 来源独立开关与生命周期 [P0] [int]

作为设计者，我想要每种触发源独立启停，且随工作流/服务生命周期生效，以便可控。  
关联：F-TRG-07

- AC-1 任一来源开关变更即时生效（无需重启服务）；Trigger 节点上显示各来源小图标（启用亮/禁用灰/异常红）。
- AC-2 `[int]` 服务启动时恢复所有已打开工作流的 schedule 与 watch；`weft serve --no-triggers` 启动则全部不激活（调试用）。

### US-TRG-08 Excel 事件触发（占位） [P2]

关联：F-TRG-08, F-XLS-13。v2 经 xlOil 伴侣插件实现 SheetChange / Ribbon 触发，本版本仅在文档中保留事件结构兼容性：`source: excel`，payload 含 `workbook, sheet, address`。无 AC。

---

## 8. Epic PKG：可移植与打包

### US-PKG-01 工作流目录自包含 [P0] [unit][int]

作为系统，我要保证工作流的全部定义都在目录内，以便拷走即完整。  
关联：F-PKG-01

- AC-1 `[unit]` `format: weft-path` 字段中的绝对路径通过 schema/语义校验并允许保存，校验结果记为 WARNING 而非 ERROR；`weft pack` 将其收集为警告清单，只有用户显式确认后继续（F-PKG-06）。
- AC-2 `[int]` 把 `demo.weft/` 整体复制到另一路径后打开，所有相对路径节点无需修改即可运行。

### US-PKG-02 依赖声明与自动同步 [P0] [int]

（主体见 US-EXE-14）  
关联：F-PKG-02

- AC-1 UI "依赖"面板可增删 `pyproject.toml` 的 `dependencies`，保存后提示并执行 `uv sync`，`uv.lock` 更新。
- AC-2 打开工作流时若 `.venv` 缺失或 `uv.lock` 与 venv 不一致（`uv sync --check` 非零）→ 自动同步。

### US-PKG-03 打包 [P0] [int][e2e]

作为设计者，我想要一键导出 zip，以便发给同事。  
关联：F-PKG-03

- AC-1 UI "打包"对话框：默认排除 `.runs/`、`.venv/`、`__pycache__`；`data/` 可勾选排除；显示预计体积；产物命名 `<name>-<yyyymmdd>.weft.zip`。
- AC-2 `weft pack <workflow-dir> [-o out.zip] [--exclude-data]` 等价。
- AC-3 `[int]` 产物 zip 根为 `<name>.weft/` 单目录；含 `workflow.json, pyproject.toml, uv.lock, nodes/, prompts/`；密钥扫描通过（US-SBX-08 AC-2）。
- AC-4 打包前校验 schema、Loop、未配置节点与外部资源：任何 ERROR 必须阻断且不能 force 跳过；绝对路径等 WARNING 展示清单，只有用户显式确认后才继续。

### US-PKG-04 导入 [P0] [int][e2e]

作为运行者，我想要导入 zip 并直接可跑，以便接收交接。  
关联：F-PKG-04

- AC-1 UI “导入” → 选 zip 与目标父目录 → 解压、schema 版本检查、`uv sync`、打开画布；全程进度可见。
- AC-2 `weft unpack a.weft.zip -d D:\flows` 等价。
- AC-3 zip 内含 Root 外路径（zip slip）→ 拒绝导入。
- AC-4 `[int]` 机器 A pack → 机器 B unpack + run；前提为兼容 Weft/uv、声明的外部资源与系统依赖可用、可安装锁定依赖。CI 用两个独立临时目录和本地 wheel 模拟，不宣称无网络/无外部资源也必能运行。
- AC-5 `[unit]` pack/unpack 保留 workflow.id；在本机执行“复制工作流/duplicate”时生成新 id 和新 revision 历史。

### US-PKG-05 schema 版本与迁移 [P0] [unit]

作为系统，我要给 `workflow.json` 版本号并向后兼容，以便升级不破坏旧工作流。
关联：F-PKG-05

- AC-1 `workflow.json` 顶层 `schema_version: 1`；打开高于当前支持版本的文件 → 明确报错"请升级 Weft"。
- AC-2 `[unit]` 迁移框架：`migrations/v1_to_v2.py` 形式注册，打开旧版本时逐级迁移，迁移前自动备份 `workflow.json.bak.v1`。
- AC-3 节点级版本：每个节点类型有 `node_version`，节点实现可提供参数迁移函数；未知节点类型以"占位节点"显示（保留参数，不可执行），不丢数据。

### US-PKG-06 绝对路径检测 [P1] [unit]

关联：F-PKG-06

- AC-1 `weft pack` 与 UI 打包对话框列出所有含绝对路径的 `(节点, 参数, 值)`；用户可逐条跳转修改。

### US-PKG-07 运行前资源预检 [P1] [int]

作为运行者，我想要运行前一次性知道缺什么外部资源，以便不被逐节点报错折磨。  
关联：F-PKG-07

- AC-1 运行前对声明了"外部资源"的参数（工作簿名、绝对路径、LLM 配置名、pi 路径）做存在性检查，汇总为一份报告；有缺失时询问"仍要运行？"。
- AC-2 检查不执行任何写操作，总耗时 < 2 s（Excel 检查仅查已打开工作簿列表）。

---

## 9. Epic SET：设置与运维

### US-SET-01 用户级配置 [P0] [unit][int]

关联：F-SET-01

- AC-1 `%APPDATA%\weft\config.toml`，首次启动生成带注释的默认文件；完整顶层结构：`[server] [llm.<name>] [sandbox] [sandbox.sandboxie] [excel] [agent] [trigger] [logging] [cache]`。
- AC-2 设置页修改后写回文件并即时生效（监听端口除外，提示需重启）。
- AC-3 `[unit]` 配置加载有 schema 校验与默认值合并；非法值报具体字段错误；统一使用 `excel.call_timeout`、`agent.confirm_timeout_s`、`trigger.http_wait_timeout_s`、`sandbox.allow_none_sandbox`。

### US-SET-02 服务启动与 UI [P0] [int][e2e][manual]

关联：F-SET-02

- AC-1 `weft serve` 启动后 2 s 内监听就绪；默认自动打开携带随机 UI 会话令牌的同源 URL（`--no-browser` 关闭），令牌不得写入日志。
- AC-2 `[manual]` 冷启动到 UI 可交互 < 5 s（PRD §9.3）。
- AC-3 端口被占用时报错并提示 `--port`。

### US-SET-03 日志 [P0] [int]

关联：F-SET-03

- AC-1 服务日志 `%APPDATA%\weft\logs\weft-<date>.log`，JSON lines，按天轮转，默认保留 14 天。
- AC-2 Run 日志独立于服务日志（`.runs/<run_id>/log.jsonl`）；两者均含 `trace_id` 可关联。
- AC-3 日志级别可调；DEBUG 记录 COM 调用与 LLM 请求摘要，不含密钥或完整 prompt。完整 prompt 默认也不写 trace，只有显式开启 `trace_full_prompt` 才记录，并按 `trace_retention_days` 清理。
- AC-4 `[int]` `.runs/chat/` 与 `.runs/memory/` 分别按 `cache.chat_retention_days`、`cache.memory_retention_days` 清理，默认 30 天，0 表示不自动清理；Run 仍按 `cache.run_retention` 保留最近 50 次。

### US-SET-04 CLI 与 doctor [P0] [int][int-win]

关联：F-SET-04

- AC-1 `weft --help` 列出 `serve run pack unpack doctor`；全部命令支持 `--json` 输出。
- AC-2 `weft doctor` 检查并逐项报告 OK/WARN/FAIL：Python 版本、uv、Excel 可连接性、Sandboxie、pi、端口占用、`%APPDATA%` 可写；退出码 = FAIL 项数。
- AC-3 `weft doctor --cleanup` 清理孤儿隐藏 Excel 实例（US-XLS-02 AC-3）与沙箱残留进程。
- AC-4 `[int]` Windows 轻量目录内置 CMD 启动器、uv、生产依赖锁与同版本本地 wheel，不内置 Python 或编译主程序；在不含宿主 Python/uv 的 PATH 和独立 `%LOCALAPPDATA%` 下，`weft.cmd --version`、首次托管 Python/依赖下载、真实 CSV 工作流、缓存离线重跑、鉴权服务 API 与前端均通过，Excel/Sandboxie doctor 使用应用环境 Python，工作流 venv 使用 uv 托管 base Python。

### US-SET-05 托盘（占位） [P2]

关联：F-SET-05。无 AC。

---

## 10. 覆盖矩阵

|PRD 需求|故事|
| --------------| ---------------------------------------------|
|F-DES-01..07|US-DES-01..08, US-DES-11|
|F-DES-08|US-DES-09|
|F-DES-09|US-DES-10|
|F-DES-10|US-DES-12（P2 占位）|
|F-EXE-01..12|US-EXE-01..14|
|F-EXE-13|US-EXE-08（Wait 取消）|
|F-XLS-01..12|US-XLS-01..12（F-XLS-13 → US-TRG-08 占位）|
|F-TBL-01..10|US-TBL-01..10|
|F-AGT-01..12|US-AGT-01..12|
|F-SBX-01..09|US-SBX-01..09|
|F-TRG-01..08|US-TRG-01..08|
|F-TRG-09|US-TRG-06|
|F-PKG-01..07|US-PKG-01..07|
|F-SET-01..05|US-SET-01..05|
|F-SET-06|US-SET-04（绿色目录与便携运行时）|

维护规则：PRD 新增/变更需求时同步本矩阵。代码中的节点声明/JSON Schema 是参数真源，`09-nodes-v1.md` 仅为自动导出的只读参考；本文始终是行为与 AC 真源，冲突时修正导出器或参考文档，不覆盖 AC。
