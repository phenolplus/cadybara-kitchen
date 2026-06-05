from __future__ import annotations

from pathlib import Path

from cadybara.config import load_config
from cadybara.runner import run_config
from cadybara_online_testing.lab_server import (
    CURRENT_JOB_PATH,
    LabState,
    assign_run_config_for_start,
    clear_current_job,
    practice_output_path,
    read_current_job,
    update_current_job_status,
    write_current_job,
    write_assigned_config,
)


def test_online_smoke_config_loads() -> None:
    config = load_config("projects/cadybara-online-testing/configs/online_smoke.yaml")
    assert config.experiment_id == "cadybara_online_smoke"
    assert config.models[0].name == "qwen2.5-coder:0.5b"


def test_lab_start_resumes_latest_partial_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "tiny.yaml"
    config_path.write_text(
        """
experiment_id: "overnight"
output_path: "workspace/manual/results.jsonl"
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
    metadata: {}
  - id: "seed_002"
    text: "Prompt two"
    metadata: {}
strategies:
  - name: "identity"
sampling:
  temperatures: [0.7]
  repetitions: 2
  max_tokens: 32
""".lstrip(),
        encoding="utf-8",
    )
    config = load_config(config_path)

    first = assign_run_config_for_start(config, dry_run=False)
    assert first.resuming is False
    assert first.config.experiment_id == "overnight_001"
    write_assigned_config(first.config)

    empty_reuse = assign_run_config_for_start(config, dry_run=False)
    assert empty_reuse.resuming is False
    assert empty_reuse.config.output_path == first.config.output_path

    practice_config = first.config.model_copy(update={"output_path": practice_output_path(first.config.output_path)})
    partial = run_config(practice_config, dry_run=True, limit=3)
    assert partial.executed == 3

    resumed = assign_run_config_for_start(config, dry_run=True)
    assert resumed.resuming is True
    assert resumed.config.output_path == first.config.output_path

    complete = run_config(practice_config, dry_run=True)
    assert complete.executed == 5

    next_run = assign_run_config_for_start(config, dry_run=True)
    assert next_run.resuming is False
    assert next_run.config.experiment_id == "overnight_002"


def test_worker_mode_run_start_does_not_auto_pull_missing_models(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CADYBARA_LAB_DISABLE_AUTO_PULL", "1")
    monkeypatch.setattr(
        "cadybara_online_testing.lab_server.missing_ollama_models",
        lambda *_args, **_kwargs: ["model_a"],
    )
    config_path = tmp_path / "tiny.yaml"
    config_path.write_text(
        """
experiment_id: "overnight"
output_path: "workspace/manual/results.jsonl"
models:
  - name: "model_a"
    provider: "ollama"
    base_url: "http://localhost:11434"
seeds:
  - id: "seed_001"
    text: "Prompt one"
    metadata: {}
strategies:
  - name: "identity"
sampling:
  temperatures: [0.7]
  repetitions: 1
  max_tokens: 32
""".lstrip(),
        encoding="utf-8",
    )
    state = LabState(tmp_path)

    started = state.start_run(config_path=str(config_path), dry_run=False)

    assert started is True
    assert state.run_job.snapshot()["status"] == "error"
    assert state.model_thread is None
    assert "Pull required models explicitly" in state.run_job.snapshot()["lines"][-1]


def test_current_job_marker_round_trips(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "tiny.yaml"
    config_path.write_text(
        """
experiment_id: "overnight"
output_path: "workspace/manual/results.jsonl"
models:
  - name: "model_a"
    provider: "ollama"
    base_url: "http://localhost:11434"
seeds:
  - id: "seed_001"
    text: "Prompt one"
    metadata: {}
strategies:
  - name: "identity"
sampling:
  temperatures: [0.7]
  repetitions: 1
  max_tokens: 32
""".lstrip(),
        encoding="utf-8",
    )
    assigned = assign_run_config_for_start(load_config(config_path), dry_run=True).config

    write_current_job(
        root=tmp_path,
        config_path=str(config_path),
        assigned_config=assigned,
        dry_run=True,
    )

    job = read_current_job()
    assert job is not None
    assert job["status"] == "active"
    assert job["config_path"] == str(config_path)
    assert job["models"] == ["model_a"]

    update_current_job_status("paused")
    assert read_current_job()["status"] == "paused"  # type: ignore[index]

    clear_current_job()
    assert read_current_job() is None
    assert not CURRENT_JOB_PATH.exists()


def test_active_current_job_auto_resumes_and_paused_job_does_not(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "tiny.yaml"
    config_path.write_text(
        """
experiment_id: "overnight"
output_path: "workspace/manual/results.jsonl"
models:
  - name: "model_a"
    provider: "ollama"
    base_url: "http://localhost:11434"
seeds:
  - id: "seed_001"
    text: "Prompt one"
    metadata: {}
strategies:
  - name: "identity"
sampling:
  temperatures: [0.7]
  repetitions: 1
  max_tokens: 32
""".lstrip(),
        encoding="utf-8",
    )
    assigned = assign_run_config_for_start(load_config(config_path), dry_run=False).config
    write_current_job(
        root=tmp_path,
        config_path=str(config_path),
        assigned_config=assigned,
        dry_run=False,
    )
    state = LabState(tmp_path)
    calls: list[tuple[str, bool]] = []

    def fake_start_run(*, config_path: str, dry_run: bool) -> bool:
        calls.append((config_path, dry_run))
        return True

    state.start_run = fake_start_run  # type: ignore[method-assign]

    assert state.resume_current_job_if_active() is True
    assert calls == [(str(config_path), False)]

    update_current_job_status("paused")
    calls.clear()
    assert state.resume_current_job_if_active() is False
    assert calls == []
