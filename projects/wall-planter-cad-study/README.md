# Wall Planter CAD Study

This is Arvin's wall-planter prompt-sensitivity project inside
`cadybara-kitchen`.

The shared harness lives at the repository root. This folder owns the actual
study setup: prompt ladder, model-family sweep config, review protocol, and
worker instructions for running the study on another computer.

## Research Question

When the design intent is the same but the prompt becomes more specific, how do
local model families and sizes affect the quality of generated CAD products?

This study varies two primary factors:

- Prompt detail level: 10 wall-planter prompts from minimal to fully specified.
- Model: Qwen 2.5, Qwen 2.5 Coder, and Llama 3.2 across multiple sizes.

The output target is not design advice. The output target is CadQuery Python
code that the harness converts into STL/STEP products for 3D review.

## Canonical Config

Use this config:

```text
projects/wall-planter-cad-study/configs/family_sweep.yaml
```

Current design:

```text
10 prompts x 10 models x 5 repetitions x 1 temperature = 500 generations
```

Each run creates a numbered folder:

```text
workspace/runs/wall_planter_family_sweep_001/
workspace/runs/wall_planter_family_sweep_002/
workspace/runs/wall_planter_family_sweep_003/
```

Each numbered folder contains:

- `config.yaml` - exact config used for that run
- `results.jsonl` - append-only run records
- `artifacts/` - per-row prompt, raw output, extracted CadQuery, STL/STEP, metadata

## Run Locally

Preflight the CAD/export path and one fast real Ollama generation:

```powershell
cadybara cad-smoke
cadybara run projects/wall-planter-cad-study/configs/smoke_fast.yaml --limit 1
```

Run the fast smoke command a second time to confirm resume; it should skip the
already-written row instead of appending a duplicate.

Start the lab:

```powershell
cadybara lab
```

Then open:

```text
http://127.0.0.1:8787/lab/
```

Click `Start Real Run`. Use `Stop After Current` if you need to pause. Starting
again resumes from completed rows in the run's JSONL. If the lab restarts after
a partial run, it resumes the latest incomplete numbered folder. Once a run is
complete, the next start creates the next numbered folder.

Headless:

```powershell
cadybara run projects/wall-planter-cad-study/configs/family_sweep.yaml
```

## Review

After rows exist, click `Review Products` in the lab. Score products from 1-10.
Keyboard `1`-`9` records that score; `0` records 10.

Scores append to:

```text
workspace/reviews/<experiment_id>_reviews.jsonl
```

## Worker Computer

For an always-on worker, follow the repository-level `WORKER_QUICKSTART.md`.
The worker should run this project config and publish findings to a results
branch without modifying source code.
