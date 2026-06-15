# AGENTS.md

Guidance for coding agents working in this repository.

Start with this file, then read `COMMON.md`, then read the `README.md` and
`AGENTS.md` inside the project folder you are touching.

If the task mentions "online" or "Cadybara API", also read
`docs/HOSTED_CADYBARA_API.md`. In this repo, `cadybara-online-testing` currently
means the local lab control plane unless a task explicitly says hosted
`api.cadybara.com`.

## Current Architecture

- The active repo has separate projects that share one repository. Do not treat
  them as one combined app just because a feature crosses folders.
- The four core projects are `projects/local-running/`,
  `projects/cad-diffusion/`, `projects/cadybara-online-testing/`, and
  `projects/website/`.
- `projects/codex-direct-testing/` is an active benchmark sandbox for manual
  Codex-in-this-thread CAD baselines. It is not online testing and it is not a
  provider API.
- `projects/cadgenbench/` is an external CADGenBench submodule. Treat it as a
  separate upstream project, not Cadybara-owned source.
- The live M1/M2 harness is Python + Typer + JSONL + CadQuery + a small
  `http.server` lab + vanilla HTML/CSS/JS.
- Ignore old React/FastAPI/SQLite notes in parked sandbox archives when
  implementing current tasks.
- Do not introduce FastAPI, SQLAlchemy, React, Vue, or a frontend build step
  unless a future milestone explicitly reverses this.
- Do not depend on handoff docs for current truth. Read the code and the
  project docs instead.

## Locked Stack

- Python 3.11+
- hatchling `pyproject.toml`
- Runtime deps: CadQuery, httpx, pydantic v2, PyYAML, Typer, Rich
- Test deps: pytest, respx
- Optional CAD token diffusion training dep: PyTorch behind the `cad-diffusion`
  extra
- Optional voxel diffusion deps: PyTorch, NumPy, trimesh, scikit-image, and
  SciPy behind the `voxel-diffusion` extra
- Frontend: vanilla HTML/CSS/JS served directly from `projects/website/lab/`
  and `projects/website/viewer/`
- Optional charting: uPlot only, and only when genuinely needed

## Project Boundaries

- Each folder under `projects/` is a project boundary. It should have its own
  `README.md`, `AGENTS.md`, focused tests, ignored `workspace/` data, and
  contribution rules.
- `projects/local-running/` owns the shared `cadybara` CLI, config schema,
  providers, runner, CadQuery artifact path, model queue, worker scripts, and
  local tests.
- `projects/cad-diffusion/` owns CAD-token dataset prep, grammar, training,
  sampling, voxel diffusion, generated sample artifacts, and evaluation.
- `projects/cadybara-online-testing/` owns the lab server, endpoint contracts,
  progress payloads, current worker job state, review scores, and grading
  helpers.
- `projects/codex-direct-testing/` owns direct Codex-written baseline CAD
  source, prompt copies, and its own ignored workspace outputs.
- `projects/website/` owns the static browser UI and assets, including hosted
  review and CAD/voxel diffusion pages. It can rely on lab APIs, but it should
  not duplicate Python runner logic.
- `projects/cadgenbench/` is a submodule pointer to
  `https://github.com/huggingface/cadgenbench.git`. Do not edit it for ordinary
  Cadybara work; use a separate CADGenBench branch/PR plan for upstream changes.
- `projects/_parked-not-active/` is preserved history. Do not reactivate,
  delete, or rewrite it unless explicitly asked.

Hosted Cadybara product API work should start at the provider boundary in
`projects/local-running/`, then use online-testing configs/lab status as the
consumer. Do not hard-code hosted API calls directly into the lab server.

Cross-project edits are allowed when an explicit public contract needs to move,
but keep them narrow. Update the docs/tests for every project whose contract
changed, and leave unrelated project internals alone.

CADGenBench integration work should start as an export/adapter design in
Cadybara docs. Do not claim Cadybara can submit to CADGenBench until an actual
exporter and tests exist.

## Research Principles

- The harness does not silently repair model output.
- Invalid CadQuery source, failed imports, missing `result`, parse failures,
  unsupported CAD programs, and render failures are data points.
- Record failures clearly; do not make model output look better by patching it
  after generation.
- Mesh/STL rendering is useful for reference, but M2 grading is based on
  source-code rubric scores.
- CAD diffusion v0 is a CAD-token denoising experiment over simple extrude
  programs. Do not describe it as finished full Stable Diffusion for CAD.
- Voxel diffusion is a geometry-native experiment over normalized occupancy
  grids. Do not describe it as parametric CAD recovery or text-to-CAD.

## Data Integrity

- Runs are append-only JSONL.
- Grades and review scores are append-only JSONL.
- Preserve deterministic resume keys and config hashes.
- Do not delete or rewrite existing `workspace/` baseline data unless the
  researcher explicitly asks.
- Config mismatch protection is intentional; do not weaken it for convenience.
- Runtime logs and local generated outputs should stay ignored, not committed
  as source.

## Visual Asset Direction

- For pixel-art UI in `projects/website/lab/`, create or use real sprite/image
  assets first; do not fake key visual elements with CSS gradients when the
  design calls for sprites.
- Keep generated sprite sheets and extracted sprites in
  `projects/website/lab/assets/` so the app can reuse them across screens.
- The Cadybara aesthetic should stay bright, clean, blue/green, mossy, and
  lively like the landing page. Avoid dark, muddy, glassy, or generic
  game-button styling.

## Important Paths

- Shared concepts: `COMMON.md`
- Hosted product API notes: `docs/HOSTED_CADYBARA_API.md`
- Active local runner configs: `projects/local-running/configs/`
- Active online testing configs: `projects/cadybara-online-testing/configs/`
- Direct Codex baseline sandbox: `projects/codex-direct-testing/`
- CAD diffusion data/checkpoints/runs: `projects/cad-diffusion/workspace/`
- Parked old research data: `projects/_parked-not-active/old-research-data/`
- Live runs: `projects/<project-name>/workspace/runs/<experiment_id>/`
- Result snapshots for sharing: `results/<experiment_id>/<timestamp_machine>/`
- Current hosted smoke snapshot:
  `results/cadybara_online_smoke_reps2/20260606_163617_windows/`
- CADGenBench integration note: `docs/CADGENBENCH_INTEGRATION.md`

## Verification

Use focused tests for the project you touched, then run the full suite when the
change could affect shared behavior:

```bash
pytest -q -p no:cacheprovider
```

For docs-only changes, also run:

```bash
git diff --check
```
