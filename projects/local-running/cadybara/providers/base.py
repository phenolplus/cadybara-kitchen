from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GenerationStopped(RuntimeError):
    """Raised when the user requests a stop during a generation."""


class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: str
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    finish_reason: str | None
    total_duration_ms: int | None = None
    load_duration_ms: int | None = None
    prompt_eval_duration_ms: int | None = None
    eval_duration_ms: int | None = None
    provider_seed: int | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    hosted_stl_base64: str | None = None


class ModelProvider(ABC):
    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        seed: int | None,
        images: list[str] | None = None,
    ) -> ProviderResponse:
        """Generate text for one prompt."""
