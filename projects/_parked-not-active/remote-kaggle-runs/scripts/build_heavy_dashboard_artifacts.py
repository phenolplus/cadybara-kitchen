from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cadybara.cadquery_runner import write_cadquery_artifacts
from cadybara.records import RunRecord


ROOT = Path("projects/remote-kaggle-runs/workspace/kaggle_downloads/heavy_loop")
SUMMARY_PATH = ROOT / "summary.json"
DETAIL_PATH = ROOT / "detail_index.json"
ARTIFACT_ROOT = ROOT / "rendered"


def href(path: str | Path | None) -> str | None:
    if not path:
        return None
    value = Path(path)
    try:
        return value.relative_to(ROOT).as_posix()
    except ValueError:
        return value.as_posix()


def records(path: Path) -> list[RunRecord]:
    if not path.exists():
        return []
    found: list[RunRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            found.append(RunRecord.model_validate_json(line))
    return found


def build_record_detail(record: RunRecord) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "run_id": record.run_id,
        "prompt_id": record.seed_id,
        "prompt_text": record.seed_text,
        "repetition": record.repetition,
        "repair_round": record.repair_round,
        "repair_total_rounds": record.repair_total_rounds,
        "output_chars": len(record.output or ""),
        "error": record.error,
        "render_error": record.render_error,
        "artifacts": {},
    }
    if not record.output.strip():
        detail["render_error"] = record.error or "model returned empty output"
        return detail

    artifacts, render_error = write_cadquery_artifacts(
        record=record,
        prompt_sent=record.prompt_sent,
        artifact_root=ARTIFACT_ROOT,
    )
    detail["artifacts"] = {key: href(value) for key, value in artifacts.items()}
    detail["render_error"] = render_error
    return detail


def build_detail(item: dict[str, Any]) -> dict[str, Any]:
    result_path = Path(item["validation"]["path"])
    detail: dict[str, Any] = {
        "model": item["model"],
        "kernel": item["kernel"],
        "status": item["status"],
        "validation": item["validation"],
        "results_href": href(result_path),
        "records": [],
        "render_error": None,
    }
    model_records = records(result_path)
    if not model_records:
        detail["render_error"] = "missing or empty results.jsonl"
        return detail

    detail["records"] = [build_record_detail(record) for record in model_records]
    errors = [record["render_error"] for record in detail["records"] if record["render_error"]]
    detail["render_error"] = "; ".join(errors[:2]) if errors else None
    return detail


def main() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    details = [build_detail(item) for item in summary]
    DETAIL_PATH.write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    record_details = [record for item in details for record in item["records"]]
    ok_previews = sum(1 for record in record_details if record["artifacts"].get("preview_png"))
    ok_stls = sum(1 for record in record_details if record["artifacts"].get("stl"))
    print(f"wrote {DETAIL_PATH}")
    print(f"rendered STLs: {ok_stls}/{len(record_details)}")
    print(f"rendered previews: {ok_previews}/{len(record_details)}")


if __name__ == "__main__":
    main()
