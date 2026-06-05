from __future__ import annotations

from cadybara.scoring.base import Scorer
from cadybara.strategies.base import Variant


class StubScorer(Scorer):
    def score(self, seed_text: str, variant: Variant, output: str) -> dict[str, float]:
        return {"output_length": float(len(output))}
