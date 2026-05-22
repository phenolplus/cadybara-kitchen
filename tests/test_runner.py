from __future__ import annotations

from pathlib import Path

from cadybara.config import load_config
from cadybara.records import RunRecord
from cadybara.runner import run_config


def read_records(path: Path) -> list[RunRecord]:
    return [
        RunRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_runner_dry_run_end_to_end_resume_and_partial_rerun(tiny_config_path: Path) -> None:
    config = load_config(tiny_config_path)
    output_path = Path(config.output_path)
    summary = run_config(config, dry_run=True)
    assert summary.executed == 8
    records = read_records(output_path)
    assert len(records) == 8
    assert all(record.output == "DRY_RUN" for record in records)
    assert [(r.model_name, r.seed_id, r.repetition) for r in records] == [
        ("model_a", "seed_001", 0),
        ("model_a", "seed_001", 1),
        ("model_a", "seed_002", 0),
        ("model_a", "seed_002", 1),
        ("model_b", "seed_001", 0),
        ("model_b", "seed_001", 1),
        ("model_b", "seed_002", 0),
        ("model_b", "seed_002", 1),
    ]

    second = run_config(config, dry_run=True)
    assert second.executed == 0
    assert second.skipped == 8
    assert len(read_records(output_path)) == 8

    kept_lines = output_path.read_text(encoding="utf-8").splitlines()[:4]
    output_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")
    third = run_config(config, dry_run=True)
    assert third.executed == 4
    assert len(read_records(output_path)) == 8
