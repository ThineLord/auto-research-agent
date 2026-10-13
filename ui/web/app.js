import { architecture } from "./architecture.js";
import { marked } from "./vendor/marked.js";
import DOMPurify from "./vendor/purify.js";
const $ = (s) => document.querySelector(s);
const e = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const paths = {
  logo: "M5 26V10l11-6 11 6v16M5 10l11 7 11-7M16 17v14M10 7v16m12-16v16",
  dashboard: "M3 3h7v7H3zM14 3h7v4h-7zM14 11h7v10h-7zM3 14h7v7H3z",
  outputs: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h5",
  analytics: "M3 3v18h18M7 16v-4m5 4V7m5 9V4",
  settings: "M4 7h16M4 17h16M8 4v6m8 4v6",
  chevron: "m14 6-6 6 6 6",
  arrow: "M4 12h16m-6-6 6 6-6 6",
  sun: "M12 3V1m0 22v-2M3 12H1m22 0h-2M5 5 3.5 3.5M19 19l1.5 1.5M5 19l-1.5 1.5M19 5l1.5-1.5M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  moon: "M20 14A8 8 0 0 1 10 4a8 8 0 1 0 10 10",
  language:
    "M3 5h12M9 2v3M5 5c0 7 7 10 7 10M13 5c0 6-8 11-10 11M14 21l4-10 4 10m-6-4h4",
  play: "m8 5 11 7-11 7z",
  stop: "M7 5v14M17 5v14",
  resume: "M4 11a8 8 0 1 1 2 7M4 4v7h7",
  expand: "M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6",
  check: "m5 12 4 4L19 6",
  close: "m6 6 12 12M18 6 6 18",
  log: "M4 5h16M4 10h10M4 15h16M4 20h10",
  download: "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
  refresh: "M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5",
  folder: "M3 5h7l2 3h9v12H3z",
  info: "M12 11v6m0-10v.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
};
const icon = (name) =>
  `<svg viewBox="0 0 ${name === "logo" ? "32 34" : "24 24"}" aria-hidden="true" class="icon"><path d="${paths[name] || paths.outputs}"/></svg>`;
const copy = {
  zh: {
    dashboard: "工作台",
    outputs: "研究产出",
    analytics: "运行分析",
    settings: "设置",
    research: "研究",
    local: "本地工作区",
    collapse: "收起边栏",
    expand: "展开边栏",
    light: "日间模式",
    dark: "夜间模式",
    language: "切换为 English",
    brief: "研究任务",
    memory: "研究记忆",
    saved: "已保存",
    unsaved: "有未保存的修改",
    save: "保存修改",
    run: "运行",
    idle: "待机",
    active: "运行中",
    model: "当前模型",
    start: "开始研究",
    resume: "继续",
    stop: "安全停止",
    logs: "运行日志",
    checkpoint: "检查点详情",
    stage: "当前阶段",
    round: "已进行轮次",
    score: "最佳评分",
    configure: "配置模型",
    keyHint: "需要先在设置中配置 Gemini API 密钥。",
    noData: "暂无可用分析数据",
    noDataHelp: "完成一次研究运行后，评分、耗时与结果将显示在这里。",
    viewOutputs: "浏览研究产出",
    ready: "研究任务与运行状态",
    readyOutputs: "文稿、报告与运行记录",
    readyAnalytics: "评分、资源使用与运行比较",
    readySettings: "模型、研究策略与本地工具",
    close: "关闭",
    fullEditor: "展开编辑器",
    emptyOutput: "尚未生成",
    emptyOutputHelp: "该文件会在相应研究步骤完成后出现。",
    download: "下载原始文件",
    source: "源文件",
    rendered: "阅读",
    connections: "模型连接",
    strategy: "运行策略",
    models: "模型管理",
    tools: "工作区工具",
    provider: "模型提供方",
    localProvider: "本地 · Ollama",
    cloudProvider: "云端 · Gemini",
    modelName: "模型名称",
    apiEnv: "密钥环境变量",
    apiKey: "临时 API 密钥",
    keyHelp: "密钥仅保留在当前页面内存中。留空时使用服务端配置或环境变量。",
    health: "检查连接",
    saveDefault: "设为默认模型",
    refresh: "刷新",
    installed: "已安装模型",
    pull: "下载模型",
    pullName: "要下载的模型",
    delete: "删除模型",
    confirmDelete: "请输入完整模型名确认删除",
    deleteHelp: "删除本机模型文件，之后需要重新下载。",
    cancel: "取消",
    tests: "项目测试",
    runTests: "运行测试",
    testsHelp: "运行现有测试套件，并显示结果。",
    location: "项目位置",
    mode: "运行模式",
    normal: "标准运行",
    continuous: "持续运行",
    diagnostic: "诊断运行",
    benchmark: "基准预设",
    quota: "配额失败上限",
    drafting: "起草方式",
    freePreset: "云端运行预设",
    cloudTools: "云端模型发现",
    discover: "发现可用模型",
    profile: "探测模型能力",
    cloudHelp: "发现与探测会访问 Gemini 服务；能力探测会发送测试请求。",
    results: "操作结果",
    overview: "概览",
    scores: "评分走势",
    rubric: "评价维度",
    similarity: "修订相似度",
    timing: "智能体耗时",
    tokens: "Token 估计",
    comparison: "运行比较",
    metadata: "运行元数据",
    allOutputs: "全部研究产出",
    loading: "正在载入…",
    network: "连接失败，请检查本地服务。",
    done: "操作已完成",
    starting: "运行已启动",
    busy: "处理中…",
    noLogs: "还没有日志。",
    noModels: "尚未发现本地模型",
    chars: "字",
    stopPending: "已请求安全停止",
    editorHelp: "编辑研究目标、约束和预期产出。",
    memoryHelp: "记录跨轮次保留的背景与研究记忆。",
    fresh: "新建草稿并参考评审",
    best: "参考最佳结果",
    previous: "继续上一轮草稿",
    smoke: "免费冒烟测试",
    eval: "免费评估",
    paid: "付费基准测试",
    auto: "自动长时间运行",
    quality: "质量优先",
    volume: "吞吐优先",
    manual: "手动选择",
    details: "查看详情",
    noProject: "没有可用项目",
    error: "操作失败",
    offline: "连接中断",
    modelsHelp: "模型的下载、检查与删除集中在这里。",
    estimated: "估计值",
    updated: "自动刷新",
    emptyCompare: "还没有可比较的运行。",
    cloudRecommendation: "推荐模型",
    projectTests: "项目测试结果",
  },
  en: {
    dashboard: "Workspace",
    outputs: "Research outputs",
    analytics: "Run analytics",
    settings: "Settings",
    research: "Research",
    local: "Local workspace",
    collapse: "Collapse sidebar",
    expand: "Expand sidebar",
    light: "Light mode",
    dark: "Dark mode",
    language: "切换为中文",
    brief: "Research task",
    memory: "Research memory",
    saved: "Saved",
    unsaved: "Unsaved changes",
    save: "Save changes",
    run: "Run",
    idle: "Idle",
    active: "Running",
    model: "Selected model",
    start: "Start research",
    resume: "Resume",
    stop: "Safe stop",
    logs: "Run logs",
    checkpoint: "Checkpoint details",
    stage: "Current stage",
    round: "Rounds",
    score: "Best score",
    configure: "Configure model",
    keyHint: "Add a Gemini API key in settings before starting.",
    noData: "No analytics available",
    noDataHelp: "Scores, timing and results will appear after a research run.",
    viewOutputs: "Browse outputs",
    ready: "Research task and run status",
    readyOutputs: "Drafts, reports and run records",
    readyAnalytics: "Scores, resource use and run comparisons",
    readySettings: "Models, research strategy and local tools",
    close: "Close",
    fullEditor: "Expand editor",
    emptyOutput: "Not generated yet",
    emptyOutputHelp:
      "This file will appear when the corresponding research step finishes.",
    download: "Download original",
    source: "Source",
    rendered: "Read",
    connections: "Model connection",
    strategy: "Run strategy",
    models: "Model management",
    tools: "Workspace tools",
    provider: "Model provider",
    localProvider: "Local · Ollama",
    cloudProvider: "Cloud · Gemini",
    modelName: "Model name",
    apiEnv: "API key environment variable",
    apiKey: "Temporary API key",
    keyHelp:
      "The key stays in this page’s memory only. Leave blank to use server configuration or environment variables.",
    health: "Check connection",
    saveDefault: "Set as default",
    refresh: "Refresh",
    installed: "Installed models",
    pull: "Download model",
    pullName: "Model to download",
    delete: "Delete model",
    confirmDelete: "Type the full model name to confirm deletion",
    deleteHelp:
      "Removes the local model files. You will need to download them again.",
    cancel: "Cancel",
    tests: "Project tests",
    runTests: "Run tests",
    testsHelp: "Run the existing test suite and display its results.",
    location: "Project location",
    mode: "Run mode",
    normal: "Standard run",
    continuous: "Continuous run",
    diagnostic: "Diagnostic run",
    benchmark: "Benchmark preset",
    quota: "Quota failure limit",
    drafting: "Drafting strategy",
    freePreset: "Cloud runner preset",
    cloudTools: "Cloud model discovery",
    discover: "Discover models",
    profile: "Profile capabilities",
    cloudHelp:
      "Discovery and profiling contact Gemini. Profiling sends test requests.",
    results: "Operation result",
    overview: "Overview",
    scores: "Score trend",
    rubric: "Rubric",
    similarity: "Revision similarity",
    timing: "Agent timing",
    tokens: "Token estimates",
    comparison: "Run comparison",
    metadata: "Run metadata",
    allOutputs: "All research outputs",
    loading: "Loading…",
    network: "Connection failed. Check the local server.",
    done: "Operation completed",
    starting: "Run started",
    busy: "Working…",
    noLogs: "No logs yet.",
    noModels: "No local models detected",
    chars: "characters",
    stopPending: "Safe stop requested",
    editorHelp:
      "Define the research objective, constraints and expected output.",
    memoryHelp: "Background and research memory retained across rounds.",
    fresh: "Fresh draft with review",
    best: "Guided by best result",
    previous: "Continue previous draft",
    smoke: "Free smoke test",
    eval: "Free evaluation",
    paid: "Paid benchmark",
    auto: "Automatic long run",
    quality: "Quality first",
    volume: "Volume first",
    manual: "Manual selection",
    details: "View details",
    noProject: "No projects available",
    error: "Operation failed",
    offline: "Disconnected",
    modelsHelp: "Download, inspect and remove your local models in one place.",
    estimated: "Estimated",
    updated: "Auto refresh",
    emptyCompare: "No runs available for comparison.",
    cloudRecommendation: "Recommended model",
    projectTests: "Project test results",
  },
};
let boot,
  data,
  analysis,
  outputContent = "",
  outputIndex = 0;
let state = {
  lang: localStorage.getItem("ara-language") || "zh",
  theme: localStorage.getItem("ara-theme") || "light",
  collapsed: localStorage.getItem("ara-collapsed") === "true",
  page: "dashboard",
  editor: "task",
  setting: "connections",
  chart: "scores",
  raw: false,
};
if (!["zh", "en"].includes(state.lang)) state.lang = "zh";
if (!["light", "dark"].includes(state.theme)) state.theme = "light";
let comparisonSelection = null;
let selected = "",
  drafts = {},
  prefs = {},
  apiKey = "",
  installed = [],
  modelError = "",
  result = null,
  runningAction = false,
  version = 0;
const t = (key, args = {}) => {
  let value =
    copy[state.lang][key] ?? boot?.translations?.[state.lang]?.[key] ?? key;
  for (const [k, v] of Object.entries(args))
    value = value.replaceAll(`{${k}}`, String(v));
  return value;
};
const message = (p) =>
  p.message_key ? t(p.message_key, p.message_args) : p.message || "";
const display = (v) => (v == null || v === "N/A" || v === "" ? "—" : v);
function localizedStage(stage) {
  if (stage === "Idle") return t("stage_idle");
  if (stage === "starting") return t("stage_starting");
  if (stage === "starting round") return t("stage_starting_round");
  if (stage.startsWith("after "))
    return t("stage_after_agent", { agent: stage.slice(6) });
  return stage;
}
function toast(text, error = false) {
  const node = $("#notice");
  node.textContent = text;
  node.className = `visible${error ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (node.className = ""), error ? 8500 : 4200);
}
async function api(route, body) {
  const response = await fetch(
    route,
    body
      ? {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Dashboard-Token": boot.token,
          },
          body: JSON.stringify(body),
        }
      : {},
  );
  const value = await response.json();
  if (!response.ok) throw Error(value.error || t("error"));
  return value;
}
function query(route) {
  return `/api/${route}?project=${encodeURIComponent(selected)}`;
}
async function operate(action, extra = {}) {
  return api("/api/action", {
    ...prefs,
    project: selected,
    model: ["health", "default"].includes(action)
      ? effectiveModel()
      : prefs.model,
    api_key: apiKey,
    action,
    ...extra,
  });
}
function empty(title = "noData", help = "noDataHelp") {
  return `<div class="empty-state">${icon("outputs")}<h3>${t(title)}</h3><p>${t(help)}</p></div>`;
}
function button(action, label, kind = "", symbol = "") {
  return `<button type="button" data-action="${action}" class="${kind}">${symbol ? icon(symbol) : ""}${e(t(label))}</button>`;
}
function select(name, options, value) {
  return `<select data-pref="${name}" id="${name}">${options.map(([v, k]) => `<option value="${e(v)}" ${v === value ? "selected" : ""}>${e(t(k))}</option>`).join("")}</select>`;
}
function field(label, control, full = false) {
  return `<label class="field ${full ? "full" : ""}"><span>${e(t(label))}</span>${control}</label>`;
}
function shell() {
  document.documentElement.lang = state.lang;
  document.documentElement.dataset.theme = state.theme;
  $("#app").className = state.collapsed ? "collapsed" : "";
  const nav = ["dashboard", "outputs", "analytics", "settings"];
  $("#app").innerHTML =
    `<aside class="sidebar" aria-label="${state.lang === "zh" ? "主导航" : "Main navigation"}"><a href="#dashboard" class="brand" aria-label="Auto research agent">${icon("logo")}<div class="brand-name">Auto research<span>agent</span></div></a><button class="collapse" data-action="collapse" title="${t(state.collapsed || matchMedia("(max-width:920px)").matches ? "expand" : "collapse")}" aria-label="${t(state.collapsed || matchMedia("(max-width:920px)").matches ? "expand" : "collapse")}" aria-expanded="${!state.collapsed && !matchMedia("(max-width:920px)").matches}">${icon("chevron")}</button><nav>${nav.map((n) => `<button class="nav-button" data-nav="${n}" aria-label="${t(n)}" title="${t(n)}" ${state.page === n ? 'aria-current="page"' : ""}>${icon(n)}<span class="nav-label">${t(n)}</span></button>`).join("")}</nav><div class="sidebar-bottom"><button class="nav-button" data-action="theme" title="${t(state.theme === "light" ? "dark" : "light")}" aria-label="${t(state.theme === "light" ? "dark" : "light")}">${icon(state.theme === "light" ? "moon" : "sun")}<span class="nav-label">${t(state.theme === "light" ? "dark" : "light")}</span></button><button class="nav-button" data-action="language" title="${t("language")}" aria-label="${t("language")}">${icon("language")}<span class="nav-label">${state.lang === "zh" ? "English" : "中文"}</span></button><div class="local-state"><span class="dot"></span><span>${t("local")}</span></div></div></aside><main id="content" tabindex="-1"><header class="page-header"><div><div class="breadcrumb"><span>${t("research")}</span><span class="slash">/</span><select class="project-select" id="project" aria-label="${t("project_selector")}">${boot.projects.map((p) => `<option ${p === selected ? "selected" : ""}>${e(p)}</option>`).join("")}</select></div><h1>${t(state.page)}</h1><div class="page-note">${t({ dashboard: "ready", outputs: "readyOutputs", analytics: "readyAnalytics", settings: "readySettings" }[state.page])}</div></div><div class="architecture" id="architecture"></div></header><div id="view"></div><footer class="footer"><span>AUTO RESEARCH AGENT · LOCAL</span><span>Hanzhi YOU</span></footer></main>`;
  architecture($("#architecture"), nav.indexOf(state.page));
  renderView();
}
function renderView() {
  if (!data) {
    $("#view").innerHTML = `<div class="loading">${t("loading")}</div>`;
    return;
  }
  $("#view").className = "fade-in";
  ({
    dashboard: renderDashboard,
    outputs: renderOutputs,
    analytics: renderAnalytics,
    settings: renderSettings,
  })[state.page]();
}
function effectiveModel() {
  return prefs.provider === "gemini" && prefs.free_runner_preset !== "manual"
    ? data?.recommendations?.[prefs.free_runner_preset]?.model_id || prefs.model
    : prefs.model;
}
function renderDashboard() {
  const draft = drafts[selected],
    p = data.progress,
    needsKey =
      prefs.provider === "gemini" && !apiKey && !boot.config.key_available;
  $("#view").innerHTML =
    `<div class="workspace-grid"><section><div class="card editor-card"><div class="editor-toolbar"><div class="editor-tabs" role="tablist" aria-label="${t("brief")}">${[
      ["task", "brief"],
      ["memory", "memory"],
    ]
      .map(
        ([k, l]) =>
          `<button role="tab" aria-selected="${state.editor === k}" class="${state.editor === k ? "active" : ""}" data-editor="${k}">${t(l)}</button>`,
      )
      .join(
        "",
      )}</div><button class="icon-button" data-action="editor" title="${t("fullEditor")}" aria-label="${t("fullEditor")}">${icon("expand")}</button></div><textarea id="editor" aria-label="${t(state.editor === "task" ? "brief" : "memory")}" spellcheck="false" placeholder="${t(state.editor === "task" ? "editorHelp" : "memoryHelp")}">${e(draft[state.editor])}</textarea><div class="editor-footer"><span class="saved-label" id="save-state">${icon("check")}${t(draft.dirty ? "unsaved" : "saved")}</span>${button("save", "save", "", "check")}</div></div><div class="metrics-strip"><div class="metric"><span class="metric-label">${t("stage")}</span><span id="stage" class="metric-value small">${e(localizedStage(p.stage))}</span></div><div class="metric"><span class="metric-label">${t("round")}</span><span id="round" class="metric-value">${e(display(p.round))}</span></div><div class="metric"><span class="metric-label">${t("score")}</span><span id="score" class="metric-value">${e(display(p.best_score))}</span></div></div><div class="recent-bar"><span>${t("allOutputs")} <span class="eyebrow">${String(data.outputs.filter((o) => o.exists).length).padStart(2, "0")}</span></span><button class="quiet" data-nav="outputs">${t("viewOutputs")}${icon("arrow")}</button></div></section><aside class="card run-card"><div class="section-top"><h2>${t("run")}</h2><span class="status-pill" id="run-status"><span class="dot"></span>${t(p.run_active ? "active" : "idle")}</span></div><span class="eyebrow">${t("model")}</span><div class="run-model">${e(effectiveModel())}</div><label for="mode" class="sr-only">${t("mode")}</label>${select(
      "mode",
      [
        ["normal", "normal"],
        ["continuous", "continuous"],
        ["diagnostic", "diagnostic"],
      ],
      prefs.mode,
    )}<button class="primary" data-action="run" ${p.run_active || needsKey ? "disabled" : ""}>${icon("play")}${t("start")}</button><div class="run-secondary"><button data-action="resume" ${!data.resume.can_resume || needsKey ? "disabled" : ""}>${icon("resume")}${t("resume")}</button><button data-action="stop" ${!p.run_active || data.stop_requested ? "disabled" : ""}>${icon("stop")}${t("stop")}</button></div><p class="run-hint">${needsKey ? t("keyHint") : `${prefs.provider === "gemini" ? "Gemini" : "Ollama"} · ${t(prefs.drafting_mode === "best_guided" ? "best" : prefs.drafting_mode === "continue_from_previous_draft" ? "previous" : "fresh")}`} <button class="link-button" data-nav="settings">${t("configure")}</button></p><div class="divider"></div><button class="detail-link" data-action="logs"><span>${t("logs")}</span>${icon("arrow")}</button><button class="detail-link" data-action="checkpoint"><span>${t("checkpoint")}</span>${icon("arrow")}</button>${data.stop_requested && p.run_active ? `<p class="run-hint">${t("stopPending")}</p>` : ""}</aside></div>`;
}
function renderOutputs() {
  const row = data.outputs.find((o) => o.id === outputIndex) || data.outputs[0];
  outputIndex = row?.id || 0;
  $("#view").innerHTML =
    `<div class="outputs-layout"><div class="file-list" aria-label="${t("outputs")}">${data.outputs.map((o) => `<button data-output="${o.id}" class="file-row ${o.id === outputIndex ? "active" : ""}" title="${e(o.path)}">${icon("outputs")}<span class="file-label">${e(t(o.label_key))}</span>${o.exists ? "" : `<span class="empty-dot" title="${t("emptyOutput")}"></span>`}</button>`).join("")}</div><section class="card document-card"><div class="document-bar"><span>${e(t(row.label_key))}</span><div class="header-tools">${row.kind === "markdown" ? button("raw", state.raw ? "rendered" : "source", "quiet") : ""}<button class="icon-button" data-action="download" title="${t("download")}" aria-label="${t("download")}" ${!row.exists ? "disabled" : ""}>${icon("download")}</button></div></div><div class="document-path">${e(row.path)}</div><div id="document">${row.exists ? `<div class="loading">${t("loading")}</div>` : empty("emptyOutput", "emptyOutputHelp")}</div></section></div>`;
  if (row.exists) loadOutput(row);
}
async function loadOutput(row) {
  const project = selected;
  try {
    const result = await api(`${query("output")}&id=${row.id}`);
    if (
      selected !== project ||
      state.page !== "outputs" ||
      outputIndex !== row.id
    )
      return;
    outputContent = result.content;
    $("#document").innerHTML = result.exists
      ? `<article class="document">${row.kind === "markdown" && !state.raw ? markdown(result.content) : `<pre>${e(result.content)}</pre>`}</article>`
      : empty("emptyOutput", "emptyOutputHelp");
  } catch (err) {
    if ($("#document"))
      $("#document").innerHTML =
        `<div class="empty-state">${e(err.message)}</div>`;
  }
}
function markdown(text) {
  return DOMPurify.sanitize(marked.parse(text), {
    FORBID_TAGS: [
      "img",
      "style",
      "iframe",
      "form",
      "input",
      "button",
      "video",
      "audio",
    ],
    FORBID_ATTR: ["style", "srcset"],
    ALLOW_DATA_ATTR: false,
  });
}
function table(rows) {
  if (!rows?.length) return empty();
  const keys = Object.keys(rows[0]);
  return `<div class="table-wrap"><table><thead><tr>${keys.map((k) => `<th>${e(column(k))}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${keys.map((k) => `<td class="${String(row[k]).length > 65 ? "long" : ""}">${e(display(row[k] !== null && typeof row[k] === "object" ? JSON.stringify(row[k]) : row[k]))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function column(key) {
  for (const candidate of [`column_${key}`, `run_meta_${key}`]) {
    if (t(candidate) !== candidate) return t(candidate);
  }
  const labels = {
    agent: state.lang === "zh" ? "智能体" : "Agent",
    score_delta: state.lang === "zh" ? "评分变化" : "Score change",
    next_round: state.lang === "zh" ? "下一轮" : "Next round",
    last_completed_round: t("round"),
    can_resume: t("resume"),
    completed_round_files_preserved:
      state.lang === "zh" ? "保留已完成文件" : "Completed files preserved",
    next_round_status: state.lang === "zh" ? "下一轮状态" : "Next round status",
    next_round_safety_action:
      state.lang === "zh" ? "恢复操作" : "Recovery action",
    next_round_path: state.lang === "zh" ? "下一轮路径" : "Next round path",
    next_round_blocks_resume:
      state.lang === "zh" ? "下一轮阻止恢复" : "Next round blocks resume",
    next_round_existing_files:
      state.lang === "zh" ? "已存在文件" : "Existing files",
    run_root: state.lang === "zh" ? "运行目录" : "Run directory",
  };
  return labels[key] || key.replaceAll("_", " ");
}
function chart(rows) {
  if (!rows?.length) return "";
  const keys = Object.keys(rows[0]).filter(
    (k) =>
      k !== "round" &&
      k !== "agent" &&
      rows.some((r) => typeof r[k] === "number"),
  );
  if (!keys.length) return "";
  const series = keys,
    values = rows.flatMap((r) =>
      series
        .map((k) => r[k])
        .filter((v) => typeof v === "number" && Number.isFinite(v)),
    );
  const min = Math.min(0, ...values),
    max = Math.max(1, ...values),
    width = 680,
    height = 200;
  const point = (r, i, k) =>
    `${45 + (i * (width - 65)) / Math.max(rows.length - 1, 1)},${height - 25 - (((Number(r[k]) || 0) - min) / (max - min)) * (height - 50)}`;
  let svg = "";
  for (let i = 0; i <= 3; i++) {
    const y = 25 + i * 50;
    svg += `<line x1="45" x2="665" y1="${y}" y2="${y}" stroke="var(--line)"/><text x="0" y="${y + 4}">${(max - ((max - min) * i) / 3).toFixed(1)}</text>`;
  }
  series.forEach((key, j) => {
    const color = [
      "var(--accent)",
      "var(--muted)",
      "var(--danger)",
      "var(--chart-4)",
      "var(--chart-5)",
    ][j % 5];
    let segment = [];
    const flush = () => {
      if (segment.length)
        svg += `<polyline fill="none" stroke="${color}" stroke-width="2" points="${segment.join(" ")}"/>`;
      segment = [];
    };
    rows.forEach((r, i) => {
      if (typeof r[key] === "number" && Number.isFinite(r[key]))
        segment.push(point(r, i, key));
      else flush();
    });
    flush();
    rows.forEach((r, i) => {
      if (typeof r[key] !== "number" || !Number.isFinite(r[key])) return;
      const [cx, cy] = point(r, i, key).split(",");
      svg += `<circle cx="${cx}" cy="${cy}" r="3" fill="${color}"><title>${e(column(key))}: ${e(r[key])}</title></circle>`;
    });
  });
  return `<svg class="chart" viewBox="0 0 680 210" role="img" aria-label="${e(t(state.chart))}">${svg}<text x="45" y="205">${e(rows[0].round ?? rows[0].agent ?? "1")}</text><text x="640" y="205">${e(rows.at(-1).round ?? rows.at(-1).agent ?? rows.length)}</text></svg><div class="legend">${series.map((k, j) => `<span style="--series-color:${["var(--accent)", "var(--muted)", "var(--danger)", "var(--chart-4)", "var(--chart-5)"][j % 5]}">${e(column(k))}</span>`).join("")}</div>`;
}
function renderAnalytics() {
  if (!analysis) {
    $("#view").innerHTML = `<div class="loading">${t("loading")}</div>`;
    loadAnalytics();
    return;
  }
  const tabs = [
    "scores",
    "rubric",
    "similarity",
    "timing",
    "tokens",
    "comparison",
    "metadata",
  ];
  const rows =
    analysis[
      {
        scores: "score_rows",
        rubric: "rubric_rows",
        similarity: "similarity_rows",
        timing: "agent_timing_rows",
        tokens: "token_rows",
        comparison: "comparison",
        metadata: "metadata",
      }[state.chart]
    ] || [];
  let actual =
    state.chart === "metadata"
      ? rows.map((r) => ({ field: t(r.field_key), value: r.value }))
      : rows;
  if (state.chart === "comparison" && comparisonSelection)
    actual = actual.filter((row) => comparisonSelection.has(row.run_id));
  const comparisonPicker =
    state.chart === "comparison"
      ? `<div class="comparison-picker">${(analysis.comparison || []).map((row) => `<label><input type="checkbox" data-compare="${e(row.run_id)}" ${!comparisonSelection || comparisonSelection.has(row.run_id) ? "checked" : ""}>${e(row.run_id)}</label>`).join("")}</div>`
      : "";
  $("#view").innerHTML =
    `${analysis.available ? `<div class="analytics-cards">${analysis.cards.map((c) => `<div class="card"><span class="metric-label">${e(t(c.label_key))}</span><span class="metric-value">${e(display(c.value))}</span></div>`).join("")}</div>` : ""}<div class="data-tabs">${tabs.map((n) => `<button data-chart="${n}" class="${state.chart === n ? "active" : ""}">${t(n)}</button>`).join("")}</div><section class="card">${analysis.blocked_reason ? `<p class="hint-banner">${e(t(analysis.blocked_reason))}</p>` : ""}${comparisonPicker}${actual.length ? `${!["metadata", "comparison"].includes(state.chart) ? chart(actual) : ""}${table(actual)}` : empty()}</section>`;
}
async function loadAnalytics() {
  const p = selected;
  try {
    const value = await api(query("analytics"));
    if (p !== selected) return;
    analysis = value;
    if (state.page === "analytics") renderAnalytics();
  } catch (err) {
    toast(err.message, true);
    if (state.page === "analytics") $("#view").innerHTML = empty();
  }
}
function renderSettings() {
  const sections = ["connections", "strategy", "models", "tools"];
  $("#view").innerHTML =
    `<div class="settings-layout"><nav class="settings-nav" aria-label="${t("settings")}">${sections.map((n) => `<button data-setting="${n}" class="${state.setting === n ? "active" : ""}">${t(n)}</button>`).join("")}</nav><section class="card settings-section" id="settings-section"></section></div>`;
  let html = `<h2>${t(state.setting)}</h2>`;
  if (state.setting === "connections") {
    html += `<div class="form-grid">${field(
      "provider",
      select(
        "provider",
        [
          ["ollama", "localProvider"],
          ["gemini", "cloudProvider"],
        ],
        prefs.provider,
      ),
    )}${field("modelName", `<input data-pref="model" value="${e(prefs.model)}" list="model-options" autocomplete="off"><datalist id="model-options">${(prefs.provider === "gemini" ? boot.config.cloud_models : installed.map((m) => m.name)).map((n) => `<option value="${e(n)}">`).join("")}</datalist>`)}${prefs.provider === "gemini" ? `${field("apiEnv", `<input data-pref="api_key_env" value="${e(prefs.api_key_env)}" spellcheck="false">`)}${field("apiKey", `<input type="password" id="api-key" value="${e(apiKey)}" autocomplete="off" placeholder="${boot.config.key_available ? "••••••••" : ""}">`)}` : ""}</div>${prefs.provider === "gemini" ? `<p class="help">${t("keyHelp")}</p>` : ""}<div class="actions">${button("health", "health", "", "check")}${button("default", "saveDefault")}</div>`;
    if (prefs.provider === "gemini")
      html += `<div class="subsection"><h3>${t("cloudTools")}</h3><p class="help">${t("cloudHelp")}</p><div class="actions">${button("discover", "discover")}${button("profile", "profile")}</div></div>`;
  } else if (state.setting === "strategy") {
    html += `<div class="form-grid">${field(
      "drafting",
      select(
        "drafting_mode",
        [
          ["best_guided", "best"],
          ["fresh_from_task_with_review", "fresh"],
          ["continue_from_previous_draft", "previous"],
        ],
        prefs.drafting_mode,
      ),
      true,
    )}${field(
      "benchmark",
      select(
        "benchmark_preset",
        [
          ["free_smoke", "smoke"],
          ["free_eval", "eval"],
          ["paid_benchmark", "paid"],
        ],
        prefs.benchmark_preset,
      ),
    )}${field("quota", `<input type="number" data-pref="max_provider_quota_failures" min="0" max="20" value="${e(prefs.max_provider_quota_failures)}">`)}${field(
      "freePreset",
      select(
        "free_runner_preset",
        [
          ["auto_long_run", "auto"],
          ["quality_free", "quality"],
          ["volume_free", "volume"],
          ["manual", "manual"],
        ],
        prefs.free_runner_preset,
      ),
      true,
    )}</div><p class="help">${state.lang === "zh" ? "这些选项应用于下一次研究运行。" : "These options apply to your next research run."}</p>`;
  } else if (state.setting === "models") {
    html += `<p class="help">${t("modelsHelp")}</p><div class="section-top"><h3>${t("installed")}</h3>${button("models", "refresh", "quiet", "refresh")}</div>${modelError ? `<p class="hint-banner">${e(modelError)}</p>` : ""}${installed.length ? `<div class="file-list">${installed.map((m) => `<div class="file-row"><span class="file-label" style="font-family:var(--mono)">${e(m.name)}</span><button class="icon-button danger" data-delete="${e(m.name)}" title="${t("delete")}" aria-label="${t("delete")} ${e(m.name)}">${icon("close")}</button></div>`).join("")}</div>` : `<p class="help">${t("noModels")}</p>`}<div class="subsection">${field("pullName", `<input id="pull-name" placeholder="qwen3:8b" autocomplete="off">`)}<div class="actions">${button("pull", "pull", "", "download")}</div></div><div class="actions">${button("model-logs", "logs", "quiet", "log")}</div>`;
  } else {
    html += `<h3>${t("tests")}</h3><p class="help">${t("testsHelp")}</p><div class="actions">${button("tests", "runTests")}</div><div class="subsection"><h3>${t("location")}</h3><p class="code">projects/${e(selected)}</p></div>`;
  }
  if (
    prefs.provider === "gemini" &&
    state.setting === "connections" &&
    effectiveModel() !== prefs.model
  )
    html += `<p class="hint-banner">${t("cloudRecommendation")}: ${e(effectiveModel())}</p>`;
  if (result)
    html += `<div class="result" role="status">${e(formatResult(result))}</div>`;
  $("#settings-section").innerHTML = html;
}
function formatResult(r) {
  if (r.message_key) return message(r);
  if (r.output) return r.output;
  if (r.recommendation)
    return `${t("cloudRecommendation")}: ${r.recommendation.model_id}\n${r.recommendation.reason || ""}`;
  if (r.profiles || r.candidates) return JSON.stringify(r, null, 2);
  return r.message || t("done");
}
function openPanel(title, body) {
  $("#panel-content").innerHTML =
    `<div class="panel-heading"><h2>${e(title)}</h2><button class="icon-button" data-action="close" aria-label="${t("close")}">${icon("close")}</button></div><div class="panel-body">${body}</div>`;
  if (!$("#panel").open) $("#panel").showModal();
}
function openLogs(model = false) {
  openPanel(
    t("logs"),
    `<pre id="live-log" data-model="${model}">${e((model ? data.model_log : data.log) || t("noLogs"))}</pre>`,
  );
}
async function loadProject(name) {
  const current = ++version;
  selected = name;
  data = null;
  analysis = null;
  comparisonSelection = null;
  outputIndex = 0;
  result = null;
  shell();
  try {
    const value = await api(query("workspace"));
    if (current !== version) return;
    data = value;
    if (!drafts[name])
      drafts[name] = {
        task: value.task,
        memory: value.memory,
        savedTask: value.task,
        savedMemory: value.memory,
        dirty: false,
      };
    renderView();
  } catch (err) {
    if (current === version) {
      $("#view").innerHTML = `<div class="empty-state">${e(err.message)}</div>`;
      toast(err.message, true);
    }
  }
}
async function save() {
  const project = selected,
    draft = drafts[project],
    task = draft.task,
    memory = draft.memory;
  const result = await operate("save", { task, memory });
  draft.savedTask = task;
  draft.savedMemory = memory;
  draft.dirty = draft.task !== task || draft.memory !== memory;
  toast(message(result));
  if (selected === project && state.page === "dashboard") renderDashboard();
}
async function act(action) {
  if (action === "collapse") {
    if (matchMedia("(max-width:920px)").matches) {
      $("#app").classList.toggle("mobile-expanded");
      const expanded = $("#app").classList.contains("mobile-expanded");
      $(".collapse").setAttribute("aria-expanded", String(expanded));
      $(".collapse").setAttribute(
        "aria-label",
        t(expanded ? "collapse" : "expand"),
      );
      return;
    }
    state.collapsed = !state.collapsed;
    localStorage.setItem("ara-collapsed", state.collapsed);
    $("#app").classList.toggle("collapsed", state.collapsed);
    $(".collapse").setAttribute("aria-expanded", String(!state.collapsed));
    $(".collapse").setAttribute(
      "aria-label",
      t(state.collapsed ? "expand" : "collapse"),
    );
    $(".collapse").title = t(state.collapsed ? "expand" : "collapse");
    return;
  }
  if (action === "theme") {
    state.theme = state.theme === "light" ? "dark" : "light";
    localStorage.setItem("ara-theme", state.theme);
    shell();
    return;
  }
  if (action === "language") {
    state.lang = state.lang === "zh" ? "en" : "zh";
    localStorage.setItem("ara-language", state.lang);
    shell();
    return;
  }
  if (action === "close") {
    $("#panel").close();
    return;
  }
  if (action === "editor") {
    openPanel(
      t(state.editor === "task" ? "brief" : "memory"),
      `<textarea id="large-editor" aria-label="${t(state.editor === "task" ? "brief" : "memory")}">${e(drafts[selected][state.editor])}</textarea><div class="actions">${button("close", "done", "primary")}</div>`,
    );
    return;
  }
  if (action === "logs" || action === "model-logs") {
    openLogs(action === "model-logs");
    return;
  }
  if (action === "checkpoint") {
    const r = data.resume;
    openPanel(
      t("checkpoint"),
      `<p class="help">${e(message(r))}</p><dl>${Object.entries(r.details || {})
        .map(([k, v]) => `<dt>${e(column(k))}</dt><dd>${e(display(v))}</dd>`)
        .join("")}</dl>`,
    );
    return;
  }
  if (action === "raw") {
    state.raw = !state.raw;
    renderOutputs();
    return;
  }
  if (action === "download") {
    const row = data.outputs.find((o) => o.id === outputIndex);
    const value = await api(`${query("output")}&id=${outputIndex}`);
    const url = URL.createObjectURL(
      new Blob([value.content], { type: "text/plain;charset=utf-8" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = row.path.split("/").at(-1) || "output.txt";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return;
  }
  if (runningAction) return;
  runningAction = true;
  const initiatingProject = selected;
  const actionButton = document.querySelector(`[data-action="${action}"]`);
  if (actionButton) {
    actionButton.disabled = true;
    actionButton.classList.add("busy");
  }
  toast(t("busy"));
  try {
    if (action === "save") await save();
    else if (["run", "resume"].includes(action)) {
      if (drafts[selected].dirty) await save();
      if (initiatingProject !== selected) throw Error(t("error"));
      await operate("run", {
        mode: action === "resume" ? "resume" : prefs.mode,
      });
      toast(t("starting"));
      await refreshStatus();
    } else if (action === "stop") {
      const r = await operate("stop");
      toast(message(r));
      await refreshStatus();
    } else if (action === "pull") {
      const target = $("#pull-name").value.trim();
      const r = await operate("pull", { target });
      toast(r.pid ? t("done") : formatResult(r));
    } else if (action === "delete") {
      const target = $("#delete-confirm").dataset.target;
      await operate("delete", {
        target,
        confirmation: $("#delete-confirm").value,
      });
      $("#panel").close();
      toast(t("done"));
    } else {
      const r = await operate(action);
      if (initiatingProject !== selected) return;
      if (action === "models") {
        installed = r.models || [];
        modelError = r.error || "";
      } else result = r;
      if (["discover", "profile"].includes(action)) {
        const updated = await api(query("workspace"));
        if (initiatingProject === selected) {
          data.recommendations = updated.recommendations;
          data.outputs = updated.outputs;
        }
      }
      if (action === "tests")
        openPanel(
          t("projectTests"),
          `<pre>${e(r.output || JSON.stringify(r, null, 2))}</pre>`,
        );
      else if (action === "health") toast(formatResult(r), !r.ok);
      else if (action !== "models") toast(formatResult(r));
      if (state.page === "settings") renderSettings();
    }
  } catch (err) {
    toast(err.message, true);
  } finally {
    runningAction = false;
    if (actionButton) {
      actionButton.disabled = false;
      actionButton.classList.remove("busy");
    }
    if (state.page === "dashboard") await refreshStatus();
  }
}
async function refreshStatus() {
  if (!selected || !data) return;
  const p = selected;
  try {
    const updated = await api(
      `${query("status")}&model=${encodeURIComponent(prefs.provider === "gemini" ? `gemini:${effectiveModel()}` : prefs.model)}`,
    );
    if (p !== selected) return;
    const wasActive = data.progress.run_active;
    Object.assign(data, updated);
    if (state.page === "dashboard") {
      $("#stage").textContent = localizedStage(data.progress.stage);
      $("#round").textContent = display(data.progress.round);
      $("#score").textContent = display(data.progress.best_score);
      $("#run-status").innerHTML =
        `<span class="dot"></span>${t(data.progress.run_active ? "active" : "idle")}`;
      const needsKey =
        prefs.provider === "gemini" && !apiKey && !boot.config.key_available;
      $('[data-action="run"]').disabled =
        data.progress.run_active ||
        needsKey ||
        !!(data.model_job?.pid && prefs.provider === "ollama");
      $('[data-action="resume"]').disabled =
        !data.resume.can_resume || needsKey;
      $('[data-action="stop"]').disabled =
        !data.progress.run_active || data.stop_requested;
    }
    if ($("#live-log"))
      $("#live-log").textContent =
        ($("#live-log").dataset.model === "true" ? data.model_log : data.log) ||
        t("noLogs");
    if (wasActive && !data.progress.run_active) {
      analysis = null;
      const w = await api(query("workspace"));
      if (p === selected) {
        data.outputs = w.outputs;
        if (state.page === "outputs") renderOutputs();
        if (state.page === "analytics") renderAnalytics();
      }
    }
  } catch {
    if ($("#run-status")) $("#run-status").textContent = t("offline");
  }
}
document.addEventListener("click", async (event) => {
  const node = event.target.closest("button,a");
  if (!node) return;
  if (node.dataset.nav || node.classList.contains("brand")) {
    event.preventDefault();
    state.page = node.dataset.nav || "dashboard";
    history.replaceState(null, "", `#${state.page}`);
    shell();
    window.scrollTo({ top: 0, behavior: "instant" });
    if (
      state.page === "settings" &&
      prefs.provider === "ollama" &&
      !installed.length
    )
      act("models");
    return;
  }
  if (node.dataset.action) {
    await act(node.dataset.action);
    return;
  }
  if (node.dataset.editor) {
    state.editor = node.dataset.editor;
    renderDashboard();
    return;
  }
  if (node.dataset.output) {
    outputIndex = Number(node.dataset.output);
    renderOutputs();
    return;
  }
  if (node.dataset.setting) {
    state.setting = node.dataset.setting;
    result = null;
    renderSettings();
    if (state.setting === "models" && !installed.length) act("models");
    return;
  }
  if (node.dataset.chart) {
    state.chart = node.dataset.chart;
    renderAnalytics();
    return;
  }
  if (node.dataset.delete) {
    const target = node.dataset.delete;
    openPanel(
      t("delete"),
      `<p class="help">${t("deleteHelp")}</p><p class="code">${e(target)}</p>${field("confirmDelete", `<input id="delete-confirm" data-target="${e(target)}" autocomplete="off">`)}<div class="actions">${button("delete", "delete", "danger")}${button("close", "cancel")}</div>`,
    );
  }
});
document.addEventListener("input", (event) => {
  const node = event.target;
  if (["editor", "large-editor"].includes(node.id)) {
    drafts[selected][state.editor] = node.value;
    drafts[selected].dirty =
      drafts[selected].task !== drafts[selected].savedTask ||
      drafts[selected].memory !== drafts[selected].savedMemory;
    if ($("#save-state"))
      $("#save-state").textContent = t(
        drafts[selected].dirty ? "unsaved" : "saved",
      );
    if (node.id === "large-editor" && $("#editor"))
      $("#editor").value = node.value;
  }
  if (node.id === "api-key") {
    apiKey = node.value;
    result = null;
  }
  if (node.dataset.pref && node.tagName === "INPUT") {
    prefs[node.dataset.pref] =
      node.type === "number" ? Number(node.value) : node.value;
    result = null;
  }
});
document.addEventListener("change", (event) => {
  const node = event.target;
  if (node.dataset.compare) {
    if (!comparisonSelection)
      comparisonSelection = new Set(
        analysis.comparison.map((row) => row.run_id),
      );
    if (node.checked) comparisonSelection.add(node.dataset.compare);
    else comparisonSelection.delete(node.dataset.compare);
    renderAnalytics();
    return;
  }
  if (node.id === "project") {
    loadProject(node.value);
    return;
  }
  if (node.dataset.pref) {
    prefs[node.dataset.pref] =
      node.type === "number" ? Number(node.value) : node.value;
    result = null;
    if (node.dataset.pref === "provider") {
      prefs.model =
        node.value === "gemini"
          ? boot.config.provider === "gemini"
            ? boot.config.model
            : boot.config.cloud_models[0]
          : boot.config.provider === "ollama"
            ? boot.config.model
            : "qwen3:8b";
      renderSettings();
      if (node.value === "ollama" && !installed.length) act("models");
    }
  }
});
$("#panel").addEventListener("click", (event) => {
  if (event.target === $("#panel")) {
    const r = $("#panel").getBoundingClientRect();
    if (
      event.clientX < r.left ||
      event.clientX > r.right ||
      event.clientY < r.top ||
      event.clientY > r.bottom
    )
      $("#panel").close();
  }
});
document.addEventListener("keydown", (event) => {
  if (
    event.target.dataset.editor &&
    ["ArrowLeft", "ArrowRight"].includes(event.key)
  ) {
    event.preventDefault();
    state.editor = state.editor === "task" ? "memory" : "task";
    renderDashboard();
    document.querySelector(`[data-editor="${state.editor}"]`).focus();
  }
});
window.addEventListener("beforeunload", (event) => {
  if (Object.values(drafts).some((d) => d.dirty)) {
    event.preventDefault();
    event.returnValue = "";
  }
});
async function init() {
  try {
    document.documentElement.dataset.theme = state.theme;
    boot = await api("/api/bootstrap");
    if (!boot.projects.length) {
      $("#app").innerHTML = `<div class="loading">${t("noProject")}</div>`;
      return;
    }
    prefs = {
      provider: boot.config.provider,
      model: boot.config.model,
      api_key_env: boot.config.api_key_env,
      drafting_mode: boot.config.drafting_mode,
      free_runner_preset: boot.config.free_runner_preset,
      mode: "normal",
      benchmark_preset: "free_smoke",
      max_provider_quota_failures: 2,
    };
    const page = location.hash.slice(1);
    if (["dashboard", "outputs", "analytics", "settings"].includes(page))
      state.page = page;
    await loadProject(
      boot.projects.includes(boot.config.project)
        ? boot.config.project
        : boot.projects[0],
    );
    setInterval(() => {
      if (!document.hidden && !runningAction) refreshStatus();
    }, 5000);
  } catch (err) {
    $("#app").innerHTML =
      `<div class="loading">${e(t("network"))}<p>${e(err.message)}</p></div>`;
  }
}
init();
