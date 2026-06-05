from __future__ import annotations

import yaml


def test_planter_prompts_yaml_loads_expected_ladder() -> None:
    with open("projects/wall-planter-cad-study/prompts/planter_prompts.yaml", encoding="utf-8") as handle:
        prompts = yaml.safe_load(handle)
    assert [prompt["id"] for prompt in prompts] == [
        "planter_01_minimal",
        "planter_03_mounting",
        "planter_05_shape",
        "planter_07_thickness",
        "planter_10_full",
    ]
    assert [prompt["specificity_level"] for prompt in prompts] == [1, 3, 5, 7, 10]
    assert all(prompt["text"].strip() for prompt in prompts)
