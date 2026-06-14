from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

from cadybara.config import ExperimentConfig, load_config
from cadybara_online_testing.reviews import review_items, review_path


DEFAULT_CONFIG_PATHS = [
    Path("projects/cadybara-online-testing/configs/online_smoke_reps2.yaml"),
    Path("projects/cadybara-online-testing/configs/online_smoke_blind_extra.yaml"),
    Path("projects/cadybara-online-testing/configs/online_smoke_blind_extra2.yaml"),
    Path("projects/cadybara-online-testing/configs/online_smoke_blind_extra3.yaml"),
    Path("projects/cadybara-online-testing/configs/online_smoke_blind_20260608_reps3.yaml"),
]


def _cell_key(item: dict[str, Any]) -> str:
    return "|".join(
        str(item.get(name))
        for name in (
            "config_path",
            "experiment_id",
            "model_name",
            "seed_id",
            "condition_name",
            "temperature",
            "repetition",
        )
    )


def _latest_cells(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        key = _cell_key(item)
        previous = by_key.get(key)
        history = [*(previous.get("attempt_history", []) if previous else []), item]
        by_key[key] = {
            **item,
            "raw_index": index,
            "attempt_count": len(history),
            "attempt_history": history,
        }
    return list(by_key.values())


def _status(item: dict[str, Any]) -> str:
    if item.get("error"):
        return "provider_error"
    if item.get("is_renderable") and item.get("render_error"):
        return "hosted_stl_source_failed"
    if item.get("is_renderable"):
        return "renderable"
    if item.get("render_error"):
        return "render_failed"
    return "no_stl"


def _score(item: dict[str, Any]) -> int | None:
    review = item.get("review")
    if not isinstance(review, dict):
        return None
    value = review.get("score")
    return value if isinstance(value, int) else None


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    x_mean = mean(xs)
    y_mean = mean(ys)
    x_delta = [value - x_mean for value in xs]
    y_delta = [value - y_mean for value in ys]
    x_var = sum(value * value for value in x_delta)
    y_var = sum(value * value for value in y_delta)
    if x_var == 0 or y_var == 0:
        return None
    return sum(x * y for x, y in zip(x_delta, y_delta, strict=True)) / ((x_var * y_var) ** 0.5)


def _seed_lookup(configs: list[ExperimentConfig]) -> dict[str, dict[str, Any]]:
    seeds: dict[str, dict[str, Any]] = {}
    for config in configs:
        for index, seed in enumerate(config.seeds, start=1):
            seeds.setdefault(
                seed.id,
                {
                    "seed_id": seed.id,
                    "prompt_order": index,
                    "specificity_level": seed.metadata.get("specificity_level"),
                    "seed_text": seed.text,
                    "metadata": seed.metadata,
                },
            )
    return seeds


def _compact_cell(item: dict[str, Any], seed_meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    artifacts = item.get("artifacts") if isinstance(item.get("artifacts"), dict) else {}
    provider_metadata = item.get("provider_metadata") if isinstance(item.get("provider_metadata"), dict) else {}
    validation = provider_metadata.get("validation") if isinstance(provider_metadata.get("validation"), dict) else {}
    seed = seed_meta.get(str(item.get("seed_id")), {})
    return {
        "config_path": item.get("config_path"),
        "experiment_id": item.get("experiment_id"),
        "run_id": item.get("run_id"),
        "model_name": item.get("model_name"),
        "provider": item.get("provider"),
        "seed_id": item.get("seed_id"),
        "specificity_level": seed.get("specificity_level"),
        "repetition": item.get("repetition"),
        "temperature": item.get("temperature"),
        "status": _status(item),
        "is_renderable": item.get("is_renderable"),
        "attempt_count": item.get("attempt_count", 1),
        "latency_ms": item.get("latency_ms"),
        "review_score": _score(item),
        "review": item.get("review"),
        "error": item.get("error"),
        "render_error": item.get("render_error"),
        "validation_valid": validation.get("valid"),
        "validation_confidence": validation.get("confidence"),
        "validation_reason": validation.get("brief_reason"),
        "stl_path": artifacts.get("stl"),
        "hosted_stl_path": artifacts.get("hosted_stl"),
        "preview_png_path": artifacts.get("preview_png"),
        "cadquery_code_path": artifacts.get("cadquery_code"),
        "model_output_path": artifacts.get("model_output"),
        "artifact_folder": artifacts.get("folder"),
    }


def _markdown_report(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    lines = [
        "# Combined Blind Review Report",
        "",
        "This folder is rebuilt from saved run JSONL files plus append-only browser",
        "review score JSONL files. Re-run the report after new hosted pulls or new",
        "blind scores; it does not regenerate CAD or spend API credits.",
        "",
        "## Totals",
        "",
        f"- Raw saved rows: {summary['raw_rows']}",
        f"- Latest run cells: {summary['latest_cells']}",
        f"- Renderable STL cells: {summary['renderable_cells']}",
        f"- Provider error cells: {summary['provider_error_cells']}",
        f"- Reviewed cells: {summary['reviewed_cells']}",
        f"- Unreviewed renderable cells: {summary['unreviewed_renderable_cells']}",
        "",
        "## Prompt Averages",
        "",
        "| Specificity | Prompt ID | Models | Renderable | Reviewed | Unreviewed | Average score |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in manifest["prompts"]:
        average = row["average_score"] if row["average_score"] is not None else ""
        lines.append(
            "| "
            f"{row['specificity_level']} | "
            f"{row['seed_id']} | "
            f"{row['model_count']} | "
            f"{row['renderable_count']} | "
            f"{row['reviewed_count']} | "
            f"{row['unreviewed_count']} | "
            f"{average} |"
        )

    correlation = manifest["correlation"]
    pearson = correlation["pearson_r"]
    lines.extend(
        [
            "",
            "## Correlation",
            "",
            f"- Metric: {correlation['metric']}",
            f"- Prompts with scores: {correlation['n_prompts']}",
            f"- Pearson r: {round(pearson, 3) if pearson is not None else 'not enough data'}",
            f"- Note: {correlation['note']}",
            "",
            "## Included Configs",
            "",
        ]
    )
    for config in manifest["configs"]:
        lines.append(
            "- "
            f"{config['experiment_id']}: {config['latest_cells']} latest cells, "
            f"{config['renderable_rows']} renderable rows, "
            f"{config['reviewed_rows']} reviewed rows"
        )

    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `manifest.json`: full combined data, including model/code/STL paths.",
            "- `prompt_goodness.csv`: one row per prompt definition.",
            "- `review_cells.csv`: one row per latest model cell.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_blind_review_report(
    config_paths: Iterable[str | Path],
    output_dir: str | Path,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    configs = [load_config(path) for path in config_paths]
    seed_meta = _seed_lookup(configs)
    configs_summary = []
    raw_items = []

    for config_path, config in zip(config_paths, configs, strict=True):
        config_path = Path(config_path)
        payload = review_items(Path(config.output_path), experiment_id=config.experiment_id)
        items = [{**item, "config_path": config_path.as_posix()} for item in payload["items"]]
        raw_items.extend(items)
        scores_path = review_path(config.experiment_id)
        configs_summary.append(
            {
                "config_path": config_path.as_posix(),
                "experiment_id": config.experiment_id,
                "output_path": config.output_path,
                "review_path": scores_path.as_posix(),
                "raw_rows": len(items),
                "latest_cells": len(_latest_cells(items)),
                "renderable_rows": payload["renderable_rows"],
                "provider_error_rows": payload["provider_error_rows"],
                "reviewed_rows": payload["reviewed_rows"],
            }
        )

    latest_items = _latest_cells(raw_items)
    cells = [_compact_cell(item, seed_meta) for item in latest_items]

    by_prompt: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        by_prompt[str(cell["seed_id"])].append(cell)

    prompt_rows = []
    for seed_id, prompt_cells in sorted(
        by_prompt.items(),
        key=lambda pair: (
            seed_meta.get(pair[0], {}).get("specificity_level") or 999,
            pair[0],
        ),
    ):
        scores = [cell["review_score"] for cell in prompt_cells if isinstance(cell.get("review_score"), int)]
        renderable = [cell for cell in prompt_cells if cell.get("is_renderable")]
        provider_errors = [cell for cell in prompt_cells if cell.get("status") == "provider_error"]
        source_failures = [cell for cell in prompt_cells if cell.get("status") == "hosted_stl_source_failed"]
        seed = seed_meta.get(seed_id, {"seed_id": seed_id, "seed_text": ""})
        prompt_rows.append(
            {
                "seed_id": seed_id,
                "prompt_order": seed.get("prompt_order"),
                "specificity_level": seed.get("specificity_level"),
                "seed_text": seed.get("seed_text"),
                "model_count": len(prompt_cells),
                "renderable_count": len(renderable),
                "provider_error_count": len(provider_errors),
                "hosted_stl_source_failed_count": len(source_failures),
                "reviewed_count": len(scores),
                "unreviewed_count": sum(1 for cell in prompt_cells if cell.get("is_renderable") and cell.get("review_score") is None),
                "average_score": round(mean(scores), 3) if scores else None,
                "median_score": median(scores) if scores else None,
                "scores": scores,
                "run_ids": [cell.get("run_id") for cell in prompt_cells],
            }
        )

    corr_rows = [
        row
        for row in prompt_rows
        if isinstance(row.get("specificity_level"), int) and row.get("average_score") is not None
    ]
    specificity = [float(row["specificity_level"]) for row in corr_rows]
    average_scores = [float(row["average_score"]) for row in corr_rows]
    correlation = {
        "metric": "specificity_level_vs_average_review_score",
        "n_prompts": len(corr_rows),
        "pearson_r": _pearson(specificity, average_scores),
        "note": "Computed only from prompts with at least one saved review score.",
    }

    manifest = {
        "configs": configs_summary,
        "summary": {
            "raw_rows": len(raw_items),
            "latest_cells": len(cells),
            "renderable_cells": sum(1 for cell in cells if cell.get("is_renderable")),
            "provider_error_cells": sum(1 for cell in cells if cell.get("status") == "provider_error"),
            "reviewed_cells": sum(1 for cell in cells if cell.get("review_score") is not None),
            "unreviewed_renderable_cells": sum(
                1 for cell in cells if cell.get("is_renderable") and cell.get("review_score") is None
            ),
        },
        "correlation": correlation,
        "prompts": prompt_rows,
        "cells": cells,
    }

    manifest_path = output_path / "manifest.json"
    prompt_csv_path = output_path / "prompt_goodness.csv"
    cell_csv_path = output_path / "review_cells.csv"
    markdown_path = output_path / "README.md"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown_report(manifest), encoding="utf-8")

    with prompt_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "seed_id",
                "prompt_order",
                "specificity_level",
                "model_count",
                "renderable_count",
                "provider_error_count",
                "hosted_stl_source_failed_count",
                "reviewed_count",
                "unreviewed_count",
                "average_score",
                "median_score",
                "scores",
                "seed_text",
            ],
        )
        writer.writeheader()
        for row in prompt_rows:
            writer.writerow({name: row.get(name) for name in writer.fieldnames})

    with cell_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "config_path",
                "experiment_id",
                "run_id",
                "seed_id",
                "specificity_level",
                "repetition",
                "status",
                "is_renderable",
                "attempt_count",
                "latency_ms",
                "review_score",
                "stl_path",
                "hosted_stl_path",
                "cadquery_code_path",
                "model_output_path",
            ],
        )
        writer.writeheader()
        for cell in cells:
            writer.writerow({name: cell.get(name) for name in writer.fieldnames})

    return {
        "manifest": manifest_path,
        "summary": markdown_path,
        "prompt_csv": prompt_csv_path,
        "cell_csv": cell_csv_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a combined blind review manifest and CSVs.")
    parser.add_argument(
        "--config",
        action="append",
        dest="config_paths",
        default=[],
        help="Config path to include. Repeat to combine multiple runs.",
    )
    parser.add_argument(
        "--output-dir",
        default="projects/cadybara-online-testing/workspace/reviews/combined_prompt_goodness_latest",
        help="Directory where manifest.json and CSV summaries are written.",
    )
    args = parser.parse_args()
    config_paths = [Path(path) for path in args.config_paths] or DEFAULT_CONFIG_PATHS
    paths = build_blind_review_report(config_paths, args.output_dir)
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
