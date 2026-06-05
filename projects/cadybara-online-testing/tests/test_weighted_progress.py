from __future__ import annotations

import math

from cadybara.config import ExperimentConfig
from cadybara.records import RunRecord
from cadybara.strategies.base import make_variant_id
from cadybara_online_testing.progress import weighted_progress


def config() -> ExperimentConfig:
    return ExperimentConfig.model_validate(
        {
            "experiment_id": "weighted",
            "output_path": "workspace/weighted/results.jsonl",
            "models": [
                {
                    "name": "small:3b",
                    "provider": "ollama",
                    "base_url": "http://localhost:11434",
                    "params_b": 3,
                    "family": "small",
                },
                {
                    "name": "large:7b",
                    "provider": "ollama",
                    "base_url": "http://localhost:11434",
                    "params_b": 7,
                    "family": "large",
                },
            ],
            "seeds": [{"id": "prompt", "text": "Prompt", "metadata": {}}],
            "strategies": [{"name": "identity"}],
            "sampling": {"temperatures": [0.7], "repetitions": 1, "max_tokens": 32},
        }
    )


def record(model_name: str, *, render_error: str | None = None) -> RunRecord:
    return RunRecord(
        run_id=f"run-{model_name}",
        experiment_id="weighted",
        timestamp_utc="2026-05-23T00:00:00Z",
        model_name=model_name,
        provider="ollama",
        seed_id="prompt",
        seed_text="Prompt",
        seed_metadata={},
        strategy="identity",
        variant_id=make_variant_id("identity", "prompt", "Prompt"),
        variant_text="Prompt",
        variant_metadata={},
        output_mode="cadquery",
        sampling={"temperature": 0.7, "seed": 1, "max_tokens": 32},
        repetition=0,
        output="code",
        latency_ms=9000,
        prompt_tokens=None,
        completion_tokens=None,
        finish_reason=None,
        total_duration_ms=9000,
        load_duration_ms=0,
        prompt_eval_duration_ms=0,
        eval_duration_ms=9000,
        provider_seed=None,
        scores={"output_length": 4.0},
        artifacts={"stl": "part.stl"} if render_error is None else {},
        render_error=render_error,
        error=None,
        config_hash="hash",
    )


def test_weighted_progress_and_eta() -> None:
    cfg = config()
    empty = weighted_progress(cfg, [])
    assert empty["weighted_progress"] == 0
    assert empty["eta_seconds"] is None

    small_weight = 3**1.5
    large_weight = 7**1.5
    one_done = weighted_progress(cfg, [record("small:3b")])
    assert math.isclose(one_done["completed_weight"], small_weight)
    assert math.isclose(one_done["weighted_progress"], small_weight / (small_weight + large_weight))
    assert one_done["eta_seconds"] is not None

    terminal = weighted_progress(cfg, [record("small:3b"), record("large:7b", render_error="bad")])
    assert terminal["failed_cells"] == 1
    assert math.isclose(terminal["weighted_progress"], 1.0)
    assert terminal["eta_seconds"] == 0
