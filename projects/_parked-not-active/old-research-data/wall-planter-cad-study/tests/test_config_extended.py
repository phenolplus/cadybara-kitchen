from __future__ import annotations

from pathlib import Path

from cadybara.config import load_config


def test_main_sweep_config_loads_prompt_file_and_model_metadata() -> None:
    config = load_config("projects/wall-planter-cad-study/configs/main_sweep.yaml")
    assert config.experiment_id == "wall_planter_main_sweep_001"
    assert config.output_mode == "cadquery"
    assert config.prompts_file is not None
    assert Path(config.prompts_file).exists()
    assert len(config.models) == 10
    assert len(config.seeds) == 5
    assert {model.family for model in config.models} == {
        "qwen-coder",
        "deepseek-coder",
        "starcoder2",
    }
    assert all(model.params_b is not None and model.params_b >= 3 for model in config.models)
    assert config.sampling.repetitions == 2
    assert config.sampling.max_attempts_per_cell == 1
    assert config.seeds[0].metadata["specificity_level"] == 1
    assert "qwen2.5-coder:32b" in {model.name for model in config.models}
    assert "deepseek-coder-v2:236b" in {model.name for model in config.models}
