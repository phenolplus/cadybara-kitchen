from __future__ import annotations

import importlib.util

import pytest

from cadybara.cadquery_runner import cadquery_prompt, export_cadquery_code, extract_code


def test_cadquery_prompt_wraps_design_request() -> None:
    prompt = cadquery_prompt("Make a small bracket.")
    assert "Return only Python CadQuery code" in prompt
    assert "Make a small bracket." in prompt
    assert "result" in prompt


def test_extract_code_prefers_python_fence() -> None:
    output = "Here:\n```python\nresult = 1\n```\nDone"
    assert extract_code(output) == "result = 1\n"


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
