from __future__ import annotations

from pathlib import Path

from cadybara.config import load_config
from cadybara.providers.base import ProviderResponse
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


def test_runner_retries_cadquery_until_stl_product(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "cad.yaml"
    output_path = tmp_path / "cad.jsonl"
    artifact_root = tmp_path / "artifacts"
    config_path.write_text(
        f"""
experiment_id: "cad_retry"
output_path: "{output_path.as_posix()}"
output_mode: "cadquery"
artifact_root: "{artifact_root.as_posix()}"
models:
  - name: "model_a"
    provider: "ollama"
    base_url: "http://localhost:11434"
seeds:
  - id: "seed_001"
    text: "Make a box."
    metadata: {{}}
strategies:
  - name: "identity"
sampling:
  temperatures: [0.7]
  repetitions: 1
  max_tokens: 128
  max_attempts_per_cell: 2
""".lstrip(),
        encoding="utf-8",
    )
    outputs = [
        "import cadquery as cq\nresult = missing_name\n",
        'import cadquery as cq\nresult = cq.Workplane("XY").box(10, 20, 3)\n',
    ]

    def fake_provider_for_model(model, *, dry_run: bool):
        class SequenceProvider:
            def generate(self, prompt, *, temperature, max_tokens, seed):
                return ProviderResponse(
                    output=outputs.pop(0),
                    latency_ms=1,
                    prompt_tokens=1,
                    completion_tokens=1,
                    finish_reason="done",
                    total_duration_ms=1,
                    load_duration_ms=0,
                    prompt_eval_duration_ms=0,
                    eval_duration_ms=1,
                    provider_seed=None,
                )

        return "fake", SequenceProvider()

    monkeypatch.setattr("cadybara.runner.provider_for_model", fake_provider_for_model)
    config = load_config(config_path)
    summary = run_config(config)
    records = read_records(output_path)
    assert summary.executed == 2
    assert [record.attempt for record in records] == [1, 2]
    assert records[0].render_error
    assert not records[0].artifacts.get("stl")
    assert records[1].render_error is None
    assert Path(records[1].artifacts["stl"]).exists()

    resumed = run_config(config)
    assert resumed.executed == 0
    assert len(read_records(output_path)) == 2
