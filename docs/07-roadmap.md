# 07-roadmap.md

# **Weft 路线图与任务拆解**

|项|值|
| ------| ---------------------------------------------------------------------------------|
|版本|v0.1（草稿）|
|上游|`01-prd.md` §7 优先级、`02-user-stories.md`|
|用法|agent 按任务卡顺序领取；每张卡独立可验证，完成 = 列出的 AC 测试通过 + `poe check` 全绿|

---

## 0. 里程碑总览

P0 仍表示完整 v1 必须交付，但不等于首个公开版全交付。**M0–M3 为首个公开 MVP，M4–M6 为后续预览，M7 才形成完整 v1**；版本号在各里程碑发布前确定。

|里程碑|主题|出口标准（Demo）|
| --------| ---------------------| ------------------------------------------------------------|
|**M0**|骨架与风险验证|仓库可构建；Sandboxie、Excel、pi/LLMProxy 三个技术 spike 有真机结论|
|**M1**|引擎核心 + 最小闭环|CLI 跑通 CSV 闭环，含冻结 Run、分类缓存、局部执行与 Worker pool|
|**M2**|画布 UI|浏览器中设计并运行 M1 工作流，状态实时、端口读 Run 快照、CAS 保存|
|**M3**|Excel 联动 + 首个公开 MVP|场景 A 端到端；公开 MVP 发布，真机门禁通过|
|**M4**|Agent 预览|场景 B（Agent Loop + 授权 NodeTool + LLMProxy）端到端|
|**M5**|沙箱预览|场景 C（Pi/沙箱工具 + 变更审批）端到端|
|**M6**|触发器 + 打包预览|场景 D、E 端到端；外部资源与依赖满足时跨机运行|
|**M7**|完整 v1|P0/P1 范围、运行历史、doctor、文档与正式发布|

依赖关系以 M1 → M2 → M3 → M4 → M5 → M6 → M7 为主；M3 与 M2 可部分并行。

规则：

- 每张卡统一使用 `- [ ] **T…**`；只有 `- [x]` 表示实现完成，验收引用 `02-user-stories.md` 的 AC。完成状态以各任务 checkbox 为准。
- 覆盖脚本只检查已完成卡中的非 manual AC，对不存在的 US/AC 引用报错；manual 项必须列入人工验收单。
- P2/占位项不排卡。P1 的完整收尾集中在 M7；预览卡若明确列出少量 P1（如 fast_mode、轨迹、人工确认），按该卡验收，不代表 P1 默认全部提前。任何裁减须在完整 v1 发布前重新确认，不能静默删除 P0。
- 实现中发现文档缺口：小缺口在 PR 中补文档；大缺口（影响数据模型/API）先停下来改文档再继续。

---

## M0 骨架与风险验证

> 目标：把“后面会死人的坑”先踩掉。spike 代码允许丢弃，结论必须写回文档。

- [ ] **T0.1 仓库骨架**
【依赖】无
【产出】monorepo；uv workspace；`weft` / `weft-worker` / `weft-sdk` 空包可安装；frontend Vite；lint/type/test/poe 与 Linux+Windows CI；import-linter；节点规格导出器骨架与 AC 覆盖脚本骨架
【验收】`uv run poe check` 与两平台 CI 绿；导出器能生成空节点索引，覆盖脚本能识别任务 checkbox 和非法 AC 引用

- [ ] **T0.2 Spike：Sandboxie 归属、外泄与变更收集**
【依赖】T0.1
【产出】Windows 真机脚本与 `docs/spikes/sandbox.md`：动态 `WeftBox-<run_id>` 创建/删除/列举/终止、进程归属、stdout、删除标记、重命名、网络默认拒绝、未授权路径与 `user\` 未知变更、stale apply 冲突
【验收】created/modified/deleted/renamed（或明确降级）可收集；只终止本 Run box；默认外网/越权写失败；未知变化令 audit_complete=false；真实目标 stale 时拒绝覆盖。任一安全关键项不可行则停止后续沙箱卡并改设计

- [x] **T0.3 Spike：xlwings 多实例、超时与 owned 生命周期**
【依赖】T0.1
【产出】`docs/spikes/excel.md`：多实例列表与 PID/窗口选择、GetActiveObject 实测、稳定目标与 `excel-targets.toml` 持久化、默认模式写回可见性、模态对话框、真超时后队列占用、独立 ExcelWorker 终止重建与跨宿主 `Local\WeftExcelCOM` 互斥、用户并发编辑、owned PID+创建时间+Run/心跳清理、10 万单元格与逐格/批量受控基准
【验收】记录环境版本和原始数据；明确可行边界并回写架构/AC，不能以 GetActiveObject 猜测实例或宣称超时后 Worker 立即可用；重建后新请求恢复且超时写请求不自动重放

- [ ] **T0.4 Spike：pi 非交互模式与沙箱外 LLMProxy**
【依赖】T0.1
【产出】确认 pi 非交互参数、输出、退出码；实现最小主机 LLMProxy，验证 pi 可配置 OpenAI 兼容本地代理；原始 key 只在主机配置，沙箱仅收到本地地址和配置名
【验收】pi 经代理完成任务，env/stdout/trace 无原始 key，直连外网默认拒绝；命令行固化到节点声明，T1.3 后由导出器写入只读 `09-nodes-v1.md`

---

## M1 引擎核心 + 最小闭环

- [x] **T1.1 数据模型与校验**
【依赖】T0.1
【产出】`weft.workflow`：Pydantic 全量模型、校验、原子保存、revision/CAS、迁移骨架；Trigger params 唯一真源、合法节点/边 ID 与 edge order、Metanode interface、动态端口 manifest
【验收】US-PKG-05/AC-1,2；US-DES-07/AC-4,5；US-EXE-04/AC-8；校验规则表全部有测试

- [x] **T1.2 端口类型与 ValueRef**
【依赖】T1.1
【产出】PortType、兼容矩阵、ValueRef、完整缓存键（实现/用户代码/uv.lock/迭代号/显式外部文件与目录内容 SHA-256）
【验收】US-DES-03/AC-5；缓存键与 ValueRef 的独立单元测试，不虚标需要 Read CSV 的 AC

- [x] **T1.3 节点协议、注册表与规格导出**
【依赖】T1.2
【产出】`weft-sdk` Node/Port/DynamicPortGroup/decorator/weft_ctx；cache_policy、cache_inputs、ui_hints、portable_params、external_resources 与工具能力声明；注册表；由代码 JSON Schema 首次生成只读 `docs/09-nodes-v1.md`
【验收】US-DES-04/AC-4；自定义节点与动态端口声明可注册，生成文档与声明一致且手改 diff 会被 CI 检出；Concatenate/Merge 行为留到对应节点卡验收

- [x] **T1.4 调度器、冻结 Run 与状态机**
【依赖】T1.3
【产出】拓扑、ExecScope、并行、分支、失败/取消、Run 队列；ready 出队、out_of_scope/skipped_branch/skipped_upstream 与 Merge 部分输入传播；入队冻结 workflow/variables/manifest 和 revision，Run 输出快照
【验收】US-EXE-01/AC-2,3；US-EXE-04/AC-6,7；US-EXE-13/AC-1,2；使用合成调度节点验证算法，不引用后续节点或 HTTP AC

- [x] **T1.5 分类缓存层**
【依赖】T1.4
【产出】pure/volatile/side_effect 策略、缓存失效/LRU、历史输出、纯缓存恢复；If/Switch activated_ports 缓存重放、缓存命中物化 Run 快照及复制基准；副作用每次执行，LLM/实时 Excel Read 禁止跨 Run 复用
【验收】US-EXE-04/AC-1,2,5（与 T1.1/T1.4/T1.7/T1.8/T4.1 分工覆盖，不重复虚标）

- [x] **T1.6 Worker pool 与 IPC**
【依赖】T1.4
【产出】独立 `weft-worker` 包、JSON-RPC stdio、Arrow IPC+memory-map、每 Run 懒启动 pool（默认 4）、结束全退出、取消/崩溃清理、精确同版本 uv.lock、显式升级重锁与 `uv sync`
【验收】US-EXE-14/AC-1..7；US-EXE-08/AC-2；真实子进程并行、跨 Run 状态隔离、无主机 PYTHONPATH 的集成测试

- [x] **T1.7 基础表格与文件节点（第一批）**
【依赖】T1.6
【产出】`Read/Write CSV·Parquet·JSON`、`Column Filter`、`Row Filter`、`Sorter`、`Column Rename`、`Variable`、`Table Row Count`、`List Files`；逐项声明缓存策略，写节点声明 side_effect，文件/目录参数声明 cache_inputs
【验收】US-TBL-02/AC-1,3,4,5；US-TBL-03/AC-1..4,8；US-TBL-06/AC-3,4；US-TBL-07/AC-1；US-EXE-04/AC-3,4,9,11

- [x] **T1.8 流程节点（第一批）与 CLI run**
【依赖】T1.7
【产出】`Trigger`（仅 manual）、`If`、`Switch`、双命名输入 `Merge`、可正常等待与取消的 `Wait`；`weft run` 服务 API/内嵌模式与共享跨进程执行锁、`weft serve` 最小 API
【验收】US-EXE-01/AC-1；US-EXE-02；US-EXE-03；US-EXE-04/AC-12；US-EXE-08/AC-1,4,5；US-EXE-12/AC-1..6；US-EXE-13/AC-6；US-TRG-01/AC-1；US-TRG-02/AC-2；**里程碑 Demo**：CSV 闭环成功，第二次运行仅 pure 上游命中，Write CSV 仍执行，`--var` 覆盖生效

---

## M2 画布 UI

- [x] **T2.1 REST/WS 完整化与本机安全边界**
【依赖】T1.8
【产出】`05-api.md` §1–5、§11 中 M2 所需端点与事件；随机 UI 会话令牌、Host/Origin 校验、WS authenticate 后订阅、403 与统一错误码
【验收】US-SBX-09/AC-4,5；US-EXE-05/AC-5；API 集成测试覆盖每个端点的成功与主要错误路径

- [x] **T2.2 画布编辑**
【依赖】T2.1
【产出】React Flow 画布：节点面板、拖拽、连线（后端校验）、参数表单（JSON Schema 生成）、变量绑定控件、自动保存、undo/redo、复制粘贴、导航、小地图
【验收】US-DES-01..04、US-DES-06..08、US-DES-11 的全部 AC（e2e 用 Playwright）

- [x] **T2.3 执行可视化**
【依赖】T2.2
【产出】状态灯、右键执行菜单（到此/从此/仅此/重置）、日志面板、端口视图（Arrow 流直读、record batch 分页、显式全量稳定排序）、错误详情
【验收】US-DES-05；US-EXE-05/AC-1,3,4；US-EXE-06/AC-1,3,4,5；US-EXE-07/AC-1,2
【Demo】浏览器中从零搭建 M1 工作流并运行、调试

- [x] **T2.4 循环节点与 UI**
【依赖】T2.3
【产出】`Loop Start/End`（Row/Chunk/Counting × concat/last/variables）、引擎虚拟循环节点、迭代进度显示、配对校验；Counting 使用上界排他的半开区间
【验收】US-EXE-10/AC-1..4；US-EXE-11/AC-1..4

- [x] **T2.5 第二批表格节点**
【依赖】T2.3
【产出】`Joiner`、动态命名端口 `Concatenate`、`GroupBy`、`Pivot/Unpivot`、`Duplicate Filter`、`Missing Value`、`Type Cast`、AST 白名单 `Polars Expression`、`Math Formula`、`String Manipulation`、`Table to Variables`、`Variables to Table`、`Table Creator`、`Table View`、`Python Script`、`Path Join`、`File Copy/Move/Rename/Delete`
【验收】US-DES-03/AC-6；US-TBL-03..07、US-TBL-08/AC-1..7、US-TBL-10 的全部 P0 AC

---

## M3 Excel 联动

- [x] **T3.1 ExcelBackend 接口 + Fake 实现**
【依赖】T1.3（可与 M2 并行）
【产出】ExcelBackend、Fake、描述符与共用契约；实时读取 volatile，App/Workbook 仅在 resolve 成功后复用
【验收】US-XLS-03/AC-4；US-XLS-04/AC-6（Fake 部分）；Linux 契约绿但不代替真机

- [x] **T3.2 ExcelWorker**
【依赖】T3.1
【产出】独立 ExcelWorker 子进程与监督器、STA 串行队列、跨宿主 `Local\WeftExcelCOM` 互斥、超时后繁忙/排队、达阈值终止重建、owned RefRegistry、fast_mode 状态恢复
【验收】US-XLS-11/AC-1..3,5；US-XLS-12/AC-1..3,5

- [x] **T3.3 XlwingsBackend**
【依赖】T3.2 + T0.3 结论
【产出】多实例 PID/窗口选择、稳定目标与用户级 `excel-targets.toml`、attach/new_hidden、整块读写、cell update、sheet/save、统一 allow_formula、显式 save|discard、owned PID 清理、可见 false/隐藏 true 的 fast_mode
【验收】US-XLS-01..08、US-XLS-10 的 `[int-win]` AC；固定基准机记录 US-XLS-04/AC-4、US-XLS-05/AC-5、US-XLS-10/AC-2 结果

- [x] **T3.4 Excel 节点 + 描述符解析与 MVP 发布**
【依赖】T3.3
【产出】Excel 节点；描述符重解析；实时 Read 每次执行；场景 A 与公开 MVP 发布包
【验收】US-XLS-11/AC-4；US-XLS-04/AC-6（win_real）；US-EXE-06/AC-2；场景 A 真机通过
【Demo】用户选择可见实例，读打开的 Excel → 处理 → 默认模式写回并立即可见

---

## M4 Agent

- [x] **T4.1 LLMProxy/LLMClient + mock 服务器**
【依赖】T1.8 + T0.4 结论
【产出】主机 LLMProxy、OpenAI 兼容客户端、命名配置、测试连接、mock；key 只在主机侧读取，volatile LLM 节点
【验收】US-AGT-01/AC-1..4；US-AGT-02/AC-5；US-EXE-04/AC-10；pi 的沙箱内代理验收留在 T5.4，不在本卡虚标

- [x] **T4.2 LLM Call + Prompt Template + 统一插值**
【依赖】T4.1
【产出】两节点共用 Jinja2 沙箱子集、`{{ var }}` 与只读 `tables.<port> | table` 表格 filter
【验收】US-AGT-02/AC-1..4；US-AGT-09/AC-1..4

- [x] **T4.3 Agent Loop + ToolDispatcher + 审计**
【依赖】T4.2
【产出】ReAct、停止正则优先、max_turns 默认失败/显式 partial、工具去重/超时/错误回填、打码 audit、默认不含完整 prompt 的 trace、事件与轨迹面板
【验收】US-AGT-03/AC-1..5；US-SBX-07/AC-1..3；US-AGT-10/AC-1..3

- [x] **T4.4 授权 Node as Tool**
【依赖】T4.3
【产出】tool_capability/参数白名单、冻结参数与 Run 输入快照、ephemeral、同 Run pool/lane 槽位与排队、Run 取消继承、禁止 Python/Shell/任意代码、副作用逐次确认、防递归
【验收】US-AGT-04/AC-1..7

- [x] **T4.5 Chat 面板与聊天触发**
【依赖】T4.3
【产出】REST 发送→ChatSource、WS 认证与推送、run/session/source/message 去重映射、独立 `.runs/chat/` 会话及保留策略
【验收】US-AGT-07/AC-1..5；US-TRG-03/AC-1,2
【Demo】场景 B（mock 自动化 + 真实模型手动 US-AGT-03/AC-6），原始 key 不进入沙箱或轨迹

---

## M5 沙箱

- [x] **T5.1 Sandbox 接口 + NoneSandbox 影子目录模拟**
【依赖】T0.2 结论
【产出】Sandbox 接口、变更模型、受保护路径与契约；NoneSandbox 仅提供受控 read/write/edit/list 影子目录工具，拒绝任意 bash/pi/spawn；实现 `sandbox.allow_none_sandbox`
【验收】US-SBX-01/AC-1..3；US-SBX-05/AC-4；Linux 契约仅覆盖替身能力，不冒充 Sandboxie 验证

- [ ] **T5.2 SandboxieSandbox**
【依赖】T5.1
【产出】独立 `WeftBox-<run_id>`、owned 进程树、helper、默认拒绝网络与环回 LLMProxy 唯一例外、显式白名单、Root/授权目录审计、未知变化提示、只清理本 Run
【验收】US-SBX-02/AC-1..4；US-SBX-03/AC-1..4；US-SBX-06/AC-1（全部 win_real）

- [x] **T5.3 基线、重命名与冲突审批流**
【依赖】T5.1
【产出】内容哈希基线、renamed/降级、audit_complete、逐项状态、备份、200 逐项 stale CHANGE_CONFLICT、显式覆盖、幂等 apply/discard
【验收】US-SBX-04/AC-1..4；US-SBX-05/AC-1..5

- [ ] **T5.4 Sandboxed Tools + Pi Agent + 人工确认**
【依赖】T5.2 + T4.3 + T0.4 结论
【产出】Sandboxie 五工具、none 下 bash/pi 拒绝、PiRunner 经沙箱外 LLMProxy、confirm 流；不得向沙箱注入原始 key
【验收】US-AGT-05/AC-1..6；US-AGT-06/AC-1..4,6；US-AGT-12/AC-1..4；US-AGT-11/AC-1..3
【Demo】场景 C 真机通过；重命名可判定或明确降级，审批前真实目录不变，stale 不覆盖

---

## M6 触发器 + 打包

- [ ] **T6.1 TriggerManager + schedule/watch/http/HTTP Response**
【依赖】T1.8 + T3.4
【产出】统一事件、Trigger params 派生视图、APScheduler、watch.watches/watchdog、token/限速/wait 超时与 drop 组合语义、P0 `HTTP Response` 单响应节点（未执行 outputs={}，重复执行失败）、来源健康、无人值守 Excel 目标唯一性预检
【验收】US-TRG-01/AC-2,3；US-TRG-04/AC-1..4；US-TRG-05/AC-1..5；US-TRG-06/AC-1..4；US-TRG-07/AC-1,2；US-SBX-09/AC-1..3；US-XLS-01/AC-4；US-EXE-13/AC-5

- [ ] **T6.2 打包/导入**
【依赖】T1.1
【产出】pack 排除规则/预检/密钥扫描/绝对路径 WARNING 清单、ERROR 阻断/WARNING 显式确认、unpack zip slip 防护与 uv sync、导入保留 id/本机 duplicate 新 id
【验收】US-PKG-01/AC-1,2；US-PKG-03/AC-1..4；US-PKG-04/AC-1..5；US-SBX-08/AC-1..3
【Demo】场景 D + E；在外部资源、精确兼容 Weft/uv 和锁定依赖可用前提下，A 机 pack → B 机 unpack → run

---

## M7 完整 v1 收尾

- [ ] **T7.1 Metanode 折叠与展开**
【依赖】T2.5
【产出】Metanode 内嵌子图、端口重连、子画布与可逆展开
【验收】US-DES-09/AC-1..4

- [ ] **T7.2 节点注释与画布便签**
【依赖】T2.2
【产出】节点注释、Markdown 便签、样式与持久化
【验收】US-DES-10/AC-1,2

- [ ] **T7.3 运行历史面板**
【依赖】T2.3
【产出】历史列表、meta/log/trace 只读视图、内联与 outputs 文件端口读取、Run 保留清理
【验收】US-EXE-09/AC-1..4

- [ ] **T7.4 Memory 节点**
【依赖】T4.5
【产出】Memory Load/Save/Clear、会话截断与保留清理
【验收】US-AGT-08/AC-1..3

- [ ] **T7.5 Rule Engine**
【依赖】T2.5
【产出】复用 Row Filter 条件语法的有序规则、default 与目标列
【验收】US-TBL-05/AC-4

- [ ] **T7.6 Shell Command**
【依赖】T1.6
【产出】可信 Worker 命令执行、PowerShell/cmd 独立转义器与元字符测试、无法安全插值时失败、流式日志与退出码
【验收】US-TBL-09/AC-1..3

- [ ] **T7.7 Excel Run Macro**
【依赖】T3.4
【产出】Application.Run、参数与 COM 错误映射
【验收】US-XLS-09/AC-1,2

- [ ] **T7.8 外部资源预检与绝对路径跳转**
【依赖】T6.2
【产出】只读资源预检、汇总报告与打包警告逐条跳转
【验收】US-PKG-06/AC-1；US-PKG-07/AC-1,2

- [ ] **T7.9 doctor 与运维**
【依赖】T5.4 + T6.2
【产出】doctor/cleanup 按 owned 记录清理、动态 box 与网络检查、日志轮转、完整设置页与保留策略
【验收】US-SET-01..04

- [ ] **T7.10 完整 v1 发布**
【依赖】T7.1..T7.9
【产出】README/安装文档/CHANGELOG、正式构建与发布；版本号发布前确定，不预写 0.1.0
【验收】全量 CI 与 win_real 绿、同机性能回归通过、PRD 成功标准启动跟踪

---

## 里程碑验收总表

|里程碑|自动化门槛|手动门槛|
| --------| ---------------------------------| --------------------------------|
|M1|T1.x 全部 AC 测试绿|CLI demo 录屏|
|M2|e2e 与 revision/CAS 测试绿|10 分钟搭建测试（PRD G1）|
|M3|Fake 契约 + win_real + 首个公开 MVP 检查|场景 A 实操|
|M4|mock LLM + LLMProxy/越权测试绿|场景 B 真实模型抽查|
|M5|NoneSandbox 契约 + Sandboxie win_real 绿|场景 C、重命名、stale 冲突实操|
|M6|触发器/打包集成测试绿|满足外部资源前提的双机交接（PRD G3）|
|M7|全量 CI + win_real 绿|PRD §4.2 成功标准启动跟踪|

## 文档状态（不代表实现完成）

当前 01–09 文档与 `AGENTS.md` 已建立；T0.1 已通过 Linux 与 Windows 本地检查，但远程 Git/CI 尚未配置，因此该卡保持未完成。T0.3、M1（T1.1–T1.8）、M2（T2.1–T2.5）、M3（T3.1–T3.4）与 M4（T4.1–T4.5）的实现及自动化验收已完成；真实 Worker 的 CSV 闭环在内嵌 CLI、服务模式及浏览器画布均通过，真实 Excel 的场景 A 主链路也已通过。场景 B 的真实模型人工抽查尚未执行，不能视为已验证。M5 的 NoneSandbox、审批流、工具与 Pi 边界已实现并通过自动化测试；T5.2/T5.4 的 Sandboxie win_real 验收仍未完成，对应任务卡保持未勾选。T0.2 因未安装 Sandboxie 而未完成，T0.4 已验证 pi/LLMProxy 但沙箱断网仍待验证。`docs/09-nodes-v1.md` 由代码节点声明/JSON Schema 自动生成，并由 `poe check` 检查漂移。

以下事项仍需真机验证，不能当成既成事实：

1. Sandboxie 独立 box、进程归属、重命名、未知路径、网络拒绝与冲突 apply 必须通过 T0.2；未授权路径“拒绝”AC 在验证前不预先弱化。若真机证明只能重定向而无法硬拒绝，再将 AC 回退为“真实路径不变、对应变更不可收集/应用”，并明确记录安全能力降级，不在 spike 中临时选择语义。
2. Excel 多实例、COM 真超时与 owned PID 生命周期已通过 T0.3 和 M3；性能结果以同机基准为准，正式后端写入优化目标尚未达成。
3. pi 非交互调用与沙箱外 LLMProxy 兼容性必须通过 T0.4。
4. NoneSandbox 已限定为受控影子目录模拟；本机 UI 会话令牌与 Host/Origin 校验是既定安全边界，`X-Weft-Client` 只作操作标记，不构成权限控制。
