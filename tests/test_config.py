from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from cadybara.config import ExperimentConfig, config_hash, load_config


def test_valid_yaml_loads(tiny_config_path: Path) -> None:
    config = load_config(tiny_config_path)
    assert config.experiment_id == "tiny"
    assert config.models[0].name == "model_a"
    assert config.sampling.repetitions == 2
    assert config_hash(config) == config_hash(config)


def test_pilot_local_config_loads() -> None:
    config = load_config("configs/pilot_local.yaml")
    assert config.experiment_id == "wall_planter_pilot_001"
    assert config.output_mode == "cadquery"
    assert len(config.models) == 3
    assert len(config.seeds) == 10
    assert config.seeds[0].text == "Make me a planter I can put on my wall."


def test_missing_required_fields_raise_validation_error() -> None:
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate({"experiment_id": "bad"})
