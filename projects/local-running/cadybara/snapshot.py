from __future__ import annotations

import re
import threading
import time
from typing import Any


class SnapshotBuffer:
    def __init__(self, *, max_lines: int = 40) -> None:
        self.max_lines = max_lines
        self._lock = threading.Lock()
        self._running = False
        self._model_name: str | None = None
        self._prompt_id: str | None = None
        self._prompt_text: str | None = None
        self._repetition: int | None = None
        self._repair_round: int | None = None
        self._repair_total_rounds: int | None = None
        self._started_at: float | None = None
        self._updated_at: float | None = None
        self._text = ""
        self._tokens_so_far = 0

    def start(
        self,
        *,
        model_name: str,
        prompt_id: str,
        prompt_text: str,
        repetition: int,
        repair_round: int | None = None,
        repair_total_rounds: int | None = None,
    ) -> None:
        now = time.monotonic()
        with self._lock:
            self._running = True
            self._model_name = model_name
            self._prompt_id = prompt_id
            self._prompt_text = prompt_text
            self._repetition = repetition
            self._repair_round = repair_round
            self._repair_total_rounds = repair_total_rounds
            self._started_at = now
            self._updated_at = now
            self._text = ""
            self._tokens_so_far = 0

    def append(self, chunk: str) -> None:
        if not chunk:
            return
        with self._lock:
            if not self._running:
                return
            self._text += chunk
            self._tokens_so_far += len(re.findall(r"\S+", chunk))
            self._updated_at = time.monotonic()

    def finish(self) -> None:
        with self._lock:
            self._running = False
            self._updated_at = time.monotonic()

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            started_at = self._started_at or now
            updated_at = self._updated_at or now
            lines = self._text.splitlines()[-self.max_lines :]
            return {
                "is_running": self._running,
                "model_name": self._model_name,
                "prompt_id": self._prompt_id,
                "prompt_text": self._prompt_text,
                "repetition": self._repetition,
                "repair_round": self._repair_round,
                "repair_total_rounds": self._repair_total_rounds,
                "tokens_so_far": self._tokens_so_far,
                "last_lines": lines,
                "elapsed_seconds": round(now - started_at, 1) if self._started_at else 0,
                "snapshot_age_seconds": round(now - updated_at, 1) if self._updated_at else None,
            }
