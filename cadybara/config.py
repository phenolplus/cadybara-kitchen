from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str
    base_url: str


class SeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class SamplingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperatures: list[float]
    repetitions: int = Field(gt=0)
    max_tokens: int = Field(gt=0)


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    output_path: str
    output_mode: Literal["text", "cadquery"] = "text"
    artifact_root: str | None = None
    models: list[ModelConfig] = Field(min_length=1)
    seeds: list[SeedConfig] = Field(min_length=1)
    strategies: list[StrategyConfig] = Field(min_length=1)
    sampling: SamplingConfig


def load_config(path: str | Path) -> ExperimentConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return ExperimentConfig.model_validate(data)


def config_hash(config: ExperimentConfig) -> str:
    data = config.model_dump(mode="json", exclude={"output_path"})
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
