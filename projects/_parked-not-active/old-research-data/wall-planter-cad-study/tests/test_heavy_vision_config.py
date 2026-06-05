from __future__ import annotations

from pathlib import Path

from cadybara.config import load_config


def test_vision_heavy_repair_config_loads() -> None:
    config = load_config("projects/wall-planter-cad-study/configs/vision_heavy_repair.yaml")
    assert config.experiment_id == "wall_planter_vision_repair_sweep_001"
    assert config.repair is not None
    assert config.repair.enabled is True
    assert config.repair.rounds == 3
    assert len(config.models) == 6
    assert len({model.family for model in config.models}) == 6
    assert all(model.vision for model in config.models)
    assert all((model.params_b or 0) >= 24 for model in config.models)
    assert all(model.num_thread == 12 for model in config.models)
    assert Path(config.prompts_file or "").exists()
    assert [seed.metadata["specificity_level"] for seed in config.seeds] == [1, 3, 5, 7, 10]
