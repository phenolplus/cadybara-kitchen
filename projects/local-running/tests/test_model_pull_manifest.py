from __future__ import annotations

from pathlib import Path

import httpx
import respx

from cadybara.model_queue import (
    DEFAULT_MODEL_STATE_PATH,
    LocalModelSpec,
    ModelQueueConfig,
    append_pull_manifest,
    ensure_free_disk_for_model,
    load_model_state,
    pull_one_model,
)


def test_pull_manifest_appends_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "pull_manifest.jsonl"
    append_pull_manifest(path, model_name="big:v1", status="planned", message="ok")
    text = path.read_text(encoding="utf-8")
    assert '"model_name":"big:v1"' in text
    assert '"status":"planned"' in text


def test_disk_floor_skips_when_cleanup_cannot_make_space(monkeypatch) -> None:
    spec = LocalModelSpec(
        name="huge:vision",
        family="vision",
        role="test",
        priority=1,
        estimated_size_gb=100,
        vision=True,
    )
    config = ModelQueueConfig(
        min_free_disk_gb=50,
        models=[spec],
        cleanup_models=["old:model"],
    )
    monkeypatch.setattr("cadybara.model_queue.free_disk_gb", lambda: 120.0)
    monkeypatch.setattr("cadybara.model_queue.remove_local_model", lambda *args, **kwargs: False)

    ok, message = ensure_free_disk_for_model(spec, config)

    assert ok is False
    assert "floor=50.0GB" in message


def test_disk_floor_respects_cleanup_disabled(monkeypatch) -> None:
    spec = LocalModelSpec(
        name="huge:vision",
        family="vision",
        role="test",
        priority=1,
        estimated_size_gb=100,
        vision=True,
    )
    config = ModelQueueConfig(
        min_free_disk_gb=50,
        models=[spec],
        cleanup_models=["old:model"],
    )
    removed: list[str] = []
    monkeypatch.setenv("CADYBARA_DISABLE_MODEL_CLEANUP", "1")
    monkeypatch.setattr("cadybara.model_queue.free_disk_gb", lambda: 120.0)
    monkeypatch.setattr(
        "cadybara.model_queue.remove_local_model",
        lambda model_name, **_kwargs: removed.append(model_name) or True,
    )

    ok, message = ensure_free_disk_for_model(spec, config)

    assert ok is False
    assert removed == []
    assert "cleanup=disabled" in message


@respx.mock
def test_pull_one_model_streams_api_progress_to_state_and_manifest(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "model_state.json"
    manifest_path = tmp_path / "pull_manifest.jsonl"
    state = load_model_state(DEFAULT_MODEL_STATE_PATH)
    state["models"] = {}
    spec = LocalModelSpec(
        name="vision-heavy:test",
        family="vision",
        role="test",
        priority=1,
        estimated_size_gb=1,
        vision=True,
    )
    chunks = [
        b'{"status":"pulling manifest"}\n',
        b'{"status":"pulling abc123","digest":"sha256:abc123","total":1000,"completed":250}\n',
        b'{"status":"pulling abc123","digest":"sha256:abc123","total":1000,"completed":1000}\n',
        b'{"status":"success"}\n',
    ]
    respx.post("http://127.0.0.1:11434/api/pull").mock(
        return_value=httpx.Response(200, content=b"".join(chunks))
    )
    monkeypatch.setattr("cadybara.model_queue.ollama_path", lambda: "ollama")
    local_calls = iter([set(), {"vision-heavy:test"}])
    monkeypatch.setattr("cadybara.model_queue.list_local_models", lambda *_args, **_kwargs: next(local_calls))

    ok = pull_one_model(
        spec,
        state=state,
        state_path=state_path,
        manifest_path=manifest_path,
        base_url="http://127.0.0.1:11434",
    )

    assert ok is True
    saved = load_model_state(state_path)["models"]["vision-heavy:test"]
    assert saved["status"] == "installed"
    assert saved["percent"] == 100
    assert saved["completed_bytes"] == 1000
    assert saved["total_bytes"] == 1000
    manifest = manifest_path.read_text(encoding="utf-8")
    assert '"completed_bytes":1000' in manifest
