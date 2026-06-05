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


def test_missing_required_fields_raise_validation_error() -> None:
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate({"experiment_id": "bad"})


def test_model_role_loads_but_does_not_affect_config_hash(tmp_path: Path) -> None:
    base = """
experiment_id: "role_hash"
output_path: "{output_path}"
models:
  - name: "model_a"
    provider: "ollama"
    base_url: "http://localhost:11434"
    {role_line}
seeds:
  - id: "seed_001"
    text: "Prompt one"
    metadata: {{}}
strategies:
  - name: "identity"
sampling:
  temperatures: [0.7]
  repetitions: 1
  max_tokens: 32
""".lstrip()
    with_role = tmp_path / "with_role.yaml"
    without_role = tmp_path / "without_role.yaml"
    with_role.write_text(
        base.format(output_path=(tmp_path / "with.jsonl").as_posix(), role_line='role: "online-smoke"'),
        encoding="utf-8",
    )
    without_role.write_text(
        base.format(output_path=(tmp_path / "without.jsonl").as_posix(), role_line=""),
        encoding="utf-8",
    )

    role_config = load_config(with_role)
    plain_config = load_config(without_role)

    assert role_config.models[0].role == "online-smoke"
    assert config_hash(role_config) == config_hash(plain_config)
