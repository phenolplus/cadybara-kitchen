from __future__ import annotations

from typing import Any

from cadybara.strategies.base import Strategy, Variant, make_variant_id


class IdentityStrategy(Strategy):
    name = "identity"

    def variants(
        self,
        seed_id: str,
        seed_text: str,
        seed_metadata: dict[str, Any],
    ) -> list[Variant]:
        return [
            Variant(
                variant_id=make_variant_id(self.name, seed_id, seed_text),
                text=seed_text,
                metadata={"strategy": self.name},
            )
        ]
