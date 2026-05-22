from __future__ import annotations

import json
import threading
from collections import deque
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from cadybara.config import load_config
from cadybara.model_queue import (
    DEFAULT_MODEL_QUEUE_PATH,
    DEFAULT_MODEL_STATE_PATH,
    load_model_queue,
    model_status_rows,
    ollama_path,
    ollama_version,
    pull_model_queue,
)
from cadybara.reviews import append_score, review_items, review_path
from cadybara.runner import read_jsonl_records, run_config, run_config_path


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
        self.model_thread: threading.Thread | None = None
        self.run_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

    def start_models(self, *, limit: int | None = None, family: str | None = None) -> bool:
        with self.lock:
            if self.model_thread is not None and self.model_thread.is_alive():
                return False
            self.model_job = JobLog("model-prefetch")

            def target() -> None:
                self.model_job.set_status("running")
                try:
                    config = load_model_queue(DEFAULT_MODEL_QUEUE_PATH)
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

            self.model_thread = threading.Thread(target=target, daemon=True)
            self.model_thread.start()
            return True

    def start_run(self, *, config_path: str, dry_run: bool) -> bool:
        with self.lock:
            if self.run_thread is not None and self.run_thread.is_alive():
                return False
            self.run_job = JobLog("experiment-run")
            self.stop_event.clear()

            def target() -> None:
                self.run_job.set_status("running")
                try:
                    if dry_run:
                        config = load_config(config_path)
                        run_config(
                            config.model_copy(update={"output_path": practice_output_path(config.output_path)}),
                            dry_run=True,
                            should_stop=self.stop_event.is_set,
                            stream=self.run_job,
                        )
                    else:
                        run_config_path(
                            config_path,
                            dry_run=False,
                            should_stop=self.stop_event.is_set,
                            stream=self.run_job,
                        )
                    self.run_job.set_status("stopped" if self.stop_event.is_set() else "done")
                except Exception as exc:  # noqa: BLE001 - lab reports failures in UI.
                    self.run_job.write(f"Error: {exc}")
                    self.run_job.set_status("error")

            self.run_thread = threading.Thread(target=target, daemon=True)
            self.run_thread.start()
            return True

    def stop_run(self) -> bool:
        with self.lock:
            if self.run_thread is None or not self.run_thread.is_alive():
                return False
            self.stop_event.set()
            self.run_job.write("Stop requested. Current generation will finish, then the queue will pause.")
            self.run_job.set_status("stopping")
            return True


def practice_output_path(output_path: str) -> str:
    path = Path(output_path)
    return str(path.with_name(f"{path.stem}.practice{path.suffix}"))


def progress_for_path(path: str, total: int) -> dict[str, Any]:
    rows = read_jsonl_records(Path(path))
    return {
        "output_path": path,
        "valid_rows": len(rows.records),
        "malformed_rows": rows.malformed_count,
        "complete_percent": round((len(rows.records) / total) * 100, 1) if total else 0,
    }


def experiment_progress(config_path: Path) -> dict[str, Any]:
    try:
        config = load_config(config_path)
    except Exception as exc:  # noqa: BLE001
        return {"config_error": str(exc)}
    total = (
        len(config.models)
        * len(config.seeds)
        * len(config.strategies)
        * len(config.sampling.temperatures)
        * config.sampling.repetitions
    )
    return {
        "config_path": str(config_path),
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


def saved_outputs(config_path: Path, *, dry_run: bool, limit: int = 20) -> dict[str, Any]:
    try:
        config = load_config(config_path)
    except Exception as exc:  # noqa: BLE001
        return {"config_error": str(exc)}

    path = Path(practice_output_path(config.output_path) if dry_run else config.output_path)
    rows = read_jsonl_records(path)
    selected = rows.records[-limit:]
    selected.reverse()
    return {
        "output_path": str(path),
        "valid_rows": len(rows.records),
        "malformed_rows": rows.malformed_count,
        "rows": [
            {
                "run_id": record.run_id,
                "timestamp_utc": record.timestamp_utc,
                "model_name": record.model_name,
                "provider": record.provider,
                "seed_id": record.seed_id,
                "seed_text": record.seed_text,
                "repetition": record.repetition,
                "temperature": record.sampling.get("temperature"),
                "latency_ms": record.latency_ms,
                "error": record.error,
                "output": record.output,
            }
            for record in selected
        ],
    }


def review_payload(config_path: Path) -> dict[str, Any]:
    try:
        config = load_config(config_path)
    except Exception as exc:  # noqa: BLE001
        return {"config_error": str(exc)}
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

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/lab", "/lab/"}:
                self.path = "/lab/index.html"
                return super().do_GET()
            if parsed.path == "/api/status":
                config_path = Path(parse_qs(parsed.query).get("config", ["configs/pilot_local.yaml"])[0])
                queue = load_model_queue(DEFAULT_MODEL_QUEUE_PATH)
                self._json(
                    {
                        "ollama": {
                            "available": ollama_path() is not None,
                            "path": ollama_path(),
                            "version": ollama_version(),
                        },
                        "models": model_status_rows(queue, state_path=DEFAULT_MODEL_STATE_PATH),
                        "jobs": {
                            "models": state.model_job.snapshot(),
                            "run": state.run_job.snapshot(),
                        },
                        "experiment": experiment_progress(config_path),
                        "viewer_url": "/viewer/?artifact=/workspace/sample_part.json",
                    }
                )
                return
            if parsed.path == "/api/results":
                query = parse_qs(parsed.query)
                config_path = Path(query.get("config", ["configs/pilot_local.yaml"])[0])
                dry_run = bool_query(query.get("dry_run", ["true"])[0], default=True)
                limit = int(query.get("limit", ["20"])[0])
                self._json(saved_outputs(config_path, dry_run=dry_run, limit=limit))
                return
            if parsed.path == "/api/review":
                query = parse_qs(parsed.query)
                config_path = Path(query.get("config", ["configs/pilot_local.yaml"])[0])
                self._json(review_payload(config_path))
                return
            return super().do_GET()

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            payload = {}
            if length:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/api/models/start":
                started = state.start_models(
                    limit=payload.get("limit"),
                    family=payload.get("family") or None,
                )
                self._json({"started": started}, status=202 if started else 409)
                return
            if self.path == "/api/run/start":
                started = state.start_run(
                    config_path=payload.get("config_path", "configs/pilot_local.yaml"),
                    dry_run=bool(payload.get("dry_run", False)),
                )
                self._json({"started": started}, status=202 if started else 409)
                return
            if self.path == "/api/run/stop":
                stopped = state.stop_run()
                self._json({"stop_requested": stopped}, status=202 if stopped else 409)
                return
            if self.path == "/api/review/score":
                config = load_config(payload.get("config_path", "configs/pilot_local.yaml"))
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
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped lab.")
    finally:
        server.server_close()
