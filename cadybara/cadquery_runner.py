from __future__ import annotations

import json
import math
import re
import traceback
from pathlib import Path
from typing import Any

from cadybara.records import RunRecord


CADQUERY_PROMPT_TEMPLATE = """You are generating parametric CAD source code.

Return only Python CadQuery code. Do not explain the design in prose.

Hard requirements:
- Use millimeters.
- Use `import cadquery as cq`.
- Define the final model in a variable named `result`.
- `result` must be a CadQuery Workplane or Shape.
- Do not call `cq.exporters.export`; the harness exports STL and STEP after your code runs.
- Do not read files, write files, use networking, shell commands, subprocesses, or external packages.
- Do not use CadQuery string selectors such as `.vertices("[1:-1]")`; use explicit Workplanes and cuts.
- Prefer simple, printable, watertight solids using boxes, cylinders, holes, cuts, unions, fillets, and chamfers.
- Keep the model as a single 3D-printable object when the request asks for one.
- If fillets fail on complex geometry, omit them instead of making invalid code.

Use this style:
import cadquery as cq

outer = cq.Workplane("XY").circle(40).extrude(90)
inner = cq.Workplane("XY").workplane(offset=3).circle(37).extrude(88)
body = outer.cut(inner)
back = cq.Workplane("XY").box(90, 4, 100).translate((0, 42, 50))
result = body.union(back)

Design request:
{design_prompt}
"""


BLOCK_RE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
DISALLOWED_PATTERNS = (
    "subprocess",
    "socket",
    "requests",
    "httpx",
    "urllib",
    "shutil",
    "pathlib",
    "open(",
    "import os",
    "from os",
    "import sys",
    "from sys",
    "exec(",
    "eval(",
    "exporters.export",
    "__",
    "os.",
    "sys.",
)


def cadquery_prompt(design_prompt: str) -> str:
    return CADQUERY_PROMPT_TEMPLATE.format(design_prompt=design_prompt)


def sample_wall_planter_code() -> str:
    return """import cadquery as cq

outer = cq.Workplane("XY").circle(40).extrude(90)
inner = cq.Workplane("XY").workplane(offset=3).circle(37).extrude(88)
body = outer.cut(inner)

back = cq.Workplane("XY").box(90, 4, 100).translate((0, 42, 50))
result = body.union(back)

for x in (-15, 15):
    for y in (-15, 15):
        cutter = cq.Workplane("XY").center(x, y).circle(1.5).extrude(6)
        result = result.cut(cutter)

key_round = cq.Workplane("XZ", origin=(0, 44, 82)).circle(4).extrude(8)
key_slot = cq.Workplane("XZ", origin=(0, 44, 72)).rect(4, 20).extrude(8)
result = result.cut(key_round).cut(key_slot)
"""


def extract_code(output: str) -> str:
    match = BLOCK_RE.search(output)
    if match:
        return match.group(1).strip() + "\n"
    return output.strip() + "\n"


def safe_slug(value: str, *, max_length: int = 80) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return (cleaned or "item")[:max_length]


def run_artifact_dir(root: Path, record: RunRecord) -> Path:
    condition = record.condition_name or f"{record.seed_id}_r{record.repetition}"
    return (
        root
        / safe_slug(record.model_name)
        / safe_slug(record.seed_id)
        / safe_slug(condition)
        / safe_slug(record.run_id[:8])
    )


def check_code_safety(code: str) -> None:
    lowered = code.lower()
    for pattern in DISALLOWED_PATTERNS:
        if pattern in lowered:
            raise ValueError(f"CAD code contains disallowed pattern: {pattern}")


def export_cadquery_code(code: str, stl_path: Path, step_path: Path) -> None:
    check_code_safety(code)
    import cadquery as cq  # noqa: PLC0415 - optional heavy CAD dependency.

    namespace: dict[str, Any] = {
        "cq": cq,
        "math": math,
        "__builtins__": {
            "__import__": __import__,
            "abs": abs,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "range": range,
            "round": round,
            "set": set,
            "sum": sum,
            "tuple": tuple,
        },
    }
    exec(compile(code, "<cadquery-generated>", "exec"), namespace)  # noqa: S102
    result = namespace.get("result")
    if result is None:
        raise ValueError("CAD code did not define a `result` variable.")
    stl_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(result, str(stl_path))
    cq.exporters.export(result, str(step_path))


def write_cadquery_artifacts(
    *,
    record: RunRecord,
    prompt_sent: str,
    artifact_root: Path,
) -> tuple[dict[str, Any], str | None]:
    folder = run_artifact_dir(artifact_root, record)
    folder.mkdir(parents=True, exist_ok=True)
    code = extract_code(record.output)
    paths = {
        "folder": folder,
        "prompt": folder / "prompt_sent.txt",
        "seed_prompt": folder / "seed_prompt.txt",
        "model_output": folder / "model_output.md",
        "cadquery_code": folder / "model.py",
        "metadata": folder / "metadata.json",
        "stl": folder / "model.stl",
        "step": folder / "model.step",
        "render_error": folder / "render_error.txt",
    }

    paths["prompt"].write_text(prompt_sent, encoding="utf-8")
    paths["seed_prompt"].write_text(record.seed_text, encoding="utf-8")
    paths["model_output"].write_text(record.output, encoding="utf-8")
    paths["cadquery_code"].write_text(code, encoding="utf-8")

    render_error: str | None = None
    try:
        export_cadquery_code(code, paths["stl"], paths["step"])
        if paths["render_error"].exists():
            paths["render_error"].unlink()
    except Exception as exc:  # noqa: BLE001 - stored for review instead of aborting sweep.
        render_error = f"{exc}\n{traceback.format_exc()}"
        paths["render_error"].write_text(render_error, encoding="utf-8")

    metadata = {
        "run_id": record.run_id,
        "experiment_id": record.experiment_id,
        "model_name": record.model_name,
        "provider": record.provider,
        "seed_id": record.seed_id,
        "strategy": record.strategy,
        "variant_id": record.variant_id,
        "sampling": record.sampling,
        "repetition": record.repetition,
        "timestamp_utc": record.timestamp_utc,
        "condition_name": record.condition_name,
        "render_error": render_error,
    }
    paths["metadata"].write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    artifacts = {
        name: path.as_posix()
        for name, path in paths.items()
        if name != "render_error" and (name != "step" or path.exists()) and (name != "stl" or path.exists())
    }
    if render_error:
        artifacts["render_error"] = paths["render_error"].as_posix()
    return artifacts, render_error
