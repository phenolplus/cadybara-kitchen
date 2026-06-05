# AGENTS.md - Local Running

You are in the local execution project. Keep changes focused on the Python CLI,
runner, providers, CadQuery export, model queue, worker scripts, and local tests.

## Read First

- Root `AGENTS.md`
- Root `COMMON.md`
- `projects/local-running/README.md`
- `projects/local-running/cadybara/runner.py`
- `projects/local-running/cadybara/cadquery_runner.py`
- `projects/local-running/cadybara/model_queue.py`

## Boundaries

- This project owns the shared `cadybara` CLI.
- This project owns model provider adapters. If the task is hosted Cadybara API
  integration, read `../../docs/HOSTED_CADYBARA_API.md` and add a provider here
  rather than wiring hosted calls into online-testing.
- It may import the CAD diffusion and online testing packages for CLI
  subcommands, but do not move their core logic here.
- Do not duplicate lab-server behavior from `projects/cadybara-online-testing/`.
- Do not edit static UI files in `projects/website/` unless a CLI or API
  contract change requires a narrow paired update.
- Do not reactivate parked wall-planter or Kaggle code.

## Rules For Runner Work

- Preserve append-only JSONL writes.
- Preserve deterministic resume keys.
- Preserve config hash mismatch protection.
- Do not silently repair model-written CadQuery.
- Keep provider failures and render failures as recorded data.
- A CadQuery run cell is complete only when it has no render error and has an
  STL artifact.
- Visual repair rounds must retain parent and feedback lineage fields.

## Rules For Model Queue Work

- Treat local model deletion as sensitive. Keep `CADYBARA_DISABLE_MODEL_CLEANUP`
  behavior intact.
- Keep model pull state and manifests in ignored workspace paths.
- Prefer actual Ollama tag discovery over stale saved state when reporting
  installed models.

## Worker Setup Contract

The root `setup_worker.sh` is the canonical setup path for Arvin's Linux Mint
T430s worker. Before changing it, read root `WORKER_QUICKSTART.md`.

Preserve these worker expectations:

- user-owned checkout at `~/cadybara-kitchen`
- `.venv` inside the repo
- `systemctl --user` lab service plus lingering
- Avahi `.local` discovery and SSH for LAN access
- Cadybara lab bound to `0.0.0.0:8787`
- Ollama bound only to `127.0.0.1:11434`
- `OLLAMA_NUM_PARALLEL=1`
- no automatic model cleanup
- no automatic model pull when starting a worker run
- idempotent reruns that preserve `workspace/` and `~/.ollama`

The worker should print both `http://cadybara-worker.local:8787/lab/` and the
current IP URL. The raw Ollama API should not be reachable from the laptop.

## Tests

For local changes:

```bash
pytest projects/local-running/tests -q -p no:cacheprovider
```

For shared CLI or record behavior:

```bash
pytest -q -p no:cacheprovider
```
