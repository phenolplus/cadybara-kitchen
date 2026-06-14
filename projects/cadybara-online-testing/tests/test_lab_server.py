from __future__ import annotations

from pathlib import Path

from cadybara.config import load_config
from cadybara.runner import run_config
from cadybara_online_testing.lab_server import (
    CURRENT_JOB_PATH,
    LabState,
    assign_run_config_for_start,
    clear_current_job,
    experiment_ollama_queue,
    practice_output_path,
    read_current_job,
    update_current_job_status,
    write_current_job,
    write_assigned_config,
)


def test_online_smoke_config_loads() -> None:
    config = load_config("projects/cadybara-online-testing/configs/online_smoke.yaml")
    assert config.experiment_id == "cadybara_online_smoke"
    assert config.models[0].name == "cadybara-agent-default"
    assert config.models[0].provider == "cadybara_api"
    assert config.models[0].response_mode == "sse"
    assert len(config.seeds) == 5
    assert [seed.id for seed in config.seeds] == [
        "planter_01_minimal",
        "planter_03_mounting",
        "planter_05_shape",
        "planter_07_thickness",
        "planter_10_full",
    ]


def test_online_smoke_reps2_config_loads() -> None:
    config = load_config("projects/cadybara-online-testing/configs/online_smoke_reps2.yaml")
    assert config.experiment_id == "cadybara_online_smoke_reps2"
    assert config.models[0].provider == "cadybara_api"
    assert config.models[0].response_mode == "sse"
    assert len(config.seeds) == 5
    assert config.sampling.repetitions == 2
    assert config.sampling.max_attempts_per_cell == 1


def test_online_smoke_blind_extra_configs_load() -> None:
    expected = {
        "online_smoke_blind_extra.yaml": ("cadybara_online_smoke_blind_extra", 1),
        "online_smoke_blind_extra2.yaml": ("cadybara_online_smoke_blind_extra2", 1),
        "online_smoke_blind_extra3.yaml": ("cadybara_online_smoke_blind_extra3", 1),
        "online_smoke_blind_20260608_reps3.yaml": (
            "cadybara_online_smoke_blind_20260608_reps3",
            3,
        ),
    }
    for filename, (experiment_id, repetitions) in expected.items():
        config = load_config(f"projects/cadybara-online-testing/configs/{filename}")
        assert config.experiment_id == experiment_id
        assert config.models[0].provider == "cadybara_api"
        assert config.models[0].response_mode == "sse"
        assert len(config.seeds) == 5
        assert config.sampling.repetitions == repetitions
        assert config.sampling.max_attempts_per_cell == 1


def test_online_snowman_reps3_config_loads() -> None:
    expected = {
        "online_snowman_20260609_reps3.yaml": ("cadybara_online_snowman_20260609_reps3", 3),
        "online_snowman_20260609_reps4.yaml": ("cadybara_online_snowman_20260609_reps4", 4),
        "online_snowman_20260610_reps3.yaml": ("cadybara_online_snowman_20260610_reps3", 3),
    }
    for filename, (experiment_id, repetitions) in expected.items():
        config = load_config(f"projects/cadybara-online-testing/configs/{filename}")
        assert config.experiment_id == experiment_id
        assert config.models[0].name == "cadybara-agent-default"
        assert config.models[0].provider == "cadybara_api"
        assert config.models[0].response_mode == "sse"
        assert len(config.seeds) == 5
        assert [seed.id for seed in config.seeds] == [
            "snowman_01_minimal",
            "snowman_03_clear",
            "snowman_05_printable",
            "snowman_07_dimensions",
            "snowman_10_full",
        ]
        assert [seed.metadata["specificity_level"] for seed in config.seeds] == [1, 3, 5, 7, 10]
        assert all("button holes" in seed.text for seed in config.seeds)
        assert config.sampling.repetitions == repetitions
        assert config.sampling.max_attempts_per_cell == 1


def test_online_hook_reps3_config_loads() -> None:
    config = load_config("projects/cadybara-online-testing/configs/online_hook_20260611_reps3.yaml")

    assert config.experiment_id == "cadybara_online_hook_20260611_reps3"
    assert config.models[0].name == "cadybara-agent-default"
    assert config.models[0].provider == "cadybara_api"
    assert config.models[0].response_mode == "sse"
    assert len(config.seeds) == 5
    assert [seed.id for seed in config.seeds] == [
        "hook_01_minimal",
        "hook_03_clear",
        "hook_05_printable",
        "hook_07_dimensions",
        "hook_10_full",
    ]
    assert [seed.metadata["specificity_level"] for seed in config.seeds] == [1, 3, 5, 7, 10]
    assert all("hook" in seed.text.lower() for seed in config.seeds)
    assert config.sampling.repetitions == 3
    assert config.sampling.max_attempts_per_cell == 1


def test_hosted_only_config_has_no_ollama_queue(tmp_path: Path) -> None:
    config = load_config("projects/cadybara-online-testing/configs/online_smoke_reps2.yaml")
    state = LabState(tmp_path)

    assert experiment_ollama_queue(config) is None
    snapshot = state.model_snapshot(None, default_if_missing=False)
    assert snapshot["models"] == []


def test_display_config_prefers_existing_manual_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "manual.yaml"
    output_path = tmp_path / "workspace" / "manual" / "results.jsonl"
    config_path.write_text(
        f"""
experiment_id: "manual_existing"
output_path: "{output_path.as_posix()}"
models:
  - name: "model_a"
    provider: "ollama"
    base_url: "http://localhost:11434"
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
""".lstrip(),
        encoding="utf-8",
    )
    config = load_config(config_path)
    run_config(config, dry_run=True)

    display = LabState(tmp_path).display_config(config_path)

    assert display.experiment_id == "manual_existing"
    assert display.output_path == output_path.as_posix()


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
