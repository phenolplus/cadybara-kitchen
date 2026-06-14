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


def test_hosted_provider_transport_fields_do_not_change_existing_config_hash(tmp_path: Path) -> None:
    base = """
experiment_id: "provider_defaults"
output_path: "{output_path}"
models:
  - name: "model_a"
    provider: "ollama"
    base_url: "http://localhost:11434"
{extra_lines}
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
    plain = tmp_path / "plain.yaml"
    explicit_defaults = tmp_path / "explicit_defaults.yaml"
    default_lines = """
    api_key_env: "CADYBARA_API_KEY"
    response_mode: "sse"
    linear_deflection: 0.1
    angular_deflection: 0.1
    unwrap_cadquery_prompt: true
""".rstrip()
    plain.write_text(
        base.format(output_path=(tmp_path / "plain.jsonl").as_posix(), extra_lines=""),
        encoding="utf-8",
    )
    explicit_defaults.write_text(
        base.format(
            output_path=(tmp_path / "explicit.jsonl").as_posix(),
            extra_lines=default_lines,
        ),
        encoding="utf-8",
    )

    assert config_hash(load_config(plain)) == config_hash(load_config(explicit_defaults))
    assert load_config(explicit_defaults).models[0].response_mode == "sse"
