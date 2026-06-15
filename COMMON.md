# Common Cadybara Concepts

This file explains the shared language used by the active projects and
experiment sandboxes.

Shared language is not shared ownership. Each folder under `projects/` remains
its own project with its own README, AGENTS file, tests, and ignored workspace.
Use this file to understand the contracts between projects, not to blur their
boundaries.

## End-to-End Flow

1. A YAML config names the experiment, output paths, models, prompts, strategy,
   temperatures, repetitions, and CAD/output settings.
2. `projects/local-running/cadybara/config.py` validates the config and builds
   a stable config hash. The hash deliberately protects existing JSONL files
   from mixed experiment regimes.
3. `projects/local-running/cadybara/runner.py` expands the config into run
   cells: model x prompt seed x strategy variant x temperature x repetition.
4. Each run cell gets a deterministic sampling seed. If the output JSONL
   already has a complete row for that resume key, the runner skips it.
5. The provider returns model text. Dry-run writes `DRY_RUN`; Ollama calls the
   local Ollama API through `httpx`; hosted Cadybara calls
   `POST /api/agent/generate` through the `cadybara_api` provider.
6. For `output_mode: cadquery`, the model text is treated as CadQuery source.
   The harness extracts source, executes it, and exports STL/STEP/PNG artifacts
   only when the code works.
7. Every attempt is appended as a JSONL row. Bad provider output, bad CadQuery,
   missing `result`, parse failures, render failures, and max-attempt failures
   stay in the data.
8. `projects/cadybara-online-testing/` can start those runs from the lab API,
   report progress, show recent artifacts, append review scores, and rebuild
   blind hosted-review reports from saved data.
9. `projects/website/` is the static UI served by the lab server. It calls the
   API for landing/dashboard flows, hosted review, CAD/voxel diffusion training
   status, and artifact viewing.
10. `projects/codex-direct-testing/` can package CadQuery written directly by
    Codex in a chat thread into comparable JSONL/artifacts without treating it
    as an online run.
11. Publishable result snapshots are copied from project `workspace/` folders
    into `results/` by worker publish tooling.
12. `projects/cadgenbench/` can be initialized as an external submodule for
    reading CADGenBench's benchmark contract. Cadybara does not yet export
    runs into CADGenBench submission folders.

Important naming trap: `projects/cadybara-online-testing/` is currently named
for the lab/control-plane layer, not for the hosted Cadybara product API. If a
task is about online hosted generation through `https://api.cadybara.com`, read
`docs/HOSTED_CADYBARA_API.md` before touching configs or providers.

## Records And Resume

The runner writes one `RunRecord` JSON object per line. A row has a fresh
`run_id`, but resume uses a deterministic key:

```text
experiment_id, model_name, seed_id, variant_id, temperature, repetition
```

For normal text output, a row without a provider error is complete. For
CadQuery output, a row is complete only when it has no render error and includes
an STL artifact. That means failed CadQuery attempts can be followed by later
attempts for the same run cell until `max_attempts_per_cell` is reached.

Visual repair runs use `repair_round`, `repair_total_rounds`, `parent_run_id`,
and optional feedback image fields. A visual repair cell is complete only when
the final requested repair round has been recorded.

## Config Hashes

The config hash is stored on each run row. The runner refuses to append to a
JSONL file that already contains rows from a different hash unless explicitly
overridden.

This protects experiments from accidentally mixing changes to prompts, models,
sampling settings, output mode, or strategy. Do not weaken this protection to
make a run easier to resume.

## Workspaces

Each active project may have an ignored `workspace/` folder:

- `projects/local-running/workspace/` for smoke artifacts, model queue state,
  worker state, local examples, and local runs.
- `projects/cadybara-online-testing/workspace/` for online test runs, review
  scores, and lab-assigned configs.
- `projects/codex-direct-testing/workspace/` for direct Codex manual baseline
  runs.
- `projects/cad-diffusion/workspace/` for source datasets, prepared tokens,
  model checkpoints, sample runs, jobs, and training logs.
- `projects/website/logs/` for local web/lab logs. These are runtime files, not
  source.

Generated workspace data is valuable, but it is not committed directly. Preserve
it unless the researcher explicitly asks for deletion or migration.

## Artifacts

CadQuery artifact folders normally contain:

- `prompt_sent.txt`
- `seed_prompt.txt`
- `model_output.md`
- `model.py`
- `metadata.json`
- `model.stl`
- `model.step`
- `preview.png`
- error text files when export or preview fails

The source and errors matter as much as the mesh. Do not edit generated
`model.py` after the fact to make a failed row pass.

CAD diffusion sample artifacts are similar but start from generated tokens:
tokens become a `CadProgram`, the program compiles to CadQuery, then the same
STL/STEP/preview path is attempted.

Hosted Cadybara API artifacts can also contain `hosted_model.stl`, decoded from
server-returned `stl_base64`. Keep it alongside the local source/export result.
If the returned source imports server-only helpers and local execution fails,
that local failure remains data even though the hosted STL is viewable.

CAD diffusion has one extra integrity rule: grammar validation and constrained
decoding are allowed, but silent post-hoc repair is not. If the sampler emits an
invalid sequence, record the parse error. If CadQuery compilation fails, record
the compile error. If preview rendering fails, record the render error. The
failure distribution is part of the experiment.

## CAD Diffusion Loop

The active CAD-native diffusion experiment is not image Stable Diffusion. It is
a masked-token denoising model over a v0 CAD program language. Its useful shape
is:

```text
Fusion-style examples
  -> supported CadProgram extraction
  -> strict token grammar
  -> denoising training
  -> sampling
  -> parse/compile/render evaluation
  -> discriminator-style score report
```

The first discriminator should be explicit and decomposed: validity,
CAD-likeness, usefulness, novelty, and manufacturability are more actionable
than one hidden scalar. See `projects/cad-diffusion/HANDOFF.md` before changing
that project.

Voxel diffusion is a separate geometry-native loop:

```text
Fusion OBJ meshes
  -> normalized voxel grids
  -> dense 3D DDPM training
  -> sampled occupancy grids
  -> marching-cubes STL/preview export
  -> geometry metrics and nearest-neighbor novelty
```

It is useful for direct shape learning, not for editable CAD reconstruction yet.

## Reviews And Grades

The browser review flow appends 1-10 scores under
`projects/cadybara-online-testing/workspace/reviews/`.

The CLI grading flow writes `grades.jsonl` inside a run directory. It records a
source-code rubric, not just mesh success. Both formats are append-only.

The intended direction is to converge visual review and source-code grading
into one richer append-only grade/review record, but the current code still has
two separate paths. Do not silently rewrite old review JSONL to force that
convergence.

`cadybara_online_testing.blind_report` reads saved run JSONL plus append-only
review scores and writes a derived manifest/CSV/README report. It should never
regenerate model outputs or rewrite source reviews.

## Hosted Product API

The public hosted Cadybara API lives at `https://api.cadybara.com`. Agent
generation uses `POST /api/agent/generate` with an `X-API-Key` header and a JSON
body containing `prompt`, `response_mode`, optional `model`, and mesh deflection
fields. The confirmed final response includes `generated_code`, `stl_base64`,
`validation`, and `response_mode`.

Use `response_mode: "sse"` for hosted smoke runs. Production sits behind an AWS
ALB with a 60 second idle timeout; SSE progress/heartbeat events keep long
generations alive while still returning the same final code/STL payload as JSON
mode.

Hosted generation is implemented as the `cadybara_api` provider in
`projects/local-running/cadybara/providers/`. It is selected by model config and
records hosted API failures as normal provider errors in the same append-only
JSONL flow as local Ollama failures. The active hosted smoke config is
`projects/cadybara-online-testing/configs/online_smoke.yaml`, which uses the
five wall-planter prompts in
`projects/cadybara-online-testing/prompts/wall_planter_agent_prompts.yaml`.
The provider preserves hosted `stl_base64` as an artifact when it is available;
if returned source code is not standalone locally, that source/export failure is
still recorded as data.

Follow-on hosted batches currently live beside the smoke config: blind
wall-planter repeats, gapfill/hook/snowman prompt sets, and saved rate-limit
probes. Treat those configs as experiment records; do not collapse them into one
rewritten YAML just to make the directory shorter.

## Results Snapshots

`results/` is for copied, shareable snapshots. Live runs write to `workspace/`
first. Worker publish tooling copies JSONL, artifacts, reviews, and a manifest
into `results/<experiment_id>/<timestamp_machine>/`.

Do not write live output directly into `results/`.

The current shareable hosted smoke snapshot is
`results/cadybara_online_smoke_reps2/20260606_163617_windows/`. It is small
enough to review in Git and exists to let collaborators inspect the hosted rows
without pulling ignored worker state.

## CADGenBench Reference

`projects/cadgenbench/` is an external Git submodule, not a normal Cadybara
project folder. It contains CADGenBench's own evaluator, submission contract,
fixtures, docs, and optional baseline agent. It uses Python 3.12+ and should be
initialized explicitly:

```bash
git submodule update --init --recursive projects/cadgenbench
```

The intended future bridge is:

```text
Cadybara run artifacts
  -> selected model.stl/model.step or hosted_model.stl
  -> CADGenBench sample folder with output.*
  -> cadgenbench evaluate / leaderboard submission
```

That bridge is not implemented yet. Until it is, do not describe Cadybara
results as CADGenBench submissions.

## Dedicated Worker Box

The current local worker target is Arvin's Linux Mint 22.3 ThinkPad T430s. It
is intentionally slow: i5-3320M, 2 cores / 4 threads, no GPU, about 7.7 GB RAM,
and roughly 150 GB usable SSD space.

The worker setup is documented in `WORKER_QUICKSTART.md`. The short version is:

- Cadybara lab is LAN-facing on port `8787`.
- Ollama stays local-only on `127.0.0.1:11434`.
- Models are pulled explicitly, never as surprise side effects.
- Worker service disables model cleanup with `CADYBARA_DISABLE_MODEL_CLEANUP=1`.
- Worker service disables lab auto-pull with `CADYBARA_LAB_DISABLE_AUTO_PULL=1`.
- Current job state lives at
  `projects/local-running/workspace/worker/current_job.json`.
- Active jobs auto-resume after service restart; paused jobs remain paused.

Do not change those defaults casually. They are not polish; they protect
benchmark integrity on a small disk and keep the unauthenticated Ollama API off
the LAN.

## Parked Data

`projects/_parked-not-active/` preserves old wall-planter research, Kaggle
experiments, sandbox archives, and legacy design notes. Treat parked docs as
historical. They may mention old paths or old architecture choices that should
not drive current implementation.
