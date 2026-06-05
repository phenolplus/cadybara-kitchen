from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from cadybara.runner import read_jsonl_records


def export_training_pairs(
    input_path: str | Path,
    output_path: str | Path,
    *,
    include_errors: bool = False,
    strict_jsonl: bool = False,
    stream: TextIO | None = None,
) -> tuple[int, int]:
    result = read_jsonl_records(Path(input_path), strict_jsonl=strict_jsonl)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0

    with output.open("w", encoding="utf-8") as handle:
        for record in result.records:
            if record.error is not None and not include_errors:
                skipped += 1
                continue
            if not record.output and not include_errors:
                skipped += 1
                continue
            row = {
                "messages": [
                    {"role": "user", "content": record.variant_text},
                    {"role": "assistant", "content": record.output},
                ],
                "metadata": {
                    "run_id": record.run_id,
                    "experiment_id": record.experiment_id,
                    "model_name": record.model_name,
                    "provider": record.provider,
                    "seed_id": record.seed_id,
                    "strategy": record.strategy,
                    "variant_id": record.variant_id,
                    "sampling": record.sampling,
                    "scores": record.scores,
                    "error": record.error,
                    "config_hash": record.config_hash,
                },
            }
            handle.write(json.dumps(row, separators=(",", ":")))
            handle.write("\n")
            written += 1

    if stream is not None and result.malformed_count:
        print(
            f"Warning: skipped {result.malformed_count} malformed JSONL row(s) in {input_path}.",
            file=stream,
        )
    return written, skipped
