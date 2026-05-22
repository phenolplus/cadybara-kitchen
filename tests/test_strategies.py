from __future__ import annotations

from cadybara.strategies.identity import IdentityStrategy


def test_identity_strategy_returns_deterministic_single_variant() -> None:
    strategy = IdentityStrategy()
    first = strategy.variants("seed_001", "Create a plate", {"domain": "cad"})
    second = strategy.variants("seed_001", "Create a plate", {"domain": "cad"})
    assert len(first) == 1
    assert first[0].text == "Create a plate"
    assert first[0].metadata == {"strategy": "identity"}
    assert first[0].variant_id == second[0].variant_id
