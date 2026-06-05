# AGENTS.md - Cadybara Online Testing

You are in the online/lab testing project. Keep changes focused on the local lab
API, run progress, review workflow, grading helpers, CAD diffusion training
control, and online configs.

Read `../../docs/HOSTED_CADYBARA_API.md` if "online" means hosted
`api.cadybara.com`. This folder name is historical/operational; it does not
mean hosted API support already exists.

## Read First

- Root `AGENTS.md`
- Root `COMMON.md`
- `projects/cadybara-online-testing/README.md`
- `projects/cadybara-online-testing/cadybara_online_testing/lab_server.py`
- `projects/cadybara-online-testing/cadybara_online_testing/progress.py`
- `projects/cadybara-online-testing/configs/online_smoke.yaml`

## Boundaries

- Do not duplicate runner logic from `projects/local-running/`. Call existing
  public functions such as `load_config()`, `run_config()`, and
  `read_jsonl_records()`.
- Do not put hosted Cadybara API generation directly in `lab_server.py`; add it
  as a provider in `projects/local-running/` and let this project observe and
  control the resulting runs.
- Do not redesign static UI from this folder unless an API change requires a
  coordinated website update.
- Do not move CAD diffusion training logic here. The training implementation
  belongs in `projects/cad-diffusion/`; this project only controls and reports
  the job.
- Do not reactivate parked wall-planter or Kaggle workflows.

## API Rules

- Keep endpoint responses JSON and cache-disabled.
- Keep run, model-pull, and CAD-diffusion jobs conflict-aware.
- Keep stop behavior cooperative: current generation or training step may
  finish before the job fully stops.
- Keep current worker job state in ignored workspace paths.
- Keep review scores append-only.
- Preserve legacy workspace route mapping unless old artifact links are
  intentionally migrated.

## Worker Job State

The dedicated Linux worker uses this project as the lab control plane. Current
job state is stored at
`projects/local-running/workspace/worker/current_job.json` by
`cadybara_online_testing.lab_server`.

Preserve this behavior:

- starting a real or dry run writes the current-job file
- active jobs auto-resume when the lab service restarts
- Stop After Current marks the job paused, not deleted
- paused jobs do not auto-resume on service startup
- completed jobs clear the current-job file
- error jobs mark the file as `error`
- worker mode can disable automatic model pulls with
  `CADYBARA_LAB_DISABLE_AUTO_PULL=1`

This state is a recovery aid for multi-day sweeps on the slow worker. It is not
a source file and should not be committed.

## Testing Rules

- Endpoint changes need endpoint tests.
- Progress semantics need weighted progress tests.
- Review or grading schema changes need append/load tests.
- Coordinated UI/API changes should also be checked from `projects/website/`.

Run:

```bash
pytest projects/cadybara-online-testing/tests -q -p no:cacheprovider
```

For shared behavior:

```bash
pytest -q -p no:cacheprovider
```
