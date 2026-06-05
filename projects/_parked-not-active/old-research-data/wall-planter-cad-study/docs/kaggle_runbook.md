# Kaggle Wall Planter Runbook

Use this when the laptop should not run models locally. Kaggle becomes the
temporary Ollama host, and the harness writes the same append-only JSONL data
under `/kaggle/working/cadybara_outputs/`.

## What To Run First

Run one heavy vision model per Kaggle notebook/session. Do not add text-only
coder/chat models to this config; rounds 2 and 3 send a render image back to the
model, so every entry must accept image input. The default runner now uses:

- `qwen3-vl:32b`
- `qwen2.5vl:32b`
- `gemma3:27b`
- `llava:34b`
- `llama3.2-vision:90b`

Start with `qwen3-vl:32b` or `qwen2.5vl:32b`. Try `gemma3:27b` next for a
different family. Treat `llama3.2-vision:90b` as a stretch attempt; it may fail
on free Kaggle hardware, but it is isolated when run as its own chunk.

## Kaggle Setup

1. Create a Kaggle notebook.
2. Settings: turn **Internet** on and choose a **GPU** accelerator.
3. Upload this repository as a Kaggle Dataset, or clone it into
   `/kaggle/working/cadybara`.
4. In the first notebook cell, choose exactly one model and run:

```bash
%cd /kaggle/working/cadybara
%env KAGGLE_MODEL_NAMES=qwen3-vl:32b
%env KAGGLE_EXPERIMENT_ID=wall_planter_kaggle_qwen3vl_32b_001
!python projects/remote-kaggle-runs/scripts/kaggle_wall_planter_runner.py
```

The script installs the repo, installs/starts Ollama, pulls the selected models,
runs the harness, and writes:

- `/kaggle/working/cadybara_outputs/<experiment_id>/results.jsonl`
- `/kaggle/working/cadybara_outputs/<experiment_id>/artifacts/`
- `/kaggle/working/cadybara_kaggle_outputs.zip`

It refreshes the zip after every JSONL row so the live session has a recent
checkpoint. For durable Kaggle output, use **Save Version / Run All** and keep
each chunk short enough to finish before the notebook limit.

## One-Model Chunks

The heavy config refuses to run unless `KAGGLE_MODEL_NAMES` is set. That keeps
Kaggle from spending the whole session downloading every large model before any
results are written.

```bash
%cd /kaggle/working/cadybara
%env KAGGLE_MODEL_NAMES=qwen2.5vl:32b
%env KAGGLE_EXPERIMENT_ID=wall_planter_kaggle_qwen25vl_32b_001
!python projects/remote-kaggle-runs/scripts/kaggle_wall_planter_runner.py
```

```bash
%cd /kaggle/working/cadybara
%env KAGGLE_MODEL_NAMES=gemma3:27b
%env KAGGLE_EXPERIMENT_ID=wall_planter_kaggle_gemma3_27b_001
!python projects/remote-kaggle-runs/scripts/kaggle_wall_planter_runner.py
```

If Kaggle disk gets tight inside a long interactive session, add:

```bash
%env KAGGLE_REMOVE_MODEL_AFTER=1
```

The safest pattern is still one fresh committed notebook version per heavy
model.

For a smoke test:

```bash
%env KAGGLE_MODEL_NAMES=qwen3-vl:32b
%env KAGGLE_LIMIT=3
%env KAGGLE_EXPERIMENT_ID=wall_planter_kaggle_heavy_smoke_001
!python projects/remote-kaggle-runs/scripts/kaggle_wall_planter_runner.py
```

If the heavy model cannot load on the assigned Kaggle GPU, switch to the smaller
fallback config explicitly:

```bash
%env CADYBARA_CONFIG=/kaggle/working/cadybara/projects/wall-planter-cad-study/configs/kaggle_vision_repair.yaml
%env KAGGLE_MODEL_NAMES=llama3.2-vision:11b
%env KAGGLE_EXPERIMENT_ID=wall_planter_kaggle_llama32vision_11b_001
!python projects/remote-kaggle-runs/scripts/kaggle_wall_planter_runner.py
```

Download `cadybara_kaggle_outputs.zip` from the notebook output, unzip it into
the local repo, and grade the resulting run directory with `cadybara grade`.
