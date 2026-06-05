from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax

from cadybara.cadquery_runner import extract_code
from cadybara.records import RunRecord
from cadybara.runner import read_jsonl_records


class GradeQuit(RuntimeError):
    pass


class CodeRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code_validity: int = Field(ge=0, le=1)
    intent_attempt: int = Field(ge=0, le=3)
    feature_accuracy: int = Field(ge=0, le=3)
    notes: str = ""


class GradeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade_id: str
    experiment_id: str
    model_name: str
    prompt_id: str
    repetition: int
    run_id: str
    repair_round: int | None = None
    rubric: CodeRubric
    graded_at_utc: str
    grader: str


def timestamp_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def grades_path(run_dir: Path) -> Path:
    return run_dir / "grades.jsonl"


def load_grade_records(path: Path) -> list[GradeRecord]:
    if not path.exists():
        return []
    grades: list[GradeRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                grades.append(GradeRecord.model_validate_json(line))
    return grades


def graded_keys(path: Path) -> set[tuple[str, str, int, int | None]]:
    return {
        (grade.model_name, grade.prompt_id, grade.repetition, grade.repair_round)
        for grade in load_grade_records(path)
    }


def code_validity(record: RunRecord) -> int:
    return int(record.error is None and record.render_error is None)


def stl_succeeded(record: RunRecord) -> bool:
    return bool((record.artifacts or {}).get("stl")) and code_validity(record) == 1


def code_for_record(record: RunRecord) -> str:
    code_path = (record.artifacts or {}).get("cadquery_code")
    if isinstance(code_path, str):
        path = Path(code_path)
        if path.exists():
            return path.read_text(encoding="utf-8")
    return extract_code(record.output)


def prompt_score(axis: str) -> int | None:
    while True:
        value = Prompt.ask(f"{axis} [0-3, s skip, q quit]").strip().lower()
        if value == "q":
            raise GradeQuit
        if value == "s":
            return None
        if value in {"0", "1", "2", "3"}:
            return int(value)


def prompt_notes() -> str:
    value = Prompt.ask("notes [Enter none, n add notes]", default="").strip()
    if value.lower() == "n":
        return Prompt.ask("notes").strip()
    return value


def append_grade(path: Path, grade: GradeRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(grade.model_dump_json())
        handle.write("\n")
        handle.flush()


def display_group(console: Console, model_name: str, prompt_id: str, records: list[RunRecord]) -> None:
    prompt_text = records[0].seed_text if records else ""
    prompt_preview = prompt_text[:200] + ("..." if len(prompt_text) > 200 else "")
    console.rule(f"{model_name} / {prompt_id}")
    console.print(prompt_preview, style="bold")

    panels = []
    for record in sorted(records, key=lambda item: (item.repetition, item.repair_round or 0)):
        header = (
            f"rep {record.repetition} | code_validity={code_validity(record)} | "
            f"stl={'yes' if stl_succeeded(record) else 'no'}"
        )
        if record.repair_round is not None:
            header += f" | round {record.repair_round}/{record.repair_total_rounds}"
        syntax = Syntax(code_for_record(record), "python", line_numbers=True, word_wrap=True)
        panels.append(Panel(syntax, title=header, border_style="grey50"))
    console.print(Columns(panels, equal=True, expand=True))


def filter_grade_records(records: list[RunRecord], round_filter: str) -> list[RunRecord]:
    if round_filter == "all":
        return records
    filtered: list[RunRecord] = []
    for record in records:
        if record.repair_total_rounds is None:
            filtered.append(record)
            continue
        if round_filter == "final" and record.repair_round == record.repair_total_rounds:
            filtered.append(record)
            continue
        if round_filter.isdigit() and record.repair_round == int(round_filter):
            filtered.append(record)
    return filtered


def grade_run_dir(
    run_dir: Path,
    *,
    resume: bool = True,
    model_filter: str | None = None,
    prompt_filter: str | None = None,
    round_filter: str = "final",
    grader: str = "aaroh",
    console: Console | None = None,
) -> tuple[int, int, bool]:
    console = console or Console()
    results_path = run_dir / "results.jsonl"
    output_path = grades_path(run_dir)
    records = read_jsonl_records(results_path).records
    groups: dict[tuple[str, str], list[RunRecord]] = defaultdict(list)
    for record in filter_grade_records(records, round_filter):
        if record.provider == "dry_run":
            continue
        if model_filter and model_filter not in record.model_name:
            continue
        if prompt_filter and prompt_filter not in record.seed_id:
            continue
        groups[(record.model_name, record.seed_id)].append(record)

    already_graded = graded_keys(output_path) if resume else set()
    written = 0
    skipped = 0
    quit_requested = False
    try:
        for (model_name, prompt_id), group in sorted(groups.items()):
            pending = [
                record
                for record in sorted(group, key=lambda item: (item.repetition, item.repair_round or 0))
                if (model_name, prompt_id, record.repetition, record.repair_round) not in already_graded
            ]
            if not pending:
                skipped += len(group)
                continue
            display_group(console, model_name, prompt_id, group)
            for record in pending:
                console.print(f"grade rep {record.repetition}", style="bold")
                intent_attempt = prompt_score("intent_attempt")
                if intent_attempt is None:
                    skipped += 1
                    continue
                feature_accuracy = prompt_score("feature_accuracy")
                if feature_accuracy is None:
                    skipped += 1
                    continue
                rubric = CodeRubric(
                    code_validity=code_validity(record),
                    intent_attempt=intent_attempt,
                    feature_accuracy=feature_accuracy,
                    notes=prompt_notes(),
                )
                grade = GradeRecord(
                    grade_id=str(uuid4()),
                    experiment_id=record.experiment_id,
                    model_name=record.model_name,
                    prompt_id=record.seed_id,
                    repetition=record.repetition,
                    run_id=record.run_id,
                    repair_round=record.repair_round,
                    rubric=rubric,
                    graded_at_utc=timestamp_utc(),
                    grader=grader,
                )
                append_grade(output_path, grade)
                already_graded.add((model_name, prompt_id, record.repetition, record.repair_round))
                written += 1
    except GradeQuit:
        quit_requested = True
    return written, skipped, quit_requested


def write_synthetic_results(run_dir: Path, records: list[RunRecord]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.model_dump(mode="json"), separators=(",", ":")))
            handle.write("\n")
