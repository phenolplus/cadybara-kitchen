from __future__ import annotations

from abc import ABC, abstractmethod

from cadybara.strategies.base import Variant


class Scorer(ABC):
    @abstractmethod
    def score(self, seed_text: str, variant: Variant, output: str) -> dict[str, float]:
        """Score one generated output."""
