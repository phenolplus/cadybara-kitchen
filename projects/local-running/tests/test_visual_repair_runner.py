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


def write_repair_config(path: Path, output_path: Path) -> None:
    path.write_text(
        f"""
experiment_id: "repair_demo"
output_path: "{output_path.as_posix()}"
output_mode: "text"
models:
  - name: "vision-big"
    provider: "ollama"
    base_url: "http://localhost:11434"
    family: "vision"
    params_b: 72
    vision: true
seeds:
  - id: "planter_01_minimal"
    text: "Make a wall planter."
    metadata: {{}}
strategies:
  - name: "identity"
sampling:
  temperatures: [0.2]
  repetitions: 1
  max_tokens: 64
cad:
  enabled: false
repair:
  enabled: true
  rounds: 3
  feedback: "render_png"
  always_run_all_rounds: true
""".lstrip(),
        encoding="utf-8",
    )


def test_visual_repair_runner_writes_three_rounds_and_resumes(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "repair.yaml"
    output_path = tmp_path / "results.jsonl"
    write_repair_config(config_path, output_path)
    calls: list[str] = []

    def fake_provider_for_model(model, *, dry_run: bool):
        class SequenceProvider:
            def generate(self, prompt, *, temperature, max_tokens, seed, images=None):
                calls.append(prompt)
                return ProviderResponse(
                    output=f"round {len(calls)}",
                    latency_ms=10,
                    prompt_tokens=1,
                    completion_tokens=1,
                    finish_reason="done",
                    total_duration_ms=10,
                    load_duration_ms=0,
                    prompt_eval_duration_ms=0,
                    eval_duration_ms=10,
                    provider_seed=None,
                )

        return "fake", SequenceProvider()

    monkeypatch.setattr("cadybara.runner.provider_for_model", fake_provider_for_model)
    config = load_config(config_path)

    partial = run_config(config, limit=2)
    assert partial.executed == 2
    assert [record.repair_round for record in read_records(output_path)] == [1, 2]

    resumed = run_config(config)
    assert resumed.executed == 1
    records = read_records(output_path)
    assert [record.repair_round for record in records] == [1, 2, 3]
    assert records[1].parent_run_id == records[0].run_id
    assert records[2].parent_run_id == records[0].run_id
    assert records[2].feedback_source_run_id == records[1].run_id

    skipped = run_config(config)
    assert skipped.executed == 0
    assert skipped.skipped == 1
