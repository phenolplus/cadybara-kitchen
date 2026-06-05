const DEFAULT_CONFIG = "projects/cadybara-online-testing/configs/online_smoke.yaml";
const query = new URLSearchParams(window.location.search);
const CONFIG_PATH = query.get("config") || DEFAULT_CONFIG;

const CONCEPTS = [
  {
    id: "pixel",
    label: "Pixel Crew",
    titleMain: "your favorite",
    titleAccent: "cad capybaras",
    note: "Flatter 2D pixel capybaras sprinting, welding, measuring, and building CAD planters.",
  },
  {
    id: "atelier",
    label: "Original Atelier",
    titleMain: "your favorite",
    titleAccent: "cad engineer",
    note: "The first loved AI CAD studio image, saved intact for reuse.",
  },
  {
    id: "voxel",
    label: "Voxel Crew",
    titleMain: "tiny builders",
    titleAccent: "big prototypes",
    note: "Busier capybara fabrication scene with deeper 3D block energy.",
  },
  {
    id: "blueprint",
    label: "Blueprint Sky",
    titleMain: "prompt sweeps",
    titleAccent: "made visible",
    note: "Cool cyan technical-overlay pass for a more engineering-first read.",
  },
  {
    id: "night",
    label: "Night Forge",
    titleMain: "overnight runs",
    titleAccent: "stay glowing",
    note: "Darker workshop mood with warm sparks and stronger contrast.",
  },
  {
    id: "whiteprint",
    label: "Whiteprint",
    titleMain: "clean cad",
    titleAccent: "clear results",
    note: "Bright product-lab treatment for a lighter, more polished SaaS feel.",
  },
  {
    id: "garden",
    label: "Bio Lab",
    titleMain: "living cad",
    titleAccent: "local models",
    note: "Small CAD-code smoke run for online Cadybara testing.",
  },
  {
    id: "console",
    label: "Terminal",
    titleMain: "append-only",
    titleAccent: "research runs",
    note: "Darker hacker-lab mode for long local experiments.",
  },
];

const dom = {
  heroTitleMain: document.querySelector("#hero-title-main"),
  heroTitleAccent: document.querySelector("#hero-title-accent"),
  conceptName: document.querySelector("#concept-name"),
  conceptNote: document.querySelector("#concept-note"),
  conceptSwitcher: document.querySelector("#concept-switcher"),
  experimentName: document.querySelector("#experiment-name"),
  experimentLine: document.querySelector("#experiment-line"),
  elapsed: document.querySelector("#elapsed"),
  eta: document.querySelector("#eta"),
  progressPercent: document.querySelector("#progress-percent"),
  overallProgress: document.querySelector("#overall-progress"),
  queueLine: document.querySelector("#queue-line"),
  outputPath: document.querySelector("#output-path"),
  startRun: document.querySelector("#start-run"),
  stopRun: document.querySelector("#stop-run"),
  refreshButton: document.querySelector("#refresh"),
  pullNext: document.querySelector("#pull-next"),
  pullAll: document.querySelector("#pull-all"),
  modelSummary: document.querySelector("#model-summary"),
  modelSummaryPanel: document.querySelector("#model-summary-panel"),
  modelGrid: document.querySelector("#model-grid"),
  installPanel: document.querySelector("#install-panel"),
  installSummary: document.querySelector("#install-summary"),
  installProgress: document.querySelector("#install-progress"),
  installDetail: document.querySelector("#install-detail"),
  snapshotCell: document.querySelector("#snapshot-cell"),
  promptText: document.querySelector("#prompt-text"),
  promptSize: document.querySelector("#prompt-size"),
  snapshotMeta: document.querySelector("#snapshot-meta"),
  snapshotLines: document.querySelector("#snapshot-lines"),
  snapshotFooter: document.querySelector("#snapshot-footer"),
  rendersSummary: document.querySelector("#renders-summary"),
  renderGrid: document.querySelector("#render-grid"),
  metricCells: document.querySelector("#metric-cells"),
  metricCellsNote: document.querySelector("#metric-cells-note"),
  metricFailures: document.querySelector("#metric-failures"),
  metricFailuresNote: document.querySelector("#metric-failures-note"),
  metricRenders: document.querySelector("#metric-renders"),
  metricRendersNote: document.querySelector("#metric-renders-note"),
  metricReview: document.querySelector("#metric-review"),
  metricReviewNote: document.querySelector("#metric-review-note"),
  resultsSummary: document.querySelector("#results-summary"),
  attemptList: document.querySelector("#attempt-list"),
  reviewCounter: document.querySelector("#review-counter"),
  reviewViewer: document.querySelector("#review-viewer"),
  reviewEmpty: document.querySelector("#review-empty"),
  reviewName: document.querySelector("#review-name"),
  reviewMeta: document.querySelector("#review-meta"),
  scoreRow: document.querySelector("#score-row"),
  reviewPrev: document.querySelector("#review-prev"),
  reviewNext: document.querySelector("#review-next"),
  reviewCode: document.querySelector("#review-code"),
  runLog: document.querySelector("#run-log"),
  modelLog: document.querySelector("#model-log"),
  logStatus: document.querySelector("#log-status"),
  gradeCommand: document.querySelector("#grade-command"),
  inspectCommand: document.querySelector("#inspect-command"),
};

const appState = {
  runStatus: null,
  modelStatus: null,
  results: null,
  review: null,
  reviewItems: [],
  selectedReviewIndex: 0,
  resultFilter: "all",
  selectedConcept: null,
  installByName: new Map(),
};

let statusTimer = null;
let snapshotTimer = null;
let resultsTimer = null;

function buildUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, value);
    }
  }
  return url;
}

async function getJson(path, params = {}) {
  const response = await fetch(buildUrl(path, params));
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `GET ${path} failed with ${response.status}`);
  }
  return payload;
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok && response.status !== 409) {
    throw new Error(data.error || `POST ${path} failed with ${response.status}`);
  }
  return data;
}

function clear(element) {
  while (element.firstChild) {
    element.firstChild.remove();
  }
}

function node(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = text;
  return element;
}

function setText(element, value) {
  if (!element) return;
  element.textContent = value ?? "";
}

function conceptById(id) {
  return CONCEPTS.find((concept) => concept.id === id) || CONCEPTS[0];
}

function conceptUrl(id) {
  const next = new URL(window.location.href);
  next.searchParams.set("concept", id);
  return next;
}

function applyConcept(id, { push = false } = {}) {
  const concept = conceptById(id);
  appState.selectedConcept = concept.id;
  document.body.dataset.concept = concept.id;
  setText(dom.heroTitleMain, concept.titleMain);
  setText(dom.heroTitleAccent, concept.titleAccent);
  setText(dom.conceptName, concept.label);
  setText(dom.conceptNote, concept.note);

  document.querySelectorAll(".concept-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.concept === concept.id);
  });

  if (push) {
    window.history.replaceState({}, "", conceptUrl(concept.id));
  }
}

function renderConceptSwitcher() {
  if (!dom.conceptSwitcher) return;
  clear(dom.conceptSwitcher);
  for (const concept of CONCEPTS) {
    const button = node("button", "concept-button");
    button.type = "button";
    button.dataset.concept = concept.id;
    const label = node("strong", "", concept.label);
    const hint = node("span", "", concept.note);
    button.append(label, hint);
    button.addEventListener("click", () => applyConcept(concept.id, { push: true }));
    dom.conceptSwitcher.appendChild(button);
  }
  applyConcept(query.get("concept") || "pixel");
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Math.round((value || 0) * 100)));
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "pending";
  const rounded = Math.max(0, Math.round(seconds));
  if (rounded < 60) return `${rounded}s`;
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatMs(ms) {
  if (ms === null || ms === undefined) return "pending";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function displayName(value, fallback = "unknown") {
  if (!value) return fallback;
  return String(value).replaceAll("_", " ");
}

function normalizePath(path) {
  return String(path || "").replaceAll("\\", "/");
}

function assetUrl(path) {
  const normalized = normalizePath(path);
  if (!normalized) return "";
  if (normalized.startsWith("http://") || normalized.startsWith("https://")) return normalized;
  if (normalized.startsWith("/")) return normalized;
  return `/${normalized}`;
}

function compactInstallMessage(message) {
  return (message || "")
    .replaceAll("pulling manifest", "")
    .replace(/\s+/g, " ")
    .replace(/(\d)([smh])(\d)/g, "$1$2 $3")
    .trim();
}

function currentMode() {
  return document.querySelector("input[name='run-mode']:checked")?.value || "real";
}

function familyColor(family) {
  const colors = {
    "qwen3-vl": "#156f66",
    "llama3.2-vision": "#5c7f3b",
    "qwen2.5-vl": "#9a7625",
    llava: "#b45363",
    gemma3: "#6d7337",
    mistral: "#8a623e",
    "qwen-coder": "#156f66",
    "deepseek-coder": "#8c5f8f",
    starcoder2: "#b45363",
  };
  return colors[family] || "#2e8f83";
}

function installLabel(install) {
  if (!install) return "not queued";
  if (install.status === "installed") return "installed";
  if (install.status === "pulling") {
    const gb = install.downloaded_gb && install.total_gb ? ` ${install.downloaded_gb}/${install.total_gb} GB` : "";
    return `pulling ${install.percent ?? 0}%${gb}`;
  }
  if (install.status === "error") return "pull error";
  if (install.status === "skipped") return "skipped";
  return "pending";
}

function renderMetrics() {
  const progress = appState.runStatus?.progress || {};
  const total = progress.total_cells || appState.runStatus?.condition_count || 0;
  const executed = progress.executed_cells || 0;
  const completed = progress.completed_cells || 0;
  const failed = progress.failed_cells || 0;
  const queued = progress.queued_cells || 0;
  const renders = appState.runStatus?.recent_renders?.length || 0;
  const review = appState.review || {};

  setText(dom.metricCells, `${executed} / ${total}`);
  setText(dom.metricCellsNote, `${completed} completed | ${queued} queued`);
  setText(dom.metricFailures, String(failed));
  setText(dom.metricFailuresNote, failed ? "needs inspection" : "clean so far");
  setText(dom.metricRenders, String(renders));
  setText(dom.metricRendersNote, renders ? "latest products available" : "waiting for STL/PNG");
  setText(dom.metricReview, `${review.reviewed_rows || 0} / ${review.renderable_rows || 0}`);
  setText(dom.metricReviewNote, `${review.render_failed_rows || 0} render failures`);
}

function renderStatus() {
  const status = appState.runStatus || {};
  const modelStatus = appState.modelStatus || {};
  const progress = status.progress || {};
  const job = modelStatus.jobs?.run || status.job || { status: "idle", lines: [] };
  const jobStatus = job.status || "idle";
  const weighted = clampPercent(progress.weighted_progress);
  const runActive = status.models?.some((model) => model.status === "running") || jobStatus === "running";
  const runWaiting = jobStatus === "waiting";
  const lastLine = job.lines?.[job.lines.length - 1];

  setText(dom.experimentName, displayName(status.experiment_id, "Wall planter sweep"));
  setText(
    dom.experimentLine,
    `${status.model_count || 0} models | ${status.prompt_count || 0} prompts | ${status.repetitions || 0} reps | ${status.condition_count || 0} cells`,
  );
  setText(dom.elapsed, `elapsed ${formatDuration(status.elapsed_seconds || 0)}`);
  setText(dom.eta, `eta ${formatDuration(progress.eta_seconds)}`);
  setText(dom.progressPercent, `${weighted}%`);
  dom.overallProgress.style.width = `${weighted}%`;
  setText(
    dom.queueLine,
    ["error", "waiting", "stopping"].includes(jobStatus) && lastLine
      ? lastLine
      : `executed ${progress.executed_cells || 0} | failed ${progress.failed_cells || 0} | queued ${progress.queued_cells || 0}`,
  );
  setText(
    dom.outputPath,
    `projects/cadybara-online-testing/workspace/runs/${status.experiment_id || "..."}/results.jsonl`,
  );
  setText(dom.modelSummary, `${weighted}% weighted | ${jobStatus}`);
  setText(dom.modelSummaryPanel, `${weighted}% weighted | ${jobStatus}`);

  dom.startRun.disabled = runActive || runWaiting;
  dom.startRun.querySelector("span").textContent = runActive ? "Running" : runWaiting ? "Queued" : "Start";
  dom.stopRun.disabled = !runActive;

  if (status.experiment_id) {
    setText(dom.gradeCommand, `cadybara grade projects/cadybara-online-testing/workspace/runs/${status.experiment_id}/`);
    setText(
      dom.inspectCommand,
      `cadybara inspect projects/cadybara-online-testing/workspace/runs/${status.experiment_id}/results.jsonl`,
    );
  }

  renderInstallPanel();
  renderModels(status.models || []);
  renderRenders(status.recent_renders || []);
  renderLogs();
  renderMetrics();
}

function renderInstallPanel() {
  const runModels = appState.runStatus?.models || [];
  const allInstalls = appState.modelStatus?.models || [];
  const requiredNames = new Set(runModels.map((model) => model.name));
  const installs = allInstalls.filter((model) => requiredNames.size === 0 || requiredNames.has(model.name));
  const modelJob = appState.modelStatus?.jobs?.models || { status: "idle", lines: [] };
  appState.installByName = new Map(installs.map((model) => [model.name, model]));

  if (installs.length === 0) {
    setText(dom.installSummary, "no models");
    setText(dom.installDetail, "No Ollama model queue is available for this config.");
    dom.installProgress.style.width = "0%";
    dom.pullNext.disabled = true;
    dom.pullAll.disabled = true;
    return;
  }

  const installed = installs.filter((model) => model.status === "installed").length;
  const pulling = installs.find((model) => model.status === "pulling");
  const errors = installs.filter((model) => model.status === "error").length;
  const pending = installs.filter((model) => !["installed", "error"].includes(model.status)).length;
  const estimatedTotal = installs.reduce((sum, model) => sum + (model.estimated_size_gb || 0), 0);
  const estimatedDone = installs.reduce((sum, model) => {
    if (model.status === "installed") return sum + (model.estimated_size_gb || 0);
    if (model.status === "pulling") {
      return sum + ((model.estimated_size_gb || 0) * ((model.percent || 0) / 100));
    }
    return sum;
  }, 0);
  const countPercent = installs.length ? (installed / installs.length) * 100 : 0;
  const sizePercent = estimatedTotal > 0 ? (estimatedDone / estimatedTotal) * 100 : countPercent;
  const percent = Math.max(0, Math.min(100, Math.round(sizePercent)));
  const modelJobRunning = modelJob.status === "running";
  const ollamaAvailable = appState.modelStatus?.ollama?.available !== false;

  dom.installProgress.style.width = `${percent}%`;
  setText(dom.installSummary, `${installed}/${installs.length} installed${errors ? ` | ${errors} errors` : ""}`);

  if (!ollamaAvailable) {
    setText(dom.installDetail, "Ollama is not available on PATH for this lab server.");
  } else if (pulling) {
    const detail = compactInstallMessage(pulling.message);
    const gb = pulling.downloaded_gb && pulling.total_gb ? ` | ${pulling.downloaded_gb}/${pulling.total_gb} GB` : "";
    const fresh = pulling.last_event_at ? ` | saved ${pulling.last_event_at}` : "";
    setText(dom.installDetail, `${pulling.name}: ${pulling.percent ?? 0}%${gb}${detail ? ` | ${detail}` : ""}${fresh}`);
  } else if (modelJob.status === "done" && pending === 0) {
    setText(dom.installDetail, "All required models are installed.");
  } else {
    const lastLine = modelJob.lines?.[modelJob.lines.length - 1];
    setText(dom.installDetail, lastLine || "No model is currently downloading.");
  }

  dom.pullNext.disabled = modelJobRunning || !ollamaAvailable || installed === installs.length;
  dom.pullAll.disabled = modelJobRunning || !ollamaAvailable || installed === installs.length;
}

function renderModels(models) {
  clear(dom.modelGrid);
  if (models.length === 0) {
    dom.modelGrid.appendChild(node("div", "empty-state", "No model rows are available yet."));
    return;
  }

  for (const model of models) {
    const install = appState.installByName.get(model.name);
    const row = node("article", "model-row");
    const main = node("div", "model-main");
    const title = node("div", "model-title");
    const dot = node("span", "family-dot");
    const name = node("strong", "", model.name);
    const meta = node("div", "model-meta");
    const status = node("span", `status-pill ${model.status || "queued"}`, model.status || "queued");
    const cells = node("span", "", `${model.completed || 0}/${model.total || 0} ok, ${model.failed || 0} failed`);
    const family = node("span", "", model.family || "family unknown");
    const current = node("span", "", model.current_cell || `${Math.round((model.progress || 0) * 100)}%`);
    const side = node("div", "model-side");
    const chip = node("span", `install-chip ${install?.status || "unknown"}`, installLabel(install));
    const bar = node("div", "tiny-bar");
    const fill = node("div");

    dot.style.background = familyColor(model.family);
    fill.style.width = `${clampPercent(model.progress)}%`;
    title.append(dot, name);
    meta.append(status, cells, family, current);
    main.append(title, meta);
    bar.appendChild(fill);
    side.append(chip, bar);
    row.append(main, side);
    dom.modelGrid.appendChild(row);
  }
}

function renderRenders(renders) {
  clear(dom.renderGrid);
  setText(dom.rendersSummary, renders?.length ? `${renders.length} latest` : "waiting");
  if (!renders || renders.length === 0) {
    dom.renderGrid.appendChild(node("div", "empty-state", "Renders appear here when CadQuery exports an STL or preview PNG."));
    return;
  }

  for (const render of renders) {
    const link = node("a", "render-card");
    link.href = render.viewer_url || assetUrl(render.preview_png || render.stl);
    const media = render.preview_png
      ? node("img", "render-image")
      : node("div", "render-thumb", "stl");
    if (render.preview_png) {
      media.src = assetUrl(render.preview_png);
      media.alt = "";
      media.loading = "lazy";
    }
    const title = node("strong", "", render.prompt_id || "prompt");
    const model = node("span", "", render.model_name || "model");
    const rep = node(
      "span",
      "",
      `rep ${render.repetition ?? 0}${render.repair_round ? ` | round ${render.repair_round}` : ""}`,
    );
    link.append(media, title, model, rep);
    dom.renderGrid.appendChild(link);
  }
}

function renderSnapshot(snapshot) {
  if (!snapshot?.is_running) {
    setText(dom.snapshotCell, "idle");
    setText(dom.promptText, "No generation is running.");
    setText(dom.promptSize, "0 chars");
    setText(dom.snapshotMeta, "0 tokens");
    setText(dom.snapshotLines, "idle");
    setText(dom.snapshotFooter, "updated when a model is running");
    return;
  }

  let cell = `${snapshot.model_name} | ${snapshot.prompt_id} | rep ${snapshot.repetition}`;
  if (snapshot.repair_round) {
    cell += ` | round ${snapshot.repair_round}/${snapshot.repair_total_rounds}`;
  }
  setText(dom.snapshotCell, cell);
  setText(dom.promptText, snapshot.prompt_text || "");
  setText(dom.promptSize, `${(snapshot.prompt_text || "").length} chars`);
  setText(dom.snapshotMeta, `${snapshot.tokens_so_far || 0} tokens`);
  setText(dom.snapshotLines, (snapshot.last_lines || []).join("\n") || "...");
  setText(
    dom.snapshotFooter,
    `elapsed ${formatDuration(snapshot.elapsed_seconds)} | last update ${snapshot.snapshot_age_seconds}s ago`,
  );
}

function renderResults() {
  const results = appState.results;
  clear(dom.attemptList);
  if (!results) {
    setText(dom.resultsSummary, "waiting");
    return;
  }

  const mode = currentMode();
  const rows = results.rows || [];
  const filtered = rows.filter((row) => {
    if (appState.resultFilter === "renderable") return row.is_renderable;
    if (appState.resultFilter === "failed") return row.error || row.render_error;
    return true;
  });
  setText(
    dom.resultsSummary,
    `${filtered.length}/${rows.length} ${mode} rows | ${results.malformed_rows || 0} malformed`,
  );

  if (filtered.length === 0) {
    dom.attemptList.appendChild(node("div", "empty-state", "No attempts match this filter."));
    return;
  }

  for (const row of filtered) {
    const failed = Boolean(row.error || row.render_error);
    const stateClass = row.is_renderable ? "renderable" : failed ? "failed" : "pending";
    const stateText = row.is_renderable ? "rendered" : failed ? "failed" : "saved";
    const article = node("article", "attempt-row");
    const main = node("div", "attempt-main");
    const heading = node("strong", "", `${row.seed_id || "prompt"} | ${row.model_name || "model"}`);
    const meta = node(
      "span",
      "",
      `seq ${row.sequence} | rep ${row.repetition} | attempt ${row.attempt} | t ${row.temperature ?? "?"} | ${formatMs(row.latency_ms)}`,
    );
    const detail = node("div", "attempt-detail");
    const issue = row.error || row.render_error;
    const output = (row.output || "").replace(/\s+/g, " ").trim();
    detail.textContent = issue || (output ? output.slice(0, 180) : "empty output");
    const side = node("div", "attempt-side");
    const state = node("span", `row-state ${stateClass}`, stateText);
    const provider = node("span", "", row.provider || "");

    main.append(heading, meta, detail);
    side.append(state, provider);
    article.append(main, side);
    dom.attemptList.appendChild(article);
  }
}

function renderScoreButtons(selectedItem) {
  clear(dom.scoreRow);
  const selectedScore = selectedItem?.review?.score;
  for (let value = 1; value <= 10; value += 1) {
    const button = node("button", selectedScore === value ? "active" : "", String(value));
    button.type = "button";
    button.disabled = !selectedItem;
    button.addEventListener("click", () => scoreSelected(value));
    dom.scoreRow.appendChild(button);
  }
}

function selectedReviewItem() {
  return appState.reviewItems[appState.selectedReviewIndex] || null;
}

function renderReview() {
  const review = appState.review;
  appState.reviewItems = (review?.items || []).filter((item) => item.is_renderable);
  if (appState.selectedReviewIndex >= appState.reviewItems.length) {
    appState.selectedReviewIndex = Math.max(0, appState.reviewItems.length - 1);
  }
  const item = selectedReviewItem();
  const count = appState.reviewItems.length;
  const position = count && item ? appState.selectedReviewIndex + 1 : 0;

  setText(dom.reviewCounter, `${position} / ${count}`);
  renderMetrics();

  if (!item) {
    dom.reviewViewer.classList.add("is-hidden");
    dom.reviewEmpty.classList.remove("is-hidden");
    dom.reviewViewer.removeAttribute("src");
    setText(dom.reviewName, "No product selected");
    setText(dom.reviewMeta, review ? `${review.render_failed_rows || 0} render failures in the run` : "Waiting for review data.");
    dom.reviewCode.href = "#";
    dom.reviewCode.classList.add("is-hidden");
    dom.reviewPrev.disabled = true;
    dom.reviewNext.disabled = true;
    renderScoreButtons(null);
    return;
  }

  dom.reviewViewer.classList.remove("is-hidden");
  dom.reviewEmpty.classList.add("is-hidden");
  if (dom.reviewViewer.getAttribute("src") !== item.viewer_url) {
    dom.reviewViewer.src = item.viewer_url;
  }
  setText(dom.reviewName, `${item.seed_id} | ${item.model_name}`);
  setText(
    dom.reviewMeta,
    `rep ${item.repetition} | attempt ${item.attempt} | ${formatMs(item.latency_ms)}${item.review ? ` | score ${item.review.score}` : ""}`,
  );
  dom.reviewCode.href = item.code_url || "#";
  dom.reviewCode.classList.toggle("is-hidden", !item.code_url);
  dom.reviewPrev.disabled = count < 2;
  dom.reviewNext.disabled = count < 2;
  renderScoreButtons(item);
}

function renderLogs() {
  const runJob = appState.modelStatus?.jobs?.run || { status: "idle", lines: [] };
  const modelJob = appState.modelStatus?.jobs?.models || { status: "idle", lines: [] };
  setText(dom.logStatus, `run ${runJob.status || "idle"} | models ${modelJob.status || "idle"}`);
  setText(dom.runLog, runJob.lines?.length ? runJob.lines.join("\n") : "run log idle");
  setText(dom.modelLog, modelJob.lines?.length ? modelJob.lines.join("\n") : "model log idle");
}

async function refreshStatus() {
  const [runStatus, modelStatus] = await Promise.all([
    getJson("/api/run_status", { config: CONFIG_PATH }),
    getJson("/api/status", { config: CONFIG_PATH }),
  ]);
  appState.runStatus = runStatus;
  appState.modelStatus = modelStatus;
  renderStatus();
}

async function refreshSnapshot() {
  const snapshot = await getJson("/api/current_snapshot");
  renderSnapshot(snapshot);
}

async function refreshResultsAndReview() {
  const dryRun = currentMode() === "practice";
  const [results, review] = await Promise.all([
    getJson("/api/results", { config: CONFIG_PATH, dry_run: String(dryRun), limit: "40" }),
    getJson("/api/review", { config: CONFIG_PATH }),
  ]);
  appState.results = results;
  appState.review = review;
  renderResults();
  renderReview();
}

async function refreshAll() {
  dom.refreshButton.disabled = true;
  const results = await Promise.allSettled([refreshStatus(), refreshSnapshot(), refreshResultsAndReview()]);
  const rejected = results.find((result) => result.status === "rejected");
  if (rejected) {
    setText(dom.logStatus, `error: ${rejected.reason.message}`);
  }
  dom.refreshButton.disabled = false;
}

async function scoreSelected(score) {
  const item = selectedReviewItem();
  if (!item) return;
  await postJson("/api/review/score", {
    config_path: CONFIG_PATH,
    run_id: item.run_id,
    score,
  });
  await refreshResultsAndReview();
}

function startPolling() {
  window.clearInterval(statusTimer);
  window.clearInterval(snapshotTimer);
  window.clearInterval(resultsTimer);
  statusTimer = window.setInterval(() => refreshStatus().catch((error) => setText(dom.logStatus, `error: ${error.message}`)), 5000);
  snapshotTimer = window.setInterval(() => refreshSnapshot().catch(() => {}), 2000);
  resultsTimer = window.setInterval(() => refreshResultsAndReview().catch(() => {}), 12000);
}

dom.startRun.addEventListener("click", async () => {
  dom.startRun.disabled = true;
  try {
    await postJson("/api/run/start", {
      config_path: CONFIG_PATH,
      dry_run: currentMode() === "practice",
    });
    await refreshAll();
  } finally {
    renderStatus();
  }
});

dom.stopRun.addEventListener("click", async () => {
  await postJson("/api/run/stop", {});
  await refreshStatus();
});

dom.pullNext.addEventListener("click", async () => {
  await postJson("/api/models/start", { config_path: CONFIG_PATH, limit: 1 });
  await refreshStatus();
});

dom.pullAll.addEventListener("click", async () => {
  await postJson("/api/models/start", { config_path: CONFIG_PATH });
  await refreshStatus();
});

dom.refreshButton.addEventListener("click", refreshAll);

document.querySelectorAll("input[name='run-mode']").forEach((input) => {
  input.addEventListener("change", () => {
    refreshResultsAndReview().catch((error) => setText(dom.logStatus, `error: ${error.message}`));
  });
});

document.querySelectorAll(".filter").forEach((button) => {
  button.addEventListener("click", () => {
    appState.resultFilter = button.dataset.filter || "all";
    document.querySelectorAll(".filter").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    renderResults();
  });
});

dom.reviewPrev.addEventListener("click", () => {
  if (appState.reviewItems.length === 0) return;
  appState.selectedReviewIndex =
    (appState.selectedReviewIndex - 1 + appState.reviewItems.length) % appState.reviewItems.length;
  renderReview();
});

dom.reviewNext.addEventListener("click", () => {
  if (appState.reviewItems.length === 0) return;
  appState.selectedReviewIndex = (appState.selectedReviewIndex + 1) % appState.reviewItems.length;
  renderReview();
});

document.addEventListener("keydown", (event) => {
  const target = event.target;
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return;
  if (!selectedReviewItem()) return;
  if (/^[1-9]$/.test(event.key)) {
    scoreSelected(Number(event.key));
  } else if (event.key === "0") {
    scoreSelected(10);
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    window.clearInterval(statusTimer);
    window.clearInterval(snapshotTimer);
    window.clearInterval(resultsTimer);
    return;
  }
  startPolling();
  refreshAll();
});

renderConceptSwitcher();
renderScoreButtons(null);
startPolling();
refreshAll();
