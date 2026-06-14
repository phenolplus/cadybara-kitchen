from __future__ import annotations

from pathlib import Path

import yaml

from cadybara.cadquery_runner import check_code_safety


def test_codex_direct_manual_outputs_match_prompt_set() -> None:
    prompts_path = Path("projects/codex-direct-testing/prompts/wall_planter_prompts.yaml")
    outputs_dir = Path("projects/codex-direct-testing/manual_outputs")
    prompts = yaml.safe_load(prompts_path.read_text(encoding="utf-8"))

    expected_files = {f"{prompt['id']}.py" for prompt in prompts}
    actual_files = {path.name for path in outputs_dir.glob("*.py")}

    assert actual_files == expected_files
    for path in outputs_dir.glob("*.py"):
        code = path.read_text(encoding="utf-8")
        check_code_safety(code)
        assert "import cadquery as cq" in code
        assert "result =" in code
