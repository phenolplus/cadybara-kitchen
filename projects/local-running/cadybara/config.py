from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str
    base_url: str
    timeout_seconds: float = Field(default=180.0, gt=0)
    family: str | None = None
    role: str | None = None
    params_b: float | None = Field(default=None, gt=0)
    vision: bool = False
    disk_gb: float | None = Field(default=None, gt=0)
    num_thread: int | None = Field(default=None, gt=0)
    api_key_env: str = "CADYBARA_API_KEY"
    hosted_model_id: str | None = None
    response_mode: Literal["json", "stl", "sse"] = "json"
    linear_deflection: float = Field(default=0.1, gt=0)
    angular_deflection: float = Field(default=0.1, gt=0)
    unwrap_cadquery_prompt: bool = True


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
    max_attempts_per_cell: int = Field(default=1, gt=0)


class CadConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_attempts_per_cell: int | None = Field(default=None, gt=0)


class RepairConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    rounds: int = Field(default=1, ge=1)
    feedback: Literal["render_png"] = "render_png"
    always_run_all_rounds: bool = True


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    output_path: str
    output_mode: Literal["text", "cadquery"] = "text"
    prompt_revision: str = "cadquery_reference_v3"
    artifact_root: str | None = None
    prompts_file: str | None = None
    models: list[ModelConfig] = Field(min_length=1)
    seeds: list[SeedConfig] = Field(default_factory=list)
    strategies: list[StrategyConfig] = Field(min_length=1)
    sampling: SamplingConfig
    cad: CadConfig | None = None
    repair: RepairConfig | None = None

    @model_validator(mode="after")
    def require_seeds(self) -> "ExperimentConfig":
        if not self.seeds:
            raise ValueError("Experiment config must define seeds or prompts_file.")
        if self.repair and self.repair.enabled and self.repair.feedback == "render_png":
            non_vision_models = [model.name for model in self.models if not model.vision]
            if non_vision_models:
                raise ValueError(
                    "render_png repair requires vision-capable models; set vision: true "
                    f"or remove: {', '.join(non_vision_models)}"
                )
        return self


def _resolve_reference(path: str | Path, *, base_path: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate
    return base_path.parent / candidate


def _load_prompt_seeds(prompts_path: Path) -> list[dict[str, Any]]:
    with prompts_path.open("r", encoding="utf-8") as handle:
        prompts = yaml.safe_load(handle)
    if not isinstance(prompts, list):
        raise ValueError(f"{prompts_path} must contain a YAML list of prompts.")

    seeds: list[dict[str, Any]] = []
    for item in prompts:
        if not isinstance(item, dict):
            raise ValueError(f"{prompts_path} contains a non-object prompt entry.")
        prompt_id = item.get("id")
        text = item.get("text")
        if not isinstance(prompt_id, str) or not isinstance(text, str):
            raise ValueError(f"{prompts_path} prompt entries require string id and text.")
        metadata = {key: value for key, value in item.items() if key not in {"id", "text"}}
        seeds.append({"id": prompt_id, "text": text.strip(), "metadata": metadata})
    return seeds


def _normalize_config_data(data: dict[str, Any], *, path: Path) -> dict[str, Any]:
    normalized = dict(data)
    prompts_file = normalized.get("prompts_file")
    if prompts_file and not normalized.get("seeds"):
        prompts_path = _resolve_reference(prompts_file, base_path=path)
        normalized["seeds"] = _load_prompt_seeds(prompts_path)

    cad = normalized.get("cad")
    if isinstance(cad, dict):
        if cad.get("enabled"):
            normalized["output_mode"] = "cadquery"
        max_attempts = cad.get("max_attempts_per_cell")
        if max_attempts is not None:
            sampling = dict(normalized.get("sampling") or {})
            sampling.setdefault("max_attempts_per_cell", max_attempts)
            normalized["sampling"] = sampling
    return normalized


def load_config(path: str | Path) -> ExperimentConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{config_path} must contain a YAML object.")
    return ExperimentConfig.model_validate(_normalize_config_data(data, path=config_path))


def config_hash(config: ExperimentConfig) -> str:
    data = config.model_dump(mode="json", exclude={"output_path"})
    data = _prune_hash_defaults(data)
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _prune_hash_defaults(value: Any) -> Any:
    if isinstance(value, list):
        return [_prune_hash_defaults(item) for item in value]
    if not isinstance(value, dict):
        return value
    pruned = {
        key: _prune_hash_defaults(item)
        for key, item in value.items()
        if not (
            (key in {"disk_gb", "num_thread", "repair", "role"} and item is None)
            or (key in {"hosted_model_id"} and item is None)
            or key == "role"
            or (key == "vision" and item is False)
            or (key == "api_key_env" and item == "CADYBARA_API_KEY")
            or key == "response_mode"
            or (key == "linear_deflection" and item == 0.1)
            or (key == "angular_deflection" and item == 0.1)
            or (key == "unwrap_cadquery_prompt" and item is True)
        )
    }
    return pruned
