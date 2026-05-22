from __future__ import annotations

from cadybara.providers.base import ModelProvider, ProviderResponse


class DryRunProvider(ModelProvider):
    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        seed: int | None,
    ) -> ProviderResponse:
        return ProviderResponse(
            output="DRY_RUN",
            latency_ms=0,
            prompt_tokens=None,
            completion_tokens=None,
            finish_reason=None,
        )
