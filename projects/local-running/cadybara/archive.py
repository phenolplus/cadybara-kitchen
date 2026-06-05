from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while path.with_name(f"{path.name}_{index:03d}").exists():
        index += 1
    return path.with_name(f"{path.name}_{index:03d}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_manifest(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return rows


def ollama_list_text() -> str:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ollama list unavailable: {exc}\n"
    return (result.stdout or result.stderr or "").strip() + "\n"


def archive_run_dir(
    run_dir: Path,
    *,
    name: str,
    archive_root: Path = Path("projects/_parked-not-active/sandbox-archive/workspace/archives"),
) -> Path:
    source = run_dir.resolve()
    if not source.exists() or not source.is_dir():
        raise ValueError(f"Run directory does not exist: {run_dir}")

    destination = next_available_path(archive_root / name)
    destination.mkdir(parents=True, exist_ok=False)
    copied_run = destination / source.name
    shutil.copytree(source, copied_run)

    manifest = {
        "archive_name": destination.name,
        "created_at_utc": now_utc(),
        "source_run_dir": str(source),
        "copied_run_dir": str(copied_run),
        "files": tree_manifest(copied_run),
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "ollama_list.txt").write_text(ollama_list_text(), encoding="utf-8")
    return destination
