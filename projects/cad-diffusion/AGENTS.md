# AGENTS.md - CAD Diffusion

You are in the CAD-native diffusion project. Keep changes focused on dataset
prep, token grammar, voxelization, model training, sampling, CAD/mesh
compilation, and evaluation.

## Read First

- Root `AGENTS.md`
- Root `COMMON.md`
- `projects/cad-diffusion/README.md`
- `projects/cad-diffusion/HANDOFF.md`
- `projects/cad-diffusion/cadybara_cad_diffusion/core.py`
- `projects/cad-diffusion/cadybara_cad_diffusion/voxel.py`
- `projects/cad-diffusion/tests/test_cad_diffusion.py`
- `projects/cad-diffusion/tests/test_voxel_diffusion.py`

## Boundaries

- CAD diffusion logic belongs here.
- Reuse `projects/local-running/cadybara/cadquery_runner.py` for CadQuery export
  and preview rendering instead of copying that machinery.
- The lab API that starts CAD diffusion training belongs in
  `projects/cadybara-online-testing/`.
- The CAD diffusion training page belongs in `projects/website/`.
- Datasets, checkpoints, generated samples, and training logs belong under
  `projects/cad-diffusion/workspace/`.

## Research Rules

- Do not fake valid CAD by repairing generated samples after the fact.
- Preserve parse, compile, render, uniqueness, and nearest-neighbor metrics.
- Unsupported source programs are expected and should be recorded clearly.
- Keep PyTorch optional outside training and sampling paths.
- Be honest in docs and UI: this is CAD diffusion v0, not finished full Stable
  Diffusion for CAD.
- Keep token diffusion and voxel diffusion distinct. Token diffusion is for
  editable CAD programs; voxel diffusion is for direct geometry learning and
  does not recover parametric CAD yet.

## Implementation Notes

- Keep grammar validation strict. Bad sequences should explain the expected next
  token class.
- Keep generated sample records append-only.
- When expanding the grammar, update round-trip tests, dataset extraction tests,
  and eval expectations together.
- When changing training or sampling behavior, write down the checkpoint/run
  folder you used and the exact command in `HANDOFF.md` or a new run note.
- Avoid committing datasets, checkpoints, or sample runs.

## Tests

For CAD diffusion changes:

```bash
pytest projects/cad-diffusion/tests -q -p no:cacheprovider
```

For shared compile/export changes:

```bash
pytest -q -p no:cacheprovider
```
