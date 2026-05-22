from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cadybara.cli import app


def test_cli_run_dry_run_and_inspect(tmp_path: Path) -> None:
    config_path = tmp_path / "example.yaml"
    output_path = tmp_path / "out.jsonl"
    config_path.write_text(
        f"""
experiment_id: "cli"
output_path: "{output_path.as_posix()}"
models:
  - name: "qwen2.5:0.5b"
    provider: "ollama"
    base_url: "http://localhost:11434"
seeds:
  - id: "seed_001"
    text: "Create four holes."
    metadata:
      domain: "cad"
strategies:
  - name: "identity"
sampling:
  temperatures: [0.7]
  repetitions: 1
  max_tokens: 16
""".lstrip(),
        encoding="utf-8",
    )
    runner = CliRunner()
    run_result = runner.invoke(app, ["run", "--dry-run", str(config_path)])
    assert run_result.exit_code == 0, run_result.output
    assert "executed=1" in run_result.output
    inspect_result = runner.invoke(app, ["inspect", str(output_path)])
    assert inspect_result.exit_code == 0, inspect_result.output
    assert "Total valid rows: 1" in inspect_result.output
    assert "Unique model/seed/variant triples: 1" in inspect_result.output

    sample_path = tmp_path / "sample_part.json"
    sample_result = runner.invoke(app, ["sample-part", str(sample_path)])
    assert sample_result.exit_code == 0, sample_result.output
    assert sample_path.exists()

    training_path = tmp_path / "training.jsonl"
    training_result = runner.invoke(
        app,
        ["export-training", str(output_path), str(training_path)],
    )
    assert training_result.exit_code == 0, training_result.output
    assert "Wrote 1 training row" in training_result.output

    status_result = runner.invoke(app, ["model-status", "configs/models_local.yaml"])
    assert status_result.exit_code == 0, status_result.output
    assert "qwen2.5:0.5b" in status_result.output
