from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field

from cadybara.config import ExperimentConfig, load_config


DEFAULT_MODEL_QUEUE_PATH = Path("projects/local-running/configs/models_local.yaml")
DEFAULT_MODEL_STATE_PATH = Path("projects/local-running/workspace/model_queue_state.json")
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
STATE_WRITE_LOCK = threading.Lock()


class LocalModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    family: str
    role: str
    priority: int
    estimated_size_gb: float | None = None
    params_b: float | None = None
    vision: bool = False


class ModelQueueConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    storage_budget_gb: float | None = None
    min_free_disk_gb: float = 50.0
    prefetch_threshold: float = 0.8
    cleanup_models: list[str] = Field(default_factory=list)
    manifest_path: str = "projects/local-running/workspace/model_pull_manifest.jsonl"
    models: list[LocalModelSpec] = Field(min_length=1)

    def sorted_models(self) -> list[LocalModelSpec]:
        return sorted(self.models, key=lambda item: (item.priority, item.name))


class ModelPullSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempted: int
    installed: int
    skipped: int
    errors: int
    state_path: str


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_model_queue(path: str | Path = DEFAULT_MODEL_QUEUE_PATH) -> ModelQueueConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return ModelQueueConfig.model_validate(data)


def queue_from_experiment_config(config: ExperimentConfig) -> ModelQueueConfig:
    return ModelQueueConfig(
        ollama_base_url=next(
            (model.base_url for model in config.models if model.provider == "ollama"),
            DEFAULT_OLLAMA_BASE_URL,
        ),
        storage_budget_gb=None,
        min_free_disk_gb=50.0,
        prefetch_threshold=0.8,
        cleanup_models=[
            "deepseek-coder-v2:236b",
            "qwen2.5-coder:0.5b",
            "qwen2.5-coder:1.5b",
            "qwen2.5:0.5b",
            "qwen2.5:1.5b",
            "llama3.2:1b",
            "gemma3:1b",
            "phi3:mini",
            "starcoder2:3b",
            "starcoder2:7b",
            "qwen2.5-coder:3b",
            "qwen2.5-coder:7b",
            "qwen2.5-coder:14b",
            "qwen2.5-coder:32b",
            "deepseek-coder:6.7b",
            "deepseek-coder-v2:16b",
            "starcoder2:15b",
        ],
        manifest_path=str(Path(config.output_path).parent / "pull_manifest.jsonl"),
        models=[
            LocalModelSpec(
                name=model.name,
                family=model.family or "unknown",
                role="experiment-required",
                priority=index,
                estimated_size_gb=model.disk_gb,
                params_b=model.params_b,
                vision=model.vision,
            )
            for index, model in enumerate(config.models, start=1)
            if model.provider == "ollama"
        ],
    )


def load_model_queue_or_experiment(path: str | Path = DEFAULT_MODEL_QUEUE_PATH) -> ModelQueueConfig:
    try:
        return load_model_queue(path)
    except Exception:
        return queue_from_experiment_config(load_config(path))


def ollama_path() -> str | None:
    from_path = shutil.which("ollama")
    if from_path is not None:
        return from_path
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.exists():
            return str(candidate)
    return None


def ollama_version() -> str | None:
    exe = ollama_path()
    if exe is None:
        return None
    try:
        result = subprocess.run(
            [exe, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (result.stdout or result.stderr).strip()
    return text or None


def list_local_models(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> set[str]:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=12)
        response.raise_for_status()
        models = response.json().get("models", [])
        names = {
            str(model.get("name") or model.get("model"))
            for model in models
            if model.get("name") or model.get("model")
        }
        if names:
            return names
    except (httpx.HTTPError, ValueError, TypeError):
        pass

    exe = ollama_path()
    if exe is None:
        return set()
    try:
        result = subprocess.run(
            [exe, "list"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if result.returncode != 0:
        return set()
    models: set[str] = set()
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if parts:
            models.add(parts[0])
    return models


def load_model_state(path: str | Path = DEFAULT_MODEL_STATE_PATH) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return {"models": {}, "updated_at": None}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = state_path.with_suffix(state_path.suffix + ".corrupt")
        state_path.replace(backup)
        return {"models": {}, "updated_at": None, "corrupt_backup": str(backup)}


def save_model_state(state: dict[str, Any], path: str | Path = DEFAULT_MODEL_STATE_PATH) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_utc()
    payload = json.dumps(state, indent=2) + "\n"
    tmp_path = state_path.with_name(
        f"{state_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    with STATE_WRITE_LOCK:
        last_error: OSError | None = None
        for _ in range(8):
            try:
                tmp_path.write_text(payload, encoding="utf-8")
                tmp_path.replace(state_path)
                return
            except OSError as exc:
                last_error = exc
                time.sleep(0.25)
        assert last_error is not None
        raise last_error


def append_pull_manifest(
    path: str | Path,
    *,
    model_name: str,
    status: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> None:
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp_utc": now_utc(),
        "model_name": model_name,
        "status": status,
        "message": message,
    }
    if extra:
        row.update(extra)
    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")))
        handle.write("\n")
        handle.flush()


def free_disk_gb(path: str | Path = ".") -> float:
    usage = shutil.disk_usage(Path(path).resolve().anchor)
    return usage.free / (1024**3)


def remove_local_model(model_name: str, *, stream: TextIO | None = None) -> bool:
    exe = ollama_path()
    if exe is None:
        return False
    if model_name not in list_local_models():
        return False
    if stream:
        print(f"DELETE {model_name} to free space for heavy vision models", file=stream)
    result = subprocess.run(
        [exe, "rm", model_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if stream and (result.stdout or result.stderr):
        print((result.stdout or result.stderr).strip(), file=stream)
    return result.returncode == 0


def ensure_free_disk_for_model(
    spec: LocalModelSpec,
    config: ModelQueueConfig,
    *,
    stream: TextIO | None = None,
) -> tuple[bool, str]:
    required_size = spec.estimated_size_gb or 0.0
    current_free = free_disk_gb()
    if current_free - required_size >= config.min_free_disk_gb:
        return True, f"free={current_free:.1f}GB required={required_size:.1f}GB"

    if os.environ.get("CADYBARA_DISABLE_MODEL_CLEANUP", "").lower() in {"1", "true", "yes"}:
        return (
            False,
            (
                f"free={current_free:.1f}GB required={required_size:.1f}GB "
                f"floor={config.min_free_disk_gb:.1f}GB cleanup=disabled"
            ),
        )

    for model_name in config.cleanup_models:
        if model_name == spec.name:
            continue
        if current_free - required_size >= config.min_free_disk_gb:
            break
        removed = remove_local_model(model_name, stream=stream)
        if removed:
            current_free = free_disk_gb()

    if current_free - required_size >= config.min_free_disk_gb:
        return True, f"free={current_free:.1f}GB required={required_size:.1f}GB after cleanup"
    return (
        False,
        (
            f"free={current_free:.1f}GB required={required_size:.1f}GB "
            f"floor={config.min_free_disk_gb:.1f}GB"
        ),
    )


def model_status_rows(
    config: ModelQueueConfig,
    *,
    state_path: str | Path = DEFAULT_MODEL_STATE_PATH,
) -> list[dict[str, Any]]:
    local = list_local_models(config.ollama_base_url)
    state = load_model_state(state_path)
    rows: list[dict[str, Any]] = []
    for spec in config.sorted_models():
        saved = dict(state.get("models", {}).get(spec.name, {}))
        status = saved.get("status", "pending")
        if spec.name in local:
            status = "installed"
            saved["percent"] = 100
        elif status == "pulling":
            saved.update(inferred_partial_progress(saved))
        elif status == "installed":
            status = "missing"
            saved["percent"] = None
        rows.append(
            {
                "name": spec.name,
                "family": spec.family,
                "role": spec.role,
                "priority": spec.priority,
                "estimated_size_gb": spec.estimated_size_gb,
                "status": status,
                "percent": saved.get("percent"),
                "completed_bytes": saved.get("completed_bytes"),
                "total_bytes": saved.get("total_bytes"),
                "downloaded_gb": bytes_to_gb(saved.get("completed_bytes")),
                "total_gb": bytes_to_gb(saved.get("total_bytes")),
                "digest": saved.get("digest"),
                "message": saved.get("message"),
                "started_at": saved.get("started_at"),
                "last_event_at": saved.get("last_event_at"),
                "finished_at": saved.get("finished_at"),
            }
        )
    return rows


def update_model_state(
    state: dict[str, Any],
    model_name: str,
    *,
    status: str,
    percent: int | None = None,
    message: str | None = None,
    extra: dict[str, Any] | None = None,
    state_path: str | Path = DEFAULT_MODEL_STATE_PATH,
) -> None:
    models = state.setdefault("models", {})
    entry = models.setdefault(model_name, {})
    previous_status = entry.get("status")
    entry["status"] = status
    if previous_status != "pulling" and status == "pulling":
        entry["started_at"] = now_utc()
    if status in {"installed", "error", "skipped"}:
        entry["finished_at"] = now_utc()
    if percent is not None:
        entry["percent"] = percent
    if message is not None:
        entry["message"] = message[-500:]
    entry["last_event_at"] = now_utc()
    if extra:
        for key, value in extra.items():
            if value is not None:
                entry[key] = value
    save_model_state(state, state_path)


def bytes_to_gb(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / (1024**3), 2)
    except (TypeError, ValueError):
        return None


def percent_from_bytes(completed: Any, total: Any) -> int | None:
    try:
        completed_int = int(completed)
        total_int = int(total)
    except (TypeError, ValueError):
        return None
    if total_int <= 0:
        return None
    return max(0, min(99, int((completed_int / total_int) * 100)))


def inferred_partial_progress(saved: dict[str, Any]) -> dict[str, Any]:
    if saved.get("completed_bytes") and saved.get("total_bytes"):
        return {}
    message = saved.get("message") or ""
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*GB\s*/\s*([0-9]+(?:\.[0-9]+)?)\s*GB", message)
    if not match:
        return {}
    completed = int(float(match.group(1)) * (1024**3))
    total = int(float(match.group(2)) * (1024**3))
    percent = percent_from_bytes(completed, total)
    return {
        "completed_bytes": completed,
        "total_bytes": total,
        "percent": percent,
    }


def parse_pull_percent(text: str) -> int | None:
    matches = re.findall(r"(\d{1,3})%", text)
    if not matches:
        return None
    return max(0, min(100, int(matches[-1])))


def clean_pull_message(text: str) -> str:
    ansi = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    cleaned = ansi.sub("", text)
    cleaned = cleaned.replace("\x1b", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def pull_one_model(
    spec: LocalModelSpec,
    *,
    state: dict[str, Any],
    state_path: str | Path = DEFAULT_MODEL_STATE_PATH,
    manifest_path: str | Path = "projects/local-running/workspace/model_pull_manifest.jsonl",
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    stream: TextIO | None = None,
) -> bool:
    base_url = base_url.rstrip("/")
    if not isinstance(manifest_path, str):
        manifest_path = Path(manifest_path)
    exe = ollama_path()
    if exe is None:
        update_model_state(
            state,
            spec.name,
            status="error",
            message="Ollama is not installed or not on PATH.",
            state_path=state_path,
        )
        append_pull_manifest(
            manifest_path,
            model_name=spec.name,
            status="error",
            message="Ollama is not installed or not on PATH.",
        )
        return False

    if spec.name in list_local_models(base_url):
        update_model_state(
            state,
            spec.name,
            status="installed",
            percent=100,
            message="Already installed.",
            state_path=state_path,
        )
        if stream:
            print(f"SKIP {spec.name} already installed", file=stream)
        append_pull_manifest(
            manifest_path,
            model_name=spec.name,
            status="installed",
            message="Already installed.",
        )
        return True

    update_model_state(
        state,
        spec.name,
        status="pulling",
        percent=state.get("models", {}).get(spec.name, {}).get("percent", 0),
        message="Starting or resuming pull.",
        state_path=state_path,
    )
    if stream:
        print(f"PULL {spec.name} via Ollama API", file=stream)
    append_pull_manifest(
        manifest_path,
        model_name=spec.name,
        status="pulling",
        message="Starting or resuming pull.",
        extra={"estimated_size_gb": spec.estimated_size_gb},
    )

    last_percent: int | None = None
    last_manifest_percent: int | None = None
    last_manifest_at = 0.0
    last_status = "starting"
    try:
        timeout = httpx.Timeout(timeout=None, connect=30.0)
        with httpx.stream(
            "POST",
            f"{base_url}/api/pull",
            json={"model": spec.name, "stream": True},
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                status_text = str(data.get("status") or "pulling")
                digest = data.get("digest")
                completed = data.get("completed")
                total = data.get("total")
                percent = percent_from_bytes(completed, total)
                if percent is not None:
                    last_percent = percent

                gb_text = ""
                if completed is not None and total is not None:
                    gb_text = f" {bytes_to_gb(completed)}/{bytes_to_gb(total)} GB"
                message = f"{status_text}{gb_text}".strip()
                update_model_state(
                    state,
                    spec.name,
                    status="pulling",
                    percent=last_percent,
                    message=message,
                    extra={
                        "digest": digest,
                        "completed_bytes": completed,
                        "total_bytes": total,
                        "raw_status": status_text,
                    },
                    state_path=state_path,
                )
                if stream:
                    prefix = f"{last_percent}%" if last_percent is not None else "..."
                    print(f"{spec.name} {prefix} {message}", file=stream)

                now = time.monotonic()
                should_checkpoint = (
                    percent is not None
                    and percent != last_manifest_percent
                ) or status_text != last_status or now - last_manifest_at >= 30.0
                if should_checkpoint:
                    append_pull_manifest(
                        manifest_path,
                        model_name=spec.name,
                        status="pulling",
                        message=message,
                        extra={
                            "percent": last_percent,
                            "digest": digest,
                            "completed_bytes": completed,
                            "total_bytes": total,
                        },
                    )
                    last_manifest_percent = last_percent
                    last_manifest_at = now
                    last_status = status_text
    except (httpx.HTTPError, OSError, ValueError) as exc:
        update_model_state(
            state,
            spec.name,
            status="error",
            percent=last_percent,
            message=f"ollama pull failed: {exc}",
            state_path=state_path,
        )
        append_pull_manifest(
            manifest_path,
            model_name=spec.name,
            status="error",
            message=f"ollama pull failed: {exc}",
            extra={"percent": last_percent},
        )
        return False

    if spec.name in list_local_models(base_url):
        update_model_state(
            state,
            spec.name,
            status="installed",
            percent=100,
            message="Installed.",
            state_path=state_path,
        )
        append_pull_manifest(
            manifest_path,
            model_name=spec.name,
            status="installed",
            message="Installed.",
        )
        return True
    update_model_state(
        state,
        spec.name,
        status="error",
        percent=last_percent,
        message="ollama pull stream ended but the model is not installed.",
        state_path=state_path,
    )
    append_pull_manifest(
        manifest_path,
        model_name=spec.name,
        status="error",
        message="ollama pull stream ended but the model is not installed.",
        extra={"percent": last_percent},
    )
    return False


def pull_model_queue(
    config: ModelQueueConfig,
    *,
    limit: int | None = None,
    family: str | None = None,
    state_path: str | Path = DEFAULT_MODEL_STATE_PATH,
    stream: TextIO | None = None,
) -> ModelPullSummary:
    state = load_model_state(state_path)
    attempted = 0
    installed = 0
    skipped = 0
    errors = 0
    specs = [
        spec
        for spec in config.sorted_models()
        if family is None or spec.family == family
    ]

    for spec in specs:
        if limit is not None and attempted >= limit:
            break
        if spec.name in list_local_models(config.ollama_base_url):
            skipped += 1
            update_model_state(
                state,
                spec.name,
                status="installed",
                percent=100,
                message="Already installed.",
                state_path=state_path,
            )
            append_pull_manifest(
                config.manifest_path,
                model_name=spec.name,
                status="installed",
                message="Already installed.",
            )
            continue
        ok_to_pull, disk_message = ensure_free_disk_for_model(spec, config, stream=stream)
        if not ok_to_pull:
            skipped += 1
            update_model_state(
                state,
                spec.name,
                status="skipped",
                percent=None,
                message=f"Skipped: insufficient disk after cleanup. {disk_message}",
                state_path=state_path,
            )
            append_pull_manifest(
                config.manifest_path,
                model_name=spec.name,
                status="skipped",
                message=f"insufficient disk after cleanup. {disk_message}",
            )
            if stream:
                print(f"SKIP {spec.name} insufficient disk: {disk_message}", file=stream)
            continue
        append_pull_manifest(
            config.manifest_path,
            model_name=spec.name,
            status="planned",
            message=disk_message,
        )
        attempted += 1
        if pull_one_model(
            spec,
            state=state,
            state_path=state_path,
            manifest_path=config.manifest_path,
            base_url=config.ollama_base_url,
            stream=stream,
        ):
            installed += 1
        else:
            errors += 1
    return ModelPullSummary(
        attempted=attempted,
        installed=installed,
        skipped=skipped,
        errors=errors,
        state_path=str(state_path),
    )
