from __future__ import annotations

import json
from pathlib import Path

from cadybara.config import load_config
from cadybara.runner import run_config
from cadybara.training import export_training_pairs


def test_export_training_pairs_from_dry_run(tmp_path: Path, tiny_config_path: Path) -> None:
    config = load_config(tiny_config_path)
    run_config(config, dry_run=True, limit=2)
    output_path = tmp_path / "training.jsonl"
    written, skipped = export_training_pairs(config.output_path, output_path)
    assert written == 2
    assert skipped == 0
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["messages"][0]["role"] == "user"
    assert rows[0]["messages"][1]["content"] == "DRY_RUN"
    assert rows[0]["metadata"]["experiment_id"] == "tiny"
