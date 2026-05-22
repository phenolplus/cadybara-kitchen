from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    experiment_id: str
    timestamp_utc: str
    model_name: str
    provider: str
    seed_id: str
    seed_text: str
    strategy: str
    variant_id: str
    variant_text: str
    variant_metadata: dict[str, Any]
    prompt_sent: str | None = None
    output_mode: str = "text"
    condition_name: str | None = None
    sampling: dict[str, Any]
    repetition: int
    output: str
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    finish_reason: str | None
    total_duration_ms: int | None
    load_duration_ms: int | None
    prompt_eval_duration_ms: int | None
    eval_duration_ms: int | None
    provider_seed: int | None
    scores: dict[str, float]
    artifacts: dict[str, Any] = {}
    render_error: str | None = None
    error: str | None
    config_hash: str


def resume_key(record: RunRecord) -> tuple[str, str, str, str, float, int]:
    return (
        record.experiment_id,
        record.model_name,
        record.seed_id,
        record.variant_id,
        float(record.sampling["temperature"]),
        record.repetition,
    )
