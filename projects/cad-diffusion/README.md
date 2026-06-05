# CAD Diffusion

`projects/cad-diffusion/` is the CAD-native generative-model experiment. It is
the place for the "stable diffusion for CAD" direction, but the current v0 is
not image Stable Diffusion. It is a token grammar and small denoising
Transformer over simple CAD operations.

Read the repo-level `COMMON.md` first if the shared artifact and JSONL rules are
new.

For a detailed cold-start handoff, including the current model folder, resume
commands, checkpoint observations, research framing, and next-step guidance,
read `HANDOFF.md`.

## What This Project Owns

- `cadybara_cad_diffusion/core.py`
  - v0 CAD program schema
  - rectangle/circle extrude token grammar
  - Fusion-style dataset extraction
  - token-to-program parsing
  - program-to-CadQuery compilation
  - optional PyTorch training
  - sampling, artifact compilation, and run evaluation
- `tests/test_cad_diffusion.py` for grammar, dataset prep, training stop,
  compile, and evaluation coverage.
- `workspace/` for ignored source datasets, prepared token splits, model
  checkpoints, sample runs, and overnight logs.

## Main Flow

1. `prepare_fusion360_dataset()` scans a dataset folder for JSON files.
2. Each supported source is reduced into a `CadProgram`.
3. v0 supports direct or sketch-derived extrudes with rectangle or circle
   profiles. Unsupported programs are recorded in `unsupported.jsonl`.
4. A valid `CadProgram` is normalized, quantized, and serialized into tokens
   such as `<BOS>`, `OP:EXTRUDE`, `PROFILE:RECT`, dimension tokens, `ENDOP`,
   and `<EOS>`.
5. `train_diffusion_model()` loads the prepared `train.jsonl`, masks tokens at
   random noise levels, and trains a small Transformer denoiser.
6. `sample_diffusion_model()` starts from masked tokens, denoises, parses the
   result back into a program, compiles it to CadQuery, and attempts STL/STEP/PNG
   artifact export.
7. Every sample is appended to `results.jsonl` as a `CadDiffusionRecord`.
8. `eval_cad_diffusion_run()` summarizes parse validity, compilation,
   renderability, uniqueness, and nearest-neighbor token distance.

Parse errors, compile errors, render errors, and near-duplicates are part of the
measurement. Do not patch generated samples into valid CAD after sampling.

## Commands

Install optional training dependency from the repo root:

```bash
pip install -e ".[test,cad-diffusion]"
```

Prepare dataset tokens:

```bash
cadybara cad-diffusion prepare
```

Train:

```bash
cadybara cad-diffusion train
```

Sample:

```bash
cadybara cad-diffusion sample
```

Evaluate a sample run:

```bash
cadybara cad-diffusion eval projects/cad-diffusion/workspace/runs/cad_diffusion_smoke
```

## Current Limits

- v0 grammar only covers simple extrudes with rectangle or circle profiles.
- Dimensions are quantized into fixed bins.
- Text conditioning is not implemented.
- Sampling is still early and can generate invalid token sequences. That is an
  evaluation signal, not a reason to patch sample artifacts after the fact.
- PyTorch is optional. Importing the package should work without PyTorch, but
  training and sampling require the `cad-diffusion` extra.
- Checkpoints and datasets can be large and belong in ignored `workspace/`.

## Current Research Direction

This project is closest to the 3D diffusion and text-to-3D literature in spirit,
but its representation is CAD-native. The practical near-term loop is:

```text
token generator -> grammar/compile/render validity gate -> discriminator report
```

The first discriminator should be a transparent score vector over validity,
CAD-likeness, usefulness, novelty, and manufacturability rather than a single
opaque reward. See `HANDOFF.md` for the fuller version of that recommendation.

## Tests

Run this project:

```bash
pytest projects/cad-diffusion/tests -q -p no:cacheprovider
```

Run the full repo suite before broad changes:

```bash
pytest -q -p no:cacheprovider
```
