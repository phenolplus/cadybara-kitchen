# Codex Direct Experiment

This folder is the "use the Codex in this thread" baseline. It is intentionally
separate from `projects/cadybara-online-testing/`, because these runs are not
hosted/online Cadybara API tests.

This does not call the OpenAI API. The CadQuery files in `manual_outputs/` were
written directly by Codex in the active chat session, then packaged into normal
Cadybara artifacts with `run_manual_baseline.py`.

This is useful for a qualitative comparison:

- direct Codex can inspect the repo, write code, run it, and iterate;
- hosted Cadybara/API runs are separate online-testing data;
- CADAM-style tools add their own OpenSCAD/browser/parameter workflow.

Because direct Codex is interactive, this is not a single-shot benchmark unless
you freeze the protocol and count any repair iteration explicitly.

This is its own benchmark project. It should stay understandable without
opening online-testing first: prompts, manual source, packaging, tests, and
ignored workspace outputs all live here.

## How To Read This Folder

- `prompts/` stores the prompt sets used for manual comparisons.
- `manual_outputs/` stores the CadQuery source files written directly by Codex.
- `run_manual_baseline.py` packages those source files into comparable
  Cadybara-style JSONL rows and CAD artifacts.
- `workspace/` is ignored output state. Keep it out of normal commits unless a
  result is deliberately published through `results/`.

This lane is useful because it answers a different question from hosted API
testing: "What can an interactive coding agent do with repo access and repair
iterations?" Hosted Cadybara runs answer the provider/API question instead.

## Generate Artifacts

From the repo root:

```bash
python projects/codex-direct-testing/run_manual_baseline.py
```

Outputs go to ignored workspace paths:

```text
projects/codex-direct-testing/workspace/runs/codex_direct_wall_planter_v1/
```

The script refuses to append to an existing `results.jsonl` unless you pass
`--append`, so accidental duplicate manual runs do not mix silently.

Run focused tests with:

```bash
pytest projects/codex-direct-testing/tests -q -p no:cacheprovider
```
