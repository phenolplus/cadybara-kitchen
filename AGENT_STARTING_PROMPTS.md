# Agent Starting Prompts

These are optional launch prompts for splitting work across the active
projects and benchmark workstreams. They are not the source of truth. Each
agent should first read root `AGENTS.md`, root `COMMON.md`, and the `README.md`
plus `AGENTS.md` in their assigned project folder.

Each assignment is project-local by default. The folders share contracts, but
they are not one combined project. Only edit another folder when the assigned
project's public interface truly requires a paired change.

If an assignment mentions hosted Cadybara API, public Cadybara API, or running
"online not local", that agent must also read `docs/HOSTED_CADYBARA_API.md`.
The current `cadybara-online-testing` project is the local lab control plane,
not an already-implemented hosted API client.

## Agent 1: Local Running

You are working in `projects/local-running/`.

Your job is to improve the local Cadybara runner: the shared `cadybara` CLI,
config loading, deterministic run cells, resume/retry behavior, Ollama and
dry-run providers, CadQuery export, JSONL records, model queue, worker scripts,
archive behavior, and training-pair export.

If the goal is hosted Cadybara API testing, this agent owns the provider
adapter work after the official request/response schema is known.

Stay inside `projects/local-running/` unless a shared CLI contract, import path,
or test requires a narrow coordinated edit elsewhere. Preserve append-only JSONL
behavior, config hash protection, deterministic resume keys, and the rule that
bad model-written CAD remains data.

Start by reading:

- `AGENTS.md`
- `COMMON.md`
- `projects/local-running/README.md`
- `projects/local-running/AGENTS.md`

Run focused tests with:

```bash
pytest projects/local-running/tests -q -p no:cacheprovider
```

## Agent 2: CAD Diffusion

You are working in `projects/cad-diffusion/`.

Your job is to improve the CAD-native diffusion experiment: Fusion-style
dataset prep, supported CAD program extraction, token grammar, denoising model
training, sampling, token-to-CadQuery compilation, generated sample artifacts,
and evaluation.

Treat this as CAD-token diffusion v0, not finished image Stable Diffusion for
CAD. Do not patch generated samples after the fact to make them valid. Keep
datasets, checkpoints, sample runs, and logs in ignored workspace paths.

Start by reading:

- `AGENTS.md`
- `COMMON.md`
- `projects/cad-diffusion/README.md`
- `projects/cad-diffusion/AGENTS.md`

Run focused tests with:

```bash
pytest projects/cad-diffusion/tests -q -p no:cacheprovider
```

## Agent 3: Cadybara Online Testing

You are working in `projects/cadybara-online-testing/`.

Your job is to improve the lab control plane: the local HTTP lab server,
run/model endpoints, CAD diffusion training endpoints, current worker job state,
weighted progress payloads, review queues, grading helpers, and active online
configs.

If the goal is hosted Cadybara API testing, this agent owns the config/status
and lab UX around the provider, not the provider HTTP client itself.

Do not duplicate runner logic from `projects/local-running/`. Do not redesign
the static UI from this folder unless an endpoint change requires a paired
website update. Keep run data, review scores, and grades append-only.

Start by reading:

- `AGENTS.md`
- `COMMON.md`
- `projects/cadybara-online-testing/README.md`
- `projects/cadybara-online-testing/AGENTS.md`

Run focused tests with:

```bash
pytest projects/cadybara-online-testing/tests -q -p no:cacheprovider
```

## Agent 4: Website

You are working in `projects/website/`.

Your job is to improve the browser-facing Cadybara experience: static landing
page, demo auth, project dashboard, CAD diffusion training page, lab assets,
vanilla JS behavior, and the Three.js viewer.

Keep the frontend vanilla. Do not add React, Vue, Vite, Next, or another build
step. Preserve the bright blue/green Cadybara direction and use real assets for
sprite-like visuals. Coordinate API expectations with online-testing.

Start by reading:

- `AGENTS.md`
- `COMMON.md`
- `projects/website/README.md`
- `projects/website/AGENTS.md`

After UI changes, serve locally with:

```bash
cadybara lab --port 8790
```

Then inspect `/lab/`, `/lab/dashboard.html`, `/lab/cad-diffusion.html`, and
`/lab/voxel-diffusion.html`, `/lab/hosted-review.html`, and `/viewer/`.

## Agent 5: Direct Codex Benchmark

You are working in `projects/codex-direct-testing/`.

Your job is to maintain the manual Codex-in-this-thread benchmark lane: prompt
copies, direct CadQuery source written interactively by Codex, the artifact
packager, and tests that keep the packaged rows comparable with normal
Cadybara runs.

This is not online testing, not hosted Cadybara API testing, and not a provider
adapter. Keep generated workspace outputs ignored. If you add or rerun manual
baselines, make the protocol explicit so the team knows whether it was
single-shot or allowed repair iterations.

Start by reading:

- `AGENTS.md`
- `COMMON.md`
- `projects/codex-direct-testing/README.md`
- `projects/codex-direct-testing/AGENTS.md`

Run focused tests with:

```bash
pytest projects/codex-direct-testing/tests -q -p no:cacheprovider
```

## Shared Finish Line

Before handing off broad changes, run:

```bash
pytest -q -p no:cacheprovider
git diff --check
```
