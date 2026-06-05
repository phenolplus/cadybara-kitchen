# Senior Dev Handoff: Cadybara

Prepared as a current engineering handoff for the active repository. This file
intentionally replaces older documentation-only, React/FastAPI/SQLite guidance.
The live project is a local-first Python/CadQuery/JSONL research workspace with
a small vanilla browser lab.

## Executive Summary

Cadybara is a local AI-CAD research system. It currently has two active
research directions:

1. The M1/M2 local runner: compare CAD-generating model behavior across prompts,
   models, repetitions, and review/grade flows.
2. CAD diffusion: train a CAD-native token denoising model over simple sketch
   and extrude programs.

The repository has already moved past the original bootstrap docs. There is a
runnable CLI, tests, a local HTTP lab server, static UI pages, CadQuery artifact
export, append-only JSONL records, model-pull helpers, review/grade flows, and
CAD diffusion training endpoints.

The locked stack is:

- Python 3.11+
- Typer CLI
- Pydantic v2 config/records
- CadQuery for CAD execution/export
- JSONL for run, review, grade, and sample records
- Python `http.server` for the local lab API
- vanilla HTML/CSS/JS for the UI
- optional PyTorch for CAD diffusion only

Do not introduce FastAPI, SQLAlchemy, React, Vue, or a frontend build step
unless Arvin explicitly changes direction.

## Current Layout

Active projects:

- `projects/local-running/`
  - importable `cadybara` package and CLI
  - config loading, deterministic runner, Ollama/dry-run providers
  - CadQuery artifact export
  - model queue and worker scripts
  - local tests
- `projects/cad-diffusion/`
  - `cadybara_cad_diffusion` package
  - v0 CAD program schema and token grammar
  - Fusion-style dataset prep
  - PyTorch denoising training
  - sampling, CadQuery compilation, evaluation
  - detailed handoff in `projects/cad-diffusion/HANDOFF.md`
- `projects/cadybara-online-testing/`
  - local lab server/API
  - background run/model/CAD-training jobs
  - progress, review, and grading helpers
  - endpoint tests
- `projects/website/`
  - static landing/dashboard/CAD-diffusion UI
  - Three.js viewer
  - assets and local UI logs
- `projects/_parked-not-active/`
  - preserved old wall-planter data, Kaggle experiments, sandbox archives, and
    obsolete design docs

Packaging currently includes three Python packages from `pyproject.toml`:

- `projects/local-running/cadybara`
- `projects/cad-diffusion/cadybara_cad_diffusion`
- `projects/cadybara-online-testing/cadybara_online_testing`

## Repository Rules That Matter

- Runs, reviews, grades, pull manifests, and CAD diffusion samples are
  append-only JSONL.
- Config hashes intentionally protect run files from accidental mixed regimes.
- Failed model output is data. Invalid CadQuery, missing `result`, unsupported
  CAD programs, parse failures, compile failures, and render failures should be
  recorded, not repaired.
- Generated workspace data is ignored but valuable. Do not delete or rewrite it
  without an explicit request.
- Parked data is history. Do not let old sandbox docs steer new work.

## Local Runner

The local runner takes a YAML config and expands it into deterministic run
cells:

```text
models x prompt seeds x strategy variants x temperatures x repetitions
```

It writes `RunRecord` rows to JSONL. For CadQuery mode, a cell is complete only
when a valid STL artifact exists and there is no render error. Failed attempts
can be followed by later attempts until `max_attempts_per_cell` is exhausted.

Important files:

- `projects/local-running/cadybara/config.py`
- `projects/local-running/cadybara/runner.py`
- `projects/local-running/cadybara/providers/`
- `projects/local-running/cadybara/cadquery_runner.py`
- `projects/local-running/tests/`

Useful commands:

```bash
cadybara run --dry-run projects/local-running/configs/example.yaml
cadybara cad-smoke
cadybara model-status
cadybara pull-models --limit 1
```

## Lab And Website

The lab server lives in online-testing and serves the static website:

```bash
cadybara lab --host 127.0.0.1 --port 8788
```

Main URLs:

- `http://127.0.0.1:8788/lab/`
- `http://127.0.0.1:8788/lab/dashboard.html`
- `http://127.0.0.1:8788/lab/cad-diffusion.html`
- `http://127.0.0.1:8788/viewer/`

Important CAD diffusion endpoints:

- `GET /api/cad-diffusion/status`
- `POST /api/cad-diffusion/train/start`
- `POST /api/cad-diffusion/train/stop`

The lab uses in-process background threads, not a distributed queue. Stop
requests are cooperative: the current generation/training step may complete,
then the job writes final state.

## CAD Diffusion

CAD diffusion is the most active forward-looking direction. Read
`projects/cad-diffusion/HANDOFF.md` before touching it.

Current v0 language:

- millimeter units
- rectangle/circle extrude operations
- `new`, `join`, and `cut` modes
- first op cannot be `cut`
- strict `ENDOP` and `<EOS>` boundaries
- `max_len = 256`

Current default lab training target:

```text
projects/cad-diffusion/workspace/models/cad_diffusion_validity_20260602
```

The prepared token dataset has been observed as:

- `2974` train examples
- `737` test examples
- `3711` supported total examples

During this handoff pass, I restarted the lab on port `8788`, resumed training
from `checkpoint_step_011400.pt`, and observed this first fresh resumed
checkpoint:

```text
checkpoint_step_011425.pt
```

Do not assume that is still the latest; training may have moved far beyond it.
Check disk and/or the lab status API.

The research framing I recommend is:

```text
generator -> hard validity gate -> discriminator/scorer -> guided selection
```

For our system, the discriminator should begin as a transparent score vector:
validity, CAD-likeness, usefulness, novelty, constraint satisfaction, and
manufacturability. Start with validity, CAD-likeness, and novelty before adding
text-prompt alignment.

## Verification Snapshot

On June 5, 2026, I ran:

```bash
python -m pytest projects/cad-diffusion/tests projects/cadybara-online-testing/tests projects/local-running/tests/test_config.py -q -p no:cacheprovider
```

Result:

```text
21 passed
```

Then I ran:

```bash
python -m pytest -q -p no:cacheprovider
```

Result:

```text
56 passed
```

After the tests, I restarted the lab on port `8788`, resumed CAD diffusion
training from `checkpoint_step_011400.pt`, and observed
`checkpoint_step_011425.pt` written with the 25-step checkpoint cadence.

## How I Would Continue

1. Resume or start the CAD diffusion trainer only after checking whether a lab
   process is already running. Avoid duplicate trainers.
2. Sample from multiple checkpoints and compare parse/compile/render validity,
   uniqueness, and nearest-neighbor distance.
3. Add grammar-constrained sampling. This should be declared decoding, not
   silent repair.
4. Add a discriminator report file for CAD diffusion sample runs.
5. Expand the CAD language only after failure analysis shows which missing
   features matter most.
6. Keep docs honest and current. If a future agent changes defaults, checkpoint
   folders, endpoints, or run policy, update this handoff and the relevant
   project README in the same change.

The project is strongest when it stays empirical: make the system run, record
what actually happened, preserve failures, and let measurements decide the next
move.
