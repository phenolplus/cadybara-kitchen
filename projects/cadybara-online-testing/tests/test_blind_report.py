from __future__ import annotations

import json
from pathlib import Path

from cadybara.records import RunRecord
from cadybara_online_testing import blind_report, reviews
from cadybara_online_testing.blind_report import build_blind_review_report


def make_hosted_record(
    *,
    experiment_id: str,
    run_id: str,
    seed_id: str,
    seed_text: str,
    specificity_level: int,
    repetition: int,
    stl_path: str,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        experiment_id=experiment_id,
        timestamp_utc="2026-06-08T00:00:00Z",
        model_name="cadybara-agent-default",
        provider="cadybara_api",
        seed_id=seed_id,
        seed_text=seed_text,
        seed_metadata={"specificity_level": specificity_level},
        strategy="identity",
        variant_id="identity",
        variant_text=seed_text,
        variant_metadata={"specificity_level": specificity_level},
        prompt_sent=seed_text,
        output_mode="cadquery",
        condition_name=f"condition-{seed_id}-{repetition}",
        attempt=1,
        sampling={"temperature": 0.0, "seed": 123 + repetition, "max_tokens": 1},
        repetition=repetition,
        output='import cadquery as cq\nresult = cq.Workplane("XY").box(10, 10, 10)\n',
        latency_ms=1000,
        prompt_tokens=None,
        completion_tokens=None,
        finish_reason="stop",
        total_duration_ms=1000,
        load_duration_ms=0,
        prompt_eval_duration_ms=0,
        eval_duration_ms=0,
        provider_seed=None,
        scores={"output_length": 64.0},
        artifacts={
            "stl": stl_path,
            "hosted_stl": stl_path,
            "cadquery_code": stl_path.replace(".stl", ".py"),
            "model_output": stl_path.replace(".stl", ".md"),
        },
        render_error=None,
        error=None,
        config_hash="hash",
    )


def write_jsonl(path: Path, rows: list[dict | RunRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = row.model_dump(mode="json") if isinstance(row, RunRecord) else row
            handle.write(json.dumps(payload))
            handle.write("\n")


def test_blind_report_combines_runs_and_latest_scores(tmp_path: Path, monkeypatch) -> None:
    reviews_dir = tmp_path / "reviews"

    def fake_review_path(experiment_id: str) -> Path:
        return reviews_dir / f"{experiment_id}_reviews.jsonl"

    monkeypatch.setattr(reviews, "review_path", fake_review_path)
    monkeypatch.setattr(blind_report, "review_path", fake_review_path)

    prompts = """
seeds:
  - id: planter_01_minimal
    text: Make me a planter I can put on my wall.
    metadata: {specificity_level: 1}
  - id: planter_10_full
    text: Make a fully specified wall planter.
    metadata: {specificity_level: 10}
models:
  - name: cadybara-agent-default
    provider: cadybara_api
    base_url: https://api.cadybara.com
    response_mode: sse
strategies:
  - name: identity
sampling:
  temperatures: [0.0]
  repetitions: 1
  max_tokens: 1
  max_attempts_per_cell: 1
""".strip()

    old_results = tmp_path / "old" / "results.jsonl"
    new_results = tmp_path / "new" / "results.jsonl"
    old_config = tmp_path / "old.yaml"
    new_config = tmp_path / "new.yaml"
    old_config.write_text(
        f'experiment_id: old_batch\noutput_path: "{old_results.as_posix()}"\n{prompts}\n',
        encoding="utf-8",
    )
    new_config.write_text(
        f'experiment_id: new_batch\noutput_path: "{new_results.as_posix()}"\n{prompts}\n',
        encoding="utf-8",
    )

    write_jsonl(
        old_results,
        [
            make_hosted_record(
                experiment_id="old_batch",
                run_id="old-low",
                seed_id="planter_01_minimal",
                seed_text="Make me a planter I can put on my wall.",
                specificity_level=1,
                repetition=0,
                stl_path="workspace/old-low.stl",
            ),
            make_hosted_record(
                experiment_id="old_batch",
                run_id="old-high",
                seed_id="planter_10_full",
                seed_text="Make a fully specified wall planter.",
                specificity_level=10,
                repetition=0,
                stl_path="workspace/old-high.stl",
            ),
        ],
    )
    write_jsonl(
        new_results,
        [
            make_hosted_record(
                experiment_id="new_batch",
                run_id="new-low",
                seed_id="planter_01_minimal",
                seed_text="Make me a planter I can put on my wall.",
                specificity_level=1,
                repetition=0,
                stl_path="workspace/new-low.stl",
            )
        ],
    )
    write_jsonl(fake_review_path("old_batch"), [{"run_id": "old-low", "score": 3}])
    write_jsonl(
        fake_review_path("old_batch"),
        [
            {"run_id": "old-low", "score": 3},
            {"run_id": "old-high", "score": 8},
        ],
    )
    paths = build_blind_review_report([old_config, new_config], tmp_path / "report")

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    summary_markdown = paths["summary"].read_text(encoding="utf-8")
    assert manifest["summary"] == {
        "raw_rows": 3,
        "latest_cells": 3,
        "renderable_cells": 3,
        "provider_error_cells": 0,
        "reviewed_cells": 2,
        "unreviewed_renderable_cells": 1,
    }
    by_prompt = {row["seed_id"]: row for row in manifest["prompts"]}
    assert by_prompt["planter_01_minimal"]["average_score"] == 3
    assert by_prompt["planter_01_minimal"]["unreviewed_count"] == 1
    assert by_prompt["planter_10_full"]["average_score"] == 8
    assert manifest["correlation"]["pearson_r"] == 1.0
    assert "Combined Blind Review Report" in summary_markdown
    assert "planter_10_full" in summary_markdown
