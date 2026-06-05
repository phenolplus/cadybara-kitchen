from __future__ import annotations

from cadybara.snapshot import SnapshotBuffer


def test_snapshot_buffer_tracks_tokens_and_truncates_lines() -> None:
    buffer = SnapshotBuffer(max_lines=3)
    buffer.start(
        model_name="qwen2.5-coder:3b",
        prompt_id="planter_01_minimal",
        prompt_text="Make a planter.",
        repetition=1,
    )
    buffer.append("line1\nline2\n")
    buffer.append("line3\nline4")
    snapshot = buffer.snapshot()
    assert snapshot["is_running"] is True
    assert snapshot["model_name"] == "qwen2.5-coder:3b"
    assert snapshot["tokens_so_far"] == 4
    assert snapshot["last_lines"] == ["line2", "line3", "line4"]
    buffer.finish()
    assert buffer.snapshot()["is_running"] is False
