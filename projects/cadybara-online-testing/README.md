# Cadybara Online Testing

`projects/cadybara-online-testing/` is the lab control plane. It serves a small
local HTTP API over Python's `http.server`, starts and stops runs through the
shared runner, reports progress, manages model prefetch jobs for local Ollama
runs, records review scores, and exposes CAD diffusion training status.

Despite the folder name, this project is still the lab/control-plane layer. The
hosted Cadybara product API client now lives in the shared local-running
provider layer. Hosted API notes live in `../../docs/HOSTED_CADYBARA_API.md`.

Neighbor project contracts: local-running provides the runner/provider layer,
and website provides the static browser UI. This folder owns the lab API and
review/reporting layer between them.

This is its own project. It owns the lab API, configs, review/reporting flow,
and worker job state. It should not absorb provider code from local-running,
training logic from cad-diffusion, or browser implementation from website.

## What This Project Owns

- `cadybara_online_testing/lab_server.py`
  - static routes for `/lab/` and `/viewer/`
  - run/model/CAD-diffusion JSON endpoints
  - background threads for runs, model pulls, and CAD diffusion training
  - current worker job state in `projects/local-running/workspace/worker/`
  - legacy workspace route mapping for old artifact links
- `cadybara_online_testing/progress.py` for weighted run progress and recent
  render payloads.
- `cadybara_online_testing/reviews.py` for browser review items and append-only
  1-10 scores.
- `cadybara_online_testing/grading.py` for CLI rubric grading into
  `grades.jsonl`.
- `configs/online_smoke.yaml` as the active online smoke config.
- `configs/online_smoke_reps2.yaml` for the first 10 hosted wall-planter
  review cells.
- `configs/online_smoke_blind_extra.yaml` for one additional hosted sample per
  wall-planter prompt, intended to be combined with the 10-cell run in blind
  review mode.
- `configs/online_smoke_blind_extra2.yaml` and
  `configs/online_smoke_blind_extra3.yaml` are saved rate-limit probes from
  2026-06-07. Both attempted one additional sample per wall-planter prompt and
  received `429 RATE_LIMITED` with `Daily limit reached (15/15 queries)`.
- `configs/online_smoke_blind_20260608_reps3.yaml` is the next hosted blind
  batch: three additional samples for each of the same five wall-planter
  prompts. It writes to its own run folder so old models and scores are not
  rewritten.
- `configs/online_snowman_20260609_reps3.yaml` is a prepared-but-not-run
  Tuesday hosted batch: three samples each for the five curved snowman prompts
  in `prompts/curved_snowman_agent_prompts.yaml`. Run it only when the
  researcher explicitly chooses to spend the day's hosted API calls.
- `configs/online_snowman_20260609_reps4.yaml` is the related 20-call Tuesday
  probe: four samples each for the same five curved snowman prompts. Use
  `--provider-retries 0` so any daily-limit response is saved once as data.
- `configs/online_snowman_20260610_reps3.yaml` is the Wednesday hosted batch:
  three samples each for the same five curved snowman prompts, saved separately
  from the Tuesday probe for blind review and comparison.
- `configs/online_hook_20260611_reps3.yaml` is the Thursday hosted batch: three
  samples each for the five wall-mounted cable/headphone hook prompts in
  `prompts/wall_hook_agent_prompts.yaml`, saved separately so snowman review
  data stays in the blind-review mix.
- `configs/online_gapfill_20260612_reps3.yaml` and
  `configs/online_gapfill2_20260613_reps3.yaml` continue the hosted blind
  review ladder with gap-fill, hook, and snowman prompt mixes. They should be
  preserved as separate experiment records instead of merged into the older
  wall-planter smoke files.
- `cadybara_online_testing/blind_report.py` rebuilds the combined blind-review
  manifest and CSVs from saved run JSONL plus append-only review scores. Use it
  after new pulls or new browser scores to refresh prompt-specific averages and
  the specificity-vs-average-score correlation.
- `tests/` for endpoints, lab config behavior, weighted progress, review, and
  grading.
- `workspace/` for ignored online run data and review scores.

## Main Flow

1. `cadybara lab` calls `serve_lab()`.
2. The server maps `/lab/` to `projects/website/lab/index.html` and `/viewer/`
   to `projects/website/viewer/index.html`.
3. The browser calls `/api/status`, `/api/run_status`, `/api/results`,
   `/api/review`, and related POST endpoints.
4. When `/api/run/start` arrives, `LabState.start_run()` assigns a numbered run
   folder, writes `config.yaml`, records current worker job state, and starts
   `run_config()` in a background thread.
5. Run records flow back into progress payloads through `on_record()`.
6. `/api/models/start` starts model prefetch jobs from the experiment config or
   the configured local model queue.
7. `/api/review/score` appends a score to online-testing workspace reviews.
8. `/api/cad-diffusion/status` checks dataset readiness, PyTorch availability,
   latest checkpoint, and current training job state.
9. `/api/cad-diffusion/train/start` starts CAD diffusion training in a separate
   thread if there is no conflicting training job and readiness blockers are
   clear.
10. `/api/voxel-diffusion/status` checks voxel dataset readiness, optional
    geometry dependencies, latest checkpoint, latest sample STL, and current
    training job state.
11. `/api/voxel-diffusion/train/start` starts geometry-native voxel diffusion
    training in a separate thread if there is no conflicting training job and
    readiness blockers are clear.
12. `/api/review` also supports hosted review board queries from
    `projects/website/lab/hosted-review.html`, including combined config lists
    and blind review mode.

For combined hosted review analysis, run:

```bash
python -m cadybara_online_testing.blind_report \
  --output-dir projects/cadybara-online-testing/workspace/reviews/combined_prompt_goodness_latest
```

The default config list includes the 2026-06-07 base/extra hosted rows, the
saved rate-limit probes, and the 2026-06-08 three-rep batch. When later
gapfill/hook/snowman configs are part of a review session, pass them
explicitly rather than editing old config history. The report records model run
IDs, STL/code artifact paths, review scores, unreviewed counts, and per-prompt
average scores without regenerating anything. It writes a readable `README.md`
plus `manifest.json`, `prompt_goodness.csv`, and `review_cells.csv`.

The lab reports failures in the UI. It should not hide provider errors, render
errors, missing models, missing datasets, or PyTorch problems.

## Hosted API Coordination

If the user says these tests should run "online, not on my computer", check the
YAML provider. The active online smoke config now names
`provider: cadybara_api`, so generation is hosted and requires
`CADYBARA_API_KEY`.

The hosted path is:

- use `projects/local-running/cadybara/providers/cadybara_api.py`;
- select it from config with `provider: cadybara_api`;
- keep API keys in `CADYBARA_API_KEY`, not YAML;
- keep this project responsible for lab status/progress/review around that run;
- keep generated rows and grades append-only.

The active smoke uses five wall-planter prompts from
`prompts/wall_planter_agent_prompts.yaml`. Hosted generation should use
`response_mode: "sse"` to avoid the production ALB idle timeout. Hosted rows
preserve server-returned STL artifacts even when the returned source is not
locally executable.

Do not implement hosted generation directly in `lab_server.py` unless the
runner/provider architecture is intentionally being replaced.

## Active Endpoints

GET:

- `/api/status`
- `/api/current_snapshot`
- `/api/run_status`
- `/api/results`
- `/api/review`
- `/api/cad-diffusion/status`
- `/api/voxel-diffusion/status`

POST:

- `/api/models/start`
- `/api/run/start`
- `/api/run/stop`
- `/api/review/score`
- `/api/cad-diffusion/train/start`
- `/api/cad-diffusion/train/stop`
- `/api/voxel-diffusion/train/start`
- `/api/voxel-diffusion/train/stop`

Keep these contracts stable unless the website is updated in the same change.

## Current Limits

- The server is intentionally small and local. Do not replace it with FastAPI or
  a database-backed service.
- Background jobs are in-process threads, not a distributed queue.
- Review scores are append-only JSONL, not a normalized database.
- Legacy workspace route mapping exists to keep old artifact links useful after
  the repo split.
- CAD diffusion training defaults are hard-coded in `CAD_DIFFUSION_DEFAULTS`
  and can be overridden by the start endpoint payload.
- The lab's model-pull UI is Ollama-specific. A hosted provider should surface
  readiness differently, probably as API-key/config status rather than a model
  download queue.

## Tests

Run this project:

```bash
pytest projects/cadybara-online-testing/tests -q -p no:cacheprovider
```

Run the full repo suite before endpoint or record behavior changes:

```bash
pytest -q -p no:cacheprovider
```
