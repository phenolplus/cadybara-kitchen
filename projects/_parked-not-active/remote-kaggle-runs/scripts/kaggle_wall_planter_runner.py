from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.request import urlopen


REPO_DIR = Path(os.environ.get("CADYBARA_REPO", Path.cwd())).resolve()
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))
PACKAGE_DIR = REPO_DIR / "projects" / "local-training"
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))
CONFIG_PATH = Path(
    os.environ.get(
        "CADYBARA_CONFIG",
        REPO_DIR / "projects/wall-planter-cad-study/configs/kaggle_heavy_vision_repair.yaml",
    )
)
OUTPUT_ROOT = Path(os.environ.get("CADYBARA_OUTPUT_ROOT", "/kaggle/working/cadybara_outputs"))
ZIP_PATH = Path(os.environ.get("CADYBARA_OUTPUT_ZIP", "/kaggle/working/cadybara_kaggle_outputs.zip"))


def run_command(command: list[str] | str, *, cwd: Path | None = None, check: bool = True) -> None:
    print(f"\n$ {command if isinstance(command, str) else ' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, shell=isinstance(command, str), check=check)


def running_on_kaggle() -> bool:
    return Path("/kaggle/working").exists()


def ensure_repo_root() -> None:
    if not (REPO_DIR / "pyproject.toml").exists():
        raise SystemExit(
            f"Expected cadybara repo at {REPO_DIR}. Upload/clone the repo, or set CADYBARA_REPO."
        )


def ensure_python_dependencies() -> None:
    run_command([sys.executable, "-m", "pip", "install", "-q", "-e", str(REPO_DIR)])


def ensure_ollama() -> None:
    if shutil.which("ollama"):
        return
    if not shutil.which("zstd"):
        run_command(["apt-get", "update"])
        run_command(["apt-get", "install", "-y", "zstd"])
    install_script = Path("/tmp/install_ollama.sh")
    print("ollama not found; downloading installer", flush=True)
    install_script.write_bytes(urlopen("https://ollama.com/install.sh", timeout=60).read())
    run_command(["bash", str(install_script)])


def start_ollama() -> subprocess.Popen | None:
    try:
        with urlopen("http://localhost:11434/api/tags", timeout=2) as response:
            if response.status == 200:
                print("ollama is already serving", flush=True)
                return None
    except Exception:
        pass

    log_path = OUTPUT_ROOT / "ollama_serve.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        ["ollama", "serve"],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        cwd=str(REPO_DIR),
    )
    for _ in range(60):
        try:
            with urlopen("http://localhost:11434/api/tags", timeout=2) as response:
                if response.status == 200:
                    print("ollama server is ready", flush=True)
                    return process
        except Exception:
            time.sleep(1)
    raise SystemExit(f"ollama did not become ready; inspect {log_path}")


def selected_model_names(all_names: list[str]) -> list[str]:
    raw = os.environ.get("KAGGLE_MODEL_NAMES", "").strip()
    if not raw and "heavy" in CONFIG_PATH.name and len(all_names) > 1:
        raise SystemExit(
            "Heavy Kaggle configs must be run one model at a time. "
            "Set KAGGLE_MODEL_NAMES, for example: qwen3-vl:32b"
        )
    if not raw:
        return all_names
    requested = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = sorted(set(requested) - set(all_names))
    if unknown:
        raise SystemExit(f"Unknown KAGGLE_MODEL_NAMES entries: {', '.join(unknown)}")
    return requested


def write_runtime_config() -> Path:
    import yaml

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    models = data["models"]
    keep = set(selected_model_names([model["name"] for model in models]))
    data["models"] = [model for model in models if model["name"] in keep]
    if not data["models"]:
        raise SystemExit("No models selected.")

    experiment_id = os.environ.get("KAGGLE_EXPERIMENT_ID", data["experiment_id"])
    data["experiment_id"] = experiment_id
    run_dir = OUTPUT_ROOT / experiment_id
    data["output_path"] = str(run_dir / "results.jsonl")
    data["artifact_root"] = str(run_dir / "artifacts")
    max_tokens = os.environ.get("KAGGLE_MAX_TOKENS", "").strip()
    if max_tokens:
        data.setdefault("sampling", {})["max_tokens"] = int(max_tokens)

    runtime_config = OUTPUT_ROOT / f"{experiment_id}.yaml"
    runtime_config.parent.mkdir(parents=True, exist_ok=True)
    with runtime_config.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)
    print(f"runtime config: {runtime_config}", flush=True)
    print("models: " + ", ".join(model["name"] for model in data["models"]), flush=True)
    return runtime_config


def pull_models(config_path: Path) -> None:
    from cadybara.config import load_config

    config = load_config(config_path)
    for model in config.models:
        print(f"\n=== pulling {model.name} ===", flush=True)
        run_command(["ollama", "pull", model.name], cwd=REPO_DIR)


def remove_selected_models(config_path: Path) -> None:
    if os.environ.get("KAGGLE_REMOVE_MODEL_AFTER", "0").strip() not in {"1", "true", "yes"}:
        return
    from cadybara.config import load_config

    config = load_config(config_path)
    for model in config.models:
        print(f"\n=== removing {model.name} after run ===", flush=True)
        run_command(["ollama", "rm", model.name], cwd=REPO_DIR, check=False)


def zip_outputs() -> None:
    if not OUTPUT_ROOT.exists():
        return
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in OUTPUT_ROOT.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(OUTPUT_ROOT.parent))
    print(f"checkpoint zip: {ZIP_PATH}", flush=True)


def run_sweep(config_path: Path) -> None:
    from cadybara.runner import run_config_path

    limit_raw = os.environ.get("KAGGLE_LIMIT", "").strip()
    limit = int(limit_raw) if limit_raw else None

    def checkpoint(_record) -> None:
        zip_outputs()

    summary = run_config_path(
        config_path,
        limit=limit,
        provider_retries=0,
        allow_config_mismatch=True,
        on_record=checkpoint,
    )
    print(f"summary: {summary}", flush=True)
    zip_outputs()


def main() -> None:
    ensure_repo_root()
    if running_on_kaggle():
        print("detected Kaggle runtime", flush=True)
    else:
        print("not running on Kaggle; this script is safe, but intended for Kaggle notebooks", flush=True)
    ensure_python_dependencies()
    ensure_ollama()
    process = start_ollama()
    try:
        runtime_config = write_runtime_config()
        pull_models(runtime_config)
        run_sweep(runtime_config)
    finally:
        zip_outputs()
        if "runtime_config" in locals():
            remove_selected_models(runtime_config)
        if process is not None:
            process.terminate()


if __name__ == "__main__":
    main()
