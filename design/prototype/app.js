const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;

const nodes = [
  { id: "trigger", name: "Trigger", type: "flow.trigger", icon: "trigger", palette: "flow", x: 50, y: 70, status: "executed", subtitle: "手动 · 定时", detail: "5 个来源", input: null, output: "flow", duration: "3 ms", description: "工作流入口，统一接收手动、聊天、定时、文件与 HTTP 事件。" },
  { id: "list", name: "List Files", type: "file.list", icon: "folder", palette: "file", x: 275, y: 70, status: "executed", subtitle: "data/inbox/*.xlsx", detail: "4 个文件", input: "flow", output: "table", duration: "18 ms", description: "列出符合规则的输入报表，路径相对于工作流 Root。" },
  { id: "read", name: "Excel Read Range", type: "excel.read_range", icon: "excel", palette: "excel", x: 500, y: 70, status: "executed", subtitle: "汇总.xlsx · 原始数据", detail: "1,000 行 × 5 列", input: "excel", output: "table", duration: "684 ms", description: "从可见 Excel 实例读取指定区域，实时读取结果不会跨 Run 缓存。" },
  { id: "filter", name: "Row Filter", type: "table.row_filter", icon: "filter", palette: "table", x: 500, y: 300, status: "executed", subtitle: "amount > 100", detail: "842 / 1,000 行", input: "table", output: "table", duration: "128 ms", description: "按列条件筛选数据行，只保留有效订单金额。" },
  { id: "group", name: "GroupBy", type: "table.groupby", icon: "group", palette: "table", x: 275, y: 300, status: "executed", subtitle: "按 region 聚合", detail: "6 个分组", input: "table", output: "table", duration: "84 ms", description: "按区域分组，并计算订单金额总和与订单数量。" },
  { id: "write", name: "Excel Write Table", type: "excel.write_table", icon: "excel", palette: "excel", x: 50, y: 300, status: "configured", subtitle: "汇总.xlsx · 本周 · A1", detail: "等待执行", input: "table", output: "excel", duration: "—", description: "将结果写回当前打开的工作簿，默认立即可见，不自动保存。" }
];

const statusMeta = {
  executed: { label: "已执行", summary: "上次执行成功", dot: "success", icon: "check" },
  configured: { label: "已配置", summary: "已配置，等待执行", dot: "warning", icon: "info" },
  running: { label: "执行中", summary: "节点正在执行", dot: "running", icon: "play" },
  unconfigured: { label: "未配置", summary: "必填参数尚未完成", dot: "warning", icon: "warn" },
  skipped: { label: "已跳过", summary: "分支未命中", dot: "", icon: "stop" }
};

let selectedNodeId = "filter";
let zoom = 100;
let runTimers = [];
let runningNodeId = null;
let saveTimer = null;
let currentView = "editor";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function toast(message) {
  const element = document.createElement("div");
  element.className = "toast";
  element.innerHTML = `${icon("check")}<span></span>`;
  $("span", element).textContent = message;
  $("#toast-region").append(element);
  setTimeout(() => element.remove(), 3200);
}

function navigate(view) {
  currentView = view;
  $$(".view").forEach((section) => section.classList.toggle("active", section.id === `view-${view}`));
  $$(".rail-button[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  const titles = { home: "本地工作区", editor: "周报汇总.weft", runs: "周报汇总.weft", chat: "周报汇总.weft", changes: "变更审批", settings: "用户设置" };
  $("#topbar-title").textContent = titles[view];
}

function nodeStatusMarkup(node) {
  const meta = statusMeta[node.status];
  return `<div class="node-status ${node.status}">${icon(meta.icon)}<span>${meta.label}</span></div>`;
}

function renderNodes() {
  $("#node-layer").innerHTML = nodes.map((node) => `
    <article class="canvas-node ${selectedNodeId === node.id ? "selected" : ""}" data-node-id="${node.id}" style="left:${node.x}px;top:${node.y}px" aria-label="${node.name} 节点">
      ${node.input ? `<button class="node-port input ${node.input}" aria-label="${node.input} 输入端口"></button>` : ""}
      ${node.output ? `<button class="node-port output ${node.output}" data-preview="output" aria-label="预览 ${node.output} 输出端口"></button>` : ""}
      <div class="node-header"><span class="palette-icon ${node.palette}">${icon(node.icon)}</span><div><strong>${node.name}</strong><small>${node.type}</small></div></div>
      <div class="node-body"><div><code>${node.subtitle}</code><div>${node.detail}</div></div>${node.status === "executed" ? `<button class="node-preview" data-preview="output" aria-label="预览输出">${icon("eye")}</button>` : ""}</div>
      ${nodeStatusMarkup(node)}
    </article>`).join("");
}

function fieldsForNode(node) {
  if (node.id === "filter" || node.name === "Row Filter") {
    return `<div class="form-section"><h3>筛选条件</h3>
      <label class="form-field"><span>列名 <b>*</b></span><div class="input-with-action"><select id="param-column" class="node-param"><option>amount</option><option>region</option><option>product</option><option>date</option><option>note</option></select><button title="绑定流变量">${icon("variable")}</button></div><small>来自上游表格的 5 个可用列</small></label>
      <label class="form-field"><span>运算符 <b>*</b></span><select id="param-operator" class="node-param"><option value=">">大于 &gt;</option><option value=">=">大于等于 ≥</option><option value="==">等于 =</option><option value="!=">不等于 ≠</option><option value="contains">包含</option></select></label>
      <label class="form-field"><span>比较值 <b>*</b></span><div class="input-with-action"><input id="param-value" class="node-param" value="100"><button title="绑定流变量">${icon("variable")}</button></div></label></div>`;
  }
  if (node.name === "Trigger") {
    return `<div class="form-section"><h3>触发来源</h3>
      ${[["手动", true], ["聊天", true], ["定时", true], ["文件监听", false], ["HTTP", false]].map(([name, checked]) => `<label class="select-all node-param"><input type="checkbox" ${checked ? "checked" : ""}><span>${name}</span></label>`).join("")}
      <label class="form-field"><span>定时规则</span><input class="node-param" value="0 9 * * 1-5"><small>下次触发：明天 09:00（本机时区）</small></label></div>`;
  }
  if (node.name.includes("Excel")) {
    const write = node.name.includes("Write");
    return `<div class="form-section"><h3>${write ? "写入目标" : "Excel 连接"}</h3>
      <label class="form-field"><span>工作簿 <b>*</b></span><div class="input-with-action"><input class="node-param" value="汇总.xlsx"><button title="绑定流变量">${icon("variable")}</button></div><small>已连接可见实例 · PID 14832</small></label>
      <label class="form-field"><span>工作表 <b>*</b></span><select class="node-param"><option>${write ? "本周" : "原始数据"}</option><option>Sheet1</option><option>参考表</option></select></label>
      <label class="form-field"><span>${write ? "起始单元格" : "读取区域"}</span><input class="node-param" value="${write ? "A1" : "A1:E1001"}"></label>
      ${write ? `<label class="select-all node-param"><input type="checkbox" checked><span>写入表头并自适应列宽</span></label><label class="select-all node-param"><input type="checkbox"><span>允许公式（默认按文本处理）</span></label>` : ""}</div>`;
  }
  if (node.name === "GroupBy") {
    return `<div class="form-section"><h3>分组与聚合</h3><label class="form-field"><span>分组列 <b>*</b></span><select class="node-param"><option>region</option><option>product</option></select></label><label class="form-field"><span>聚合列</span><select class="node-param"><option>amount</option><option>date</option></select></label><label class="form-field"><span>聚合方式</span><select class="node-param"><option>sum · 求和</option><option>count · 计数</option><option>mean · 平均值</option></select></label><label class="form-field"><span>输出列名</span><input class="node-param" value="total_amount"></label></div>`;
  }
  if (node.name === "List Files") {
    return `<div class="form-section"><h3>文件规则</h3><label class="form-field"><span>目录 <b>*</b></span><div class="input-with-action"><input class="node-param" value="data/inbox"><button>${icon("folder")}</button></div><small>相对于工作流 Root</small></label><label class="form-field"><span>Glob 规则</span><input class="node-param" value="*.xlsx"></label><label class="select-all node-param"><input type="checkbox"><span>递归扫描子目录</span></label></div>`;
  }
  return `<div class="form-section"><h3>节点配置</h3><label class="form-field"><span>节点名称</span><input class="node-param" value="${node.name}"></label><label class="form-field"><span>说明</span><textarea class="node-param" rows="4">${node.description}</textarea></label><div class="security-inline">${icon("info")}<span>双击节点库中的类型可继续添加到画布。</span></div></div>`;
}

function renderInspector() {
  const node = nodes.find((item) => item.id === selectedNodeId) || nodes[0];
  const meta = statusMeta[node.status];
  $("#inspector-title").textContent = node.name;
  $("#inspector-type").textContent = `${node.type} · v1`;
  $("#inspector-icon").className = `palette-icon ${node.palette}`;
  $("#inspector-icon").innerHTML = icon(node.icon);
  $("#inspector-params").innerHTML = `
    <div class="node-state-summary"><span class="status-dot ${meta.dot}"></span><span>${meta.summary}</span><span>${node.duration}</span></div>
    ${fieldsForNode(node)}
    <div class="form-section port-section"><h3>端口</h3>
      ${node.input ? `<button class="port-row" data-preview="input"><span><i class="port ${node.input}"></i>输入</span><code>in · ${node.input === "table" ? "Table" : node.input}</code>${icon("eye")}</button>` : ""}
      ${node.output ? `<button class="port-row" data-preview="output"><span><i class="port ${node.output}"></i>输出</span><code>out · ${node.output === "table" ? "Table" : node.output}</code>${icon("eye")}</button>` : ""}
    </div>
    <div class="cache-note">${icon("info")}<div><strong>${node.name.includes("Excel") || node.name.includes("Write") ? "Volatile / Side effect" : "Pure 节点"}</strong><p>${node.description}</p></div></div>`;
}

function selectNode(id) {
  selectedNodeId = id;
  renderNodes();
  renderInspector();
}

function markDirty() {
  clearTimeout(saveTimer);
  $("#dirty-mark").hidden = false;
  $("#save-state").innerHTML = "有未保存的更改";
  saveTimer = setTimeout(saveWorkflow, 2000);
}

function saveWorkflow() {
  clearTimeout(saveTimer);
  $("#dirty-mark").hidden = true;
  $("#save-state").innerHTML = `${icon("check")}所有更改已保存`;
}

function addLog(level, node, message) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.dataset.level = level;
  const now = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  entry.innerHTML = `<time>${now}</time><span class="log-level ${level.toLowerCase()}">${level}</span><span class="log-node"></span><p></p>`;
  $(".log-node", entry).textContent = node;
  $("p", entry).textContent = message;
  $("#log-list").prepend(entry);
  $("#log-count").textContent = $$(".log-entry").length;
  filterLogs();
}

function filterLogs() {
  const level = $("#log-level").value;
  $$(".log-entry").forEach((entry) => { entry.hidden = level !== "ALL" && entry.dataset.level !== level; });
}

function clearRunTimers() {
  runTimers.forEach(clearTimeout);
  runTimers = [];
}

function finishRun(targetButton) {
  runningNodeId = null;
  targetButton.innerHTML = `${icon("play")}<span>运行</span><kbd>Ctrl ↵</kbd>`;
  targetButton.classList.remove("stopping");
  addLog("INFO", "Engine", "运行完成：6 个节点成功 · 2.4 s");
  toast("运行成功，结果已写回 Excel");
  renderNodes();
  renderInspector();
}

function startRun(scope = "all") {
  if (runningNodeId) {
    clearRunTimers();
    const current = nodes.find((node) => node.id === runningNodeId);
    if (current) current.status = "configured";
    addLog("WARN", "Engine", `运行已取消${current ? `，${current.name} 已停止` : ""}`);
    runningNodeId = null;
    $("#run-button").innerHTML = `${icon("play")}<span>运行</span><kbd>Ctrl ↵</kbd>`;
    renderNodes();
    renderInspector();
    toast("运行已停止，已完成节点的缓存保留");
    return;
  }

  const button = scope === "all" ? $("#run-button") : $("#execute-to-button");
  const sequence = scope === "all" ? nodes : nodes.slice(0, nodes.findIndex((node) => node.id === selectedNodeId) + 1);
  if (sequence.length === 0) return;
  nodes.forEach((node) => { if (sequence.includes(node)) node.status = "configured"; });
  runningNodeId = "pending";
  button.innerHTML = `${icon("stop")}<span>停止</span>`;
  addLog("INFO", "Trigger", scope === "all" ? "手动运行已启动 · 正在冻结工作流快照" : `执行到 ${nodes.find((node) => node.id === selectedNodeId).name}`);
  renderNodes();
  renderInspector();

  sequence.forEach((node, index) => {
    runTimers.push(setTimeout(() => {
      if (index > 0) sequence[index - 1].status = "executed";
      node.status = "running";
      runningNodeId = node.id;
      addLog("INFO", node.name, "节点开始执行");
      renderNodes();
      if (selectedNodeId === node.id) renderInspector();
    }, index * 720));
  });
  runTimers.push(setTimeout(() => {
    sequence[sequence.length - 1].status = "executed";
    if (scope === "all") finishRun(button);
    else {
      runningNodeId = null;
      button.innerHTML = `${icon("play")}执行到此`;
      addLog("INFO", "Engine", `局部执行完成：${sequence.length} 个节点`);
      toast("已执行到所选节点");
      renderNodes();
      renderInspector();
    }
  }, sequence.length * 720));
}

function openModal(id) {
  $(`#${id}`).hidden = false;
}

function closeModals() {
  $$(".modal-backdrop").forEach((modal) => { modal.hidden = true; });
}

function openPreview(trigger) {
  const nodeElement = trigger.closest("[data-node-id]");
  const node = nodeElement ? nodes.find((item) => item.id === nodeElement.dataset.nodeId) : nodes.find((item) => item.id === selectedNodeId);
  if (node && node.status !== "executed" && currentView === "editor") {
    toast("节点未执行，暂无输出快照");
    return;
  }
  $("#preview-title").textContent = `${node ? node.name : "GroupBy"} · out`;
  openModal("preview-modal");
}

function setZoom(value) {
  zoom = Math.min(200, Math.max(25, value));
  $("#canvas-world").style.transform = `scale(${zoom / 100})`;
  $("#zoom-value").textContent = `${zoom}%`;
}

function filterNodes() {
  const query = $("#node-search").value.trim().toLowerCase();
  let visibleCount = 0;
  $$(".palette-node").forEach((button) => {
    const matches = !query || `${button.dataset.nodeType} ${button.dataset.keywords}`.toLowerCase().includes(query);
    button.classList.toggle("search-hidden", !matches);
    if (matches) visibleCount += 1;
  });
  $$(".node-category").forEach((category) => {
    const visible = $$(".palette-node:not(.search-hidden)", category).length > 0;
    category.classList.toggle("search-hidden", !visible);
    if (query && visible) category.classList.remove("collapsed");
  });
  $("#palette-empty").hidden = visibleCount > 0;
}

function addNodeFromPalette(button) {
  const name = button.dataset.nodeType;
  const id = `custom_${Date.now()}`;
  const isExcel = name.includes("Excel");
  const isAgent = name.includes("Agent") || name.includes("LLM");
  nodes.push({ id, name, type: `custom.${name.toLowerCase().replaceAll(" ", "_")}`, icon: isExcel ? "excel" : isAgent ? "agent" : "table", palette: isExcel ? "excel" : isAgent ? "agent" : "table", x: 500, y: 435, status: "configured", subtitle: "使用默认参数", detail: "尚未执行", input: "table", output: "table", duration: "—", description: `${name} 节点，使用默认参数创建。` });
  selectNode(id);
  markDirty();
  toast(`${name} 已添加到画布`);
}

function updateChangeCount() {
  const count = $$(".change-checkbox:checked").length;
  $("#selected-change-count").textContent = count;
  $("#apply-changes").disabled = count === 0;
  const all = $$(".change-checkbox");
  $("#select-all-changes").checked = count === all.length;
}

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = value;
  return element.innerHTML;
}

function sendChat() {
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text) return;
  const user = document.createElement("div");
  user.className = "message user";
  user.innerHTML = `<div class="message-avatar">L</div><div><span>你 · 刚刚</span><p>${escapeHtml(text)}</p></div>`;
  $("#chat-messages").append(user);
  input.value = "";
  $("#chat-messages").scrollTop = $("#chat-messages").scrollHeight;
  setTimeout(() => {
    const assistant = document.createElement("div");
    assistant.className = "message assistant";
    assistant.innerHTML = `<div class="message-avatar"><span class="brand mini"><span></span><span></span><span></span></span></div><div><span>Weft · 周报汇总</span><p>已触发工作流运行。当前原型使用模拟回复；正式版本会在这里流式展示 Agent 输出和工具调用。</p><footer><span>Run 已创建 · 正在执行</span></footer></div>`;
    $("#chat-messages").append(assistant);
    $("#chat-messages").scrollTop = $("#chat-messages").scrollHeight;
  }, 650);
}

function showRunDetail(type, id) {
  const tag = $("#run-detail-tag");
  tag.className = `tag ${type === "success" ? "success" : type === "failed" ? "danger" : "neutral"}`;
  tag.textContent = type === "success" ? "成功" : type === "failed" ? "失败" : "已取消";
  $("#run-detail-id").textContent = id;
  $("#run-detail-meta").textContent = `${type === "success" ? "手动" : type === "failed" ? "定时" : "聊天"}触发 · 冻结工作流快照 · revision 18`;
  if (type === "failed") {
    $("#execution-timeline").innerHTML = `<div><span class="timeline-node success">${icon("trigger")}</span><section><strong>Trigger</strong><small>定时事件已接收</small></section><time>2 ms</time></div><div><span class="timeline-node success">${icon("folder")}</span><section><strong>List Files</strong><small>发现 4 个待处理工作簿</small></section><time>16 ms</time></div><div><span class="timeline-node failed">${icon("excel")}</span><section><strong>Excel Read Range</strong><small>Excel is busy (modal dialog open?) · 请检查 Excel 窗口</small></section><time>1.1 s</time></div>`;
  } else {
    $("#execution-timeline").innerHTML = nodes.map((node) => `<div><span class="timeline-node ${type === "cancelled" && node.id === "filter" ? "failed" : "success"}">${icon(node.icon)}</span><section><strong>${node.name}</strong><small>${type === "cancelled" && node.id === "filter" ? "用户取消运行，下游未执行" : node.description}</small></section><time>${node.duration}</time></div>`).join("");
  }
}

document.addEventListener("click", (event) => {
  const viewButton = event.target.closest("[data-view]");
  if (viewButton) navigate(viewButton.dataset.view);

  const nodeElement = event.target.closest(".canvas-node");
  if (nodeElement && !event.target.closest("[data-preview]")) selectNode(nodeElement.dataset.nodeId);

  const preview = event.target.closest("[data-preview]");
  if (preview) openPreview(preview);

  if (event.target.closest(".modal-close")) closeModals();
  if (event.target.classList.contains("modal-backdrop")) closeModals();

  const category = event.target.closest(".category-title");
  if (category) category.parentElement.classList.toggle("collapsed");

  const inspectorTab = event.target.closest("[data-inspector-tab]");
  if (inspectorTab) {
    $$("[data-inspector-tab]").forEach((button) => button.classList.toggle("active", button === inspectorTab));
    ["params", "note", "trace"].forEach((tab) => { $(`#inspector-${tab}`).hidden = tab !== inspectorTab.dataset.inspectorTab; });
  }
});

$("#node-layer").addEventListener("dblclick", (event) => {
  const node = event.target.closest(".canvas-node");
  if (node) selectNode(node.dataset.nodeId);
});
$("#node-search").addEventListener("input", filterNodes);
$$(".palette-node").forEach((button) => {
  button.addEventListener("dblclick", () => addNodeFromPalette(button));
  button.addEventListener("click", (event) => { if (event.target.closest(".add-icon")) addNodeFromPalette(button); });
});

$("#run-button").addEventListener("click", () => startRun("all"));
$("#execute-to-button").addEventListener("click", () => startRun("selected"));
$("#reset-node-button").addEventListener("click", () => {
  const index = nodes.findIndex((node) => node.id === selectedNodeId);
  nodes.slice(index).forEach((node) => { node.status = "configured"; node.duration = "—"; });
  renderNodes();
  renderInspector();
  markDirty();
  toast("所选节点及下游已重置");
});
$("#inspector").addEventListener("change", (event) => { if (event.target.classList.contains("node-param")) markDirty(); });
$("#inspector").addEventListener("input", (event) => { if (event.target.classList.contains("node-param") || event.target.id === "node-note") markDirty(); });
$("#log-level").addEventListener("change", filterLogs);
$("#clear-logs").addEventListener("click", () => { $("#log-list").innerHTML = ""; $("#log-count").textContent = "0"; });
$("#toggle-logs").addEventListener("click", () => $("#log-panel").classList.toggle("collapsed"));
$("#zoom-in").addEventListener("click", () => setZoom(zoom + 10));
$("#zoom-out").addEventListener("click", () => setZoom(zoom - 10));
$("#zoom-value").addEventListener("click", () => setZoom(100));
$("#zoom-fit").addEventListener("click", () => { setZoom(100); toast("已适应全部节点"); });

$("#package-button").addEventListener("click", () => openModal("package-modal"));
$("#confirm-package").addEventListener("click", () => { closeModals(); toast("weekly-report-20261103.weft.zip 已导出"); });
$("#new-workflow-button").addEventListener("click", () => openModal("new-workflow-modal"));
$("#create-workflow").addEventListener("click", () => {
  const name = $("#new-workflow-name").value.trim() || "untitled";
  closeModals();
  navigate("editor");
  $("#topbar-title").textContent = `${name}.weft`;
  toast(`${name}.weft 已创建，环境同步完成`);
});
$("#import-button").addEventListener("click", () => toast("请选择 .weft.zip 文件与目标父目录"));
$$("[data-open-editor]").forEach((button) => button.addEventListener("click", () => navigate("editor")));

$("#new-chat").addEventListener("click", () => { $("#chat-messages").innerHTML = ""; $("#chat-input").focus(); toast("已创建新会话，session_id 已更新"); });
$("#send-chat").addEventListener("click", sendChat);
$("#chat-input").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendChat(); } });

$$(".change-checkbox").forEach((checkbox) => checkbox.addEventListener("change", updateChangeCount));
$("#select-all-changes").addEventListener("change", (event) => { $$(".change-checkbox").forEach((checkbox) => { checkbox.checked = event.target.checked; }); updateChangeCount(); });
$("#apply-changes").addEventListener("click", () => { toast(`已安全应用 ${$$(".change-checkbox:checked").length} 项变更，原文件已备份`); });
$("#discard-changes").addEventListener("click", () => { $$(".change-checkbox").forEach((checkbox) => { checkbox.checked = false; }); updateChangeCount(); toast("沙箱副本已丢弃，真实目录未改变"); });

$("#test-llm").addEventListener("click", () => {
  const result = $("#llm-test-result");
  result.hidden = false;
  toast("LLM 连接测试成功");
});
$(".test-connection").addEventListener("click", () => toast("内网网关连接成功"));
$("#add-llm").addEventListener("click", () => toast("已添加空白 LLM 配置"));

$$(".run-item").forEach((button) => button.addEventListener("click", () => {
  $$(".run-item").forEach((item) => item.classList.toggle("active", item === button));
  showRunDetail(button.dataset.run, $("strong", button).textContent);
}));

$$('.filter-pills button').forEach((button) => button.addEventListener("click", () => {
  $$('.filter-pills button').forEach((item) => item.classList.toggle('active', item === button));
  const filter = button.textContent;
  $$('.run-item').forEach((item) => {
    item.hidden = filter !== '全部' && $('.tag', item).textContent !== filter;
  });
}));

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModals();
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); saveWorkflow(); toast("工作流已保存"); }
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && currentView === "editor") { event.preventDefault(); startRun("all"); }
  if (event.key === "/" && currentView === "editor" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) { event.preventDefault(); $("#node-search").focus(); }
});

renderNodes();
renderInspector();
navigate("editor");
