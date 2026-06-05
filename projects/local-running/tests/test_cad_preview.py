from __future__ import annotations

from pathlib import Path

import pytest

from cadybara.cadquery_runner import export_cadquery_code, render_stl_preview


def test_render_stl_preview_writes_png(tmp_path: Path) -> None:
    pytest.importorskip("vtk")
    stl_path = tmp_path / "box.stl"
    step_path = tmp_path / "box.step"
    png_path = tmp_path / "preview.png"

    export_cadquery_code(
        'import cadquery as cq\nresult = cq.Workplane("XY").box(10, 20, 5)\n',
        stl_path,
        step_path,
    )
    render_stl_preview(stl_path, png_path, width=160, height=120)

    assert png_path.exists()
    assert png_path.read_bytes().startswith(b"\x89PNG")
