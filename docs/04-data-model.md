# 04-data-model.md

**Weft API 契约（REST + WebSocket）**

|项|值|
| --------| --------------------------------|
|版本|v0.1（草稿）|
|状态|待确认|
|上游|`02-user-stories.md`​、​`04-data-model.md`|
|消费方|前端 UI、CLI、外部 HTTP 触发方|

约定：前缀 ​`/api`​；请求/响应均为 ​`application/json`（除注明 Arrow 流处）；时间为 ISO 8601 带时区；错误统一结构：

```jsonc
// 非 2xx 响应体
{"error": {"code": "WORKFLOW_NOT_FOUND", "message": "人类可读", "detail": {...}}}
```

|HTTP 状态|场景|
| -----------| ------------------------------------------------------------|
|400|参数/校验错误（含受保护文件 apply）|
|401|token 缺失或错误|
|404|资源不存在（HTTP 触发未启用也返回 404，见 US-TRG-06 AC-3）|
|409|状态冲突（运行期改图、重复 apply、队列满）|
|422|workflow.json schema 校验失败（detail 含逐条错误）|
|202|异步接受（触发运行）|

鉴权：监听 ​`127.0.0.1`​ 时除 ​`/trigger`​ 外免鉴权；监听非本机时全部要求 ​`Authorization: Bearer <global_token>`​（US-SBX-09）。图结构修改接口要求头 ​`X-Weft-Client: ui`（US-AGT-11 AC-2）。

---

## 1. 工作流管理

|方法|路径|说明|
| --------| ------| -----------------------------------------------------------------------------------|
|GET|`/api/workflows`|已打开的工作流列表：​`[{id, name, path, dirty, env_status}]`|
|POST|`/api/workflows`|新建：​`{name, parent_dir}`​ → 201 ​`{id, path}`；同名目录存在 → 409|
|POST|`/api/workflows/open`|打开已有目录：​`{path}`​ → ​`{id, env_status: ok\|syncing\|error}`​；触发 ​`uv sync`（US-PKG-02）|
|GET|`/api/workflows/{id}`|返回完整 ​`workflow.json` 文档|
|PUT|`/api/workflows/{id}`|整文档保存（前端自动保存用）；校验失败 422；Run 活跃时改图结构 → 409|
|PATCH|`/api/workflows/{id}`|局部更新（JSON Merge Patch）：节点参数、位置、注释等非结构字段在 Run 活跃时也允许|
|DELETE|`/api/workflows/{id}`|从服务关闭（不删目录）；​`?purge_cache=true` 顺带清缓存|
|GET|`/api/workflows/{id}/validate`|返回校验结果 ​`{errors: [...], warnings: [...]}`​（规则见 ​`04-data-model.md` §2）|
|GET|`/api/workflows/{id}/env`|环境状态：​`{status, python, uv_output}`|
|POST|`/api/workflows/{id}/env/sync`|手动触发 ​`uv sync`​；进度经 WS ​`env.progress`|

## 2. 节点类型

|方法|路径|说明|
| ------| ------| --------------------------------------------------------------------------|
|GET|`/api/nodes/types`|全部可用节点类型（内置 + 当前工作流 ​`user.*`​）：​`[{type, node_version, category, name, description, lane, inputs, outputs, params_schema, ui_hints}]`（US-DES-04 AC-4）|
|GET|`/api/nodes/types/{type}`|单个类型详情|
|POST|`/api/workflows/{id}/nodes/{node_id}/column-hints`|返回该节点各输入端口上游缓存的列名（表单下拉用）：​`{port: [col, ...]}`；上游未执行 → 空|

## 3. 运行

|方法|路径|说明|
| ------| ------| ------------------------------------------------------------------|
|POST|`/api/workflows/{id}/runs`|发起运行：​`{scope: {kind: all\|to_node\|from_node\|single, node_id?}, overrides?: {k: v}}`​ → 202 ​`{run_id, queued: bool}`；未配置节点存在 → 400（detail 列出）|
|GET|`/api/workflows/{id}/runs?status=&limit=20`|运行历史（US-EXE-09）|
|GET|`/api/runs/{run_id}`|Run 详情 = ​`meta.json`​ 内容（​`04-data-model.md` §6）|
|POST|`/api/runs/{run_id}/cancel`|取消 → 202；已终态 → 409|
|POST|`/api/runs/{run_id}/confirm`|`{request_id, decision: approve\|reject, modified_args?}`（US-AGT-12）|
|GET|`/api/runs/{run_id}/log?offset=0&limit=500&level=&node_id=`|分页日志|
|GET|`/api/runs/{run_id}/audit`|审计记录列表（US-SBX-07）|
|GET|`/api/runs/{run_id}/nodes/{node_id}/trace`|agent 轨迹（trace.jsonl 内容）|

## 4. 节点状态与缓存操作

|方法|路径|说明|
| ------| ------| ------------------------------------|
|POST|`/api/workflows/{id}/nodes/{node_id}/reset`|重置本节点及下游（US-EXE-03 AC-3）|
|POST|`/api/workflows/{id}/reset`|重置全部|
|GET|`/api/workflows/{id}/nodes/{node_id}/status`|`{status, from_cache, last_run_id}`|

## 5. 端口数据预览

|方法|路径|说明|
| ------| ------| ------------------------------------------------------------------------------------------------------|
|GET|`/api/workflows/{id}/nodes/{node_id}/ports/{port}`|读取**缓存**的端口值（设计期端口视图）。Table：​`?offset=0&limit=100&sort_by=&desc=`​ → ​`Content-Type: application/vnd.apache.arrow.stream`​（切片后的 Arrow IPC）+ 头 ​`X-Weft-Total-Rows`；其他类型 → JSON|
|GET|`/api/runs/{run_id}/nodes/{node_id}/ports/{port}`|同上，但读指定 Run 的记录（历史回看）|

未执行 → 404 ​`PORT_NOT_EXECUTED`（US-EXE-06 AC-5）。

## 6. 沙箱变更审批

|方法|路径|说明|
| ------| ------| ------------------------------------------------------------------------------------------|
|GET|`/api/runs/{run_id}/changes`|`changes.json` 内容（§8）|
|GET|`/api/runs/{run_id}/changes/diff?path=`|文本文件 unified diff：​`{old: str\|null, new: str\|null, diff: str}`；二进制 → 400|
|POST|`/api/runs/{run_id}/changes/apply`|`{paths: [...]}`​ → ​`{results: [{path, ok, error?}]}`；含 protected 路径 → 400 整体拒绝；重复 → 幂等返回已应用状态（US-SBX-05）|
|POST|`/api/runs/{run_id}/changes/discard`|丢弃全部未应用变更|

## 7. 触发

|方法|路径|说明|
| ------| ------| --------------------------------------------------------------------------|
|POST|`/api/workflows/{id}/trigger`|外部 HTTP 触发（US-TRG-06）。​`Authorization: Bearer <workflow_token>`​；body 任意 JSON；​`?wait=true`​ 同步等待 → ​`{run_id, status, outputs}`|
|POST|`/api/workflows/{id}/trigger/token`|生成/轮换 workflow token（仅 UI），返回明文一次|
|GET|`/api/workflows/{id}/triggers/status`|各来源状态：​`{manual: {enabled}, schedule: {enabled, next_fire_times: [...]}, watch: {enabled, health: ok\|error, error?}, ...}`|

## 8. 聊天

|方法|路径|说明|
| ------| ------| ------------------------------------------------------------------------------------|
|POST|`/api/workflows/{id}/chat`|`{message, session_id?}`​ → 202 ​`{run_id, session_id}`​；未启用 chat 触发 → 400 ​`CHAT_DISABLED`（面板据此显示提示，US-TRG-03 AC-2）|
|GET|`/api/workflows/{id}/chat/{session_id}`|本会话消息列表（含历次 Run 的 Chat Output）|
|POST|`/api/workflows/{id}/chat/{session_id}/clear`|清空会话（含 Memory 文件）|

## 9. 打包与导入

|方法|路径|说明|
| ------| ------| --------------------------------------------------------------------------------------|
|POST|`/api/workflows/{id}/pack`|`{exclude_data: bool}`​ → ​`{job_id}`​；完成经 WS ​`pack.finished`​ 给出产物路径；校验 ERROR 未确认 → 409（​`?force=true` 跳过确认）|
|GET|`/api/workflows/{id}/pack/preflight`|打包预检报告：​`{errors, warnings, abs_paths: [{node_id, param, value}], size_estimate}`|
|POST|`/api/workflows/unpack`|`{zip_path, dest_dir}`​ → ​`{id, path}`；zip slip → 400|

## 10. 设置与系统

|方法|路径|说明|
| -----------| ------| ----------------------------------------------------------|
|GET / PUT|`/api/settings`|用户级配置（api_key 读取时掩码；PUT 时 ​`"***"` 表示不变更）|
|POST|`/api/settings/llm/{name}/test`|测试连接（US-AGT-01 AC-2）|
|GET|`/api/system/doctor`|`weft doctor` 的 JSON 输出|
|GET|`/api/system/version`|`{version, schema_version}`|
|POST|`/api/fs/browse`|服务端文件选择器：​`{path, dirs_only}` → 目录列表（表单路径选择用）|

## 11. WebSocket

`WS /api/ws`（单连接多路复用，连接后客户端发送订阅）：

```jsonc
// 客户端 → 服务端
{"op": "subscribe",   "topics": ["workflow:wf_8f3a", "run:r_2025..."]}
{"op": "unsubscribe", "topics": [...]}

// 服务端 → 客户端（统一信封）
{"topic": "run:r_...", "event": "node.started", "ts": "...", "data": {...}}
```

事件目录（​`data` 字段）：

|event|data|对应 AC|
| -------------| --------------------------------------------------------------| ----------------|
|`run.started`|`{run_id, scope}`|US-EXE-05|
|`run.finished`|`{run_id, status, usage}`||
|`run.queued`​ / ​`run.dequeued`|`{run_id, position}`|US-EXE-13|
|`node.status`|`{node_id, status}`（configured/running/executed/failed/skipped/cancelled）|US-DES-05|
|`node.started`​ / ​`node.finished`|`{node_id, duration_ms?, from_cache?}`||
|`node.failed`|`{node_id, error: {type, message}}`（完整 traceback 走 REST）|US-EXE-07|
|`node.progress`|`{node_id, fraction, message?}`||
|`node.log`|`{node_id, level, message}`||
|`node.stream`|`{node_id, delta}`|US-EXE-05 AC-2|
|`node.tool_call`|`{node_id, tool, args_redacted, status, duration_ms, result_summary}`|US-AGT-03 AC-5|
|`node.confirm_request`|`{request_id, node_id, tool, args, timeout_at}`|US-AGT-12|
|`node.iteration`|`{loop_node_id, index, total}`|US-EXE-10 AC-3|
|`chat.message`|`{session_id, role, content, streaming: bool}`|US-AGT-07|
|`changes.ready`|`{run_id, count}`|US-SBX-04|
|`env.progress`|`{workflow_id, line}`（uv 输出逐行）|US-EXE-14 AC-1|
|`pack.finished`|`{job_id, path}`​ / ​`pack.failed`|US-PKG-03|
|`workflow.saved`|`{workflow_id, modified_at}`（多标签页同步）||
|`trigger.status`|`{workflow_id, source, health}`|US-TRG-05 AC-4|

重连语义：WS 无事件回放；客户端重连后用 REST 补齐（US-EXE-05 AC-3）。

## 12. 兼容性承诺

- v1 期间 API 可变；​`/api/system/version`​ 的 ​`schema_version` 是唯一跨版本契约。
- 事件只增不改：新增 event 或 data 字段向后兼容，删除/重命名需升主版本。
- CLI 的 ​`--json` 输出结构与对应 REST 响应一致。

‍
