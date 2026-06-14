# Results Snapshots

Worker machines publish completed experiment findings here on separate
`results/...` branches.

Do not write live output directly into this folder. Runs should write to
project `workspace/` folders first, then `projects/local-running/scripts/worker_publish_results.py` copies a snapshot
into `results/<experiment_id>/<timestamp_machine>/` and commits only that
snapshot.

The current shareable snapshot is:

```text
results/cadybara_online_smoke_reps2/20260606_163617_windows/
```

It contains hosted Cadybara Agent API rows and artifacts copied out of the
online-testing workspace. Keep this kind of snapshot reviewable and intentional:
small enough for Git, free of secrets, and separate from live `workspace/`
state.
