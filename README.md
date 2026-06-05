# Cadybara Monorepo

Cadybara is a local-first AI CAD research workspace. The repo is split into
four active projects that work together, plus one parked area for preserved old
research.

The short version:

1. A YAML config defines models, prompts, temperatures, repetitions, and output
   paths.
2. `projects/local-running/` turns that config into deterministic run cells,
   sends prompts to Ollama or the dry-run provider, and appends JSONL rows.
3. For CadQuery runs, model output is executed as written. Valid products get
   STL/STEP/PNG artifacts; invalid code and render failures remain measured
   failures.
4. `projects/cadybara-online-testing/` serves a small lab API over
   `http.server`, starts/stops runs, tracks progress, queues model pulls, and
   records reviews.
5. `projects/website/` is the static browser experience that calls those lab
   APIs and displays the dashboard, CAD diffusion trainer, and 3D viewer.
6. `projects/cad-diffusion/` owns the CAD-native diffusion experiment: dataset
   prep, token grammar, denoising training, sampling, and evaluation.

For shared terms and dataflow details, read `COMMON.md`.

If you are trying to run against the hosted Cadybara product API rather than
local Ollama, read `docs/HOSTED_CADYBARA_API.md` first. The current
`online_smoke.yaml` is still a local-runner smoke config unless it is explicitly
changed to a hosted provider.

## Active Projects

### `projects/local-running/`

The local Python harness and shared `cadybara` CLI.

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

This is the "stable diffusion for CAD" project direction, but the current code
is not image Stable Diffusion. It is an early CAD-token denoising model.

If you are taking over CAD diffusion work, read
`projects/cad-diffusion/HANDOFF.md`. It contains the current checkpoint/run
state, how to resume training, how sampling/eval should be handled, and the
recommended discriminator framing.

### `projects/cadybara-online-testing/`

The online/lab control plane that sits above local runs.

Owns:

- `http.server` lab server and JSON endpoints
- run start/stop, current worker job state, and progress payloads
- model status and model prefetch jobs
- review score JSONL and rubric grading helpers
- active online smoke configs
- endpoint tests

Use this folder when changing the lab API, run/review workflow, online configs,
or progress semantics. The UI lives in `projects/website/`; the execution
engine lives in `projects/local-running/`.

### `projects/website/`

The browser-facing Cadybara experience.

Owns:

- static landing page and demo localStorage auth
- project dashboard
- CAD diffusion training page
- static image/sprite assets
- Three.js-based 3D viewer
- old local logs that should not become source

The lab server serves this folder at `/lab/` and `/viewer/`.

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
online smoke config currently points at local Ollama, so it needs local Ollama
and the named model installed. A hosted API smoke test should be introduced as
a provider/config change, not by bypassing the runner.

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

## Data Rules

- Live generated data belongs under project `workspace/` folders, which are
  ignored.
- Runs, grades, review scores, model pull manifests, and CAD diffusion samples
  are append-only JSONL.
- `results/` is only for publishable snapshots copied out of `workspace/`.
- Runtime logs, `.log`, `.err`, caches, checkpoints, and local model state are
  not source.
- Failed CadQuery, missing `result`, provider errors, parse failures, and
  render failures are experiment data. Do not patch them into successes after
  the fact.

## Documentation Map

- `COMMON.md` explains shared concepts and cross-project dataflow.
- `docs/HOSTED_CADYBARA_API.md` records the current state of the public hosted
  Cadybara API investigation.
- Root `AGENTS.md` gives repository-wide agent rules.
- Each active project has its own `README.md` and `AGENTS.md`.
- `projects/cad-diffusion/HANDOFF.md` is the detailed cold-start guide for the
  CAD-native diffusion work.
- `AGENT_STARTING_PROMPTS.md` is optional. It is a launch-pad for splitting
  work among four agents, not the canonical source of truth.
