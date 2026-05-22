from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tiny_config_path(tmp_path: Path) -> Path:
    path = tmp_path / "tiny.yaml"
    output_path = tmp_path / "tiny.jsonl"
    path.write_text(
        f"""
experiment_id: "tiny"
output_path: "{output_path.as_posix()}"
models:
  - name: "model_a"
    provider: "ollama"
    base_url: "http://localhost:11434"
  - name: "model_b"
    provider: "ollama"
    base_url: "http://localhost:11434"
seeds:
  - id: "seed_001"
    text: "Prompt one"
    metadata: {{}}
  - id: "seed_002"
    text: "Prompt two"
    metadata: {{}}
strategies:
  - name: "identity"
sampling:
  temperatures: [0.7]
  repetitions: 2
  max_tokens: 32
""".lstrip(),
        encoding="utf-8",
    )
    return path
