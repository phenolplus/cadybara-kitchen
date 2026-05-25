from __future__ import annotations

import json
import time
from collections.abc import Callable

import httpx

from cadybara.providers.base import GenerationStopped, ModelProvider, ProviderResponse


def _duration_ms(value: int | float | None) -> int | None:
    if value is None:
        return None
    return int(value / 1_000_000)


class OllamaProvider(ModelProvider):
    def __init__(self, *, model_name: str, base_url: str, timeout: float = 600.0) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        seed: int | None,
    ) -> ProviderResponse:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "seed": seed,
            },
        }
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

    def generate_interruptible(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        seed: int | None,
        should_stop: Callable[[], bool],
    ) -> ProviderResponse:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "seed": seed,
            },
        }
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
                    raise GenerationStopped("generation stopped by user")
                if not line:
                    continue
                data = json.loads(line)
                chunks.append(str(data.get("response", "")))
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
