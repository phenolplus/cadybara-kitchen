from __future__ import annotations

import base64
import importlib.util
from pathlib import Path

import pytest

from cadybara.cadquery_runner import (
    cadquery_prompt,
    export_cadquery_code,
    extract_code,
    write_cadquery_artifacts,
)
from cadybara.records import RunRecord
from cadybara.runner import record_is_complete


def test_cadquery_prompt_wraps_design_request() -> None:
    prompt = cadquery_prompt("Make a small bracket.")
    assert "Return only Python CadQuery code" in prompt
    assert "Make a small bracket." in prompt
    assert "result" in prompt
    assert "wall-mounted planter" not in prompt
    assert "outer = cq.Workplane" not in prompt


def test_extract_code_prefers_python_fence() -> None:
    output = "Here:\n```python\nresult = 1\n```\nDone"
    assert extract_code(output) == "result = 1\n"


def test_extract_code_preserves_model_code_for_fair_scoring() -> None:
    output = """
```python
import cadquery as cq
result = cq.Workplane("XY").box(1, 1, 1)
cq.exporters.export(result, "part.stl")
```
"""
    code = extract_code(output)
    assert "exporters.export" in code
    assert "result =" in code


def test_export_cadquery_code_requires_model_to_import_cadquery(tmp_path) -> None:
    if importlib.util.find_spec("cadquery") is None:
        pytest.skip("cadquery is not installed")
    code = 'result = cq.Workplane("XY").box(10, 20, 3)\n'
    with pytest.raises(NameError):
        export_cadquery_code(code, tmp_path / "part.stl", tmp_path / "part.step")


def test_export_cadquery_code_writes_stl_and_step(tmp_path) -> None:
    if importlib.util.find_spec("cadquery") is None:
        pytest.skip("cadquery is not installed")
    code = """
import cadquery as cq
result = cq.Workplane("XY").box(10, 20, 3)
"""
    stl = tmp_path / "part.stl"
    step = tmp_path / "part.step"
    export_cadquery_code(code, stl, step)
    assert stl.exists()
    assert step.exists()
    assert stl.stat().st_size > 0
    assert step.stat().st_size > 0


def test_write_artifacts_preserves_hosted_stl_when_local_code_fails(tmp_path: Path) -> None:
    stl_bytes = b"solid hosted\nendsolid hosted\n"
    record = RunRecord(
        run_id="run-hosted",
        experiment_id="hosted",
        timestamp_utc="2026-06-06T00:00:00Z",
        model_name="cadybara-agent-default",
        provider="cadybara_api",
        seed_id="planter_01_minimal",
        seed_text="Make me a planter I can put on my wall.",
        seed_metadata={},
        strategy="identity",
        variant_id="identity",
        variant_text="Make me a planter I can put on my wall.",
        variant_metadata={},
        prompt_sent="Make me a planter I can put on my wall.",
        output_mode="cadquery",
        condition_name="hosted|planter",
        attempt=1,
        sampling={"temperature": 0.0, "seed": 1, "max_tokens": 1},
        repetition=0,
        output="import cadquery as cq\nimport planter\nresult = planter.build()\n",
        latency_ms=1000,
        prompt_tokens=None,
        completion_tokens=None,
        finish_reason="validation_valid",
        total_duration_ms=1000,
        load_duration_ms=None,
        prompt_eval_duration_ms=None,
        eval_duration_ms=None,
        provider_seed=None,
        scores={},
        artifacts={},
        render_error=None,
        error=None,
        config_hash="hash",
    )

    artifacts, render_error = write_cadquery_artifacts(
        record=record,
        prompt_sent=record.prompt_sent or "",
        artifact_root=tmp_path,
        hosted_stl_base64=base64.b64encode(stl_bytes).decode("ascii"),
    )

    assert render_error
    assert artifacts["stl"] == artifacts["hosted_stl"]
    assert Path(artifacts["stl"]).read_bytes() == stl_bytes
    assert Path(artifacts["cadquery_code"]).exists()

    completed_record = record.model_copy(
        update={"artifacts": artifacts, "render_error": render_error},
    )
    assert record_is_complete(completed_record)
