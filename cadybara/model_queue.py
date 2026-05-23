from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import yaml
from pydantic import BaseModel, ConfigDict, Field


DEFAULT_MODEL_QUEUE_PATH = Path("configs/models_local.yaml")
DEFAULT_MODEL_STATE_PATH = Path("workspace/model_queue_state.json")


class LocalModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    family: str
    role: str
    priority: int
    estimated_size_gb: float | None = None


class ModelQueueConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_budget_gb: float | None = None
    prefetch_threshold: float = 0.8
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


def list_local_models() -> set[str]:
    exe = ollama_path()
    if exe is None:
        return set()
    try:
        result = subprocess.run(
            [exe, "list"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
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
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    last_error: OSError | None = None
    for _ in range(5):
        try:
            tmp_path.write_text(payload, encoding="utf-8")
            tmp_path.replace(state_path)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.2)
    assert last_error is not None
    raise last_error


def model_status_rows(
    config: ModelQueueConfig,
    *,
    state_path: str | Path = DEFAULT_MODEL_STATE_PATH,
) -> list[dict[str, Any]]:
    local = list_local_models()
    state = load_model_state(state_path)
    rows: list[dict[str, Any]] = []
    for spec in config.sorted_models():
        saved = dict(state.get("models", {}).get(spec.name, {}))
        status = saved.get("status", "pending")
        if spec.name in local:
            status = "installed"
            saved["percent"] = 100
        rows.append(
            {
                "name": spec.name,
                "family": spec.family,
                "role": spec.role,
                "priority": spec.priority,
                "estimated_size_gb": spec.estimated_size_gb,
                "status": status,
                "percent": saved.get("percent"),
                "message": saved.get("message"),
                "started_at": saved.get("started_at"),
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
    save_model_state(state, state_path)


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
    stream: TextIO | None = None,
) -> bool:
    exe = ollama_path()
    if exe is None:
        update_model_state(
            state,
            spec.name,
            status="error",
            message="Ollama is not installed or not on PATH.",
            state_path=state_path,
        )
        return False

    if spec.name in list_local_models():
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
        return True

    update_model_state(
        state,
        spec.name,
        status="pulling",
        percent=0,
        message="Starting pull.",
        state_path=state_path,
    )
    if stream:
        print(f"PULL {spec.name}", file=stream)

    process = subprocess.Popen(
        [exe, "pull", spec.name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    buffer = ""
    last_percent: int | None = None
    assert process.stdout is not None
    while True:
        char = process.stdout.read(1)
        if char == "" and process.poll() is not None:
            break
        if char == "":
            continue
        if char in {"\r", "\n"}:
            message = clean_pull_message(buffer)
            if message:
                percent = parse_pull_percent(message)
                if percent is not None:
                    last_percent = percent
                update_model_state(
                    state,
                    spec.name,
                    status="pulling",
                    percent=last_percent,
                    message=message,
                    state_path=state_path,
                )
                if stream:
                    prefix = f"{last_percent}%" if last_percent is not None else "..."
                    print(f"{spec.name} {prefix} {message}", file=stream)
            buffer = ""
            continue
        buffer += char

    return_code = process.wait()
    if return_code == 0 and spec.name in list_local_models():
        update_model_state(
            state,
            spec.name,
            status="installed",
            percent=100,
            message="Installed.",
            state_path=state_path,
        )
        return True
    update_model_state(
        state,
        spec.name,
        status="error",
        message=f"ollama pull exited with code {return_code}.",
        state_path=state_path,
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
        if spec.name in list_local_models():
            skipped += 1
            update_model_state(
                state,
                spec.name,
                status="installed",
                percent=100,
                message="Already installed.",
                state_path=state_path,
            )
            continue
        attempted += 1
        if pull_one_model(spec, state=state, state_path=state_path, stream=stream):
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
