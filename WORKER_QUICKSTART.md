# Worker Quickstart

This file is for a separate always-on computer whose job is to run experiments,
save CAD products, and push findings back to GitHub without changing source code.

## What The Worker Does

Input:

- YAML config, usually `configs/pilot_local.yaml`
- Local Ollama models
- The prompt ladder in the config

Output:

- Append-only JSONL rows under `workspace/`
- Per-run CAD artifact folders under `workspace/artifacts/`
- `model.py`, `model.stl`, `model.step`, metadata, raw model output, and prompts
- Optional manual review scores under `workspace/reviews/`

Publish:

- Copies findings into `results/<experiment>/<timestamp_machine>/`
- Creates a new Git branch named like `results/wall_planter_pilot_001/<machine>-<timestamp>`
- Commits only that result snapshot
- Pushes that branch to GitHub

It should not edit application code.

## One-Time Setup On The Worker

Install these first:

- Git
- Python 3.11 or newer
- Ollama

Clone the repo:

```powershell
git clone https://github.com/phenolplus/cadybara-kitchen.git
cd cadybara-kitchen
```

Run setup on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/worker_setup.ps1
```

Run setup on macOS/Linux:

```bash
bash scripts/worker_setup.sh
```

The setup script creates `.venv`, installs this project, runs tests, checks
Ollama, and pulls the configured model queue.

## Start The Worker UI

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/worker_start_lab.ps1
```

macOS/Linux:

```bash
bash scripts/worker_start_lab.sh
```

Open the printed URL. From another computer on the same network, use:

```text
http://WORKER_IP_ADDRESS:8787/lab/
```

Click `Start Real Run`. The run asks local models for CadQuery code, exports
STL/STEP products, and saves everything. Use `Stop After Current` to pause
without losing completed rows.

## Headless Run

If you do not need the UI:

```powershell
.\.venv\Scripts\cadybara.exe run configs/pilot_local.yaml
```

or:

```bash
.venv/bin/cadybara run configs/pilot_local.yaml
```

The CLI resumes from the JSONL if interrupted.

## Publish Findings To GitHub

After the run, publish the results snapshot:

```powershell
.\.venv\Scripts\python.exe scripts/worker_publish_results.py --config configs/pilot_local.yaml
```

or:

```bash
.venv/bin/python scripts/worker_publish_results.py --config configs/pilot_local.yaml
```

The script refuses to publish if tracked source files are modified. It stages
only the copied `results/...` folder, commits it, and pushes a new branch to
GitHub. It does not commit `workspace/` directly.

If pushing fails, the worker probably is not authenticated with GitHub. Fix
GitHub auth on that machine, then run the same publish command again. The
safest options are GitHub Desktop, Git Credential Manager, or `gh auth login`.

Use this if you want to inspect the commit before pushing:

```powershell
.\.venv\Scripts\python.exe scripts/worker_publish_results.py --config configs/pilot_local.yaml --no-push
```

## If Something Looks Wrong

Check the worker state:

```powershell
git remote -v
git status --short
.\.venv\Scripts\cadybara.exe model-status
.\.venv\Scripts\cadybara.exe inspect workspace/wall_planter_pilot_001.jsonl
```

The expected remote is:

```text
https://github.com/phenolplus/cadybara-kitchen.git
```
