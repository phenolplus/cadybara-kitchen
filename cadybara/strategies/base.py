from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Variant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def make_variant_id(strategy: str, seed_id: str, variant_text: str) -> str:
    payload = f"{strategy}|{seed_id}|{variant_text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class Strategy(ABC):
    name: str

    @abstractmethod
    def variants(
        self,
        seed_id: str,
        seed_text: str,
        seed_metadata: dict[str, Any],
    ) -> list[Variant]:
        """Return prompt variants for one seed."""
