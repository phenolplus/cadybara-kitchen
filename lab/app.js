const DEFAULT_CONFIG = "configs/pilot_local.yaml";

const configInput = document.querySelector("#config-path");
const ollamaState = document.querySelector("#ollama-state");
const modelSummary = document.querySelector("#model-summary");
const pilotSummary = document.querySelector("#pilot-summary");
const modelDetailSummary = document.querySelector("#model-detail-summary");
const progressText = document.querySelector("#progress-text");
const progressPercent = document.querySelector("#progress-percent");
const progressFill = document.querySelector("#progress-fill");
const outputPath = document.querySelector("#output-path");
const startRun = document.querySelector("#start-run");
const stopRun = document.querySelector("#stop-run");
const runTitle = document.querySelector("#run-title");
const runExplain = document.querySelector("#run-explain");
const modeDry = document.querySelector("#mode-dry");
const modeReal = document.querySelector("#mode-real");
const modelList = document.querySelector("#model-list");
const runLog = document.querySelector("#run-log");
const modelLog = document.querySelector("#model-log");
const resultsSummary = document.querySelector("#results-summary");
const resultsList = document.querySelector("#results-list");
const reviewProducts = document.querySelector("#review-products");
const reviewPanel = document.querySelector("#review-panel");
const closeReview = document.querySelector("#close-review");
const reviewFrame = document.querySelector("#review-frame");
const reviewTitle = document.querySelector("#review-title");
const reviewSubtitle = document.querySelector("#review-subtitle");
const reviewPosition = document.querySelector("#review-position");
const reviewMeta = document.querySelector("#review-meta");
const scoreButtons = document.querySelector("#score-buttons");
const prevReview = document.querySelector("#prev-review");
const nextReview = document.querySelector("#next-review");
const reviewCode = document.querySelector("#review-code");
const codeStatus = document.querySelector("#code-status");
let latestExperiment = null;
let reviewItems = [];
let reviewIndex = 0;

let dryRun = false;
let lastStatus = null;

if (!configInput.value || configInput.value === "configs/example.yaml") {
  configInput.value = DEFAULT_CONFIG;
}

const statusUrl = () =>
  `/api/status?config=${encodeURIComponent(configInput.value || DEFAULT_CONFIG)}`;

const resultsUrl = () =>
  `/api/results?config=${encodeURIComponent(configInput.value || DEFAULT_CONFIG)}&dry_run=${
    dryRun ? "1" : "0"
  }&limit=20`;

const reviewUrl = () =>
  `/api/review?config=${encodeURIComponent(configInput.value || DEFAULT_CONFIG)}`;

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}

function setRunMode(nextDryRun) {
  dryRun = nextDryRun;
  modeDry.classList.toggle("active", dryRun);
  modeReal.classList.toggle("active", !dryRun);
  startRun.textContent = dryRun ? "Start Practice Run" : "Start Real Run";
  startRun.classList.toggle("real", !dryRun);
  renderExperimentProgress();
  refreshResults();
  updateStartState();
}

function modelCounts(models) {
  const total = models.length;
  const installed = models.filter((model) => model.status === "installed").length;
  const active = models.filter((model) => model.status === "pulling").length;
  return { total, installed, active };
}

function renderModels(models) {
  modelList.innerHTML = "";
  for (const model of models) {
    const percent =
      model.status === "installed"
        ? 100
        : model.percent === null || model.percent === undefined
          ? 0
          : model.percent;
    const card = document.createElement("div");
    card.className = "model-card";
    card.innerHTML = `
      <strong>${model.name}</strong>
      <span>${model.family} - ${model.role}</span>
      <span>${model.status}${model.message ? ` - ${model.message}` : ""}</span>
      <div class="bar"><div style="width:${percent}%"></div></div>
    `;
    modelList.appendChild(card);
  }
}

function renderLog(element, job) {
  element.textContent = `[${job.status}]\n${job.lines.join("\n")}`;
  element.scrollTop = element.scrollHeight;
}

function updateStartState() {
  if (!lastStatus) return;
  const runStatus = lastStatus.jobs.run.status;
  const ollamaReady = lastStatus.ollama.available;
  const disableForOllama = !dryRun && !ollamaReady;
  const runActive = runStatus === "running" || runStatus === "stopping";
  startRun.disabled = runActive || disableForOllama;
  stopRun.disabled = !runActive;
  if (runStatus === "running") {
    startRun.textContent = "Running...";
  } else if (runStatus === "stopping") {
    startRun.textContent = "Stopping after current...";
  } else if (disableForOllama) {
    startRun.textContent = "Ollama Missing";
  } else {
    startRun.textContent = dryRun ? "Start Practice Run" : "Start Real Run";
  }
}

function renderExperimentProgress() {
  if (!latestExperiment) return;
  const exp = latestExperiment;
  if (exp.config_error) {
    pilotSummary.textContent = "Config error";
    progressText.textContent = exp.config_error;
    progressPercent.textContent = "";
    progressFill.style.width = "0%";
    outputPath.textContent = "";
    return;
  }

  const selected = dryRun ? exp.practice : exp.real;
  const temps = (exp.temperatures || []).join(", ");
  const generationLabel = `${exp.seed_count} planter prompts x ${exp.model_count} models x ${exp.repetitions} reps; t=${temps}; ${exp.output_mode}`;
  runTitle.textContent = `Run ${exp.total_cells} generations`;
  runExplain.textContent = generationLabel;
  pilotSummary.textContent = `${exp.seed_count} planter prompts`;
  progressText.textContent = `${selected.valid_rows}/${exp.total_cells} ${dryRun ? "practice" : "real"} rows`;
  progressPercent.textContent = `${selected.complete_percent}%`;
  progressFill.style.width = `${selected.complete_percent}%`;
  outputPath.textContent = selected.output_path;
}

function renderResults(results) {
  if (!resultsSummary || !resultsList) return;
  resultsList.innerHTML = "";
  if (results.config_error) {
    resultsSummary.textContent = "Config error";
    const empty = document.createElement("p");
    empty.className = "empty-results";
    empty.textContent = results.config_error;
    resultsList.appendChild(empty);
    return;
  }

  resultsSummary.textContent = `${results.valid_rows} ${dryRun ? "practice" : "real"} row${
    results.valid_rows === 1 ? "" : "s"
  }`;
  if (reviewProducts) {
    reviewProducts.disabled = dryRun || results.valid_rows === 0;
  }
  if (results.rows.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-results";
    empty.textContent = dryRun
      ? "No practice outputs saved yet."
      : "No real outputs saved yet.";
    resultsList.appendChild(empty);
    return;
  }

  for (const row of results.rows) {
    const item = document.createElement("details");
    item.className = row.error ? "result-item error" : "result-item";
    const summary = document.createElement("summary");
    const title = document.createElement("span");
    title.textContent = `${row.provider} / ${row.model_name} / ${row.seed_id} / t=${row.temperature} / rep ${row.repetition}`;
    const meta = document.createElement("span");
    meta.textContent = row.error ? "error" : `${row.latency_ms} ms`;
    summary.append(title, meta);
    const prompt = document.createElement("p");
    prompt.className = "result-prompt";
    prompt.textContent = row.seed_text;
    const output = document.createElement("pre");
    output.textContent = row.error || row.output;
    item.append(summary, prompt, output);
    resultsList.appendChild(item);
  }
}

async function loadReviewItems() {
  const payload = await fetch(reviewUrl()).then((response) => response.json());
  reviewItems = (payload.items || []).filter((item) => item.error === null);
  reviewIndex = Math.min(reviewIndex, Math.max(reviewItems.length - 1, 0));
  return payload;
}

function renderScoreButtons(item) {
  scoreButtons.innerHTML = "";
  const activeScore = item.review?.score;
  for (let score = 1; score <= 10; score += 1) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = String(score);
    button.classList.toggle("active", activeScore === score);
    button.addEventListener("click", () => saveScore(score));
    scoreButtons.appendChild(button);
  }
}

async function renderReview() {
  if (!reviewPanel || reviewItems.length === 0) return;
  const item = reviewItems[reviewIndex];
  reviewPosition.textContent = `${reviewIndex + 1} / ${reviewItems.length}`;
  reviewTitle.textContent = `${item.model_name} / ${item.seed_id}`;
  reviewSubtitle.textContent = `t=${item.temperature} / rep ${item.repetition} / ${item.provider}`;
  prevReview.disabled = reviewIndex === 0;
  nextReview.disabled = reviewIndex >= reviewItems.length - 1;

  reviewMeta.innerHTML = "";
  const fields = [
    ["Condition", item.condition_name || "unknown"],
    ["Latency", `${item.latency_ms} ms`],
    ["Tokens", `${item.prompt_tokens ?? "?"} in / ${item.completion_tokens ?? "?"} out`],
    ["Render", item.render_error ? "failed; code is still saved" : "STL ready"],
    ["Score", item.review?.score ? `${item.review.score}/10` : "not scored"],
  ];
  for (const [label, value] of fields) {
    const row = document.createElement("div");
    const strong = document.createElement("strong");
    strong.textContent = label;
    row.append(strong, `: ${value}`);
    reviewMeta.appendChild(row);
  }

  if (item.viewer_url) {
    reviewFrame.src = item.viewer_url;
  } else {
    reviewFrame.removeAttribute("src");
  }
  renderScoreButtons(item);

  reviewCode.textContent = "";
  codeStatus.textContent = item.code_url ? "Loading" : "No code";
  if (item.code_url) {
    try {
      reviewCode.textContent = await fetch(item.code_url).then((response) => response.text());
      codeStatus.textContent = "Saved";
    } catch (error) {
      reviewCode.textContent = String(error);
      codeStatus.textContent = "Error";
    }
  }
}

async function openReview() {
  await loadReviewItems();
  reviewPanel.classList.remove("hidden");
  if (reviewItems.length === 0) {
    reviewTitle.textContent = "No products ready yet";
    reviewSubtitle.textContent = "Run CAD generation first.";
    reviewPosition.textContent = "0 / 0";
    reviewMeta.textContent = "";
    scoreButtons.innerHTML = "";
    reviewCode.textContent = "";
    return;
  }
  await renderReview();
  reviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function saveScore(score) {
  const item = reviewItems[reviewIndex];
  if (!item) return;
  await postJson("/api/review/score", {
    config_path: configInput.value || DEFAULT_CONFIG,
    run_id: item.run_id,
    score,
  });
  await loadReviewItems();
  await renderReview();
}

async function moveReview(delta) {
  if (reviewItems.length === 0) return;
  reviewIndex = Math.max(0, Math.min(reviewItems.length - 1, reviewIndex + delta));
  await renderReview();
}

async function refreshResults() {
  if (!resultsSummary || !resultsList) return;
  try {
    const results = await fetch(resultsUrl()).then((response) => response.json());
    renderResults(results);
  } catch (error) {
    resultsSummary.textContent = "Unavailable";
    resultsList.innerHTML = "";
    const empty = document.createElement("p");
    empty.className = "empty-results";
    empty.textContent = String(error);
    resultsList.appendChild(empty);
  }
}

async function refresh() {
  const data = await fetch(statusUrl()).then((response) => response.json());
  lastStatus = data;

  const ollama = data.ollama;
  ollamaState.textContent = ollama.available ? "Ready" : "Missing";

  const counts = modelCounts(data.models);
  modelSummary.textContent =
    counts.installed === counts.total
      ? `${counts.installed}/${counts.total} ready`
      : `${counts.installed}/${counts.total} ready`;
  modelDetailSummary.textContent =
    counts.active > 0 ? `${counts.active} downloading` : "Show installed models";

  const exp = data.experiment;
  latestExperiment = exp;
  renderExperimentProgress();

  renderModels(data.models);
  renderLog(runLog, data.jobs.run);
  renderLog(modelLog, data.jobs.models);
  await refreshResults();
  updateStartState();
}

modeDry.addEventListener("click", () => setRunMode(true));
modeReal.addEventListener("click", () => setRunMode(false));
reviewProducts?.addEventListener("click", openReview);
closeReview?.addEventListener("click", () => reviewPanel.classList.add("hidden"));
prevReview?.addEventListener("click", () => moveReview(-1));
nextReview?.addEventListener("click", () => moveReview(1));
window.addEventListener("keydown", (event) => {
  if (!reviewPanel || reviewPanel.classList.contains("hidden")) return;
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    moveReview(-1);
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    moveReview(1);
  } else if (/^[0-9]$/.test(event.key)) {
    event.preventDefault();
    saveScore(event.key === "0" ? 10 : Number(event.key));
  }
});
document.querySelector("#refresh").addEventListener("click", refresh);
document.querySelector("#pull-one").addEventListener("click", async () => {
  await postJson("/api/models/start", { limit: 1 });
  await refresh();
});
document.querySelector("#pull-all").addEventListener("click", async () => {
  await postJson("/api/models/start", {});
  await refresh();
});
startRun.addEventListener("click", async () => {
  await postJson("/api/run/start", {
    config_path: configInput.value || DEFAULT_CONFIG,
    dry_run: dryRun,
  });
  await refresh();
});
stopRun.addEventListener("click", async () => {
  stopRun.disabled = true;
  stopRun.textContent = "Stop Requested";
  await postJson("/api/run/stop", {});
  await refresh();
  stopRun.textContent = "Stop After Current";
});
configInput.addEventListener("change", refresh);

setRunMode(false);
setInterval(refresh, 1500);
refresh();
