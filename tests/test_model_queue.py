from __future__ import annotations

from pathlib import Path

from cadybara.model_queue import (
    clean_pull_message,
    load_model_queue,
    model_status_rows,
    parse_pull_percent,
    save_model_state,
)


def test_model_queue_loads_default_config() -> None:
    config = load_model_queue("configs/models_local.yaml")
    names = [model.name for model in config.sorted_models()]
    assert names[0] == "qwen2.5:0.5b"
    assert "qwen2.5-coder:7b" in names


def test_parse_pull_percent() -> None:
    assert parse_pull_percent("pulling layer 42%") == 42
    assert parse_pull_percent("done") is None
    assert parse_pull_percent("101%") == 100


def test_clean_pull_message_strips_ansi() -> None:
    message = clean_pull_message("pulling abc: 42% \x1b[K\x1b[?25h\n")
    assert message == "pulling abc: 42%"


def test_model_status_rows_merge_saved_state(tmp_path: Path) -> None:
    config = load_model_queue("configs/models_local.yaml")
    state_path = tmp_path / "state.json"
    save_model_state(
        {
            "models": {
                "qwen2.5:0.5b": {
                    "status": "pulling",
                    "percent": 55,
                    "message": "downloading",
                }
            }
        },
        state_path,
    )
    rows = model_status_rows(config, state_path=state_path)
    first = rows[0]
    assert first["name"] == "qwen2.5:0.5b"
    assert first["status"] in {"pulling", "installed"}
    if first["status"] == "pulling":
        assert first["percent"] == 55


def test_save_model_state_writes_json_atomically(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    save_model_state({"models": {"m": {"status": "installed"}}}, state_path)
    assert state_path.exists()
    assert not state_path.with_suffix(".json.tmp").exists()
