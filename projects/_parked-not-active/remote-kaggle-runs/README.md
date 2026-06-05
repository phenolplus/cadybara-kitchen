# Remote Kaggle Runs

This project contains the remote-run tooling and downloaded Kaggle outputs.

It owns:

- `scripts/` - Kaggle setup, one-model heavy loop runner, and dashboard builder.
- `workspace/kaggle_upload/` - repo bundles prepared for Kaggle.
- `workspace/kaggle_kernel_submit/` - generated Kaggle kernel submission files.
- `workspace/kaggle_downloads/` - downloaded outputs, logs, summaries, and
  rendered heavy-loop dashboard data.
- `workspace/kaggle_*_probe/` - one-off Kaggle API/quota probes.

Keep this project separate from local training so remote-compute experiments do
not clutter the local harness.
