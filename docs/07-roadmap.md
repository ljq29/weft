# 07-roadmap.md

# **Weft 路线图与任务拆解**

|项|值|
| ------| ---------------------------------------------------------------------------------|
|版本|v0.1（草稿）|
|上游|`01-prd.md`​ §7 优先级、​`02-user-stories.md`|
|用法|agent 按任务卡顺序领取；每张卡独立可验证，完成 = 列出的 AC 测试通过 + ​`poe check` 全绿|

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

- 每张卡统一使用 `- [ ] **T…**`；只有 `- [x]` 表示实现完成，验收引用 `02-user-stories.md` 的 AC。当前所有任务均未完成。
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

- [ ] **T0.3 Spike：xlwings 多实例、超时与 owned 生命周期**
【依赖】T0.1
【产出】`docs/spikes/excel.md`：多实例列表与 PID/窗口选择、GetActiveObject 实测、默认模式写回可见性、模态对话框、真超时后队列占用、用户并发编辑、owned PID+创建时间+Run/心跳清理、10 万单元格与逐格/批量受控基准
【验收】记录环境版本和原始数据；明确可行边界并回写架构/AC，不能以 GetActiveObject 猜测实例或宣称超时后 Worker 立即可用

- [ ] **T0.4 Spike：pi 非交互模式与沙箱外 LLMProxy**
【依赖】T0.1
【产出】确认 pi 非交互参数、输出、退出码；实现最小主机 LLMProxy，验证 pi 可配置 OpenAI 兼容本地代理；原始 key 只在主机配置，沙箱仅收到本地地址和配置名
【验收】pi 经代理完成任务，env/stdout/trace 无原始 key，直连外网默认拒绝；命令行固化到节点声明，T1.3 后由导出器写入只读 `09-nodes-v1.md`

---

## M1 引擎核心 + 最小闭环

- [ ] **T1.1 数据模型与校验**
【依赖】T0.1
【产出】`weft.workflow`：Pydantic 全量模型、校验、原子保存、revision/CAS、迁移骨架；Trigger params 唯一真源、合法节点 ID 与 edge order
【验收】US-PKG-05/AC-1,2；US-DES-07/AC-4,5；US-EXE-04/AC-8；校验规则表全部有测试

- [ ] **T1.2 端口类型与 ValueRef**
【依赖】T1.1
【产出】PortType、兼容矩阵、ValueRef、完整缓存键（实现/用户代码/uv.lock/迭代号/内容 SHA-256）
【验收】US-DES-03/AC-5；US-EXE-04/AC-1..3

- [ ] **T1.3 节点协议、注册表与规格导出**
【依赖】T1.2
【产出】`weft-sdk` Node/Port/decorator/weft_ctx；cache_policy 与工具能力声明；注册表；由代码 JSON Schema 首次生成只读 `docs/09-nodes-v1.md`
【验收】US-DES-04/AC-4；自定义节点可注册，生成文档与声明一致且手改 diff 会被 CI 检出

- [ ] **T1.4 调度器、冻结 Run 与状态机**
【依赖】T1.3
【产出】拓扑、ExecScope、并行、分支、失败/取消、Run 队列；入队冻结 workflow/variables/manifest 和 revision，Run 输出快照
【验收】US-EXE-01/AC-1,2,3；US-EXE-02；US-EXE-03；US-EXE-04/AC-6,7；US-EXE-08/AC-1,4；US-EXE-12/AC-1,2,3；US-EXE-13/AC-1,2

- [ ] **T1.5 分类缓存层**
【依赖】T1.4
【产出】pure/volatile/side_effect 策略、缓存失效/LRU、历史输出、纯缓存恢复；副作用每次执行，LLM/实时 Excel Read 禁止跨 Run 复用
【验收】US-EXE-04/AC-1..8（与 T1.1/T1.4 分工覆盖，不重复虚标）

- [ ] **T1.6 Worker pool 与 IPC**
【依赖】T1.4
【产出】独立 `weft-worker` 包、JSON-RPC stdio、Arrow IPC+memory-map、每 Run 懒启动 pool（默认 4）、结束全退出、取消/崩溃清理、同版本 uv.lock 与 `uv sync`
【验收】US-EXE-14/AC-1..6；US-EXE-08/AC-2；真实子进程并行、跨 Run 状态隔离、无主机 PYTHONPATH 的集成测试

- [ ] **T1.7 基础表格与文件节点（第一批）**
【依赖】T1.6
【产出】`Read/Write CSV·Parquet·JSON`、`Column Filter`、`Row Filter`、`Sorter`、`Column Rename`、`Variable`、`Table Row Count`、`List Files`；写节点声明 side_effect
【验收】US-TBL-02/AC-1,3,4,5；US-TBL-03/AC-1..4,8；US-TBL-06/AC-3,4；US-TBL-07/AC-1；US-EXE-04/AC-4

- [ ] **T1.8 流程节点（第一批）与 CLI run**
【依赖】T1.7
【产出】`Trigger`（仅 manual）、`If`、`Switch`、`Merge`、`Wait`；`weft run` 内嵌模式、`weft serve` 最小 API
【验收】US-TRG-01/AC-1；US-TRG-02/AC-2；**里程碑 Demo**：CSV 闭环成功，第二次运行仅 pure 上游命中，Write CSV 仍执行，`--var` 覆盖生效

---

## M2 画布 UI

- [ ] **T2.1 REST/WS 完整化**
【依赖】T1.8
【产出】​`05-api.md` §1–5、§11 中 M2 所需端点与事件；WS 多路订阅；错误码统一
【验收】API 集成测试覆盖每个端点的 200 与主要错误路径

- [ ] **T2.2 画布编辑**
【依赖】T2.1
【产出】React Flow 画布：节点面板、拖拽、连线（后端校验）、参数表单（JSON Schema 生成）、变量绑定控件、自动保存、undo/redo、复制粘贴、导航、小地图
【验收】US-DES-01..04、US-DES-06..08、US-DES-11 的全部 AC（e2e 用 Playwright）

- [ ] **T2.3 执行可视化**
【依赖】T2.2
【产出】状态灯、右键执行菜单（到此/从此/仅此/重置）、日志面板、端口视图（Arrow 流直读 + 分页排序）、错误详情
【验收】US-DES-05；US-EXE-05/AC-1,3,4；US-EXE-06/AC-1,3,4,5；US-EXE-07/AC-1,2
【Demo】浏览器中从零搭建 M1 工作流并运行、调试

- [ ] **T2.4 循环节点与 UI**
【依赖】T2.3
【产出】​`Loop Start/End`（Row/Chunk/Counting × concat/last/variables）、引擎虚拟循环节点、迭代进度显示、配对校验
【验收】US-EXE-10/AC-1..4；US-EXE-11/AC-1..4

- [ ] **T2.5 第二批表格节点**
【依赖】T2.3
【产出】​`Joiner`​、​`Concatenate`​、​`GroupBy`​、​`Pivot/Unpivot`​、​`Duplicate Filter`​、​`Missing Value`​、​`Type Cast`​、​`Polars Expression`​、​`Math Formula`​、​`String Manipulation`​、​`Table to Variables`​、​`Variables to Table`​、​`Table Creator`​、​`Table View`​、​`Python Script`​、​`Path Join`​、​`File Copy/Move/Rename/Delete`
【验收】US-TBL-03..07、US-TBL-08/AC-1..7、US-TBL-10 的全部 P0 AC

---

## M3 Excel 联动

- [ ] **T3.1 ExcelBackend 接口 + Fake 实现**
【依赖】T1.3（可与 M2 并行）
【产出】ExcelBackend、Fake、描述符与共用契约；实时读取 volatile，App/Workbook 仅在 resolve 成功后复用
【验收】US-XLS-03/AC-4；US-XLS-04/AC-6（Fake 部分）；Linux 契约绿但不代替真机

- [ ] **T3.2 ExcelWorker**
【依赖】T3.1
【产出】STA 串行队列、超时后繁忙/排队、错误映射、owned RefRegistry、fast_mode 状态恢复
【验收】US-XLS-11/AC-1..3；US-XLS-12/AC-1..3

- [ ] **T3.3 XlwingsBackend**
【依赖】T3.2 + T0.3 结论
【产出】多实例 PID/窗口选择、attach/new_hidden、整块读写、cell update、sheet/save、显式 save|discard、owned PID 清理、可见 false/隐藏 true 的 fast_mode
【验收】US-XLS-01..08、US-XLS-10 的 `[int-win]` AC；固定基准机记录 US-XLS-04/AC-4、US-XLS-05/AC-5、US-XLS-10/AC-2 结果

- [ ] **T3.4 Excel 节点 + 描述符解析与 MVP 发布**
【依赖】T3.3
【产出】Excel 节点；描述符重解析；实时 Read 每次执行；场景 A 与公开 MVP 发布包
【验收】US-XLS-11/AC-4；US-XLS-04/AC-6（win_real）；US-EXE-06/AC-2；场景 A 真机通过
【Demo】用户选择可见实例，读打开的 Excel → 处理 → 默认模式写回并立即可见

---

## M4 Agent

- [ ] **T4.1 LLMProxy/LLMClient + mock 服务器**
【依赖】T1.8 + T0.4 结论
【产出】主机 LLMProxy、OpenAI 兼容客户端、命名配置、测试连接、mock；key 只在主机侧读取，volatile LLM 节点
【验收】US-AGT-01/AC-1..4；US-AGT-02/AC-5；US-AGT-06/AC-4；US-EXE-04/AC-4

- [ ] **T4.2 LLM Call + Prompt Template + 插值**
【依赖】T4.1
【产出】两节点 + `{var}` / `{table:port}` 插值 + Jinja2 沙箱
【验收】US-AGT-02/AC-1..4；US-AGT-09/AC-1..4

- [ ] **T4.3 Agent Loop + ToolDispatcher + 审计**
【依赖】T4.2
【产出】ReAct、停止正则优先、max_turns 默认失败/显式 partial、工具去重/超时/错误回填、打码 audit、默认不含完整 prompt 的 trace、事件与轨迹面板
【验收】US-AGT-03/AC-1..5；US-SBX-07/AC-1..3；US-AGT-10/AC-1..3

- [ ] **T4.4 授权 Node as Tool**
【依赖】T4.3
【产出】tool_capability/参数白名单、冻结参数与 Run 输入快照、ephemeral、禁止 Python/Shell/任意代码、副作用逐次确认、防递归
【验收】US-AGT-04/AC-1..7

- [ ] **T4.5 Chat 面板与聊天触发**
【依赖】T4.3
【产出】REST 发送→ChatSource、WS 推送、run/session/source/message 去重映射、独立 `.runs/chat/` 会话
【验收】US-AGT-07/AC-1..5；US-TRG-03/AC-1,2
【Demo】场景 B（mock 自动化 + 真实模型手动 US-AGT-03/AC-6），原始 key 不进入沙箱或轨迹

---

## M5 沙箱

- [ ] **T5.1 Sandbox 接口 + NoneSandbox（现有语义待讨论）**
【依赖】T0.2 结论 + NoneSandbox 讨论定案
【产出】Sandbox 接口、变更模型、受保护路径与契约；NoneSandbox 严格按 US-SBX-01/架构 §7.3/ADR A-07 的定案实现，不在本任务中擅自改名或改语义
【验收】US-SBX-01/AC-1..3；US-SBX-05/AC-4；Linux 契约仅覆盖替身能力，不冒充 Sandboxie 验证

- [ ] **T5.2 SandboxieSandbox**
【依赖】T5.1
【产出】独立 `WeftBox-<run_id>`、owned 进程树、helper、网络默认拒绝/白名单、Root/授权目录审计、未知变化提示、只清理本 Run
【验收】US-SBX-02/AC-1..4；US-SBX-03/AC-1..4；US-SBX-06/AC-1（全部 win_real）

- [ ] **T5.3 基线、重命名与冲突审批流**
【依赖】T5.1
【产出】内容哈希基线、renamed/降级、audit_complete、逐项状态、备份、stale CHANGE_CONFLICT、显式覆盖、幂等 apply/discard
【验收】US-SBX-04/AC-1..4；US-SBX-05/AC-1..5

- [ ] **T5.4 Sandboxed Tools + Pi Agent + 人工确认**
【依赖】T5.2 + T4.3 + T0.4 结论
【产出】五工具、PiRunner 经沙箱外 LLMProxy、confirm 流；不得向沙箱注入原始 key
【验收】US-AGT-05/AC-1..6；US-AGT-06/AC-1..4；US-AGT-12/AC-1..4；US-AGT-11/AC-1..3
【Demo】场景 C 真机通过；重命名可判定或明确降级，审批前真实目录不变，stale 不覆盖

---

## M6 触发器 + 打包

- [ ] **T6.1 TriggerManager + schedule/watch/http/HTTP Response**
【依赖】T1.8
【产出】统一事件、Trigger params 派生视图、APScheduler、watchdog、token/限速/wait、P0 `HTTP Response` 节点（未执行时 outputs={}）、来源健康
【验收】US-TRG-01/AC-2,3；US-TRG-04/AC-1..4；US-TRG-05/AC-1..5；US-TRG-06/AC-1..3；US-TRG-07/AC-1,2；US-SBX-09/AC-1..3

- [ ] **T6.2 打包/导入**
【依赖】T1.1
【产出】pack 排除规则/预检/密钥扫描/绝对路径清单、ERROR 阻断/WARNING 显式确认、unpack zip slip 防护与 uv sync、导入保留 id/本机 duplicate 新 id
【验收】US-PKG-01/AC-2；US-PKG-03/AC-1..4；US-PKG-04/AC-1..4；US-SBX-08/AC-1..3
【Demo】场景 D + E；在外部资源、兼容 Weft/uv 和锁定依赖可用前提下，A 机 pack → B 机 unpack → run

---

## M7 完整 v1 收尾

- [ ] **T7.1 P1 功能包**：Metanode、注释/便签、运行历史（含 Run 输出快照）、Memory、Rule Engine、Shell Command、Excel Run Macro、资源预检、绝对路径跳转（对应 US-DES-09/10、US-EXE-09、US-AGT-08、US-TBL-05/AC-4、US-TBL-09、US-XLS-09、US-PKG-06/07）
- [ ] **T7.2 doctor 与运维**：doctor/cleanup 按 owned 记录清理、动态 box 与网络检查、日志轮转、设置页（US-SET-01..04）
- [ ] **T7.3 完整 v1 发布**：全量 win_real、同机性能回归、README/安装文档/CHANGELOG、构建正式发布；版本号发布前确定，不预写 0.1.0

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

当前 01–08 设计文档与 `AGENTS.md` 已建立；所有实现任务仍为 `- [ ]`。`docs/09-nodes-v1.md` 当前不存在，T0.1 建导出器骨架、T1.3 首次由代码节点声明/JSON Schema 自动生成，之后只读更新。

以下事项仍未验证或待讨论，不能当成既成真机事实：

1. Sandboxie 独立 box、进程归属、重命名、未知路径、网络拒绝与冲突 apply 必须通过 T0.2。
2. Excel 多实例、COM 真超时、用户并发编辑与 owned PID 生命周期必须通过 T0.3；性能是同机基准。
3. pi 非交互调用与沙箱外 LLMProxy 兼容性必须通过 T0.4。
4. `NoneSandbox` 语义待讨论；`X-Weft-Client: ui` 暂不优化，不能据此声称完成权限控制。
