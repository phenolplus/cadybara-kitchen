from __future__ import annotations

import time

import httpx

from cadybara.providers.base import ModelProvider, ProviderResponse


def _duration_ms(value: int | float | None) -> int | None:
    if value is None:
        return None
    return int(value / 1_000_000)


class OllamaProvider(ModelProvider):
    def __init__(self, *, model_name: str, base_url: str, timeout: float = 120.0) -> None:
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
