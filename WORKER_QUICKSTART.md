# Cadybara Worker Quickstart

This file is the operator handoff for Arvin's dedicated local compute box.
Future agents should read this before changing worker setup, lab connectivity,
model pulling, or run-resume behavior.

The worker is not a normal dev laptop. It is a slow, always-on LAN machine whose
job is to keep Cadybara cooking while Arvin's main computer stays usable.

## Target Machine

The intended worker is a ThinkPad T430s running Linux Mint 22.3 Cinnamon after
reflash:

- CPU: Intel i5-3320M, 2 physical cores / 4 threads, Ivy Bridge, AVX1, no AVX2
- RAM: about 7.7 GB usable
- GPU: none for inference
- Disk: Intel 520-series 180 GB SSD, roughly 150 GB usable after OS
- Inference: local Ollama only
- Network: same home LAN as Arvin's laptop

Those specs matter. The machine will page to SSD on larger models and may run
for days. That is acceptable. Do not "protect" it by silently reducing the
experiment unless Arvin asks.

This worker quickstart is for the local-worker path. It is not the hosted
Cadybara product API path. If the goal is to run against
`https://api.cadybara.com`, read `docs/HOSTED_CADYBARA_API.md` first; that
future path needs a hosted provider adapter and `CADYBARA_API_KEY`, not local
Ollama model pulls.

## Operating Model

The worker should be:

- local-first: live data stays on the box under project `workspace/` folders
- resumable: interrupted runs resume from append-only JSONL
- explicit: model pulls happen only when requested
- conservative with storage: never auto-delete Ollama models
- honest: failed CadQuery, bad imports, missing `result`, and render failures
  are data
- LAN-only: browser UI is reachable from the laptop; raw Ollama is not
- hot-running: use all available compute unless a specific A/B test says
  otherwise

The important split is:

- Cadybara lab UI is LAN-facing at port `8787`.
- Ollama stays bound to `127.0.0.1:11434`.
- SSH is enabled for later `rsync` pulls from the laptop.

## Fresh Box Setup

On the freshly flashed Linux Mint worker, install Git, then clone and run the
root setup script:

```bash
git clone GITHUB_URL ~/cadybara-kitchen
cd ~/cadybara-kitchen
bash setup_worker.sh --hostname cadybara-worker
```

Replace `GITHUB_URL` with the real repository URL when setting up the actual
box. Keeping clone + setup as two steps is intentional: Arvin should be able to
open and edit the script before it runs. Do not replace this with `curl | bash`.

To explicitly pull known models during setup:

```bash
bash setup_worker.sh --hostname cadybara-worker --models qwen2.5-coder:1.5b,qwen2.5-coder:7b
```

If the repo is already cloned, rerun:

```bash
cd ~/cadybara-kitchen
bash setup_worker.sh
```

The script is intended to be idempotent. It preserves `workspace/`, `.venv`
when present, and `~/.ollama`. If the git tree is clean, it runs
`git pull --ff-only`; if the tree is dirty, it skips the pull and still
restarts services.

## What `setup_worker.sh` Does

The root setup script:

- installs apt packages: `avahi-daemon`, `build-essential`, `ca-certificates`,
  `curl`, `git`, `iproute2`, `logrotate`, `pciutils`, `python3-dev`,
  `python3-venv`, `openssh-server`, and `ufw`
- optionally sets the hostname, usually `cadybara-worker`
- enables Avahi so the laptop can use `cadybara-worker.local`
- enables SSH for later `rsync` result pulls
- installs Ollama through the official installer when missing
- writes `/etc/systemd/system/ollama.service.d/10-cadybara-worker.conf`
- keeps Ollama local-only with `OLLAMA_HOST=127.0.0.1:11434`
- sets `OLLAMA_NUM_PARALLEL=1`
- creates `.venv` inside the repo and installs the package
- runs a fast health check: imports, config parse, Ollama ping
- writes a user service at `~/.config/systemd/user/cadybara-worker.service`
- enables lingering with `loginctl enable-linger`
- starts the lab service with `systemctl --user`
- writes lab logs to `projects/local-running/workspace/logs/cadybara-worker.log`
- configures logrotate for operational logs
- when `ufw` is available, allows only LAN-scoped TCP `8787` and TCP `22`

Worker service environment:

```text
CADYBARA_OLLAMA_NUM_CTX=4096
CADYBARA_OLLAMA_NUM_THREAD=4
CADYBARA_DISABLE_MODEL_CLEANUP=1
CADYBARA_LAB_DISABLE_AUTO_PULL=1
```

`CADYBARA_OLLAMA_NUM_THREAD=4` is the starting default because the box has four
logical threads. It is not sacred. CPU inference on this chip may be faster at
2 threads than 4; run a small A/B benchmark later and keep the faster setting.

If a future config uses a hosted provider instead of `provider: ollama`, the
Ollama pull/status parts of this worker setup are irrelevant for generation.
The append-only JSONL, CadQuery export, review, resume, and publish rules still
apply.

## Connecting From The Laptop

Preferred URL:

```text
http://cadybara-worker.local:8787/lab/
```

Fallback URL:

```text
http://WORKER_IP_ADDRESS:8787/lab/
```

The setup script prints both. If `.local` does not resolve from the laptop, use
the printed IP and check Avahi/mDNS on the LAN. The raw Ollama API should not be
reachable from the laptop; that is deliberate.

SSH should work as:

```bash
ssh USER@cadybara-worker.local
```

Later, result sync should be pulled from the laptop with `rsync` over SSH. Do
not couple laptop sync into worker boot. The laptop is not always on, and the
worker should keep running without it.

## Services And Logs

Check the Cadybara user service:

```bash
systemctl --user status cadybara-worker.service
journalctl --user -u cadybara-worker.service -f
```

Check the persistent workspace log:

```bash
tail -f projects/local-running/workspace/logs/cadybara-worker.log
```

Check Ollama:

```bash
systemctl status ollama --no-pager
curl http://127.0.0.1:11434/api/version
ollama list
```

If the lab service does not survive logout or reboot, verify lingering:

```bash
loginctl show-user "$USER" | grep Linger
```

It should report `Linger=yes`.

## Running Jobs

Use the lab UI from the laptop for normal operation.

The worker service disables automatic model pulls. If a config references a
missing model, the lab should warn and wait. Pull models explicitly through the
UI or with:

```bash
.venv/bin/cadybara pull-models projects/cadybara-online-testing/configs/online_smoke.yaml
```

or with a custom explicit queue file. This rule protects the 150 GB disk from
surprise multi-GB downloads.

Run behavior:

- one run at a time
- one Ollama request at a time
- append-only JSONL
- Stop After Current asks the running generation to finish, then pauses
- service restart auto-resumes only jobs marked active
- paused jobs stay paused until explicitly started again

Current worker job state lives at:

```text
projects/local-running/workspace/worker/current_job.json
```

That file stores config path, assigned output path, model list, start time,
commit hash, dry-run flag, and status. It is not source. It is ignored
workspace state.

## Smoke Tests

Before trusting a fresh worker for a long run:

```bash
.venv/bin/cadybara cad-smoke
.venv/bin/cadybara run --dry-run projects/local-running/configs/example.yaml
```

`cad-smoke` proves the local CadQuery export path can create STL/STEP. The
dry-run proves config loading, JSONL append, and resume mechanics without
requiring an Ollama model.

When at least one small model is installed:

```bash
.venv/bin/cadybara run projects/cadybara-online-testing/configs/online_smoke.yaml --limit 1
.venv/bin/cadybara run projects/cadybara-online-testing/configs/online_smoke.yaml --limit 1
```

The second command should skip completed work. That is the resume proof.

## Publishing Or Syncing Results

Live runs stay in workspace paths. To publish a GitHub snapshot later:

```bash
.venv/bin/python projects/local-running/scripts/worker_publish_results.py --config projects/cadybara-online-testing/configs/online_smoke.yaml
```

The publish script refuses dirty tracked source by default, creates a results
branch, and stages only the copied `results/...` snapshot.

For local laptop sync, prefer an explicit pull from the laptop:

```bash
rsync -av --progress USER@cadybara-worker.local:~/cadybara-kitchen/projects/cadybara-online-testing/workspace/runs/ ./worker-runs/
```

Adjust the destination path on the laptop as needed. Do not delete worker
workspace data after syncing.

## Storage Policy

- Keep all run JSONL rows.
- Keep failed outputs; they are research data.
- Keep artifacts unless Arvin explicitly asks for cleanup.
- Never auto-delete Ollama models.
- Compress finished runs deliberately as housekeeping, not as an automatic
  service action.
- Runtime logs can rotate; experiment data should not be pruned silently.

## Things Future Agents Must Not Break

- Do not expose Ollama to the LAN.
- Do not replace explicit model pulls with surprise automatic downloads on the
  worker.
- Do not re-enable model cleanup in the worker service.
- Do not weaken config hash mismatch protection.
- Do not rewrite old JSONL rows to make resume easier.
- Do not patch model-written CadQuery into success.
- Do not couple laptop sync to service startup.
- Do not make boot update code from GitHub automatically.

## If Something Looks Wrong

Basic state:

```bash
git remote -v
git status --short
.venv/bin/cadybara model-status
```

Inspect a run:

```bash
.venv/bin/cadybara inspect projects/cadybara-online-testing/workspace/runs/cadybara_online_smoke_001/results.jsonl
```

Inspect current worker job:

```bash
cat projects/local-running/workspace/worker/current_job.json
```

If the lab is unreachable:

```bash
hostname
hostname -I
systemctl --user status cadybara-worker.service
systemctl status avahi-daemon --no-pager
sudo ufw status verbose
```

If Ollama is unreachable locally:

```bash
systemctl status ollama --no-pager
journalctl -u ollama -n 80 --no-pager
curl http://127.0.0.1:11434/api/version
```

## Developer Verification

After changing worker setup, local-running, or lab job state:

```bash
pytest projects/local-running/tests -q -p no:cacheprovider
pytest projects/cadybara-online-testing/tests -q -p no:cacheprovider
pytest -q -p no:cacheprovider
git diff --check
```

On Windows, `bash -n setup_worker.sh` may hang because `bash.exe` is the WSL
launcher. Run shell syntax checks on Linux Mint or a real Bash environment.

### Last Verification From This Documentation Pass

On 2026-06-05, this pass verified the Python behavior and setup-script contract
from the Windows development machine:

```text
python -m pytest projects/local-running/tests -q -p no:cacheprovider
38 passed in 6.63s

python -m pytest projects/cadybara-online-testing/tests -q -p no:cacheprovider
12 passed in 2.32s

python -m pytest -q -p no:cacheprovider
56 passed in 13.06s

git diff --check
no whitespace errors; Windows reported LF-to-CRLF conversion warnings only
```

What this does and does not prove:

- proves local-running and online-testing tests pass with the worker contract
  checks included
- proves current-job state tests pass
- proves the setup script still contains the intended safety fragments
- does not prove `systemctl --user`, Avahi, `ufw`, or Ollama service behavior
  on Linux Mint; that must be tested on the worker itself after reflash
