# Prompt Robustness and Prompt Expansion Research Framework
## Goal: Understanding How Prompt Formulation Affects AI CAD Model Quality

`cadybara-kitchen` is a Python research harness for benchmarking how local
Ollama models respond to semantically similar prompts. Milestone 1 is a
single-researcher CLI workflow: load a YAML config, run each deterministic
experiment cell sequentially, append one JSONL row per generation, and inspect
the results later with pandas or notebooks.

## Install

Requires Python 3.11+.

```bash
pip install -e .
```

For tests:

```bash
pip install -e ".[test]"
pytest -v
```

## Quickstart

Validate the runner without Ollama or network access:

```bash
cadybara run --dry-run configs/example.yaml
```

Run the same command again to verify resume behavior. Existing completed rows
are skipped and no duplicate rows are appended.

Inspect the JSONL output:

```bash
cadybara inspect workspace/smoke_test_001.jsonl
```

Run against a local Ollama model:

```bash
ollama pull qwen2.5:0.5b
cadybara run configs/example.yaml
```

## 3D Viewer

Create a sample part artifact:

```bash
cadybara sample-part
```

Serve the local 3D viewer:

```bash
cadybara view workspace/sample_part.json
```

Open the printed localhost URL to spin, zoom, and inspect the part. The viewer
loads simple JSON part artifacts with boxes, cylinders, and plates with through
holes. This is the first visual judging path; future milestones can connect
model-generated CAD artifacts to the same viewer.

## CAD-Code Runs and Review

For the wall-planter pilot, `configs/pilot_local.yaml` uses
`output_mode: cadquery`. The runner wraps each seed prompt with a CadQuery code
instruction prompt, sends that to Ollama, extracts the returned Python code,
and stores each attempt in its own artifact folder under the numbered run
directory, for example
`workspace/runs/wall_planter_family_sweep_001/artifacts/`.

Each folder keeps the full prompt sent to the model, the original seed prompt,
the raw model output, extracted `model.py`, metadata, and, when rendering
succeeds, `model.stl` and `model.step`. The JSONL row stores provider, model,
prompt id, temperature, repetition, timings, token counts, artifact paths, and
render errors. Earlier text-only outputs are archived separately in
`workspace/archive/`.

Open the lab and use `Review Products` after rows are generated. The review
panel loads the generated STL in the 3D viewer, shows the CadQuery source code,
lets you move forward/backward, and records 1-10 scores; keyboard `1`-`9`
score directly, and `0` records a 10.

While a run is active, use `Stop After Current` to pause the queue after the
current Ollama generation finishes. Already-written JSONL rows and artifact
folders are kept, and starting again resumes from the next incomplete cell.

## Training Export

Convert successful run rows into simple supervised message pairs:

```bash
cadybara export-training workspace/smoke_test_001.jsonl workspace/training_pairs.jsonl
```

Rows with errors or empty outputs are skipped by default. This is a data-prep
step, not model training itself.

## Local Lab and Model Cache

Start the local dashboard:

```bash
cadybara lab
```

Open `http://127.0.0.1:8787/lab/` to see Ollama status, model cache progress,
experiment progress, saved outputs from the JSONL, logs, and a link to the 3D
viewer.

The default model queue is `configs/models_local.yaml`. It pulls Qwen 2.5 first,
then Qwen 2.5 Coder, then Llama, Gemma, Phi, and Mistral comparison models.
Qwen is first because it gives the best early balance for local prompt-quality
experiments: small variants for fast pilots, 7B variants for stronger judging,
and coder variants for future CAD-code artifacts.

Check cache status:

```bash
cadybara model-status
```

Pull the next missing model:

```bash
cadybara pull-models --limit 1
```

Pull one family at a time:

```bash
cadybara pull-models --family qwen2.5
```

The pull state is stored in `workspace/model_queue_state.json`. If the machine
crashes mid-download, restart the command or the lab; Ollama will reuse cached
layers where it can, and already-installed models are skipped.

The lab defaults to `configs/pilot_local.yaml`, a local 500-generation wall
planter family sweep: ten installed models across Qwen 2.5, Qwen 2.5 Coder,
and Llama 3.2; ten seed prompts; one identity strategy; and five repetitions.
Each click of `Start Real Run` creates a numbered folder such as
`workspace/runs/wall_planter_family_sweep_001/` with `results.jsonl`,
`config.yaml`, and generated CAD artifacts. Select `Real run` in the lab before
starting real Ollama generations.

## Dedicated Worker Machine

For large sweeps, run this repo on a spare always-on computer instead of your
daily machine. See `WORKER_QUICKSTART.md` for the exact dumb-runner workflow:
clone, setup, pull models, start the lab on `0.0.0.0`, run the sweep, review
products, and publish findings back to GitHub.

Worker publishing is results-only. The worker writes live outputs to
`workspace/`, then `scripts/worker_publish_results.py` copies JSONL, CAD
artifacts, reviews, and a manifest into `results/...`, creates a new
`results/<experiment>/<machine>-<timestamp>` branch, commits only that snapshot,
and pushes it. It refuses to publish if tracked source files were modified.

## Architecture

The harness is intentionally small: Pydantic config models, a Typer CLI, a
sequential runner, provider adapters, prompt strategies, stub scoring, and JSONL
records. The only implemented strategy is `identity`, which sends the seed
prompt unchanged. The only real provider is Ollama over `httpx`; `--dry-run`
uses an instant local provider that writes `DRY_RUN`.

## Resume and Crash Tolerance

Each row includes a deterministic resume key and a fresh UUID row id. On resume,
malformed JSONL lines are skipped by default with a warning and counted in the
summary; use `--strict-jsonl` to fail fast while debugging. Provider failures
are retried once by default before an error row is written. Use
`--retry-errors` to re-run terminal error rows.

Rows also include a config hash. The runner refuses to append to an existing
JSONL file with a different config hash unless `--allow-config-mismatch` is
provided. This protects against mixing regimes after changing models, base URLs,
sampling, seeds, or strategies.

Ollama seed handling is logged as the sampling seed sent to the provider.
Newer Ollama versions may echo a provider seed, which is stored separately as
`provider_seed`; some backends may ignore seeds silently.

## Scaling Up

Scale by editing the YAML config, not the code. Add models, seeds,
temperatures, and repetitions to grow from a smoke test to a larger sweep.
Output remains append-only JSONL under `workspace/`, which is gitignored.

## License
Please see LICENSE for derivative use of this project.
Please see CLA.md if you wish to contribute to this project.
