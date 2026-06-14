# AGENTS.md - Codex Direct Testing

This folder owns manual/direct Codex baselines. It is not hosted Cadybara API
testing and should not write results under `projects/cadybara-online-testing/`.

## Boundaries

- Keep direct Codex-written source in `manual_outputs/`.
- Keep prompts local to `prompts/` so this project is self-contained.
- Write generated artifacts and JSONL only under this project's ignored
  `workspace/` folder.
- Reuse shared artifact/export helpers from `projects/local-running/`; do not
  copy runner logic into this folder.
- Do not add API-backed model providers here. API-backed hosted runs belong in
  the shared provider boundary and online-testing configs.
- If a manual run allowed inspection, retries, or repair iterations, document
  that protocol in the prompt/run note. Do not present interactive Codex output
  as a one-shot provider baseline unless it actually was one-shot.

## Verification

Run:

```bash
python projects/codex-direct-testing/run_manual_baseline.py
pytest projects/codex-direct-testing/tests -q -p no:cacheprovider
```
