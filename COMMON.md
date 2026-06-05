# Common Cadybara Concepts

This file explains the shared language used by all four active projects.

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
   local Ollama API through `httpx`.
6. For `output_mode: cadquery`, the model text is treated as CadQuery source.
   The harness extracts source, executes it, and exports STL/STEP/PNG artifacts
   only when the code works.
7. Every attempt is appended as a JSONL row. Bad provider output, bad CadQuery,
   missing `result`, parse failures, render failures, and max-attempt failures
   stay in the data.
8. `projects/cadybara-online-testing/` can start those runs from the lab API,
   report progress, show recent artifacts, and append review scores.
9. `projects/website/` is the static UI served by the lab server. It calls the
   API and loads artifacts through the viewer.
10. Publishable result snapshots are copied from project `workspace/` folders
    into `results/` by worker publish tooling.

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

## Reviews And Grades

The browser review flow appends 1-10 scores under
`projects/cadybara-online-testing/workspace/reviews/`.

The CLI grading flow writes `grades.jsonl` inside a run directory. It records a
source-code rubric, not just mesh success. Both formats are append-only.

The intended direction is to converge visual review and source-code grading
into one richer append-only grade/review record, but the current code still has
two separate paths. Do not silently rewrite old review JSONL to force that
convergence.

## Hosted Product API

The public hosted Cadybara API appears to live at `https://api.cadybara.com`.
The app's API-key UI names `POST /api/agent/generate` with an `X-API-Key`
header as the agent-facing endpoint. The exact body and response schema are not
yet documented in this repo.

Until official endpoint examples are available, do not guess the hosted request
schema in production code. When it is implemented, it should be a normal
`ModelProvider` in `projects/local-running/cadybara/providers/`, selected by
model config, and it should record hosted API failures as data in the same
append-only JSONL flow as local Ollama failures.

## Results Snapshots

`results/` is for copied, shareable snapshots. Live runs write to `workspace/`
first. Worker publish tooling copies JSONL, artifacts, reviews, and a manifest
into `results/<experiment_id>/<timestamp_machine>/`.

Do not write live output directly into `results/`.

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
