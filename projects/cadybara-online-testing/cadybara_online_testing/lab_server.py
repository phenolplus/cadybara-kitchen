from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml

from cadybara.config import ExperimentConfig, config_hash
from cadybara.config import load_config
from cadybara.csv_export import export_attempts_csv
from cadybara.model_queue import (
    DEFAULT_MODEL_QUEUE_PATH,
    DEFAULT_MODEL_STATE_PATH,
    list_local_models,
    load_model_queue,
    model_status_rows,
    ollama_path,
    ollama_version,
    pull_model_queue,
    queue_from_experiment_config,
)
from cadybara.records import resume_key
from cadybara.runner import build_cells, read_jsonl_records, record_is_complete, run_config, timestamp_utc
from cadybara.snapshot import SnapshotBuffer
from cadybara_cad_diffusion import (
    latest_checkpoint,
    load_prepared_examples,
    train_diffusion_model,
    validate_cad_token_grammar,
)
from cadybara_online_testing.progress import run_status_payload
from cadybara_online_testing.reviews import append_score, review_items, review_path

DEFAULT_PROJECT_CONFIG = "projects/cadybara-online-testing/configs/online_smoke.yaml"
LAB_STATIC_ROOT = Path("projects/website/lab")
VIEWER_STATIC_ROOT = Path("projects/website/viewer")
DEFAULT_SAMPLE_ARTIFACT = "/projects/local-running/workspace/examples/sample_part.json"
WORKER_STATE_DIR = Path("projects/local-running/workspace/worker")
CURRENT_JOB_PATH = WORKER_STATE_DIR / "current_job.json"
CAD_DIFFUSION_DEFAULTS = {
    "data_dir": "projects/cad-diffusion/workspace/datasets/fusion360_tokens",
    "model_dir": "projects/cad-diffusion/workspace/models/cad_diffusion_validity_20260602",
    "max_steps": 50000,
    "batch_size": 32,
    "max_len": 256,
    "d_model": 128,
    "layers": 2,
    "heads": 4,
    "learning_rate": 3e-4,
    "checkpoint_interval": 100,
    "time_limit_minutes": 480.0,
    "seed": 20260602,
    "resume": True,
}


def legacy_workspace_target(path: str) -> Path | None:
    if path.startswith("/workspace/runs/wall_planter_"):
        return Path("projects/_parked-not-active/old-research-data/wall-planter-cad-study") / path.removeprefix("/")
    if path.startswith("/workspace/artifacts/") or path.startswith("/workspace/reviews/"):
        return Path("projects/_parked-not-active/old-research-data/wall-planter-cad-study") / path.removeprefix("/")
    if path.startswith("/workspace/runs/cad_") or path.startswith("/workspace/runs/real_smoke_"):
        return Path("projects/local-running") / path.removeprefix("/")
    if path.startswith(("/workspace/datasets/", "/workspace/models/", "/workspace/jobs/")):
        return Path("projects/cad-diffusion") / path.removeprefix("/")
    if path == "/workspace/sample_part.json":
        return Path("projects/local-running/workspace/examples/sample_part.json")
    return None


def cad_diffusion_train_options(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(CAD_DIFFUSION_DEFAULTS)
    for key, value in (overrides or {}).items():
        if key in data and value is not None:
            data[key] = value
    for key in ("max_steps", "batch_size", "max_len", "d_model", "layers", "heads", "checkpoint_interval", "seed"):
        data[key] = int(data[key])
    data["learning_rate"] = float(data["learning_rate"])
    data["time_limit_minutes"] = float(data["time_limit_minutes"])
    data["resume"] = bool(data["resume"])
    data["data_dir"] = str(data["data_dir"])
    data["model_dir"] = str(data["model_dir"])
    return data


def cad_torch_status() -> dict[str, Any]:
    try:
        import torch
    except ImportError as exc:
        return {
            "available": False,
            "version": None,
            "cuda_available": False,
            "cuda_device_count": 0,
            "device": "missing",
            "message": str(exc),
        }
    cuda_available = bool(torch.cuda.is_available())
    return {
        "available": True,
        "version": str(torch.__version__),
        "cuda_available": cuda_available,
        "cuda_device_count": int(torch.cuda.device_count()),
        "device": "cuda" if cuda_available else "cpu",
        "message": "CUDA is available." if cuda_available else "CPU-only PyTorch detected; overnight training is expected.",
    }


def lab_auto_pull_disabled() -> bool:
    return os.environ.get("CADYBARA_LAB_DISABLE_AUTO_PULL", "").lower() in {"1", "true", "yes"}


def git_commit_hash(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value or None


def read_current_job(path: Path = CURRENT_JOB_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def write_current_job(
    *,
    root: Path,
    config_path: str,
    assigned_config: ExperimentConfig,
    dry_run: bool,
    status: str = "active",
    path: Path = CURRENT_JOB_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": status,
        "config_path": config_path,
        "assigned_config_path": str(Path(assigned_config.output_path).parent / "config.yaml"),
        "experiment_id": assigned_config.experiment_id,
        "output_path": assigned_config.output_path,
        "artifact_root": assigned_config.artifact_root,
        "dry_run": dry_run,
        "commit_hash": git_commit_hash(root),
        "cli_args": ["lab-ui", "run", config_path, "--dry-run" if dry_run else "--real-run"],
        "models": [model.name for model in assigned_config.models],
        "started_at_utc": timestamp_utc(),
        "updated_at_utc": timestamp_utc(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def update_current_job_status(status: str, path: Path = CURRENT_JOB_PATH) -> None:
    data = read_current_job(path)
    if data is None:
        return
    data["status"] = status
    data["updated_at_utc"] = timestamp_utc()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def clear_current_job(path: Path = CURRENT_JOB_PATH) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def cad_dataset_readiness(data_dir: Path, *, max_len: int) -> dict[str, Any]:
    blockers: list[str] = []
    manifest_path = data_dir / "manifest.json"
    manifest: dict[str, Any] | None = None
    train_count = 0
    test_count = 0
    grammar_valid = False
    grammar_error: str | None = None
    if not data_dir.exists():
        blockers.append(f"Prepared dataset is missing: {data_dir}")
    else:
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 - returned as readiness detail.
                blockers.append(f"Manifest is unreadable: {exc}")
        train_path = data_dir / "train.jsonl"
        test_path = data_dir / "test.jsonl"
        train_count = count_jsonl_lines(train_path)
        test_count = count_jsonl_lines(test_path)
        if train_count <= 0:
            blockers.append(f"Prepared train split is empty or missing: {train_path}")
        else:
            try:
                for example in load_prepared_examples(data_dir, split="train"):
                    validate_cad_token_grammar(example.tokens, max_len=max_len)
                grammar_valid = True
            except Exception as exc:  # noqa: BLE001 - returned as readiness detail.
                grammar_error = str(exc)
                blockers.append(f"Prepared train grammar failed: {grammar_error}")
    return {
        "data_dir": data_dir.as_posix(),
        "manifest_path": manifest_path.as_posix(),
        "manifest": manifest,
        "train_count": train_count,
        "test_count": test_count,
        "grammar_valid": grammar_valid,
        "grammar_error": grammar_error,
        "blockers": blockers,
    }


def count_jsonl_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def file_cache_marker(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_mtime_ns, stat.st_size


@dataclass(frozen=True)
class RunAssignment:
    config: ExperimentConfig
    resuming: bool


class JobLog:
    def __init__(self, name: str) -> None:
        self.name = name
        self.status = "idle"
        self.lines: deque[str] = deque(maxlen=250)
        self.lock = threading.Lock()

    def write(self, value: str) -> int:
        text = value.strip()
        if text:
            with self.lock:
                self.lines.append(text)
        return len(value)

    def flush(self) -> None:
        return None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "name": self.name,
                "status": self.status,
                "lines": list(self.lines),
            }

    def set_status(self, status: str) -> None:
        with self.lock:
            self.status = status


class LabState:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.model_job = JobLog("model-prefetch")
        self.run_job = JobLog("experiment-run")
        self.cad_train_job = JobLog("cad-diffusion-train")
        self.model_thread: threading.Thread | None = None
        self.run_thread: threading.Thread | None = None
        self.cad_train_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.cad_train_stop_event = threading.Event()
        self.active_run_config: ExperimentConfig | None = None
        self.snapshot_buffer = SnapshotBuffer()
        self.run_records = []
        self.run_started_at: float | None = None
        self.cad_train_started_at: float | None = None
        self.cad_train_progress: dict[str, Any] = {}
        self.cad_readiness_cache_key: tuple[Any, ...] | None = None
        self.cad_readiness_cache: dict[str, Any] | None = None
        self.cad_readiness_lock = threading.Lock()
        self.run_status_cache: dict[str, Any] | None = None
        self.model_cache: dict[str, Any] | None = None
        self.model_cache_at = 0.0
        self.model_queue_config = None
        self.pending_run_request: dict[str, Any] | None = None
        self.lock = threading.Lock()

    def _start_models_locked(
        self,
        *,
        limit: int | None = None,
        family: str | None = None,
        queue_config=None,
    ) -> bool:
        if self.model_thread is not None and self.model_thread.is_alive():
            return False
        self.model_job = JobLog("model-prefetch")
        self.model_cache = None
        self.model_cache_at = 0.0
        self.model_queue_config = queue_config

        def target() -> None:
            self.model_job.set_status("running")
            try:
                config = queue_config or load_model_queue(DEFAULT_MODEL_QUEUE_PATH)
                summary = pull_model_queue(
                    config,
                    limit=limit,
                    family=family,
                    state_path=DEFAULT_MODEL_STATE_PATH,
                    stream=self.model_job,
                )
                self.model_job.write(
                    "Summary: "
                    f"attempted={summary.attempted} installed={summary.installed} "
                    f"skipped={summary.skipped} errors={summary.errors}"
                )
                self.model_job.set_status("done" if summary.errors == 0 else "error")
            except Exception as exc:  # noqa: BLE001 - lab reports failures in UI.
                self.model_job.write(f"Error: {exc}")
                self.model_job.set_status("error")
            finally:
                self.start_pending_run_if_ready()

        self.model_thread = threading.Thread(target=target, daemon=True)
        self.model_thread.start()
        return True

    def start_models(self, *, limit: int | None = None, family: str | None = None) -> bool:
        with self.lock:
            return self._start_models_locked(limit=limit, family=family)

    def start_models_for_config(
        self,
        *,
        config_path: str,
        limit: int | None = None,
        family: str | None = None,
    ) -> bool:
        queue_config = queue_from_experiment_config(load_config(config_path))
        with self.lock:
            return self._start_models_locked(
                limit=limit,
                family=family,
                queue_config=queue_config,
            )

    def start_run(self, *, config_path: str, dry_run: bool) -> bool:
        with self.lock:
            if self.run_thread is not None and self.run_thread.is_alive():
                return False
            self.run_job = JobLog("experiment-run")
            self.stop_event.clear()
            assignment = assign_run_config_for_start(load_config(config_path), dry_run=dry_run)
            assigned_config = assignment.config
            if not dry_run:
                missing = missing_ollama_models(assigned_config)
                if missing:
                    if lab_auto_pull_disabled():
                        self.run_job.write(
                            "Missing Ollama models: "
                            + ", ".join(missing)
                            + ". Pull required models explicitly before starting this run."
                        )
                        self.run_job.set_status("error")
                        self.pending_run_request = None
                        return True
                    model_running = (
                        self.model_thread is not None and self.model_thread.is_alive()
                    )
                    self.pending_run_request = {
                        "config_path": config_path,
                        "dry_run": dry_run,
                    }
                    if model_running:
                        self.run_job.write(
                            "Waiting for model pulls to finish. Missing now: "
                            + ", ".join(missing)
                            + ". The run will start automatically when they are installed."
                        )
                        self.run_job.set_status("waiting")
                        return True
                    self.run_job.write(
                        "Missing Ollama models: "
                        + ", ".join(missing)
                        + ". Starting required pulls now; the run will start automatically."
                    )
                    self.run_job.set_status("waiting")
                    self._start_models_locked(queue_config=queue_from_experiment_config(assigned_config))
                    return True
            self.active_run_config = assigned_config
            write_assigned_config(assigned_config)
            write_current_job(
                root=self.root,
                config_path=config_path,
                assigned_config=assigned_config,
                dry_run=dry_run,
            )
            target_path = (
                practice_output_path(assigned_config.output_path)
                if dry_run
                else assigned_config.output_path
            )
            self.run_records = read_jsonl_records(Path(target_path)).records
            self.run_started_at = time.monotonic()
            self.run_status_cache = run_status_payload(
                assigned_config,
                self.run_records,
                active_snapshot=self.snapshot_buffer.snapshot(),
                started_at=self.run_started_at,
            )

            def update_status() -> None:
                with self.lock:
                    self.run_status_cache = run_status_payload(
                        assigned_config,
                        self.run_records,
                        active_snapshot=self.snapshot_buffer.snapshot(),
                        started_at=self.run_started_at,
                    )

            def on_record(record) -> None:
                with self.lock:
                    self.run_records.append(record)
                update_status()

            def target() -> None:
                self.run_job.set_status("running")
                action = "Resuming" if assignment.resuming else "Starting"
                self.run_job.write(f"{action} run folder: {Path(target_path).parent}")
                try:
                    if dry_run:
                        run_config(
                            assigned_config.model_copy(
                                update={"output_path": practice_output_path(assigned_config.output_path)}
                            ),
                            dry_run=True,
                            should_stop=self.stop_event.is_set,
                            on_record=on_record,
                            stream=self.run_job,
                        )
                    else:
                        run_config(
                            assigned_config,
                            dry_run=False,
                            should_stop=self.stop_event.is_set,
                            snapshot_buffer=self.snapshot_buffer,
                            on_record=on_record,
                            stream=self.run_job,
                        )
                    csv_path = Path(target_path).with_name(
                        "attempts.practice.csv" if dry_run else "attempts.csv"
                    )
                    rows, malformed = export_attempts_csv(Path(target_path), csv_path)
                    self.run_job.write(
                        f"Wrote attempt CSV: {csv_path} "
                        f"(rows={rows}, malformed={malformed})"
                    )
                    if self.stop_event.is_set():
                        update_current_job_status("paused")
                        self.run_job.set_status("stopped")
                    else:
                        clear_current_job()
                        self.run_job.set_status("done")
                except Exception as exc:  # noqa: BLE001 - lab reports failures in UI.
                    self.run_job.write(f"Error: {exc}")
                    update_current_job_status("error")
                    self.run_job.set_status("error")
                finally:
                    self.snapshot_buffer.finish()
                    update_status()
                    with self.lock:
                        self.active_run_config = None

            self.run_thread = threading.Thread(target=target, daemon=True)
            self.run_thread.start()
            return True

    def start_pending_run_if_ready(self) -> None:
        with self.lock:
            pending = self.pending_run_request
            self.pending_run_request = None
        if not pending:
            return

        config = load_config(pending["config_path"])
        missing = missing_ollama_models(config)
        if missing:
            self.run_job.write(
                "Model pulls finished, but these models are still missing: "
                + ", ".join(missing)
                + ". The queued run was not started."
            )
            self.run_job.set_status("error")
            return

        self.run_job.write("Model pulls complete. Starting queued run.")
        self.start_run(
            config_path=pending["config_path"],
            dry_run=bool(pending["dry_run"]),
        )

    def stop_run(self) -> bool:
        with self.lock:
            if self.run_thread is None or not self.run_thread.is_alive():
                return False
            self.stop_event.set()
            update_current_job_status("paused")
            self.run_job.write("Stop requested. Current generation will finish, then the queue will pause.")
            self.run_job.set_status("stopping")
            return True

    def resume_current_job_if_active(self) -> bool:
        job = read_current_job()
        if not job:
            return False
        status = str(job.get("status") or "")
        if status == "paused":
            self.run_job.write(
                "Worker job is paused. Use Start to resume: "
                + str(job.get("config_path") or "unknown config")
            )
            self.run_job.set_status("stopped")
            return False
        if status != "active":
            return False
        config_path = str(job.get("config_path") or "")
        if not config_path:
            update_current_job_status("error")
            self.run_job.write("Current job is missing config_path; not resuming.")
            self.run_job.set_status("error")
            return False
        self.run_job.write(f"Auto-resuming active worker job: {config_path}")
        return self.start_run(
            config_path=config_path,
            dry_run=bool(job.get("dry_run", False)),
        )

    def cad_diffusion_status(self) -> dict[str, Any]:
        options = cad_diffusion_train_options()
        data_dir = Path(options["data_dir"])
        model_dir = Path(options["model_dir"])
        dataset = self.cached_cad_dataset_readiness(data_dir, max_len=int(options["max_len"]))
        torch_info = cad_torch_status()
        blockers = [*dataset["blockers"]]
        if not torch_info["available"]:
            blockers.append("PyTorch is not installed for CAD diffusion training.")
        checkpoint = latest_checkpoint(model_dir)
        with self.lock:
            running = self.cad_train_thread is not None and self.cad_train_thread.is_alive()
            progress = dict(self.cad_train_progress)
            started_at = self.cad_train_started_at
        elapsed = round(time.monotonic() - started_at, 1) if started_at else 0.0
        return {
            "defaults": options,
            "ready": not blockers,
            "blockers": blockers,
            "dataset": dataset,
            "torch": torch_info,
            "model_dir": model_dir.as_posix(),
            "latest_checkpoint": checkpoint.as_posix() if checkpoint else None,
            "job": self.cad_train_job.snapshot(),
            "running": running,
            "progress": progress,
            "elapsed_seconds": elapsed,
        }

    def start_cad_diffusion_train(self, *, overrides: dict[str, Any] | None = None) -> bool:
        options = cad_diffusion_train_options(overrides)
        data_dir = Path(options["data_dir"])
        model_dir = Path(options["model_dir"])
        dataset = self.cached_cad_dataset_readiness(data_dir, max_len=int(options["max_len"]))
        torch_info = cad_torch_status()
        blockers = [*dataset["blockers"]]
        if not torch_info["available"]:
            blockers.append("PyTorch is not installed for CAD diffusion training.")

        with self.lock:
            if self.cad_train_thread is not None and self.cad_train_thread.is_alive():
                return False
            self.cad_train_job = JobLog("cad-diffusion-train")
            self.cad_train_progress = {}
            self.cad_train_started_at = None
            self.cad_train_stop_event.clear()
            if blockers:
                self.cad_train_job.write("Blocked: " + " | ".join(blockers))
                self.cad_train_job.set_status("blocked")
                return False

        def on_progress(progress: dict[str, Any]) -> None:
            with self.lock:
                self.cad_train_progress = dict(progress)
            phase = str(progress.get("phase") or "")
            step = int(progress.get("step") or 0)
            if phase in {"started", "checkpoint", "complete", "stopped"}:
                loss = progress.get("loss")
                loss_text = f" loss={loss:.4f}" if isinstance(loss, (float, int)) else ""
                self.cad_train_job.write(
                    f"{phase} step={step}/{progress.get('max_steps')}"
                    f"{loss_text} checkpoint={progress.get('checkpoint_path')}"
                )

        def target() -> None:
            self.cad_train_job.set_status("running")
            with self.lock:
                self.cad_train_started_at = time.monotonic()
            self.cad_train_job.write(
                f"Training CAD diffusion on {dataset['train_count']} examples with {torch_info['device']}."
            )
            self.cad_train_job.write(f"Data: {data_dir.as_posix()}")
            self.cad_train_job.write(f"Model: {model_dir.as_posix()}")
            try:
                summary = train_diffusion_model(
                    data_dir,
                    model_dir,
                    max_steps=int(options["max_steps"]),
                    batch_size=int(options["batch_size"]),
                    max_len=int(options["max_len"]),
                    d_model=int(options["d_model"]),
                    layers=int(options["layers"]),
                    heads=int(options["heads"]),
                    learning_rate=float(options["learning_rate"]),
                    checkpoint_interval=int(options["checkpoint_interval"]),
                    time_limit_minutes=float(options["time_limit_minutes"]),
                    seed=int(options["seed"]),
                    resume=bool(options["resume"]),
                    should_stop=self.cad_train_stop_event.is_set,
                    on_progress=on_progress,
                )
                self.cad_train_job.write(
                    f"trained_steps={summary.steps} examples={summary.examples} "
                    f"device={summary.device} elapsed_seconds={summary.elapsed_seconds:.1f}"
                )
                self.cad_train_job.write(f"checkpoint={summary.checkpoint_path.as_posix()}")
                self.cad_train_job.set_status(
                    "stopped" if self.cad_train_stop_event.is_set() else "done"
                )
            except Exception as exc:  # noqa: BLE001 - lab reports failures in UI.
                self.cad_train_job.write(f"Error: {exc}")
                self.cad_train_job.set_status("error")

        self.cad_train_thread = threading.Thread(target=target, daemon=True)
        self.cad_train_thread.start()
        return True

    def cached_cad_dataset_readiness(self, data_dir: Path, *, max_len: int) -> dict[str, Any]:
        key = (
            data_dir.as_posix(),
            max_len,
            file_cache_marker(data_dir / "manifest.json"),
            file_cache_marker(data_dir / "train.jsonl"),
            file_cache_marker(data_dir / "test.jsonl"),
        )
        with self.cad_readiness_lock:
            if self.cad_readiness_cache_key == key and self.cad_readiness_cache is not None:
                return self.cad_readiness_cache
            readiness = cad_dataset_readiness(data_dir, max_len=max_len)
            self.cad_readiness_cache_key = key
            self.cad_readiness_cache = readiness
            return readiness

    def stop_cad_diffusion_train(self) -> bool:
        with self.lock:
            if self.cad_train_thread is None or not self.cad_train_thread.is_alive():
                return False
            self.cad_train_stop_event.set()
            self.cad_train_job.write("Stop requested. A final checkpoint will be saved after the current step.")
            self.cad_train_job.set_status("stopping")
            return True

    def model_snapshot(self, queue_config=None) -> dict[str, Any]:
        model_status = self.model_job.snapshot()["status"]
        cache_ttl = 2.0 if model_status in {"running", "stopping"} else 30.0
        now = time.monotonic()
        if queue_config is not None:
            with self.lock:
                self.model_queue_config = queue_config
                self.model_cache = None
                self.model_cache_at = 0.0
        with self.lock:
            if self.model_cache is not None and now - self.model_cache_at < cache_ttl:
                return self.model_cache

        queue = queue_config or self.model_queue_config or load_model_queue(DEFAULT_MODEL_QUEUE_PATH)
        exe = ollama_path()
        snapshot = {
            "ollama": {
                "available": exe is not None,
                "path": exe,
                "version": ollama_version() if exe is not None else None,
            },
            "models": model_status_rows(queue, state_path=DEFAULT_MODEL_STATE_PATH),
        }
        with self.lock:
            self.model_cache = snapshot
            self.model_cache_at = now
        return snapshot

    def display_config(self, config_path: Path) -> ExperimentConfig:
        with self.lock:
            if (
                self.active_run_config is not None
                and self.run_thread is not None
                and self.run_thread.is_alive()
            ):
                return self.active_run_config
            self.active_run_config = None
        return assign_numbered_run_config(load_config(config_path), create=False)

    def current_snapshot(self) -> dict[str, Any]:
        return self.snapshot_buffer.snapshot()

    def run_status(self, config_path: Path) -> dict[str, Any]:
        with self.lock:
            if (
                self.run_status_cache is not None
                and self.run_thread is not None
                and self.run_thread.is_alive()
            ):
                return self.run_status_cache
        config = self.display_config(config_path)
        rows = read_jsonl_records(Path(config.output_path)).records
        payload = run_status_payload(
            config,
            rows,
            active_snapshot=self.snapshot_buffer.snapshot(),
            started_at=self.run_started_at,
        )
        payload["job"] = self.run_job.snapshot()
        return payload


def practice_output_path(output_path: str) -> str:
    path = Path(output_path)
    return str(path.with_name(f"{path.stem}.practice{path.suffix}"))


def base_experiment_id(experiment_id: str) -> str:
    return re.sub(r"_\d{3}$", "", experiment_id)


def total_cells(config: ExperimentConfig) -> int:
    return (
        len(config.models)
        * len(config.seeds)
        * len(config.strategies)
        * len(config.sampling.temperatures)
        * config.sampling.repetitions
    )


def missing_ollama_models(config: ExperimentConfig, *, limit: int | None = None) -> list[str]:
    local = list_local_models()
    cells = build_cells(config)
    if limit is not None:
        cells = cells[:limit]
    return sorted(
        {
            cell.model.name
            for cell in cells
            if cell.model.provider == "ollama" and cell.model.name not in local
        }
    )


def assign_numbered_run_config(config: ExperimentConfig, *, create: bool = True) -> ExperimentConfig:
    base_id = base_experiment_id(config.experiment_id)
    configured_parent = Path(config.output_path).parent
    root = (
        configured_parent.parent
        if configured_parent.parent.name == "runs"
        else Path("projects/cadybara-online-testing/workspace/runs")
    )
    root.mkdir(parents=True, exist_ok=True)
    index = 1
    if not create:
        existing = sorted(root.glob(f"{base_id}_[0-9][0-9][0-9]"))
        for run_dir in reversed(existing):
            candidate = config.model_copy(
                update={
                    "experiment_id": run_dir.name,
                    "output_path": str(run_dir / "results.jsonl"),
                    "artifact_root": str(run_dir / "artifacts"),
                }
            )
            rows = read_jsonl_records(Path(candidate.output_path))
            candidate_hash = config_hash(candidate)
            if not rows.records or all(record.config_hash == candidate_hash for record in rows.records):
                return candidate
    while (root / f"{base_id}_{index:03d}").exists():
        index += 1
    run_id = f"{base_id}_{index:03d}"
    run_dir = root / run_id
    if create:
        run_dir.mkdir(parents=True, exist_ok=True)
    return config.model_copy(
        update={
            "experiment_id": run_id,
            "output_path": str(run_dir / "results.jsonl"),
            "artifact_root": str(run_dir / "artifacts"),
        }
    )


def has_resumable_rows(config: ExperimentConfig, *, dry_run: bool) -> bool:
    output_path = Path(practice_output_path(config.output_path) if dry_run else config.output_path)
    rows = read_jsonl_records(output_path)
    if not rows.records:
        return False
    completed = {resume_key(record) for record in rows.records if record_is_complete(record)}
    if len(completed) >= total_cells(config):
        return False
    current_hash = config_hash(config)
    return all(record.config_hash == current_hash for record in rows.records)


def assign_run_config_for_start(config: ExperimentConfig, *, dry_run: bool) -> RunAssignment:
    latest_config = assign_numbered_run_config(config, create=False)
    latest_dir = Path(latest_config.output_path).parent
    if latest_dir.exists():
        output_path = Path(
            practice_output_path(latest_config.output_path)
            if dry_run
            else latest_config.output_path
        )
        rows = read_jsonl_records(output_path)
        if not rows.records:
            return RunAssignment(config=latest_config, resuming=False)
        if has_resumable_rows(latest_config, dry_run=dry_run):
            return RunAssignment(config=latest_config, resuming=True)
    return RunAssignment(config=assign_numbered_run_config(config, create=True), resuming=False)


def write_assigned_config(config: ExperimentConfig) -> None:
    config_path = Path(config.output_path).parent / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )


def progress_for_path(path: str, total: int) -> dict[str, Any]:
    rows = read_jsonl_records(Path(path))
    completed = {resume_key(record) for record in rows.records if record_is_complete(record)}
    return {
        "output_path": path,
        "valid_rows": len(rows.records),
        "completed_cells": len(completed),
        "malformed_rows": rows.malformed_count,
        "complete_percent": round((len(completed) / total) * 100, 1) if total else 0,
    }


def experiment_progress(config_path: Path, *, config: ExperimentConfig | None = None) -> dict[str, Any]:
    try:
        config = config or load_config(config_path)
    except Exception as exc:  # noqa: BLE001
        return {"config_error": str(exc)}
    total = total_cells(config)
    return {
        "config_path": str(config_path),
        "assigned_config_path": str(Path(config.output_path).parent / "config.yaml"),
        "experiment_id": config.experiment_id,
        "output_path": config.output_path,
        "model_count": len(config.models),
        "seed_count": len(config.seeds),
        "strategy_count": len(config.strategies),
        "temperature_count": len(config.sampling.temperatures),
        "temperatures": config.sampling.temperatures,
        "repetitions": config.sampling.repetitions,
        "output_mode": config.output_mode,
        "total_cells": total,
        "real": progress_for_path(config.output_path, total),
        "practice": progress_for_path(practice_output_path(config.output_path), total),
    }


def bool_query(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def saved_outputs(config: ExperimentConfig, *, dry_run: bool, limit: int = 20) -> dict[str, Any]:
    path = Path(practice_output_path(config.output_path) if dry_run else config.output_path)
    rows = read_jsonl_records(path)
    selected = list(enumerate(rows.records, start=1))[-limit:]
    selected.reverse()
    return {
        "output_path": str(path),
        "valid_rows": len(rows.records),
        "malformed_rows": rows.malformed_count,
        "rows": [
            {
                "sequence": index,
                "run_id": record.run_id,
                "timestamp_utc": record.timestamp_utc,
                "model_name": record.model_name,
                "provider": record.provider,
                "seed_id": record.seed_id,
                "seed_text": record.seed_text,
                "repetition": record.repetition,
                "attempt": record.attempt,
                "temperature": record.sampling.get("temperature"),
                "latency_ms": record.latency_ms,
                "error": record.error,
                "render_error": record.render_error,
                "is_renderable": bool(
                    (record.artifacts or {}).get("stl")
                    and record.error is None
                    and record.render_error is None
                ),
                "output": record.output,
            }
            for index, record in selected
        ],
    }


def review_payload(config: ExperimentConfig) -> dict[str, Any]:
    return review_items(Path(config.output_path), experiment_id=config.experiment_id)


def make_handler(state: LabState):
    root = state.root

    class LabHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def _json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            super().end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/lab", "/lab/"}:
                self.path = "/" + (LAB_STATIC_ROOT / "index.html").as_posix()
                return super().do_GET()
            if parsed.path.startswith("/lab/"):
                self.path = "/" + (LAB_STATIC_ROOT / parsed.path.removeprefix("/lab/")).as_posix()
                return super().do_GET()
            if parsed.path in {"/viewer", "/viewer/"}:
                self.path = "/" + (VIEWER_STATIC_ROOT / "index.html").as_posix()
                return super().do_GET()
            if parsed.path.startswith("/viewer/"):
                self.path = "/" + (VIEWER_STATIC_ROOT / parsed.path.removeprefix("/viewer/")).as_posix()
                return super().do_GET()
            legacy_target = legacy_workspace_target(parsed.path)
            if legacy_target is not None:
                self.path = "/" + legacy_target.as_posix()
                return super().do_GET()
            if parsed.path == "/api/status":
                config_path = Path(parse_qs(parsed.query).get("config", [DEFAULT_PROJECT_CONFIG])[0])
                display_config = state.display_config(config_path)
                model_snapshot = state.model_snapshot(queue_from_experiment_config(display_config))
                self._json(
                    {
                        "ollama": model_snapshot["ollama"],
                        "models": model_snapshot["models"],
                        "jobs": {
                            "models": state.model_job.snapshot(),
                            "run": state.run_job.snapshot(),
                        },
                        "experiment": experiment_progress(config_path, config=display_config),
                        "viewer_url": f"/viewer/?artifact={DEFAULT_SAMPLE_ARTIFACT}",
                    }
                )
                return
            if parsed.path == "/api/current_snapshot":
                self._json(state.current_snapshot())
                return
            if parsed.path == "/api/cad-diffusion/status":
                self._json(state.cad_diffusion_status())
                return
            if parsed.path == "/api/run_status":
                config_path = Path(parse_qs(parsed.query).get("config", [DEFAULT_PROJECT_CONFIG])[0])
                self._json(state.run_status(config_path))
                return
            if parsed.path == "/api/results":
                query = parse_qs(parsed.query)
                config_path = Path(query.get("config", [DEFAULT_PROJECT_CONFIG])[0])
                display_config = state.display_config(config_path)
                dry_run = bool_query(query.get("dry_run", ["true"])[0], default=True)
                limit = int(query.get("limit", ["20"])[0])
                self._json(saved_outputs(display_config, dry_run=dry_run, limit=limit))
                return
            if parsed.path == "/api/review":
                query = parse_qs(parsed.query)
                config_path = Path(query.get("config", [DEFAULT_PROJECT_CONFIG])[0])
                self._json(review_payload(state.display_config(config_path)))
                return
            return super().do_GET()

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            payload = {}
            if length:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/api/models/start":
                config_path = payload.get("config_path")
                if config_path:
                    started = state.start_models_for_config(
                        config_path=config_path,
                        limit=payload.get("limit"),
                        family=payload.get("family") or None,
                    )
                else:
                    started = state.start_models(
                        limit=payload.get("limit"),
                        family=payload.get("family") or None,
                    )
                self._json({"started": started}, status=202 if started else 409)
                return
            if self.path == "/api/run/start":
                started = state.start_run(
                    config_path=payload.get("config_path", DEFAULT_PROJECT_CONFIG),
                    dry_run=bool(payload.get("dry_run", False)),
                )
                self._json({"started": started}, status=202 if started else 409)
                return
            if self.path == "/api/run/stop":
                stopped = state.stop_run()
                self._json({"stop_requested": stopped}, status=202 if stopped else 409)
                return
            if self.path == "/api/cad-diffusion/train/start":
                started = state.start_cad_diffusion_train(overrides=payload)
                self._json(
                    {"started": started, "status": state.cad_diffusion_status()},
                    status=202 if started else 409,
                )
                return
            if self.path == "/api/cad-diffusion/train/stop":
                stopped = state.stop_cad_diffusion_train()
                self._json(
                    {"stop_requested": stopped, "status": state.cad_diffusion_status()},
                    status=202 if stopped else 409,
                )
                return
            if self.path == "/api/review/score":
                config = state.display_config(Path(payload.get("config_path", DEFAULT_PROJECT_CONFIG)))
                saved = append_score(
                    review_path(config.experiment_id),
                    run_id=str(payload["run_id"]),
                    score=int(payload["score"]),
                )
                self._json({"saved": saved})
                return
            self._json({"error": "not found"}, status=404)

    return LabHandler


def serve_lab(host: str = "127.0.0.1", port: int = 8787) -> None:
    root = Path.cwd().resolve()
    state = LabState(root)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    print(f"Serving cadybara lab: http://{host}:{port}/lab/")
    print("Press Ctrl+C to stop.")
    state.resume_current_job_if_active()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped lab.")
    finally:
        server.server_close()
