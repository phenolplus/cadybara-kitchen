from __future__ import annotations

import csv
from pathlib import Path

from cadybara.runner import MalformedJsonlError, read_jsonl_records


CSV_FIELDNAMES = [
    "run_id",
    "experiment_id",
    "timestamp_utc",
    "model_name",
    "provider",
    "seed_id",
    "prompt_level",
    "detail",
    "strategy",
    "variant_id",
    "temperature",
    "repetition",
    "attempt",
    "sampling_seed",
    "max_tokens",
    "output_mode",
    "is_product",
    "provider_error",
    "render_error",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_duration_ms",
    "load_duration_ms",
    "prompt_eval_duration_ms",
    "eval_duration_ms",
    "cadquery_code_path",
    "stl_path",
    "step_path",
    "output_length",
    "condition_name",
]


def export_attempts_csv(
    input_jsonl: Path,
    output_csv: Path,
    *,
    strict_jsonl: bool = False,
) -> tuple[int, int]:
    result = read_jsonl_records(input_jsonl, strict_jsonl=strict_jsonl)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for record in result.records:
            metadata = record.seed_metadata or record.variant_metadata or {}
            artifacts = record.artifacts or {}
            is_product = (
                record.error is None
                and record.render_error is None
                and bool(artifacts.get("stl"))
            )
            writer.writerow(
                {
                    "run_id": record.run_id,
                    "experiment_id": record.experiment_id,
                    "timestamp_utc": record.timestamp_utc,
                    "model_name": record.model_name,
                    "provider": record.provider,
                    "seed_id": record.seed_id,
                    "prompt_level": metadata.get("prompt_level"),
                    "detail": metadata.get("detail"),
                    "strategy": record.strategy,
                    "variant_id": record.variant_id,
                    "temperature": record.sampling.get("temperature"),
                    "repetition": record.repetition,
                    "attempt": record.attempt,
                    "sampling_seed": record.sampling.get("seed"),
                    "max_tokens": record.sampling.get("max_tokens"),
                    "output_mode": record.output_mode,
                    "is_product": is_product,
                    "provider_error": record.error or "",
                    "render_error": (
                        (record.render_error or "").splitlines()[0]
                        if (record.render_error or "").splitlines()
                        else ""
                    ),
                    "latency_ms": record.latency_ms,
                    "prompt_tokens": record.prompt_tokens,
                    "completion_tokens": record.completion_tokens,
                    "total_duration_ms": record.total_duration_ms,
                    "load_duration_ms": record.load_duration_ms,
                    "prompt_eval_duration_ms": record.prompt_eval_duration_ms,
                    "eval_duration_ms": record.eval_duration_ms,
                    "cadquery_code_path": artifacts.get("cadquery_code", ""),
                    "stl_path": artifacts.get("stl", ""),
                    "step_path": artifacts.get("step", ""),
                    "output_length": len(record.output),
                    "condition_name": record.condition_name,
                }
            )
    return len(result.records), result.malformed_count
