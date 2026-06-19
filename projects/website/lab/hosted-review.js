const DEFAULT_CONFIG = "projects/cadybara-online-testing/configs/online_smoke_reps2.yaml";

const query = new URLSearchParams(window.location.search);
const configPaths = configPathsFromQuery(query);
const configPath = configPaths[0];

const dom = {
  runMeta: document.querySelector("#run-meta"),
  total: document.querySelector("#metric-total"),
  stl: document.querySelector("#metric-stl"),
  errors: document.querySelector("#metric-errors"),
  reviewed: document.querySelector("#metric-reviewed"),
  grid: document.querySelector("#result-grid"),
  browseView: document.querySelector("#browse-view"),
  blindView: document.querySelector("#blind-view"),
  battleView: document.querySelector("#battle-view"),
  refresh: document.querySelector("#refresh"),
  filterButtons: [...document.querySelectorAll("[data-filter]")],
  modeButtons: [...document.querySelectorAll("[data-mode]")],
  detailKind: document.querySelector("#detail-kind"),
  detailTitle: document.querySelector("#detail-title"),
  loadViewer: document.querySelector("#load-viewer"),
  openViewer: document.querySelector("#open-viewer"),
  viewerWrap: document.querySelector("#viewer-wrap"),
  viewer: document.querySelector("#detail-viewer"),
  emptyViewer: document.querySelector("#empty-viewer"),
  scoreRow: document.querySelector("#score-row"),
  prompt: document.querySelector("#detail-prompt"),
  status: document.querySelector("#detail-status"),
  validation: document.querySelector("#detail-validation"),
  source: document.querySelector("#detail-source"),
  codePreview: document.querySelector("#code-preview"),
  blindVisual: document.querySelector("#blind-visual"),
  blindViewer: document.querySelector("#blind-viewer"),
  blindEmpty: document.querySelector("#blind-empty"),
  blindProgress: document.querySelector("#blind-progress"),
  blindTitle: document.querySelector("#blind-title"),
  blindNote: document.querySelector("#blind-note"),
  blindScoreRow: document.querySelector("#blind-score-row"),
  blindReveal: document.querySelector("#blind-reveal"),
  blindNext: document.querySelector("#blind-next"),
  blindShuffle: document.querySelector("#blind-shuffle"),
  blindLedger: document.querySelector("#blind-ledger"),
  battleProgress: document.querySelector("#battle-progress"),
  battleLeftViewer: document.querySelector("#battle-left-viewer"),
  battleRightViewer: document.querySelector("#battle-right-viewer"),
  battleLeftEmpty: document.querySelector("#battle-left-empty"),
  battleRightEmpty: document.querySelector("#battle-right-empty"),
  battleLeftSecret: document.querySelector("#battle-left-secret"),
  battleRightSecret: document.querySelector("#battle-right-secret"),
  battleLeftWin: document.querySelector("#battle-left-win"),
  battleRightWin: document.querySelector("#battle-right-win"),
  battleTie: document.querySelector("#battle-tie"),
  battleSkip: document.querySelector("#battle-skip"),
  battleReveal: document.querySelector("#battle-reveal"),
  battleRankings: document.querySelector("#battle-rankings"),
};

const state = {
  reviews: [],
  rawItems: [],
  items: [],
  selectedRunId: null,
  loadedViewerRunId: null,
  filter: "all",
  mode: ["blind", "battle"].includes(query.get("mode")) ? query.get("mode") : "browse",
  blindOrder: [],
  blindIndex: 0,
  blindScoredRunId: null,
  blindRevealText: "",
  battleCandidates: [],
  battleSummary: null,
  battlePairs: [],
  battleIndex: 0,
  battleRevealText: "",
  savingBattle: false,
  savingScore: false,
  includeReviewedBlind: query.get("include_reviewed") === "1",
};

function configPathsFromQuery(params) {
  const paths = [];
  const configs = params.get("configs");
  if (configs) {
    paths.push(...configs.split(",").map((value) => value.trim()).filter(Boolean));
  } else {
    paths.push(params.get("config") || DEFAULT_CONFIG);
    paths.push(...params.getAll("extra_config").map((value) => value.trim()).filter(Boolean));
  }
  return [...new Set(paths)];
}

function buildUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) url.searchParams.set(key, value);
  }
  return url;
}

async function getJson(path, params = {}) {
  const response = await fetch(buildUrl(path, params));
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `${path} returned ${response.status}`);
  return payload;
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `${path} returned ${response.status}`);
  return data;
}

function assetUrl(path) {
  const value = String(path || "").replaceAll("\\", "/");
  if (!value) return "";
  if (value.startsWith("http://") || value.startsWith("https://")) return value;
  if (value.startsWith("/")) return value;
  return `/${value}`;
}

function formatMs(ms) {
  if (ms === null || ms === undefined) return "pending";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function shortPromptId(id) {
  return String(id || "prompt").replace(/^(planter|snowman)_/, "").replaceAll("_", " ");
}

function firstLine(value) {
  return String(value || "").split(/\r?\n/).find(Boolean) || "";
}

function cellKey(item) {
  return [
    item.config_path,
    item.experiment_id,
    item.model_name,
    item.seed_id,
    item.condition_name,
    item.temperature,
    item.repetition,
  ].join("|");
}

function shuffle(values) {
  const shuffled = [...values];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled;
}

function viewerUrlFor(item) {
  return item.viewer_url || (item.artifacts?.stl ? `/viewer/?stl=${assetUrl(item.artifacts.stl)}` : "");
}

function sampleLabel(item) {
  const labels = {
    cadybara_online_smoke_reps2: "2026-06-07 base",
    cadybara_online_smoke_blind_extra: "2026-06-07 extra",
    cadybara_online_smoke_blind_extra2: "2026-06-07 limit probe 2",
    cadybara_online_smoke_blind_extra3: "2026-06-07 limit probe 3",
    cadybara_online_smoke_blind_20260608_reps3: "2026-06-08",
    cadybara_online_snowman_20260609_reps3: "2026-06-09 snowman",
    cadybara_online_snowman_20260609_reps4: "2026-06-09 snowman 20-call probe",
    cadybara_online_snowman_20260610_reps3: "2026-06-10 snowman",
    cadybara_online_hook_20260611_reps3: "2026-06-11 wall hook",
    cadybara_online_gapfill_20260612_reps3: "2026-06-12 gap fill",
    cadybara_online_gapfill2_20260613_reps3: "2026-06-13 gap fill",
    cadybara_online_gapfill3_20260614_reps3: "2026-06-14 gap fill",
    cadybara_online_gapfill_solidish_20260615_reps3: "2026-06-15 solid-ish",
    cadybara_online_gapfill_existing_20260617_reps3: "2026-06-17 existing fill",
  };
  const experiment = labels[item.experiment_id] || item.experiment_id || "run";
  return `${shortPromptId(item.seed_id)} (${experiment}, rep ${Number(item.repetition) + 1})`;
}

function latestCellItems(items) {
  const byCell = new Map();
  items.forEach((item, index) => {
    const key = cellKey(item);
    const saved = byCell.get(key);
    const attempts = saved ? saved.attempts + 1 : 1;
    byCell.set(key, {
      ...item,
      raw_index: index,
      attempts,
      attempt_history: [...(saved?.attempt_history || []), item],
    });
  });
  return [...byCell.values()];
}

function statusFor(item) {
  if (item.error) return { label: "HTTP 504", kind: "error" };
  if (item.render_error && item.artifacts?.hosted_stl) return { label: "API STL", kind: "warn" };
  if (item.is_renderable) return { label: "STL", kind: "ok" };
  return { label: "No STL", kind: "error" };
}

function validationText(item) {
  const validation = item.provider_metadata?.validation;
  if (!validation) return "No validation payload.";
  const valid = validation.valid ? "valid" : "invalid";
  const confidence = validation.confidence !== undefined ? `, confidence ${validation.confidence}` : "";
  const reason = validation.brief_reason ? ` ${validation.brief_reason}` : "";
  return `${valid}${confidence}.${reason}`;
}

function sourceText(item) {
  if (!item.render_error) return "Local CadQuery source executed.";
  if (item.artifacts?.hosted_stl) {
    return `Hosted STL is viewable. Local source failed: ${firstLine(item.render_error)}`;
  }
  return firstLine(item.render_error) || "No local source result.";
}

function cardMeta(item) {
  const pieces = [`rep ${item.repetition}`];
  if (item.attempts > 1) pieces.push(`try ${item.attempts}`);
  pieces.push(formatMs(item.latency_ms));
  if (item.review?.score) pieces.push(`score ${item.review.score}`);
  return pieces.join(" | ");
}

function filteredItems() {
  if (state.filter === "stl") return state.items.filter((item) => item.is_renderable);
  if (state.filter === "error") return state.items.filter((item) => item.error || !item.is_renderable);
  if (state.filter === "unreviewed") return state.items.filter((item) => !item.review);
  return state.items;
}

function syncSelectionToFilter() {
  const items = filteredItems();
  if (items.some((item) => item.run_id === state.selectedRunId)) return;
  state.selectedRunId = items[0]?.run_id || null;
  state.loadedViewerRunId = null;
}

function renderMetrics() {
  const items = state.items;
  dom.total.textContent = String(items.length);
  dom.stl.textContent = String(items.filter((item) => item.is_renderable).length);
  dom.errors.textContent = String(items.filter((item) => item.error || !item.is_renderable).length);
  dom.reviewed.textContent = String(items.filter((item) => item.review).length);
  const rawCount = state.rawItems.length;
  const attemptText = rawCount && rawCount !== items.length ? ` | ${rawCount} saved attempts` : "";
  const loadedText = configPaths.length > 1 ? `${configPaths.length} configs` : configPath;
  const outputText = state.reviews.map((review) => review.output_path).filter(Boolean).join(" + ");
  dom.runMeta.textContent = `${loadedText} | ${outputText || "loading"}${attemptText}`;
}

function renderCard(item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "result-card";
  if (item.run_id === state.selectedRunId) button.classList.add("selected");
  button.dataset.runId = item.run_id;

  const status = statusFor(item);
  const top = document.createElement("div");
  top.className = "card-top";
  const title = document.createElement("div");
  title.className = "card-title";
  const strong = document.createElement("strong");
  strong.textContent = sampleLabel(item);
  const sub = document.createElement("span");
  sub.textContent = cardMeta(item);
  title.append(strong, sub);
  const badge = document.createElement("span");
  badge.className = `badge ${status.kind}`;
  badge.textContent = status.label;
  top.append(title, badge);

  const thumb = document.createElement("div");
  thumb.className = "thumb";
  const preview = item.artifacts?.preview_png;
  if (preview) {
    const img = document.createElement("img");
    img.src = assetUrl(preview);
    img.alt = "";
    img.loading = "lazy";
    thumb.appendChild(img);
  } else {
    const fallback = document.createElement("div");
    fallback.className = `thumb-fallback ${item.error ? "error" : ""}`;
    fallback.textContent = item.error ? "504 timeout" : "no preview";
    thumb.appendChild(fallback);
  }

  const footer = document.createElement("div");
  footer.className = "card-footer";
  const prompt = document.createElement("span");
  prompt.textContent = item.seed_text || "";
  const score = document.createElement("span");
  score.textContent = item.review?.score ? `score ${item.review.score}` : "unreviewed";
  footer.append(prompt, score);

  button.append(top, thumb, footer);
  button.addEventListener("click", () => selectItem(item.run_id));
  return button;
}

function renderGrid() {
  syncSelectionToFilter();
  const items = filteredItems();
  dom.grid.replaceChildren(...items.map(renderCard));
  if (items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "result-card";
    empty.textContent = "No rows match this filter.";
    dom.grid.appendChild(empty);
  }
}

function renderScoreButtons(item, container = dom.scoreRow, handler = saveScore) {
  const current = item?.review?.score;
  container.replaceChildren();
  for (let value = 1; value <= 10; value += 1) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = String(value);
    button.classList.toggle("active", current === value);
    button.disabled = state.savingScore || !item;
    button.addEventListener("click", () => handler(value));
    container.appendChild(button);
  }
}

function renderDetail() {
  const item = state.items.find((candidate) => candidate.run_id === state.selectedRunId) || null;
  if (!item) {
    dom.detailKind.textContent = "Select a row";
    dom.detailTitle.textContent = "No result selected";
    dom.loadViewer.classList.add("is-hidden");
    dom.openViewer.classList.add("is-hidden");
    dom.viewerWrap.classList.remove("has-viewer");
    dom.viewer.removeAttribute("src");
    dom.emptyViewer.textContent = "No STL for this cell";
    dom.prompt.textContent = "";
    dom.status.textContent = "";
    dom.validation.textContent = "";
    dom.source.textContent = "";
    dom.codePreview.textContent = "";
    renderScoreButtons(null);
    return;
  }

  const status = statusFor(item);
  const viewerUrl = viewerUrlFor(item);
  const attemptText = item.attempts > 1 ? ` | latest of ${item.attempts} tries` : "";
  dom.detailKind.textContent = `${status.label} | rep ${item.repetition} | ${formatMs(item.latency_ms)}${attemptText}`;
  dom.detailTitle.textContent = sampleLabel(item);
  dom.prompt.textContent = item.seed_text || "";
  dom.status.textContent = item.error ? firstLine(item.error) : `${status.label}; provider ${item.provider}`;
  dom.validation.textContent = validationText(item);
  dom.source.textContent = sourceText(item);
  dom.codePreview.textContent = item.output_preview || "No generated code captured for this row.";

  if (viewerUrl && item.is_renderable) {
    dom.loadViewer.classList.remove("is-hidden");
    dom.loadViewer.disabled = false;
    dom.openViewer.href = viewerUrl;
    dom.openViewer.classList.remove("is-hidden");
  } else {
    dom.loadViewer.classList.add("is-hidden");
    dom.openViewer.classList.add("is-hidden");
  }

  if (viewerUrl && item.is_renderable && state.loadedViewerRunId === item.run_id) {
    dom.viewerWrap.classList.add("has-viewer");
    if (dom.viewer.getAttribute("src") !== viewerUrl) dom.viewer.src = viewerUrl;
  } else {
    dom.viewerWrap.classList.remove("has-viewer");
    dom.viewer.removeAttribute("src");
    dom.emptyViewer.textContent = viewerUrl && item.is_renderable ? "STL ready" : "No STL for this cell";
  }
  renderScoreButtons(item);
}

function blindCandidates() {
  const renderable = state.items.filter((item) => item.is_renderable);
  if (state.includeReviewedBlind) return renderable;
  const unreviewed = renderable.filter((item) => !item.review);
  if (!unreviewed.length) return renderable;
  const justScored = renderable.find((item) => item.run_id === state.blindScoredRunId);
  if (!justScored) return unreviewed;
  return [justScored, ...unreviewed.filter((item) => item.run_id !== justScored.run_id)];
}

function syncBlindOrder({ force = false } = {}) {
  const candidates = blindCandidates();
  const ids = new Set(candidates.map((item) => item.run_id));
  const currentIds = new Set(state.blindOrder);
  const orderMatches =
    state.blindOrder.length === candidates.length
    && [...ids].every((runId) => currentIds.has(runId));
  if (!force && orderMatches) return;
  state.blindOrder = shuffle(candidates.map((item) => item.run_id));
  state.blindIndex = 0;
  state.blindScoredRunId = null;
  state.blindRevealText = "";
}

function currentBlindItem() {
  const runId = state.blindOrder[state.blindIndex];
  return state.items.find((item) => item.run_id === runId) || null;
}

function familyForItem(item) {
  return item?.family || String(item?.seed_id || "unknown").split("_")[0] || "unknown";
}

function syncBattlePairs({ force = false } = {}) {
  const candidates = state.battleCandidates.filter((item) => item.is_renderable);
  const signature = candidates.map((item) => item.run_id).sort().join("|");
  if (!force && state.battleSignature === signature && state.battlePairs.length) return;
  const crossFamily = [];
  const sameFamily = [];
  for (let leftIndex = 0; leftIndex < candidates.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < candidates.length; rightIndex += 1) {
      const pair = [candidates[leftIndex].run_id, candidates[rightIndex].run_id];
      if (familyForItem(candidates[leftIndex]) !== familyForItem(candidates[rightIndex])) {
        crossFamily.push(pair);
      } else {
        sameFamily.push(pair);
      }
    }
  }
  state.battlePairs = shuffle([...shuffle(crossFamily), ...shuffle(sameFamily)]);
  state.battleIndex = 0;
  state.battleRevealText = "";
  state.battleSignature = signature;
}

function currentBattlePair() {
  const pair = state.battlePairs[state.battleIndex];
  if (!pair) return [null, null];
  const left = state.battleCandidates.find((item) => item.run_id === pair[0]) || null;
  const right = state.battleCandidates.find((item) => item.run_id === pair[1]) || null;
  return [left, right];
}

function revealBattleLabel(item) {
  const score = item?.review?.score ? ` | score ${item.review.score}/10` : "";
  const rating = state.battleSummary?.items?.find((row) => row.run_id === item?.run_id);
  const elo = rating ? ` | Elo ${rating.rating}` : "";
  return `${sampleLabel(item)}${score}${elo}`;
}

function renderBattleViewer(item, iframe, empty, secret) {
  const wrap = iframe.closest(".battle-viewer");
  const viewerUrl = viewerUrlFor(item);
  if (item && viewerUrl) {
    wrap.classList.add("has-viewer");
    if (iframe.getAttribute("src") !== viewerUrl) iframe.src = viewerUrl;
    empty.textContent = "";
  } else {
    wrap.classList.remove("has-viewer");
    iframe.removeAttribute("src");
    empty.textContent = "No model";
  }
  secret.textContent = state.battleRevealText && item ? revealBattleLabel(item) : "Hidden model";
}

function renderBattleRankings() {
  const rows = state.battleSummary?.items || [];
  if (!rows.length) {
    dom.battleRankings.textContent = "No rankings yet.";
    return;
  }
  dom.battleRankings.replaceChildren(...rows.slice(0, 12).map((item, index) => {
    const row = document.createElement("div");
    row.className = "ledger-item";
    const title = document.createElement("strong");
    title.textContent = `${index + 1}. ${item.rating} Elo -> ${item.label}`;
    const detail = document.createElement("span");
    const scoreText = item.score ? `seed score ${item.score}/10` : "no seed score";
    detail.textContent = `${item.family}; ${item.battle_count} battles; ${scoreText}`;
    row.append(title, detail);
    return row;
  }));
}

function renderBattle() {
  syncBattlePairs();
  const [left, right] = currentBattlePair();
  const total = state.battlePairs.length;
  dom.battleProgress.textContent = total
    ? `Battle ${state.battleIndex + 1} of ${total} | ${state.battleSummary?.battle_count || 0} saved votes`
    : "Battle queue";
  renderBattleViewer(left, dom.battleLeftViewer, dom.battleLeftEmpty, dom.battleLeftSecret);
  renderBattleViewer(right, dom.battleRightViewer, dom.battleRightEmpty, dom.battleRightSecret);
  const disabled = state.savingBattle || !left || !right;
  [dom.battleLeftWin, dom.battleRightWin, dom.battleTie, dom.battleSkip].forEach((button) => {
    button.disabled = disabled && button !== dom.battleSkip;
  });
  if (state.battleRevealText) {
    dom.battleReveal.textContent = state.battleRevealText;
    dom.battleReveal.classList.remove("is-hidden");
  } else {
    dom.battleReveal.textContent = "";
    dom.battleReveal.classList.add("is-hidden");
  }
  renderBattleRankings();
}

function advanceBattle() {
  if (!state.battlePairs.length) return;
  state.battleIndex = (state.battleIndex + 1) % state.battlePairs.length;
  state.battleRevealText = "";
  renderBattle();
}

function renderBlindLedger() {
  const scored = state.items
    .filter((item) => item.review)
    .sort((left, right) => String(right.review.timestamp_utc || "").localeCompare(String(left.review.timestamp_utc || "")));
  if (!scored.length) {
    dom.blindLedger.textContent = "No blind scores yet.";
    return;
  }
  dom.blindLedger.replaceChildren(...scored.map((item) => {
    const row = document.createElement("div");
    row.className = "ledger-item";
    const title = document.createElement("strong");
    title.textContent = `${item.review.score}/10 -> ${sampleLabel(item)}`;
    const detail = document.createElement("span");
    detail.textContent = item.seed_text || item.seed_id;
    row.append(title, detail);
    return row;
  }));
}

function renderBlind() {
  syncBlindOrder();
  const item = currentBlindItem();
  const total = state.blindOrder.length;
  if (!item) {
    dom.blindProgress.textContent = "Blind queue";
    dom.blindTitle.textContent = "No viewable models";
    dom.blindNote.textContent = "The current run set does not have any STL rows to judge.";
    dom.blindVisual.classList.remove("has-viewer");
    dom.blindViewer.removeAttribute("src");
    dom.blindEmpty.textContent = "No blind item loaded";
    dom.blindReveal.classList.add("is-hidden");
    dom.blindReveal.textContent = "";
    renderScoreButtons(null, dom.blindScoreRow, saveBlindScore);
    renderBlindLedger();
    return;
  }

  const viewerUrl = viewerUrlFor(item);
  dom.blindProgress.textContent = `Blind item ${state.blindIndex + 1} of ${total}`;
  dom.blindTitle.textContent = "Hidden category";
  dom.blindNote.textContent = item.review
    ? "This model already has a score. You can rescore it, or move to the next randomized item."
    : "Judge only the model. Prompt and category are hidden until you score.";

  if (viewerUrl) {
    dom.blindVisual.classList.add("has-viewer");
    if (dom.blindViewer.getAttribute("src") !== viewerUrl) dom.blindViewer.src = viewerUrl;
  } else {
    dom.blindVisual.classList.remove("has-viewer");
    dom.blindViewer.removeAttribute("src");
    dom.blindEmpty.textContent = "No STL for this blind item";
  }

  if (state.blindScoredRunId === item.run_id && state.blindRevealText) {
    dom.blindReveal.textContent = state.blindRevealText;
    dom.blindReveal.classList.remove("is-hidden");
  } else {
    dom.blindReveal.textContent = "";
    dom.blindReveal.classList.add("is-hidden");
  }

  renderScoreButtons(item, dom.blindScoreRow, saveBlindScore);
  renderBlindLedger();
}

function selectItem(runId) {
  state.selectedRunId = runId;
  renderGrid();
  renderDetail();
}

async function saveScore(score) {
  const item = state.items.find((candidate) => candidate.run_id === state.selectedRunId);
  await saveScoreForItem(item, score);
  renderMetrics();
  renderGrid();
  renderDetail();
  renderBlind();
}

async function saveScoreForItem(item, score) {
  if (!item || state.savingScore) return;
  state.savingScore = true;
  renderScoreButtons(item);
  renderScoreButtons(currentBlindItem(), dom.blindScoreRow, saveBlindScore);
  try {
    const response = await postJson("/api/review/score", {
      config_path: item.config_path || configPath,
      run_id: item.run_id,
      score,
    });
    item.review = response.saved;
  } finally {
    state.savingScore = false;
    renderScoreButtons(item);
    renderScoreButtons(currentBlindItem(), dom.blindScoreRow, saveBlindScore);
  }
}

async function saveBlindScore(score) {
  const item = currentBlindItem();
  await saveScoreForItem(item, score);
  if (item) {
    state.blindScoredRunId = item.run_id;
    state.blindRevealText = `You gave ${score}/10 to ${sampleLabel(item)}.`;
  }
  renderMetrics();
  renderGrid();
  renderDetail();
  renderBlind();
}

async function saveBattle(outcome) {
  if (state.savingBattle) return;
  const [left, right] = currentBattlePair();
  if (!left || !right) return;
  state.savingBattle = true;
  renderBattle();
  try {
    const response = await postJson("/api/review/battle", {
      left_run_id: left.run_id,
      right_run_id: right.run_id,
      outcome,
      criterion: "overall_quality",
      config_paths: configPaths,
    });
    state.battleSummary = response.summary;
    const winnerText = outcome === "tie"
      ? "You marked this battle as a tie."
      : `You picked ${outcome === "left" ? "left" : "right"} as better overall.`;
    state.battleRevealText = `${winnerText} Left: ${revealBattleLabel(left)}. Right: ${revealBattleLabel(right)}.`;
  } finally {
    state.savingBattle = false;
    renderBattle();
  }
}

function setMode(mode) {
  state.mode = mode;
  dom.modeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  dom.browseView.classList.toggle("is-hidden", mode !== "browse");
  dom.blindView.classList.toggle("is-hidden", mode !== "blind");
  dom.battleView.classList.toggle("is-hidden", mode !== "battle");
  if (mode === "blind") renderBlind();
  if (mode === "battle") renderBattle();
}

async function refresh() {
  dom.runMeta.textContent = "Loading review data...";
  const reviews = await Promise.all(configPaths.map(async (path) => {
    const review = await getJson("/api/review", { config: path });
    const items = (review.items || []).map((item) => ({ ...item, config_path: path }));
    return { ...review, config_path: path, items };
  }));
  state.reviews = reviews;
  state.rawItems = reviews.flatMap((review) => review.items || []);
  state.items = latestCellItems(state.rawItems);
  const battlePayload = await getJson("/api/review/battles", { configs: configPaths.join(",") });
  state.battleCandidates = battlePayload.candidates || [];
  state.battleSummary = battlePayload.summary || null;
  syncBattlePairs({ force: true });
  if (!state.items.some((item) => item.run_id === state.selectedRunId) && state.items.length) {
    state.selectedRunId = state.items.find((item) => item.is_renderable)?.run_id || state.items[0].run_id;
  }
  syncSelectionToFilter();
  syncBlindOrder();
  renderMetrics();
  renderGrid();
  renderDetail();
  renderBlind();
  renderBattle();
  setMode(state.mode);
}

dom.filterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    state.filter = button.dataset.filter;
    dom.filterButtons.forEach((candidate) => {
      candidate.classList.toggle("active", candidate === button);
    });
    syncSelectionToFilter();
    renderGrid();
    renderDetail();
  });
});

dom.modeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setMode(button.dataset.mode);
  });
});

dom.refresh.addEventListener("click", () => {
  refresh().catch((error) => {
    dom.runMeta.textContent = error.message;
  });
});

dom.loadViewer.addEventListener("click", () => {
  state.loadedViewerRunId = state.selectedRunId;
  renderDetail();
});

dom.blindNext.addEventListener("click", () => {
  if (!state.blindOrder.length) return;
  state.blindIndex = (state.blindIndex + 1) % state.blindOrder.length;
  state.blindScoredRunId = null;
  state.blindRevealText = "";
  renderBlind();
});

dom.blindShuffle.addEventListener("click", () => {
  syncBlindOrder({ force: true });
  renderBlind();
});

dom.battleLeftWin.addEventListener("click", () => {
  saveBattle("left").catch((error) => {
    state.battleRevealText = error.message;
    renderBattle();
  });
});

dom.battleRightWin.addEventListener("click", () => {
  saveBattle("right").catch((error) => {
    state.battleRevealText = error.message;
    renderBattle();
  });
});

dom.battleTie.addEventListener("click", () => {
  saveBattle("tie").catch((error) => {
    state.battleRevealText = error.message;
    renderBattle();
  });
});

dom.battleSkip.addEventListener("click", () => {
  advanceBattle();
});

refresh().catch((error) => {
  dom.runMeta.textContent = error.message;
});
