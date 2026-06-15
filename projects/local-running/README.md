# Local Running

`projects/local-running/` is the execution spine for Cadybara. Its real
providers are local Ollama and the hosted Cadybara Agent API. It owns the
importable `cadybara` package, the shared CLI, provider adapters, CadQuery
artifact generation, JSONL run records, model queue tooling, worker scripts, and
most of the resume/retry logic.

Read the repo-level `COMMON.md` first if the record/artifact flow is new.

This is its own project, not a miscellaneous helper folder. Changes here should
make sense for the runner/CLI/provider layer even when no website or lab UI is
being edited.

## What This Project Owns

- `cadybara/cli.py` exposes the `cadybara` Typer CLI.
- `cadybara/config.py` validates YAML configs and computes config hashes.
- `cadybara/runner.py` expands configs into deterministic cells, resumes
  completed work, retries failures, and appends JSONL rows.
- `cadybara/providers/` contains the dry-run provider, Ollama provider, and
  hosted Cadybara API provider.
- `cadybara/cadquery_runner.py` executes model-written CadQuery as written and
  exports STL/STEP/PNG artifacts when it succeeds.
- `cadybara/model_queue.py` checks, pulls, and tracks local Ollama models.
- `cadybara/training.py` exports successful run rows into supervised
  message-pair JSONL.
- `cadybara/archive.py` copies run folders into the parked archive with a file
  manifest. It does not delete source data.
- `scripts/` contains worker setup/start/publish helpers.
- `configs/` contains the local dry-run smoke config and the local model queue.
- `tests/` covers config loading, records, runner behavior, CadQuery export,
  model queue logic, visual repair, CLI commands, and provider adapters.

## Main Flow

1. A command such as `cadybara run projects/local-running/configs/example.yaml`
   loads an `ExperimentConfig`.
2. The runner builds cells from models, seeds, strategies, temperatures, and
   repetitions. The only current strategy is `identity`, so the seed prompt is
   sent unchanged unless `output_mode: cadquery` wraps it in the CadQuery
   instruction prompt.
3. Each cell gets a deterministic seed and resume key.
4. The provider is chosen per model: `--dry-run` uses `DryRunProvider`;
   `provider: ollama` uses `OllamaProvider` over the local Ollama API; and
   `provider: cadybara_api` uses the hosted Agent API over HTTPS. Hosted
   generation stays here rather than being special-cased in the lab server.
5. The returned text is scored by the current stub scorer and written into a
   `RunRecord`.
6. For CadQuery mode, the record is handed to `write_cadquery_artifacts()`.
   The harness extracts code, checks a small blocklist, executes the code, and
   expects a final `result` object. Hosted Cadybara rows can also carry a
   server-exported STL; that STL is preserved even when local source execution
   records an error.
7. Every attempt is appended to JSONL. A CadQuery cell is complete only when an
   STL artifact exists and there is no render error.

Provider failures, invalid source, missing imports, missing `result`, and render
failures are all preserved as experiment data.

## Important Commands

Install from the repo root:

```bash
pip install -e ".[test]"
```

Dry-run the local config:

```bash
cadybara run --dry-run projects/local-running/configs/example.yaml
```

Inspect JSONL:

```bash
cadybara inspect projects/local-running/workspace/examples/example_dry_run_001.jsonl
```

Smoke-test CadQuery export:

```bash
cadybara cad-smoke
```

Check or pull local Ollama models:

```bash
cadybara model-status
cadybara pull-models --limit 1
```

Export training pairs:

```bash
cadybara export-training INPUT_RESULTS.jsonl OUTPUT_PAIRS.jsonl
```

Start the lab server through the shared CLI:

```bash
cadybara lab --port 8787
```

## Worker Scripts

For a dedicated Linux Mint worker, the root script is the highest-level path:

```bash
bash setup_worker.sh --hostname cadybara-worker
```

Read root `WORKER_QUICKSTART.md` before changing this path. The target machine
is a slow ThinkPad T430s with about 7.7 GB RAM, no GPU, and roughly 150 GB of
usable SSD. The worker is supposed to run hot and resume multi-day sweeps, but
it must never surprise-pull models or auto-delete local Ollama weights.

The root setup script installs system packages and Ollama, creates `.venv`,
installs the repo, keeps Ollama bound to `127.0.0.1`, creates a `systemctl
--user` service for the lab, enables lingering, enables Avahi `.local`
discovery, enables SSH for future `rsync` pulls, and writes worker logs under
`projects/local-running/workspace/logs/`.

Worker service defaults:

- `CADYBARA_OLLAMA_NUM_CTX=4096`
- `CADYBARA_OLLAMA_NUM_THREAD=4`
- `CADYBARA_DISABLE_MODEL_CLEANUP=1`
- `CADYBARA_LAB_DISABLE_AUTO_PULL=1`

The worker service is deliberately LAN-facing only through Cadybara. Ollama
must stay local-only; it has no auth.

The platform-specific helpers in `scripts/` are lower-level manual paths:

- `worker_setup.sh` and `worker_setup.ps1`
- `worker_start_lab.sh` and `worker_start_lab.ps1`
- `worker_publish_results.py`

Publishing copies run outputs into `results/` and refuses dirty source by
default. It does not commit live `workspace/` data directly.

## Current Limits

- Only the `identity` prompt strategy is implemented.
- The scorer is still a stub for automatic scoring.
- Hosted Cadybara API support is implemented for `response_mode: "json"`,
  `"stl"`, and `"sse"`. Use `"sse"` for hosted smoke runs because the
  production load balancer can time out quiet JSON requests around 60 seconds.
  This repo sends `export_format: "stl"` and still prefers JSON/SSE final
  payloads over binary-only STL mode because source-code grading needs
  `generated_code`; hosted STL bytes are preserved separately for visual review.
  See
  `../../docs/HOSTED_CADYBARA_API.md`.
- CadQuery execution is intentionally not repaired or normalized into success.
- Model cleanup can remove configured local Ollama models unless disabled with
  `CADYBARA_DISABLE_MODEL_CLEANUP=1`; worker service setup disables cleanup.
- Generated data belongs in ignored `workspace/` paths.

## Tests

Run local-running tests:

```bash
pytest projects/local-running/tests -q -p no:cacheprovider
```

Run the full repo suite before broad changes:

```bash
pytest -q -p no:cacheprovider
```
