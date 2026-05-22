from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cadybara.records import RunRecord
from cadybara.runner import read_jsonl_records


def review_path(experiment_id: str) -> Path:
    return Path("workspace") / "reviews" / f"{experiment_id}_reviews.jsonl"


def timestamp_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def latest_scores(path: Path) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return scores
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            run_id = payload.get("run_id")
            if isinstance(run_id, str):
                scores[run_id] = payload
    return scores


def append_score(path: Path, *, run_id: str, score: int) -> dict[str, Any]:
    if score < 1 or score > 10:
        raise ValueError("score must be between 1 and 10")
    payload = {
        "run_id": run_id,
        "score": score,
        "timestamp_utc": timestamp_utc(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
        handle.flush()
    return payload


def review_items(output_path: Path, *, experiment_id: str) -> dict[str, Any]:
    rows = read_jsonl_records(output_path)
    scores = latest_scores(review_path(experiment_id))
    items = []
    for record in rows.records:
        item = record_to_review_item(record)
        item["review"] = scores.get(record.run_id)
        items.append(item)
    return {
        "output_path": str(output_path),
        "valid_rows": len(rows.records),
        "malformed_rows": rows.malformed_count,
        "reviewed_rows": sum(1 for item in items if item["review"] is not None),
        "items": items,
    }


def record_to_review_item(record: RunRecord) -> dict[str, Any]:
    artifacts = record.artifacts or {}
    stl_path = artifacts.get("stl")
    code_path = artifacts.get("cadquery_code")
    return {
        "run_id": record.run_id,
        "experiment_id": record.experiment_id,
        "timestamp_utc": record.timestamp_utc,
        "model_name": record.model_name,
        "provider": record.provider,
        "seed_id": record.seed_id,
        "seed_text": record.seed_text,
        "condition_name": record.condition_name,
        "temperature": record.sampling.get("temperature"),
        "repetition": record.repetition,
        "output_mode": record.output_mode,
        "latency_ms": record.latency_ms,
        "prompt_tokens": record.prompt_tokens,
        "completion_tokens": record.completion_tokens,
        "error": record.error,
        "render_error": record.render_error,
        "artifacts": artifacts,
        "viewer_url": f"/viewer/?stl=/{stl_path}" if stl_path else None,
        "code_url": f"/{code_path}" if code_path else None,
    }
