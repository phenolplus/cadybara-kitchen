from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Vec3(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    z: float


class Hole2D(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    radius: float


class PartObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["box", "cylinder", "plate_with_holes"]
    position: Vec3 = Field(default_factory=lambda: Vec3(x=0.0, y=0.0, z=0.0))
    size: Vec3 | None = None
    radius: float | None = None
    depth: float | None = None
    axis: Literal["x", "y", "z"] = "z"
    holes: list[Hole2D] = Field(default_factory=list)
    color: str = "#67b7dc"
    opacity: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PartScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    id: str
    name: str
    units: str = "mm"
    objects: list[PartObject]
    metadata: dict[str, Any] = Field(default_factory=dict)


def sample_mounting_plate() -> PartScene:
    return PartScene(
        id="sample_mounting_plate",
        name="Sample mounting plate",
        units="mm",
        objects=[
            PartObject(
                id="plate",
                kind="plate_with_holes",
                size=Vec3(x=100.0, y=50.0, z=6.0),
                holes=[
                    Hole2D(x=-35.0, y=-15.0, radius=4.0),
                    Hole2D(x=35.0, y=-15.0, radius=4.0),
                    Hole2D(x=-35.0, y=15.0, radius=4.0),
                    Hole2D(x=35.0, y=15.0, radius=4.0),
                ],
                color="#62a87c",
                metadata={"feature": "baseline plate with four through holes"},
            ),
            PartObject(
                id="center_boss",
                kind="cylinder",
                position=Vec3(x=0.0, y=0.0, z=6.0),
                radius=8.0,
                depth=8.0,
                axis="z",
                color="#d0a85c",
                metadata={"feature": "raised boss for depth perception"},
            ),
        ],
        metadata={"source": "cadybara sample artifact"},
    )


def write_part_scene(scene: PartScene, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(scene.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def load_part_scene(path: str | Path) -> PartScene:
    return PartScene.model_validate_json(Path(path).read_text(encoding="utf-8"))
