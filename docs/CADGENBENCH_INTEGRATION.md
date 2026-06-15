# CADGenBench Integration Notes

`projects/cadgenbench/` is a Git submodule pointing to the external
CADGenBench project:

```text
https://github.com/huggingface/cadgenbench.git
```

It is included as a benchmark reference and future compatibility target. It is
not vendored Cadybara source, and it should not be edited as part of ordinary
Cadybara runner, lab, website, or diffusion work.

## Setup

After cloning Cadybara, initialize the submodule:

```bash
git submodule update --init --recursive projects/cadgenbench
```

CADGenBench has its own Python 3.12+ environment and dependency set. Keep it
separate from Cadybara's root Python 3.11+ environment.

## Current Relationship

Cadybara currently produces append-only JSONL rows and CAD artifacts such as:

- `model.stl`
- `model.step`
- `hosted_model.stl`
- `model.py`
- `metadata.json`

CADGenBench expects one candidate artifact per benchmark sample, usually named
`output.step`, `output.stp`, or a supported mesh name such as `output.stl`.

There is no implemented Cadybara exporter that maps Cadybara run artifacts into
CADGenBench submission folders yet.

## Future Bridge

The likely future bridge is:

```text
Cadybara run directory
  -> choose rows/artifacts for named benchmark samples
  -> copy or convert each candidate to output.*
  -> write CADGenBench submission metadata
  -> run CADGenBench validation/evaluation
```

That bridge will need its own CLI, tests, and documentation before Cadybara
outputs should be described as CADGenBench submissions.

## Contribution Boundary

Changes to CADGenBench itself should use the CADGenBench repository workflow.
Changes to Cadybara should only reference CADGenBench through documented
contracts until an explicit integration layer exists.
