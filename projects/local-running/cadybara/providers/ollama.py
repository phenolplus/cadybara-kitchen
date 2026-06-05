from __future__ import annotations

import json
import os
import time
from pathlib import Path
from collections.abc import Callable
from typing import TYPE_CHECKING

import httpx

from cadybara.providers.base import ModelProvider, ProviderResponse

if TYPE_CHECKING:
    from cadybara.snapshot import SnapshotBuffer


def _duration_ms(value: int | float | None) -> int | None:
    if value is None:
        return None
    return int(value / 1_000_000)


class OllamaProvider(ModelProvider):
    def __init__(
        self,
        *,
        model_name: str,
        base_url: str,
        timeout: float = 600.0,
        num_thread: int | None = None,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.num_thread = num_thread

    def _options(self, *, temperature: float, max_tokens: int, seed: int | None) -> dict:
        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
            "seed": seed,
        }
        num_ctx = os.environ.get("CADYBARA_OLLAMA_NUM_CTX")
        if num_ctx:
            options["num_ctx"] = int(num_ctx)
        if self.num_thread is not None:
            options["num_thread"] = self.num_thread
        else:
            num_thread = os.environ.get("CADYBARA_OLLAMA_NUM_THREAD")
            if num_thread:
                options["num_thread"] = int(num_thread)
        return options

    def _use_chat_endpoint(self) -> bool:
        value = os.environ.get("CADYBARA_OLLAMA_USE_CHAT", "")
        return value.lower() in {"1", "true", "yes"}

    def _encoded_images(self, images: list[str] | None) -> list[str] | None:
        if not images:
            return None
        import base64  # noqa: PLC0415 - only needed for vision repair calls.

        encoded: list[str] = []
        for image in images:
            path = Path(image)
            if path.exists():
                encoded.append(base64.b64encode(path.read_bytes()).decode("ascii"))
            else:
                encoded.append(image)
        return encoded

    def _prompt(self, prompt: str) -> str:
        return (
            os.environ.get("CADYBARA_OLLAMA_PROMPT_PREFIX", "")
            + prompt
            + os.environ.get("CADYBARA_OLLAMA_PROMPT_SUFFIX", "")
        )

    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        seed: int | None,
        images: list[str] | None = None,
    ) -> ProviderResponse:
        if self._use_chat_endpoint():
            return self._generate_chat(
                prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
                images=images,
            )
        payload = {
            "model": self.model_name,
            "prompt": self._prompt(prompt),
            "stream": False,
            "think": False,
            "options": self._options(
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
            ),
        }
        encoded_images = self._encoded_images(images)
        if encoded_images:
            payload["images"] = encoded_images
        started = time.perf_counter()
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        wall_latency_ms = int((time.perf_counter() - started) * 1000)
        total_duration_ms = _duration_ms(data.get("total_duration"))
        return ProviderResponse(
            output=str(data.get("response", "")),
            latency_ms=total_duration_ms if total_duration_ms is not None else wall_latency_ms,
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            finish_reason=data.get("done_reason") or data.get("finish_reason"),
            total_duration_ms=total_duration_ms,
            load_duration_ms=_duration_ms(data.get("load_duration")),
            prompt_eval_duration_ms=_duration_ms(data.get("prompt_eval_duration")),
            eval_duration_ms=_duration_ms(data.get("eval_duration")),
            provider_seed=data.get("seed"),
        )

    def _generate_chat(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        seed: int | None,
        images: list[str] | None = None,
    ) -> ProviderResponse:
        message: dict = {
            "role": "user",
            "content": self._prompt(prompt),
        }
        encoded_images = self._encoded_images(images)
        if encoded_images:
            message["images"] = encoded_images
        payload = {
            "model": self.model_name,
            "messages": [message],
            "stream": False,
            "think": False,
            "options": self._options(
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
            ),
        }
        started = time.perf_counter()
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        wall_latency_ms = int((time.perf_counter() - started) * 1000)
        total_duration_ms = _duration_ms(data.get("total_duration"))
        response_message = data.get("message") or {}
        return ProviderResponse(
            output=str(response_message.get("content", "")),
            latency_ms=total_duration_ms if total_duration_ms is not None else wall_latency_ms,
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            finish_reason=data.get("done_reason") or data.get("finish_reason"),
            total_duration_ms=total_duration_ms,
            load_duration_ms=_duration_ms(data.get("load_duration")),
            prompt_eval_duration_ms=_duration_ms(data.get("prompt_eval_duration")),
            eval_duration_ms=_duration_ms(data.get("eval_duration")),
            provider_seed=data.get("seed"),
        )

    def generate_interruptible(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        seed: int | None,
        should_stop: Callable[[], bool],
        snapshot_buffer: "SnapshotBuffer | None" = None,
        images: list[str] | None = None,
    ) -> ProviderResponse:
        if self._use_chat_endpoint():
            return self._generate_chat_interruptible(
                prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
                should_stop=should_stop,
                snapshot_buffer=snapshot_buffer,
                images=images,
            )
        payload = {
            "model": self.model_name,
            "prompt": self._prompt(prompt),
            "stream": True,
            "think": False,
            "options": self._options(
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
            ),
        }
        encoded_images = self._encoded_images(images)
        if encoded_images:
            payload["images"] = encoded_images
        started = time.perf_counter()
        chunks: list[str] = []
        final: dict = {}
        with httpx.stream(
            "POST",
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if should_stop():
                    from cadybara.providers.base import GenerationStopped  # noqa: PLC0415

                    raise GenerationStopped("generation stopped by user")
                if not line:
                    continue
                data = json.loads(line)
                chunk = str(data.get("response", ""))
                chunks.append(chunk)
                if snapshot_buffer is not None:
                    snapshot_buffer.append(chunk)
                if data.get("done"):
                    final = data
                    break
        wall_latency_ms = int((time.perf_counter() - started) * 1000)
        total_duration_ms = _duration_ms(final.get("total_duration"))
        return ProviderResponse(
            output="".join(chunks),
            latency_ms=total_duration_ms if total_duration_ms is not None else wall_latency_ms,
            prompt_tokens=final.get("prompt_eval_count"),
            completion_tokens=final.get("eval_count"),
            finish_reason=final.get("done_reason") or final.get("finish_reason"),
            total_duration_ms=total_duration_ms,
            load_duration_ms=_duration_ms(final.get("load_duration")),
            prompt_eval_duration_ms=_duration_ms(final.get("prompt_eval_duration")),
            eval_duration_ms=_duration_ms(final.get("eval_duration")),
            provider_seed=final.get("seed"),
        )

    def _generate_chat_interruptible(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        seed: int | None,
        should_stop: Callable[[], bool],
        snapshot_buffer: "SnapshotBuffer | None" = None,
        images: list[str] | None = None,
    ) -> ProviderResponse:
        message: dict = {
            "role": "user",
            "content": self._prompt(prompt),
        }
        encoded_images = self._encoded_images(images)
        if encoded_images:
            message["images"] = encoded_images
        payload = {
            "model": self.model_name,
            "messages": [message],
            "stream": True,
            "think": False,
            "options": self._options(
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
            ),
        }
        started = time.perf_counter()
        chunks: list[str] = []
        final: dict = {}
        with httpx.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if should_stop():
                    from cadybara.providers.base import GenerationStopped  # noqa: PLC0415

                    raise GenerationStopped("generation stopped by user")
                if not line:
                    continue
                data = json.loads(line)
                message_chunk = data.get("message") or {}
                chunk = str(message_chunk.get("content", ""))
                chunks.append(chunk)
                if snapshot_buffer is not None:
                    snapshot_buffer.append(chunk)
                if data.get("done"):
                    final = data
                    break
        wall_latency_ms = int((time.perf_counter() - started) * 1000)
        total_duration_ms = _duration_ms(final.get("total_duration"))
        return ProviderResponse(
            output="".join(chunks),
            latency_ms=total_duration_ms if total_duration_ms is not None else wall_latency_ms,
            prompt_tokens=final.get("prompt_eval_count"),
            completion_tokens=final.get("eval_count"),
            finish_reason=final.get("done_reason") or final.get("finish_reason"),
            total_duration_ms=total_duration_ms,
            load_duration_ms=_duration_ms(final.get("load_duration")),
            prompt_eval_duration_ms=_duration_ms(final.get("prompt_eval_duration")),
            eval_duration_ms=_duration_ms(final.get("eval_duration")),
            provider_seed=final.get("seed"),
        )
