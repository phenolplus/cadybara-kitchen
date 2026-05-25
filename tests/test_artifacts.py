from __future__ import annotations

from pathlib import Path

from cadybara.artifacts import load_part_scene, sample_mounting_plate, write_part_scene


def test_sample_part_artifact_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "sample_part.json"
    write_part_scene(sample_mounting_plate(), path)
    scene = load_part_scene(path)
    assert scene.id == "sample_mounting_plate"
    assert scene.objects[0].kind == "plate_with_holes"
    assert len(scene.objects[0].holes) == 4
