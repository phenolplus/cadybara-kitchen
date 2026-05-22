from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from cadybara.config import config_hash, load_config


MAX_GITHUB_FILE_BYTES = 95 * 1024 * 1024


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def safe_slug(value: str) -> str:
    keep = []
    for char in value:
        keep.append(char if char.isalnum() or char in "._-" else "-")
    return "".join(keep).strip(".-") or "worker"


def tracked_source_is_clean() -> bool:
    result = run(["git", "status", "--porcelain", "--untracked-files=no"])
    return result.stdout.strip() == ""


def copy_if_exists(source: Path, destination: Path) -> list[Path]:
    copied: list[Path] = []
    if not source.exists():
        return copied
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
        copied.extend(path for path in destination.rglob("*") if path.is_file())
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(destination)
    return copied


def large_files(paths: list[Path]) -> list[Path]:
    return [path for path in paths if path.stat().st_size > MAX_GITHUB_FILE_BYTES]


def git_has_staged_changes() -> bool:
    result = run(["git", "diff", "--cached", "--quiet"], check=False)
    return result.returncode != 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy workspace findings into results/ and push a results-only branch.",
    )
    parser.add_argument("--config", default="configs/pilot_local.yaml")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch-prefix", default="results")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--allow-dirty-source", action="store_true")
    parser.add_argument("--allow-large-files", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path.cwd()
    config = load_config(args.config)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    machine = safe_slug(socket.gethostname())
    experiment = safe_slug(config.experiment_id)
    snapshot_name = f"{timestamp}_{machine}"
    result_root = repo_root / "results" / experiment / snapshot_name
    branch = f"{args.branch_prefix}/{experiment}/{machine}-{timestamp}"

    remote = run(["git", "remote", "get-url", args.remote]).stdout.strip()
    if not remote:
        raise SystemExit(f"Git remote {args.remote!r} is not configured.")

    if not args.allow_dirty_source and not tracked_source_is_clean():
        raise SystemExit(
            "Tracked source files are modified. Refusing to publish results from a dirty code tree. "
            "Commit/revert code first, or pass --allow-dirty-source."
        )

    run(["git", "switch", "-c", branch])

    copied: list[Path] = []
    output_path = Path(config.output_path)
    copied += copy_if_exists(output_path, result_root / "jsonl" / output_path.name)

    practice_path = output_path.with_name(f"{output_path.stem}.practice{output_path.suffix}")
    copied += copy_if_exists(practice_path, result_root / "jsonl" / practice_path.name)

    if config.artifact_root:
        copied += copy_if_exists(Path(config.artifact_root), result_root / "artifacts")

    review_file = Path("workspace") / "reviews" / f"{config.experiment_id}_reviews.jsonl"
    copied += copy_if_exists(review_file, result_root / "reviews" / review_file.name)

    manifest = {
        "experiment_id": config.experiment_id,
        "config_path": args.config,
        "config_hash": config_hash(config),
        "created_utc": timestamp,
        "machine": socket.gethostname(),
        "remote": remote,
        "output_path": config.output_path,
        "artifact_root": config.artifact_root,
        "copied_file_count": len(copied),
    }
    result_root.mkdir(parents=True, exist_ok=True)
    manifest_path = result_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    copied.append(manifest_path)

    oversized = large_files(copied)
    if oversized and not args.allow_large_files:
        names = "\n".join(str(path) for path in oversized)
        raise SystemExit(
            "Some files are too large for normal GitHub pushes. "
            "Use Git LFS/a release artifact, or rerun with --allow-large-files if you know what you are doing.\n"
            f"{names}"
        )

    run(["git", "add", result_root.as_posix()])
    if not git_has_staged_changes():
        raise SystemExit("No result files were staged; nothing to publish.")

    run(["git", "commit", "-m", f"Add results for {config.experiment_id} from {machine}"])
    if args.no_push:
        print(f"Created local results branch: {branch}")
        print("Push later with:")
        print(f"git push -u {args.remote} {branch}")
        return

    run(["git", "push", "-u", args.remote, branch])
    print(f"Pushed results branch: {branch}")


if __name__ == "__main__":
    main()
