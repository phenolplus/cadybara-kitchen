const dom = {
  refresh: document.querySelector("#refresh"),
  start: document.querySelector("#start-train"),
  stop: document.querySelector("#stop-train"),
  statusLabel: document.querySelector("#status-label"),
  statusLine: document.querySelector("#status-line"),
  devicePill: document.querySelector("#device-pill"),
  examples: document.querySelector("#metric-examples"),
  test: document.querySelector("#metric-test"),
  step: document.querySelector("#metric-step"),
  target: document.querySelector("#metric-target"),
  elapsed: document.querySelector("#metric-elapsed"),
  loss: document.querySelector("#metric-loss"),
  checkpoint: document.querySelector("#metric-checkpoint"),
  modelDir: document.querySelector("#metric-model-dir"),
  progressSummary: document.querySelector("#progress-summary"),
  progressPercent: document.querySelector("#progress-percent"),
  progressFill: document.querySelector("#progress-fill"),
  readinessDataset: document.querySelector("#readiness-dataset"),
  readinessGrammar: document.querySelector("#readiness-grammar"),
  readinessTorch: document.querySelector("#readiness-torch"),
  readinessDefaults: document.querySelector("#readiness-defaults"),
  log: document.querySelector("#train-log"),
};

let statusTimer = null;

async function getJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function postJson(path, payload = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data?.status?.blockers?.join(" | ") || `${response.status} ${response.statusText}`);
  }
  return data;
}

function setText(element, value) {
  if (element) {
    element.textContent = value;
  }
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds || 0)));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

function shortPath(value) {
  if (!value) return "none";
  const normalized = String(value).replaceAll("\\", "/");
  const parts = normalized.split("/");
  if (parts.length <= 3) return normalized;
  return parts.slice(-3).join("/");
}

function renderStatus(status) {
  const job = status.job || { status: "idle", lines: [] };
  const progress = status.progress || {};
  const defaults = status.defaults || {};
  const dataset = status.dataset || {};
  const torch = status.torch || {};
  const active = job.status === "running" || job.status === "stopping" || status.running;
  const step = Number(progress.step || 0);
  const maxSteps = Number(progress.max_steps || defaults.max_steps || 0);
  const percent = maxSteps > 0 ? Math.min(100, Math.round((step / maxSteps) * 1000) / 10) : 0;
  const loss = progress.loss;
  const blockers = status.blockers || [];

  setText(dom.statusLabel, active ? job.status : status.ready ? "Ready" : "Blocked");
  setText(
    dom.statusLine,
    blockers.length
      ? blockers.join(" | ")
      : torch.message || "Prepared dataset and trainer are ready.",
  );
  setText(dom.devicePill, torch.device === "cuda" ? "CUDA" : torch.device === "cpu" ? "CPU overnight" : "no torch");

  setText(dom.examples, formatNumber(dataset.train_count));
  setText(dom.test, `${formatNumber(dataset.test_count)} test`);
  setText(dom.step, formatNumber(step));
  setText(dom.target, `${formatNumber(maxSteps)} target`);
  setText(dom.elapsed, formatDuration(status.elapsed_seconds || progress.elapsed_seconds || 0));
  setText(dom.loss, typeof loss === "number" ? `loss ${loss.toFixed(4)}` : "loss pending");
  setText(dom.checkpoint, shortPath(progress.checkpoint_path || status.latest_checkpoint));
  setText(dom.modelDir, shortPath(status.model_dir || defaults.model_dir));

  setText(dom.progressSummary, active ? `training ${formatNumber(step)} / ${formatNumber(maxSteps)}` : job.status || "waiting");
  setText(dom.progressPercent, `${percent}%`);
  dom.progressFill.style.width = `${percent}%`;

  setText(
    dom.readinessDataset,
    dataset.manifest
      ? `${formatNumber(dataset.manifest.written)} supported from ${formatNumber(dataset.manifest.scanned_json)} scanned`
      : dataset.data_dir || "missing",
  );
  setText(dom.readinessGrammar, dataset.grammar_valid ? "valid v0 token grammar" : dataset.grammar_error || "not checked");
  setText(dom.readinessTorch, `${torch.version || "missing"} | ${torch.message || ""}`.trim());
  setText(
    dom.readinessDefaults,
    `${formatNumber(defaults.batch_size)} batch | ${formatNumber(defaults.max_len)} max len | seed ${defaults.seed}`,
  );

  setText(dom.log, job.lines?.length ? job.lines.join("\n") : "Idle");
  dom.start.disabled = active || !status.ready;
  dom.stop.disabled = !active;
  dom.start.querySelector("span").textContent = active ? "Running" : "Start";
}

async function refreshStatus() {
  const status = await getJson("/api/cad-diffusion/status");
  renderStatus(status);
}

async function startTraining() {
  dom.start.disabled = true;
  try {
    await postJson("/api/cad-diffusion/train/start", {});
    await refreshStatus();
  } catch (error) {
    setText(dom.log, error.message);
    await refreshStatus().catch(() => {});
  }
}

async function stopTraining() {
  dom.stop.disabled = true;
  try {
    await postJson("/api/cad-diffusion/train/stop", {});
  } finally {
    await refreshStatus().catch(() => {});
  }
}

function startPolling() {
  window.clearInterval(statusTimer);
  statusTimer = window.setInterval(() => refreshStatus().catch((error) => setText(dom.log, error.message)), 3000);
}

dom.refresh.addEventListener("click", () => refreshStatus().catch((error) => setText(dom.log, error.message)));
dom.start.addEventListener("click", startTraining);
dom.stop.addEventListener("click", stopTraining);

refreshStatus().catch((error) => setText(dom.log, error.message));
startPolling();
