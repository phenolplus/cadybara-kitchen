# Cadybara Monorepo

Cadybara is a local-first AI CAD research workspace. This repo contains
separate projects that happened to evolve together in one checkout. Treat each
folder under `projects/` as its own project with its own docs, ownership,
commands, tests, and generated data.

The short version:

1. A YAML config defines models, prompts, temperatures, repetitions, and output
   paths.
2. `projects/local-running/` turns that config into deterministic run cells,
   sends prompts to Ollama, dry-run, or the hosted Cadybara Agent API provider,
   and appends JSONL rows.
3. For CadQuery runs, model output is executed as written. Valid products get
   STL/STEP/PNG artifacts; invalid code and render failures remain measured
   failures.
4. `projects/cadybara-online-testing/` serves a small lab API over
   `http.server`, starts/stops runs, tracks progress, queues local model pulls,
   records reviews, and builds blind hosted-review reports.
5. `projects/website/` is the static browser experience that calls those lab
   APIs and displays the landing page, dashboard, hosted review board, CAD and
   voxel diffusion trainers, and 3D viewer.
6. `projects/cad-diffusion/` owns the CAD-native diffusion experiments:
   token/CAD grammar diffusion and geometry-native voxel diffusion.
7. `projects/codex-direct-testing/` holds manual Codex-in-this-thread CAD
   baselines outside online-testing so they can be compared without pretending
   they came from a provider API.

For shared terms and dataflow details, read `COMMON.md`. Shared concepts do not
make the folders one combined project; they are contracts that let independent
projects exchange runs, artifacts, reviews, and result snapshots safely.

If you are trying to run against the hosted Cadybara product API rather than
local Ollama, read `docs/HOSTED_CADYBARA_API.md` first. The active
`online_smoke.yaml` uses the hosted `cadybara_api` provider with
`response_mode: "sse"` and requires `CADYBARA_API_KEY`.

## Status Snapshot

This is the honest "what works / what is still rough" map for new humans and
AI agents arriving without extra context.

| Project | Works now | Still rough or intentionally limited |
| --- | --- | --- |
| `projects/local-running/` | CLI runs configs, resumes JSONL, retries CAD cells, writes CadQuery artifacts, preserves hosted STL artifacts, talks to dry-run/Ollama/hosted Cadybara providers, manages local Ollama queues, exports training pairs, and archives runs. | Only the `identity` prompt strategy exists, automatic scoring is still a stub, hosted source can fail local execution when the API returns server-only helper imports, and live output belongs in ignored `workspace/`. |
| `projects/cadybara-online-testing/` | Lab server serves static routes, run/model endpoints, progress payloads, current worker job state, CAD/voxel diffusion controls, review scoring, grading helpers, hosted configs, and blind-review reports. | It is a local `http.server` control plane with in-process jobs, not a production web service; hosted generation must stay in the local-running provider layer. |
| `projects/cad-diffusion/` | Token grammar round-trips simple CAD programs, prepares supported Fusion-style examples, trains/samples/evaluates token diffusion, and has a voxel diffusion path with dataset prep, training, sampling, STL export, and metrics. | CAD-token v0 only covers simple rectangle/circle extrudes, text conditioning is not implemented, voxel diffusion learns occupancy geometry rather than editable CAD, and datasets/checkpoints stay in ignored `workspace/`. |
| `projects/website/` | Static landing, demo auth, project dashboard, hosted review board, CAD diffusion page, voxel diffusion page, and Three.js viewer are present as vanilla HTML/CSS/JS. | Dashboard is intentionally a stable project library, not live telemetry; richer `lab/app.js` is preserved but not the active routed dashboard. |
| `projects/codex-direct-testing/` | Manual Codex-written CadQuery baselines can be packaged into comparable JSONL/artifacts and tested against prompt sets. | This is interactive benchmark data, not hosted/API output; any repair iterations must be documented as part of the protocol. |
| `projects/_parked-not-active/` | Old wall-planter research, Kaggle work, and sandbox archives are preserved. | Historical docs may mention obsolete paths or architectures and should not drive current work. |

## Project Independence

Each active project folder is self-contained enough for a human or AI teammate
to start there:

- read that folder's `README.md` for what the project is;
- read that folder's `AGENTS.md` for contribution rules;
- keep that folder's `workspace/` outputs separate and ignored;
- run that folder's focused tests before widening to the full suite;
- update another project only when an explicit interface changes.

The root docs are a map of the repo. They are not a replacement for the project
docs inside each folder.

## Active Projects

### `projects/local-running/`

The local Python harness and CLI project.

Owns:

- Typer commands in `cadybara/cli.py`
- config loading and config hashes
- deterministic run cells and resume behavior
- Ollama and dry-run providers
- CadQuery execution, STL/STEP export, and preview rendering
- model queue and worker helper scripts
- local tests for the runner core

Use this folder when changing local execution, provider behavior, CadQuery
artifacts, JSONL records, model pulls, worker scripts, archive behavior, or
training-pair export.

### `projects/cad-diffusion/`

The CAD-native diffusion experiment.

Owns:

- Fusion-style CAD dataset preparation
- v0 rectangle/circle extrude token grammar
- token-to-program and program-to-CadQuery compilation
- optional PyTorch denoising Transformer training
- sample generation, artifact compilation, and run evaluation
- voxel diffusion over normalized Fusion OBJ geometry, with STL export

This is the "stable diffusion for CAD" project direction, but the current code
is not image Stable Diffusion. It now has two early pilots: CAD-token denoising
for editability and voxel denoising for direct shape learning.

If you are taking over CAD diffusion work, read
`projects/cad-diffusion/HANDOFF.md`. It contains the current checkpoint/run
state, how to resume training, how sampling/eval should be handled, and the
recommended discriminator framing.

### `projects/cadybara-online-testing/`

The online/lab control-plane project.

Owns:

- `http.server` lab server and JSON endpoints
- run start/stop, current worker job state, and progress payloads
- model status and model prefetch jobs
- review score JSONL and rubric grading helpers
- active hosted smoke, blind-review, gapfill, hook, and snowman configs
- endpoint tests

Use this folder when changing the lab API, run/review workflow, online configs,
or progress semantics. It consumes runner and UI contracts from neighboring
projects, but it remains its own project.

### `projects/website/`

The browser-facing Cadybara experience.

Owns:

- static landing page and demo localStorage auth
- project dashboard
- hosted review board
- CAD diffusion and voxel diffusion training pages
- static image/sprite assets
- Three.js-based 3D viewer
- old local logs that should not become source

The lab server serves this folder at `/lab/` and `/viewer/`, but the website is
still its own static frontend project.

### `projects/codex-direct-testing/`

The manual Codex baseline sandbox.

Owns:

- prompt copies used for direct Codex comparisons
- CadQuery files written directly in a Codex chat thread
- a small packager that writes Cadybara-style JSONL and artifacts
- ignored workspace outputs for those manual baselines

Use this folder when comparing direct interactive Codex CAD work against
hosted/API or CADAM-style tool workflows. Do not put these outputs under
`projects/cadybara-online-testing/`, and do not describe them as normal
single-shot provider generations unless the manual protocol was frozen.

## Parked Work

`projects/_parked-not-active/` preserves old research and scratch work without
letting it drive current development. The wall-planter study data lives there,
along with old Kaggle scripts and sandbox archives.

Do not delete or rewrite parked research data unless explicitly asked. Some
parked docs still mention old paths; that is historical context, not current
architecture.

## Install

Requires Python 3.11+.

```bash
pip install -e ".[test]"
pytest -q
```

The install command runs from the repo root. `pyproject.toml` points at the
active Python packages in:

- `projects/local-running/cadybara`
- `projects/cad-diffusion/cadybara_cad_diffusion`
- `projects/cadybara-online-testing/cadybara_online_testing`

To install the optional CAD diffusion training dependency:

```bash
pip install -e ".[test,cad-diffusion]"
```

To install the optional voxel geometry diffusion dependencies:

```bash
pip install -e ".[test,voxel-diffusion]"
```

## Common Commands

Dry-run the local runner:

```bash
cadybara run --dry-run projects/local-running/configs/example.yaml
```

Start the lab UI:

```bash
cadybara lab --port 8790
```

Run the online testing smoke config:

```bash
cadybara cad-smoke
cadybara run projects/cadybara-online-testing/configs/online_smoke.yaml --limit 1
```

Today this command path uses the providers named in the YAML config. The active
online smoke config points at the hosted Cadybara Agent API. For a local Ollama
smoke on a worker box, use
`projects/cadybara-online-testing/configs/local_ollama_smoke.yaml`.

Build the combined blind hosted-review report from saved rows and append-only
review scores:

```bash
python -m cadybara_online_testing.blind_report
```

Check local model status:

```bash
cadybara model-status
```

Pull one missing model from the configured queue:

```bash
cadybara pull-models --limit 1
```

Prepare, train, sample, or evaluate CAD diffusion through the shared CLI:

```bash
cadybara cad-diffusion prepare
cadybara cad-diffusion train
cadybara cad-diffusion sample
cadybara cad-diffusion eval projects/cad-diffusion/workspace/runs/cad_diffusion_smoke
```

Prepare, train, sample, or evaluate voxel diffusion:

```bash
cadybara voxel-diffusion prepare --resolution 32 --max-examples 3
cadybara voxel-diffusion train --resolution 32 --max-steps 1
cadybara voxel-diffusion sample --count 1
cadybara voxel-diffusion eval projects/cad-diffusion/workspace/runs/voxel_diffusion_64_sample_001
```

## Data Rules

- Live generated data belongs under project `workspace/` folders, which are
  ignored.
- Runs, grades, review scores, model pull manifests, and CAD diffusion samples
  are append-only JSONL.
- `results/` is only for publishable snapshots copied out of `workspace/`.
- The current checked-in hosted smoke snapshot is
  `results/cadybara_online_smoke_reps2/20260606_163617_windows/`.
- Runtime logs, `.log`, `.err`, caches, checkpoints, and local model state are
  not source.
- Failed CadQuery, missing `result`, provider errors, parse failures, and
  render failures are experiment data. Do not patch them into successes after
  the fact.

## Documentation Map

- `COMMON.md` explains shared concepts and cross-project dataflow contracts.
- `docs/HOSTED_CADYBARA_API.md` records the current state of the public hosted
  Cadybara API investigation.
- Root `AGENTS.md` gives repository-wide agent rules.
- Each active project has its own `README.md` and `AGENTS.md`.
- `projects/cad-diffusion/HANDOFF.md` is the detailed cold-start guide for the
  CAD-native diffusion work.
- `AGENT_STARTING_PROMPTS.md` is optional. It is a launch-pad for splitting
  work among project/workstream agents, not the canonical source of truth.
