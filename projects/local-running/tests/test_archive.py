from __future__ import annotations

import json
from pathlib import Path

from cadybara.archive import archive_run_dir


def test_archive_run_dir_copies_data_and_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "workspace" / "runs" / "demo_001"
    run_dir.mkdir(parents=True)
    (run_dir / "results.jsonl").write_text('{"ok":true}\n', encoding="utf-8")
    (run_dir / "artifacts").mkdir()
    (run_dir / "artifacts" / "model.py").write_text("result = None\n", encoding="utf-8")

    archive = archive_run_dir(
        run_dir,
        name="snapshot",
        archive_root=tmp_path / "workspace" / "archives",
    )

    copied = archive / "demo_001"
    assert (copied / "results.jsonl").read_text(encoding="utf-8") == '{"ok":true}\n'
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    paths = {row["path"] for row in manifest["files"]}
    assert "results.jsonl" in paths
    assert "artifacts/model.py" in paths
    assert (archive / "ollama_list.txt").exists()
