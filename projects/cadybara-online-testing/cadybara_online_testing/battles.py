from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Literal

from cadybara.config import ExperimentConfig
from cadybara_online_testing.reviews import review_items


BattleOutcome = Literal["left", "right", "tie"]

BASE_RATING = 1500.0
K_FACTOR = 32.0
SCORE_SEED_SPREAD = 320.0


def battle_path() -> Path:
    return Path("projects") / "cadybara-online-testing" / "workspace" / "reviews" / "hosted_battles.jsonl"


def timestamp_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def family_for_seed(seed_id: str | None) -> str:
    value = str(seed_id or "unknown")
    return value.split("_", 1)[0] if "_" in value else value


def battle_item_id(item: dict[str, Any]) -> str:
    return str(item["run_id"])


def load_battles(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or battle_path()
    if not source.exists():
        return []
    rows = []
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _valid_battle(payload):
                rows.append(payload)
    return rows


def append_battle(
    path: Path | None = None,
    *,
    left_run_id: str,
    right_run_id: str,
    outcome: BattleOutcome,
    criterion: str = "overall_quality",
    config_paths: Iterable[str] = (),
) -> dict[str, Any]:
    if left_run_id == right_run_id:
        raise ValueError("battle requires two different run_ids")
    if outcome not in {"left", "right", "tie"}:
        raise ValueError("outcome must be left, right, or tie")
    payload = {
        "left_run_id": left_run_id,
        "right_run_id": right_run_id,
        "outcome": outcome,
        "criterion": criterion,
        "config_paths": list(config_paths),
        "timestamp_utc": timestamp_utc(),
    }
    target = path or battle_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
        handle.flush()
    return payload


def battle_candidates(config_paths: Iterable[str | Path], configs: Iterable[ExperimentConfig]) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for config_path, config in zip(config_paths, configs, strict=True):
        payload = review_items(Path(config.output_path), experiment_id=config.experiment_id)
        for item in payload["items"]:
            if not item.get("is_renderable"):
                continue
            run_id = str(item.get("run_id") or "")
            if not run_id:
                continue
            candidates[run_id] = {
                **item,
                "config_path": Path(config_path).as_posix(),
                "family": family_for_seed(item.get("seed_id")),
            }
    return list(candidates.values())


def battle_summary(
    candidates: Iterable[dict[str, Any]],
    battles: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    items = {battle_item_id(item): item for item in candidates}
    ratings = _seed_ratings(items.values())
    battle_counts: dict[str, int] = defaultdict(int)
    wins: dict[str, int] = defaultdict(int)
    losses: dict[str, int] = defaultdict(int)
    ties: dict[str, int] = defaultdict(int)
    usable_battles = []

    for battle in battles if battles is not None else load_battles():
        left_id = battle.get("left_run_id")
        right_id = battle.get("right_run_id")
        if left_id not in items or right_id not in items:
            continue
        outcome = battle.get("outcome")
        if outcome not in {"left", "right", "tie"}:
            continue
        left_score = 0.5 if outcome == "tie" else (1.0 if outcome == "left" else 0.0)
        right_score = 1.0 - left_score
        ratings[left_id], ratings[right_id] = _elo_pair(ratings[left_id], ratings[right_id], left_score)
        battle_counts[left_id] += 1
        battle_counts[right_id] += 1
        if outcome == "tie":
            ties[left_id] += 1
            ties[right_id] += 1
        elif outcome == "left":
            wins[left_id] += 1
            losses[right_id] += 1
        else:
            wins[right_id] += 1
            losses[left_id] += 1
        usable_battles.append(battle)

    item_rows = [
        _ranking_item(
            item,
            rating=ratings[run_id],
            battle_count=battle_counts[run_id],
            wins=wins[run_id],
            losses=losses[run_id],
            ties=ties[run_id],
        )
        for run_id, item in items.items()
    ]
    item_rows.sort(key=lambda row: (-row["rating"], -row["battle_count"], row["label"]))
    return {
        "base_rating": BASE_RATING,
        "k_factor": K_FACTOR,
        "seeded_from_scores": True,
        "battle_count": len(usable_battles),
        "items": item_rows,
        "families": _aggregate_rows(item_rows, "family"),
        "prompts": _aggregate_rows(item_rows, "seed_id"),
    }


def _valid_battle(payload: dict[str, Any]) -> bool:
    return (
        isinstance(payload.get("left_run_id"), str)
        and isinstance(payload.get("right_run_id"), str)
        and payload.get("outcome") in {"left", "right", "tie"}
    )


def _seed_ratings(items: Iterable[dict[str, Any]]) -> dict[str, float]:
    ratings = {}
    for item in items:
        score = None
        review = item.get("review")
        if isinstance(review, dict) and isinstance(review.get("score"), int):
            score = review["score"]
        offset = ((score - 5.5) / 4.5 * SCORE_SEED_SPREAD) if score is not None else 0.0
        ratings[battle_item_id(item)] = BASE_RATING + offset
    return ratings


def _elo_pair(left_rating: float, right_rating: float, left_score: float) -> tuple[float, float]:
    expected_left = 1.0 / (1.0 + 10.0 ** ((right_rating - left_rating) / 400.0))
    expected_right = 1.0 - expected_left
    right_score = 1.0 - left_score
    return (
        left_rating + K_FACTOR * (left_score - expected_left),
        right_rating + K_FACTOR * (right_score - expected_right),
    )


def _ranking_item(
    item: dict[str, Any],
    *,
    rating: float,
    battle_count: int,
    wins: int,
    losses: int,
    ties: int,
) -> dict[str, Any]:
    review = item.get("review") if isinstance(item.get("review"), dict) else {}
    return {
        "run_id": item.get("run_id"),
        "rating": round(rating, 1),
        "battle_count": battle_count,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "seed_id": item.get("seed_id"),
        "family": item.get("family") or family_for_seed(item.get("seed_id")),
        "experiment_id": item.get("experiment_id"),
        "repetition": item.get("repetition"),
        "score": review.get("score"),
        "label": _item_label(item),
    }


def _aggregate_rows(item_rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in item_rows:
        groups[str(row.get(key) or "unknown")].append(row)
    rows = []
    for group_name, group in groups.items():
        score_values = [row["score"] for row in group if isinstance(row.get("score"), int)]
        rows.append(
            {
                key: group_name,
                "rating": round(sum(row["rating"] for row in group) / len(group), 1),
                "battle_count": sum(row["battle_count"] for row in group),
                "item_count": len(group),
                "average_score": round(sum(score_values) / len(score_values), 2) if score_values else None,
            }
        )
    rows.sort(key=lambda row: (-row["rating"], -row["battle_count"], row[key]))
    return rows


def _item_label(item: dict[str, Any]) -> str:
    seed_id = str(item.get("seed_id") or "prompt")
    experiment = str(item.get("experiment_id") or "run")
    repetition = item.get("repetition")
    rep_text = f", rep {int(repetition) + 1}" if isinstance(repetition, int) else ""
    return f"{seed_id} ({experiment}{rep_text})"
