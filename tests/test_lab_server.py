from __future__ import annotations

from pathlib import Path

from cadybara.config import load_config
from cadybara.lab_server import assign_run_config_for_start, practice_output_path, write_assigned_config
from cadybara.runner import run_config


def test_lab_start_resumes_latest_partial_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "tiny.yaml"
    config_path.write_text(
        """
experiment_id: "overnight"
output_path: "workspace/manual/results.jsonl"
models:
  - name: "model_a"
    provider: "ollama"
    base_url: "http://localhost:11434"
  - name: "model_b"
    provider: "ollama"
    base_url: "http://localhost:11434"
seeds:
  - id: "seed_001"
    text: "Prompt one"
    metadata: {}
  - id: "seed_002"
    text: "Prompt two"
    metadata: {}
strategies:
  - name: "identity"
sampling:
  temperatures: [0.7]
  repetitions: 2
  max_tokens: 32
""".lstrip(),
        encoding="utf-8",
    )
    config = load_config(config_path)

    first = assign_run_config_for_start(config, dry_run=False)
    assert first.resuming is False
    assert first.config.experiment_id == "overnight_001"
    write_assigned_config(first.config)

    empty_reuse = assign_run_config_for_start(config, dry_run=False)
    assert empty_reuse.resuming is False
    assert empty_reuse.config.output_path == first.config.output_path

    practice_config = first.config.model_copy(update={"output_path": practice_output_path(first.config.output_path)})
    partial = run_config(practice_config, dry_run=True, limit=3)
    assert partial.executed == 3

    resumed = assign_run_config_for_start(config, dry_run=True)
    assert resumed.resuming is True
    assert resumed.config.output_path == first.config.output_path

    complete = run_config(practice_config, dry_run=True)
    assert complete.executed == 5

    next_run = assign_run_config_for_start(config, dry_run=True)
    assert next_run.resuming is False
    assert next_run.config.experiment_id == "overnight_002"
