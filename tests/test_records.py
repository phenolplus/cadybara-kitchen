from __future__ import annotations

import pytest
from pydantic import ValidationError

from cadybara.records import RunRecord


def record_payload() -> dict:
    return {
        "run_id": "run-1",
        "experiment_id": "exp",
        "timestamp_utc": "2026-05-21T00:00:00Z",
        "model_name": "model",
        "provider": "ollama",
        "seed_id": "seed",
        "seed_text": "Seed text",
        "strategy": "identity",
        "variant_id": "variant",
        "variant_text": "Seed text",
        "variant_metadata": {},
        "sampling": {"temperature": 0.7, "seed": 123, "max_tokens": 512},
        "repetition": 0,
        "output": "result",
        "latency_ms": 10,
        "prompt_tokens": None,
        "completion_tokens": None,
        "finish_reason": None,
        "total_duration_ms": 10,
        "load_duration_ms": 1,
        "prompt_eval_duration_ms": 2,
        "eval_duration_ms": 7,
        "provider_seed": 123,
        "scores": {"output_length": 6.0},
        "error": None,
        "config_hash": "abc123",
    }


def test_run_record_round_trips_json() -> None:
    record = RunRecord.model_validate(record_payload())
    parsed = RunRecord.model_validate_json(record.model_dump_json())
    assert parsed == record
    assert parsed.total_duration_ms == 10
    assert parsed.config_hash == "abc123"


def test_run_record_required_fields_enforced() -> None:
    payload = record_payload()
    del payload["run_id"]
    with pytest.raises(ValidationError):
        RunRecord.model_validate(payload)
