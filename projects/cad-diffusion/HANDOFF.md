# CAD Diffusion Handoff

This is the handoff I would want if I were the next agent landing cold in this
project. Read this after root `AGENTS.md`, root `COMMON.md`, and
`projects/cad-diffusion/README.md`.

## The Point

Arvin is trying to build the "Stable Diffusion for CAD" direction, but the
current system is deliberately smaller and more honest than that phrase can
sound. It is a CAD-native token denoising experiment:

1. Extract simple Fusion-style CAD programs.
2. Convert them into a strict token language.
3. Train a tiny Transformer denoiser over token sequences.
4. Sample token sequences from noise.
5. Parse, compile, render, and score the generated CAD without repairing it.

The most important research rule is that invalid output is data. Do not patch
generated tokens, CadQuery, STL files, previews, or JSONL rows after the fact to
make a sample look better. The system should become better because training,
decoding, grammar constraints, or scoring improves, not because the evaluation
path hides failures.

## Current Implementation

The whole project currently lives in one implementation module:

- `projects/cad-diffusion/cadybara_cad_diffusion/core.py`

Important surfaces in that file:

- `ExtrudeOp` and `CadProgram`: the v0 CAD program schema.
- `program_to_tokens()` and `tokens_to_program()`: strict round-trip path.
- `cad_grammar_allowed_next()` and `validate_cad_token_grammar()`: declared
  grammar infrastructure.
- `prepare_fusion360_dataset()`: source JSON extraction into supported token
  examples.
- `train_diffusion_model()`: PyTorch masked-token denoising trainer.
- `sample_diffusion_model()`: iterative denoising sampler plus parse/compile
  evaluation.
- `eval_cad_diffusion_run()`: summary metrics over append-only sample JSONL.

The lab server controls training from:

- `projects/cadybara-online-testing/cadybara_online_testing/lab_server.py`

The browser page is:

- `projects/website/lab/cad-diffusion.html`
- `projects/website/lab/cad-diffusion.js`
- `projects/website/lab/cad-diffusion.css`

The shared CLI entry point is in:

- `projects/local-running/cadybara/cli.py`

## V0 CAD Language

The v0 language is intentionally narrow:

- Units: millimeters.
- Operations: extrudes only.
- Profiles: rectangle or circle only.
- Modes: `new`, `join`, `cut`.
- First operation cannot be `cut`.
- Rectangle parameters: `x`, `y`, `width`, `height`, `distance`.
- Circle parameters: `x`, `y`, `radius`, `distance`.
- Numeric values are quantized into fixed token bins.
- Max sequence length is normally `256`.

Representative token shape:

```text
<BOS>
OP:EXTRUDE PROFILE:RECT MODE:NEW
X:+000 Y:+000 W:020 H:010 D:005 ENDOP
<EOS>
```

Actual token spellings depend on the bin helpers in `core.py`; inspect
`default_vocab_tokens()` before adding new tokens.

Grammar validation is not post-hoc repair. It is used to reject invalid
training examples and to explain why malformed sampled sequences are invalid.
When expanding the language, update the grammar, parser, serializer, dataset
prep, and tests together.

## Dataset State

The prepared dataset used by the lab defaults to:

```text
projects/cad-diffusion/workspace/datasets/fusion360_tokens
```

The readiness endpoint has observed:

- `2974` train examples
- `737` test examples
- `3711` supported total examples
- many unsupported source files, mostly because v0 only accepts rectangle or
  circle profiles

That split is good enough to run an overnight CPU experiment. It is not enough
to claim broad CAD generation. Treat it as a validity-first pilot.

Do not mutate existing prepared data casually. If you add grammar coverage,
write to a new dataset folder or make the migration explicit.

## Training State

The main active model folder is:

```text
projects/cad-diffusion/workspace/models/cad_diffusion_validity_20260602
```

The lab defaults are in `CAD_DIFFUSION_DEFAULTS`:

```text
data_dir: projects/cad-diffusion/workspace/datasets/fusion360_tokens
model_dir: projects/cad-diffusion/workspace/models/cad_diffusion_validity_20260602
max_steps: 50000
batch_size: 32
max_len: 256
d_model: 128
layers: 2
heads: 4
learning_rate: 0.0003
checkpoint_interval: 100
time_limit_minutes: 480
seed: 20260602
resume: true
```

For the aggressive June 2026 CPU run, I restarted training with
`checkpoint_interval = 25` so a battery loss or stop only loses a small amount
of work. During this documentation pass, I resumed from
`checkpoint_step_011400.pt` and observed this first fresh resumed checkpoint:

```text
projects/cad-diffusion/workspace/models/cad_diffusion_validity_20260602/checkpoint_step_011425.pt
```

That was an observation, not a promise. Training may have moved far beyond it.
Always verify current state from disk:

```powershell
Get-ChildItem projects/cad-diffusion/workspace/models/cad_diffusion_validity_20260602 -Filter 'checkpoint_step_*.pt' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 10 Name, LastWriteTime, Length
```

If the lab is running, verify through the API:

```powershell
(Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8788/api/cad-diffusion/status').Content
```

## Starting Or Resuming Training

From the lab UI:

```text
http://127.0.0.1:8788/lab/cad-diffusion.html
```

From the lab API, with frequent checkpointing:

```powershell
$body = @{ checkpoint_interval = 25; resume = $true } | ConvertTo-Json
Invoke-WebRequest `
  -UseBasicParsing `
  -Method Post `
  -Uri 'http://127.0.0.1:8788/api/cad-diffusion/train/start' `
  -ContentType 'application/json' `
  -Body $body
```

If the lab server is down:

```powershell
cadybara lab --host 127.0.0.1 --port 8788
```

For a detached-ish local desktop start, use `Start-Process` and redirect logs
under ignored workspace paths:

```powershell
$logDir = 'projects/cad-diffusion/workspace/runs/lab_server'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Start-Process `
  -FilePath 'cadybara' `
  -ArgumentList @('lab','--host','127.0.0.1','--port','8788') `
  -WorkingDirectory (Get-Location) `
  -RedirectStandardOutput (Join-Path $logDir 'lab-8788.out.log') `
  -RedirectStandardError (Join-Path $logDir 'lab-8788.err.log') `
  -WindowStyle Hidden
```

CLI training also works, but note the CLI default output directory is different
unless you pass `--output-dir`:

```powershell
cadybara cad-diffusion train `
  projects/cad-diffusion/workspace/datasets/fusion360_tokens `
  --output-dir projects/cad-diffusion/workspace/models/cad_diffusion_validity_20260602 `
  --max-steps 50000 `
  --batch-size 32 `
  --max-len 256 `
  --d-model 128 `
  --layers 2 `
  --heads 4 `
  --checkpoint-interval 25 `
  --time-limit-minutes 480 `
  --seed 20260602 `
  --resume
```

## Sampling And Evaluation

Sampling is the next thing to make more useful after training. The code already
records honest failures:

- token sequence
- parse error
- compile error
- render error
- artifacts
- simple program metrics
- nearest-neighbor token distance

Example:

```powershell
cadybara cad-diffusion sample `
  projects/cad-diffusion/workspace/models/cad_diffusion_validity_20260602/checkpoint_step_011425.pt `
  --run-dir projects/cad-diffusion/workspace/runs/cad_diffusion_validity_sample_001 `
  --model-dir projects/cad-diffusion/workspace/models/cad_diffusion_validity_20260602 `
  --data-dir projects/cad-diffusion/workspace/datasets/fusion360_tokens `
  --count 100 `
  --denoise-steps 16 `
  --temperature 1.0 `
  --seed 20260602
```

Evaluate:

```powershell
cadybara cad-diffusion eval projects/cad-diffusion/workspace/runs/cad_diffusion_validity_sample_001
```

Do not overwrite a sample run when changing sampler behavior. Use a new
`run_dir` so the comparison remains clean.

## Relationship To 3D Diffusion Research

Arvin asked me to read these reference maps:

- `cwchenwang/awesome-3d-diffusion`
- `yyeboah/Awesome-Text-to-3D`

They are bibliographies, not implementation repos to vendor in. The useful
pattern to copy is the research structure:

```text
generator -> hard validity gate -> discriminator/scorer -> guided selection
```

Most text-to-3D systems score or guide outputs by some mix of prompt alignment,
multi-view consistency, geometry plausibility, reconstruction quality, and human
preference. Our representation is different: symbolic CAD programs rather than
pixels, NeRFs, point clouds, SDFs, or meshes. That is an advantage if we exploit
CAD-native validity and usefulness instead of chasing image aesthetics.

My recommended discriminator shape is a score vector first, not one magic
scalar:

```text
validity_score        parses, compiles, exports, renders
cad_likeness_score    resembles real simple CAD examples
usefulness_score      looks like a plausible part, not random primitive soup
novelty_score         not a memorized nearest neighbor
constraint_score      obeys requested constraints once conditioning exists
manufacturability     sane dimensions, connected solids, nondegenerate features
```

Start with validity, CAD-likeness, and novelty because those are available
before text conditioning. Add prompt alignment later.

## What I Would Do Next

1. Add grammar-constrained decoding instead of only grammar validation.
   Sampling should mask logits to `cad_grammar_allowed_next(prefix)` as tokens
   are finalized. This is still not repair; it is declared decoding.
2. Run a checkpoint sweep: sample `100` outputs from several checkpoints
   (`005000`, `010000`, latest), evaluate validity and novelty, and compare.
3. Build the discriminator report as append-only JSONL next to sample runs.
   Keep raw component scores, not only an aggregate.
4. Add richer v0.1 grammar only after measuring current failure modes. Likely
   next language features are hole/cut patterns, multiple sketches, and simple
   fillets/chamfers, but let sample failures decide.
5. Keep the lab page boring and trustworthy: readiness, latest checkpoint,
   running/stopped state, step, loss, device, checkpoint cadence, and recent
   logs matter more than decoration.

## Verification I Ran

On June 5, 2026, from the repo root:

```powershell
python -m pytest projects/cad-diffusion/tests projects/cadybara-online-testing/tests projects/local-running/tests/test_config.py -q -p no:cacheprovider
```

Result:

```text
21 passed
```

Then:

```powershell
python -m pytest -q -p no:cacheprovider
```

Result:

```text
56 passed
```

After those tests, I restarted the lab on port `8788`, resumed CAD diffusion
training from `checkpoint_step_011400.pt`, and observed a fresh
`checkpoint_step_011425.pt` written with the 25-step checkpoint cadence.

## Failure Modes To Respect

- Missing PyTorch is a blocker for training/sampling, not for importing most of
  the repo.
- Missing dataset manifest means `/api/cad-diffusion/status` should be blocked.
- A running CAD training job should conflict with another start request.
- Stop is cooperative; it saves a final checkpoint after the current step.
- Sampling can produce invalid sequences. Record them.
- Render failures do not imply the generated program was repaired or discarded.
- Workspace data is valuable local research state even though it is ignored by
  Git.

The tone of this project should stay relentlessly empirical: generate, record,
score, compare, and only then expand the model or grammar.
