from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cadybara.cli import app
from cadybara.records import RunRecord
from cadybara_online_testing.grading import load_grade_records


def make_record(run_id: str, repetition: int, *, render_error: str | None = None) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        experiment_id="grade_demo",
        timestamp_utc="2026-05-23T00:00:00Z",
        model_name="qwen2.5-coder:3b",
        provider="ollama",
        seed_id="planter_01_minimal",
        seed_text="Make me a planter I can put on my wall.",
        seed_metadata={"specificity_level": 1},
        strategy="identity",
        variant_id="variant",
        variant_text="Make me a planter I can put on my wall.",
        variant_metadata={},
        prompt_sent="prompt",
        output_mode="cadquery",
        condition_name=f"condition-{repetition}",
        attempt=1,
        sampling={"temperature": 0.7, "seed": 123 + repetition, "max_tokens": 128},
        repetition=repetition,
        output='import cadquery as cq\nresult = cq.Workplane("XY").box(10, 10, 10)\n',
        latency_ms=1000,
        prompt_tokens=10,
        completion_tokens=20,
        finish_reason="stop",
        total_duration_ms=1000,
        load_duration_ms=0,
        prompt_eval_duration_ms=100,
        eval_duration_ms=900,
        provider_seed=None,
        scores={"output_length": 64.0},
        artifacts={"stl": "workspace/fake.stl"} if render_error is None else {},
        render_error=render_error,
        error=None,
        config_hash="hash",
    )


def test_grade_cli_writes_and_resumes(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    records = [make_record("run-0", 0), make_record("run-1", 1, render_error="bad code")]
    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json())
            handle.write("\n")

    answers = iter(["2", "1", "", "3", "2", "n", "second note"])

    def fake_ask(*args, **kwargs):
        return next(answers)

    monkeypatch.setattr("cadybara_online_testing.grading.Prompt.ask", fake_ask)
    runner = CliRunner()
    result = runner.invoke(app, ["grade", str(run_dir)])
    assert result.exit_code == 0, result.output
    assert "wrote=2" in result.output

    grades = load_grade_records(run_dir / "grades.jsonl")
    assert len(grades) == 2
    assert grades[0].rubric.code_validity == 1
    assert grades[1].rubric.code_validity == 0
    assert grades[1].rubric.notes == "second note"

    resume = runner.invoke(app, ["grade", str(run_dir)])
    assert resume.exit_code == 0, resume.output
    assert "wrote=0" in resume.output
    assert "skipped=2" in resume.output
