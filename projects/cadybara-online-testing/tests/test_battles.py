from __future__ import annotations

import json
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

from cadybara.records import RunRecord
from cadybara.config import load_config
from cadybara_online_testing import battles, reviews
from cadybara_online_testing.lab_server import LabState, make_handler


def candidate(run_id: str, seed_id: str, score: int | None = None) -> dict:
    review = {"run_id": run_id, "score": score} if score is not None else None
    return {
        "run_id": run_id,
        "seed_id": seed_id,
        "experiment_id": "exp",
        "repetition": 0,
        "is_renderable": True,
        "review": review,
        "viewer_url": f"/viewer/?stl=/tmp/{run_id}.stl",
        "artifacts": {"stl": f"tmp/{run_id}.stl"},
        "family": battles.family_for_seed(seed_id),
    }


def make_record(
    *,
    experiment_id: str,
    run_id: str,
    seed_id: str,
    stl_path: str | None,
    error: str | None = None,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        experiment_id=experiment_id,
        timestamp_utc="2026-06-18T00:00:00Z",
        model_name="cadybara-agent-default",
        provider="cadybara_api",
        seed_id=seed_id,
        seed_text=f"Prompt {seed_id}",
        seed_metadata={},
        strategy="identity",
        variant_id="identity",
        variant_text=f"Prompt {seed_id}",
        variant_metadata={},
        prompt_sent=f"Prompt {seed_id}",
        output_mode="cadquery",
        condition_name=f"condition-{run_id}",
        attempt=1,
        sampling={"temperature": 0.0, "seed": 1, "max_tokens": 1},
        repetition=0,
        output='import cadquery as cq\nresult = cq.Workplane("XY").box(10, 10, 10)\n',
        latency_ms=100,
        prompt_tokens=None,
        completion_tokens=None,
        finish_reason="stop",
        total_duration_ms=100,
        load_duration_ms=0,
        prompt_eval_duration_ms=0,
        eval_duration_ms=0,
        provider_seed=None,
        scores={},
        artifacts={"stl": stl_path, "hosted_stl": stl_path} if stl_path else {},
        render_error=None,
        error=error,
        config_hash="hash",
    )


def write_jsonl(path: Path, rows: list[dict | RunRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = row.model_dump(mode="json") if isinstance(row, RunRecord) else row
            handle.write(json.dumps(payload) + "\n")


def get_json(url: str) -> dict:
    with urlopen(url, timeout=5) as response:  # noqa: S310 - local test server.
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> tuple[int, dict]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:  # noqa: S310 - local test server.
        return response.status, json.loads(response.read().decode("utf-8"))


def test_append_and_load_battles_ignores_malformed_rows(tmp_path: Path) -> None:
    path = tmp_path / "battles.jsonl"
    path.write_text("{bad json\n", encoding="utf-8")

    saved = battles.append_battle(path, left_run_id="left", right_run_id="right", outcome="left")

    assert saved["outcome"] == "left"
    assert battles.load_battles(path) == [saved]


def test_battle_summary_replays_wins_and_ties() -> None:
    candidates = [
        candidate("planter-a", "planter_01_minimal"),
        candidate("hook-a", "hook_01_minimal"),
    ]
    rows = [
        {"left_run_id": "planter-a", "right_run_id": "hook-a", "outcome": "left"},
        {"left_run_id": "planter-a", "right_run_id": "hook-a", "outcome": "tie"},
    ]

    summary = battles.battle_summary(candidates, rows)
    by_id = {row["run_id"]: row for row in summary["items"]}

    assert summary["battle_count"] == 2
    assert by_id["planter-a"]["rating"] > by_id["hook-a"]["rating"]
    assert by_id["planter-a"]["wins"] == 1
    assert by_id["planter-a"]["ties"] == 1
    assert summary["families"][0]["battle_count"] == 2


def test_old_scores_seed_starting_ratings() -> None:
    summary = battles.battle_summary(
        [
            candidate("low", "snowman_01_minimal", score=1),
            candidate("high", "hook_10_full", score=10),
        ],
        [],
    )
    by_id = {row["run_id"]: row for row in summary["items"]}

    assert by_id["high"]["rating"] > 1500
    assert by_id["low"]["rating"] < 1500
    assert by_id["high"]["rating"] > by_id["low"]["rating"]


def test_battle_candidates_only_include_viewable_rows(tmp_path: Path, monkeypatch) -> None:
    reviews_dir = tmp_path / "reviews"

    def fake_review_path(experiment_id: str) -> Path:
        return reviews_dir / f"{experiment_id}_reviews.jsonl"

    monkeypatch.setattr(reviews, "review_path", fake_review_path)
    config_path = tmp_path / "config.yaml"
    output_path = tmp_path / "results.jsonl"
    config_path.write_text(
        f"""
experiment_id: battle_fixture
output_path: "{output_path.as_posix()}"
models:
  - name: cadybara-agent-default
    provider: cadybara_api
    base_url: https://api.cadybara.com
seeds:
  - id: planter_01_minimal
    text: Prompt one
strategies:
  - name: identity
sampling:
  temperatures: [0.0]
  repetitions: 1
  max_tokens: 1
""".lstrip(),
        encoding="utf-8",
    )
    write_jsonl(
        output_path,
        [
            make_record(experiment_id="battle_fixture", run_id="viewable", seed_id="planter_01_minimal", stl_path="ok.stl"),
            make_record(
                experiment_id="battle_fixture",
                run_id="provider-error",
                seed_id="hook_01_minimal",
                stl_path=None,
                error="failed",
            ),
        ],
    )

    found = battles.battle_candidates([config_path], [load_config(config_path)])

    assert [item["run_id"] for item in found] == ["viewable"]
    assert found[0]["family"] == "planter"


def test_battle_endpoints_return_candidates_and_save_outcome(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    output_path = tmp_path / "results.jsonl"
    config_path.write_text(
        f"""
experiment_id: battle_endpoint
output_path: "{output_path.as_posix()}"
models:
  - name: cadybara-agent-default
    provider: cadybara_api
    base_url: https://api.cadybara.com
seeds:
  - id: planter_01_minimal
    text: Prompt one
  - id: hook_01_minimal
    text: Prompt two
strategies:
  - name: identity
sampling:
  temperatures: [0.0]
  repetitions: 1
  max_tokens: 1
""".lstrip(),
        encoding="utf-8",
    )
    write_jsonl(
        output_path,
        [
            make_record(experiment_id="battle_endpoint", run_id="left", seed_id="planter_01_minimal", stl_path="left.stl"),
            make_record(experiment_id="battle_endpoint", run_id="right", seed_id="hook_01_minimal", stl_path="right.stl"),
        ],
    )

    state = LabState(tmp_path)
    state.display_config = lambda path: load_config(path)  # type: ignore[method-assign]
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        payload = get_json(f"{base}/api/review/battles?config={config_path.as_posix()}")
        assert [item["run_id"] for item in payload["candidates"]] == ["left", "right"]
        assert payload["summary"]["battle_count"] == 0

        status, saved = post_json(
            f"{base}/api/review/battle",
            {
                "left_run_id": "left",
                "right_run_id": "right",
                "outcome": "right",
                "config_paths": [config_path.as_posix()],
            },
        )
        assert status == 200
        assert saved["saved"]["outcome"] == "right"
        assert saved["summary"]["battle_count"] == 1
    finally:
        server.shutdown()
        server.server_close()
