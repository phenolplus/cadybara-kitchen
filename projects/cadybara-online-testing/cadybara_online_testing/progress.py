from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from cadybara.config import ExperimentConfig, ModelConfig
from cadybara.records import RunRecord, resume_key
from cadybara.runner import build_cells, cell_key, record_is_complete


def record_failed(record: RunRecord) -> bool:
    return record.error is not None or record.render_error is not None


def record_has_viewable_stl(record: RunRecord) -> bool:
    artifacts = record.artifacts or {}
    if not artifacts.get("stl") or record.error is not None:
        return False
    return record.render_error is None or (
        record.provider == "cadybara_api" and bool(artifacts.get("hosted_stl"))
    )


def model_weight(model: ModelConfig) -> float:
    params_b = model.params_b or 1.0
    return float(params_b) ** 1.5


def records_by_key(
    records: list[RunRecord],
    *,
    include_dry_run: bool = True,
) -> dict[tuple[str, str, str, str, float, int], list[RunRecord]]:
    grouped: dict[tuple[str, str, str, str, float, int], list[RunRecord]] = defaultdict(list)
    for record in records:
        if not include_dry_run and record.provider == "dry_run":
            continue
        grouped[resume_key(record)].append(record)
    return grouped


def weighted_progress(
    config: ExperimentConfig,
    records: list[RunRecord],
    *,
    include_dry_run: bool = True,
) -> dict[str, Any]:
    cells = build_cells(config)
    grouped = records_by_key(records, include_dry_run=include_dry_run)
    max_attempts = config.sampling.max_attempts_per_cell
    total_weight = sum(model_weight(cell.model) for cell in cells)
    completed_weight = 0.0
    failed_weight = 0.0
    completed_latency_seconds = 0.0
    completed_cells = 0
    failed_cells = 0

    for cell in cells:
        key = cell_key(config.experiment_id, cell)
        attempts = grouped.get(key, [])
        complete_record = next((record for record in attempts if record_is_complete(record)), None)
        weight = model_weight(cell.model)
        if complete_record is not None:
            if record_failed(complete_record):
                failed_cells += 1
                failed_weight += weight
            else:
                completed_cells += 1
                completed_weight += weight
                completed_latency_seconds += max(complete_record.latency_ms / 1000.0, 0.001)
            continue
        if attempts and not (config.repair and config.repair.enabled) and len(attempts) >= max_attempts:
            failed_cells += 1
            failed_weight += weight

    terminal_weight = completed_weight + failed_weight
    terminal_cells = completed_cells + failed_cells
    queued_cells = max(len(cells) - terminal_cells, 0)
    remaining_weight = max(total_weight - terminal_weight, 0.0)
    if completed_weight > 0 and completed_latency_seconds > 0:
        weight_per_second = completed_weight / completed_latency_seconds
        eta_seconds = remaining_weight / weight_per_second if weight_per_second > 0 else None
    else:
        eta_seconds = None

    return {
        "total_cells": len(cells),
        "completed_cells": completed_cells,
        "failed_cells": failed_cells,
        "queued_cells": queued_cells,
        "executed_cells": terminal_cells,
        "total_weight": total_weight,
        "completed_weight": completed_weight,
        "failed_weight": failed_weight,
        "terminal_weight": terminal_weight,
        "weighted_progress": terminal_weight / total_weight if total_weight else 0.0,
        "eta_seconds": eta_seconds,
    }


def run_status_payload(
    config: ExperimentConfig,
    records: list[RunRecord],
    *,
    active_snapshot: dict[str, Any] | None = None,
    started_at: float | None = None,
    include_dry_run: bool = False,
) -> dict[str, Any]:
    progress = weighted_progress(config, records, include_dry_run=include_dry_run)
    cells = build_cells(config)
    grouped = records_by_key(records, include_dry_run=include_dry_run)
    active_snapshot = active_snapshot or {"is_running": False}
    active_model = active_snapshot.get("model_name") if active_snapshot.get("is_running") else None
    active_prompt = active_snapshot.get("prompt_id")
    active_rep = active_snapshot.get("repetition")
    now = time.monotonic()

    model_rows = []
    for model in config.models:
        model_cells = [cell for cell in cells if cell.model.name == model.name]
        model_weight_total = sum(model_weight(cell.model) for cell in model_cells)
        model_terminal_weight = 0.0
        model_failed = 0
        model_completed = 0
        for cell in model_cells:
            attempts = grouped.get(cell_key(config.experiment_id, cell), [])
            complete_record = next((record for record in attempts if record_is_complete(record)), None)
            if complete_record is not None:
                if record_failed(complete_record):
                    model_failed += 1
                else:
                    model_completed += 1
                model_terminal_weight += model_weight(cell.model)
            elif attempts and len(attempts) >= config.sampling.max_attempts_per_cell:
                if not (config.repair and config.repair.enabled):
                    model_failed += 1
                    model_terminal_weight += model_weight(cell.model)

        if active_model == model.name:
            status = "running"
            current_cell = f"{active_prompt}, rep {active_rep}"
            if active_snapshot.get("repair_round"):
                current_cell += (
                    f", round {active_snapshot.get('repair_round')}/"
                    f"{active_snapshot.get('repair_total_rounds')}"
                )
        elif model_cells and model_completed + model_failed >= len(model_cells):
            status = "failed" if model_failed else "done"
            current_cell = None
        else:
            status = "queued"
            current_cell = None
        model_rows.append(
            {
                "name": model.name,
                "family": model.family,
                "params_b": model.params_b,
                "status": status,
                "completed": model_completed,
                "failed": model_failed,
                "total": len(model_cells),
                "progress": model_terminal_weight / model_weight_total if model_weight_total else 0.0,
                "current_cell": current_cell,
            }
        )

    recent_renders = []
    for record in reversed(records):
        artifacts = record.artifacts or {}
        stl = artifacts.get("stl")
        preview_png = artifacts.get("preview_png")
        if (stl or preview_png) and record_has_viewable_stl(record):
            recent_renders.append(
                {
                    "run_id": record.run_id,
                    "model_name": record.model_name,
                    "prompt_id": record.seed_id,
                    "repetition": record.repetition,
                    "repair_round": record.repair_round,
                    "stl": stl,
                    "preview_png": preview_png,
                    "viewer_url": f"/viewer/?stl=/{stl}" if stl else None,
                }
            )
        if len(recent_renders) >= 6:
            break

    return {
        "experiment_id": config.experiment_id,
        "model_count": len(config.models),
        "prompt_count": len(config.seeds),
        "repetitions": config.sampling.repetitions,
        "condition_count": len(cells),
        "elapsed_seconds": round(now - started_at, 1) if started_at else 0,
        "progress": progress,
        "models": model_rows,
        "recent_renders": recent_renders,
    }
