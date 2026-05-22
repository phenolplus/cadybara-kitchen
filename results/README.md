# Results Snapshots

Worker machines publish completed experiment findings here on separate
`results/...` branches.

Do not write live output directly into this folder. Runs should write to
`workspace/` first, then `scripts/worker_publish_results.py` copies a snapshot
into `results/<experiment_id>/<timestamp_machine>/` and commits only that
snapshot.

