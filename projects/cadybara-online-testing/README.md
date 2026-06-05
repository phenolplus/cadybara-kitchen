# Cadybara Online Testing

`projects/cadybara-online-testing/` is the lab control plane. It serves a small
local HTTP API over Python's `http.server`, starts and stops runs through the
shared runner, reports progress, manages model prefetch jobs for local Ollama
runs, records review scores, and exposes CAD diffusion training status.

Despite the folder name, this is not currently the hosted Cadybara product API
client. Hosted API notes live in `../../docs/HOSTED_CADYBARA_API.md`.

The local execution engine lives in `projects/local-running/`. The static UI
lives in `projects/website/`.

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

The lab reports failures in the UI. It should not hide provider errors, render
errors, missing models, missing datasets, or PyTorch problems.

## Hosted API Coordination

If the user says these tests should run "online, not on my computer", clarify
that the current code still uses whichever provider the YAML names. The active
online smoke config currently names `provider: ollama`, so it is local.

The right hosted path is:

- add a hosted provider in `projects/local-running/cadybara/providers/`;
- select it from a config with a distinct provider name such as
  `cadybara_api`;
- keep API keys in `CADYBARA_API_KEY`, not YAML;
- keep this project responsible for lab status/progress/review around that run;
- keep generated rows and grades append-only.

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

POST:

- `/api/models/start`
- `/api/run/start`
- `/api/run/stop`
- `/api/review/score`
- `/api/cad-diffusion/train/start`
- `/api/cad-diffusion/train/stop`

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
