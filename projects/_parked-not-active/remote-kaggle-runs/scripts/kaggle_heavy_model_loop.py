from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path


OWNER = "aarohkandhare"
DATASET = "aarohkandhare/human-data"
SUBMIT_DIR = Path("projects/remote-kaggle-runs/workspace/kaggle_kernel_submit")
DOWNLOAD_ROOT = Path("projects/remote-kaggle-runs/workspace/kaggle_downloads/heavy_loop")
POLL_SECONDS = 300
LIMIT_ROWS = 1

MODELS = [
    "qwen3-vl:32b",
    "qwen3-vl:30b-a3b-instruct",
    "qwen2.5vl:32b",
    "gemma3:27b",
    "llava:34b",
    "llama3.2-vision:90b",
    "llama3.2-vision:11b",
]


def slug_for_model(model: str) -> str:
    slug = model.lower()
    slug = slug.replace("qwen2.5", "qwen25").replace("llama3.2", "llama32")
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"wall-planter-{slug}-vision-loop"


def experiment_for_model(model: str) -> str:
    return slug_for_model(model).replace("-", "_")


def run(command: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(command), flush=True)
    env = dict(**__import__("os").environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        command,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def write_submission(model: str) -> str:
    SUBMIT_DIR.mkdir(parents=True, exist_ok=True)
    slug = slug_for_model(model)
    experiment_id = experiment_for_model(model)
    provider_text = Path("projects/local-training/cadybara/providers/ollama.py").read_text(encoding="utf-8")
    runner_text = Path("projects/local-training/cadybara/runner.py").read_text(encoding="utf-8")
    kaggle_runner_text = Path("projects/remote-kaggle-runs/scripts/kaggle_wall_planter_runner.py").read_text(encoding="utf-8")
    config_text = Path("projects/wall-planter-cad-study/configs/kaggle_heavy_vision_repair.yaml").read_text(encoding="utf-8")
    use_chat = "1"
    is_qwen3 = model.startswith("qwen3-vl:")
    num_ctx = "8192" if is_qwen3 else "1024" if model == "llama3.2-vision:90b" else "4096"
    max_tokens = "4096" if is_qwen3 else "512" if model == "llama3.2-vision:90b" else "4096"
    prompt_prefix = ""
    prompt_suffix = "\\n/no_think\\n" if is_qwen3 else ""

    script = f"""import os
import subprocess
import sys
from pathlib import Path

repo_src = Path('/kaggle/input/datasets/aarohkandhare/human-data')
repo_dst = Path('/tmp/cadybara')

print('repo input:', repo_src, flush=True)
print('repo exists:', repo_src.exists(), flush=True)
if not repo_src.exists():
    raise SystemExit('Repo dataset not found. Attach aarohkandhare/human-data as an input dataset.')

subprocess.run(['rm', '-rf', str(repo_dst)], check=True)
subprocess.run(['cp', '-R', str(repo_src), str(repo_dst)], check=True)
os.chdir(repo_dst)
os.environ['CADYBARA_REPO'] = str(repo_dst)
os.environ['PYTHONPATH'] = str(repo_dst) + os.pathsep + os.environ.get('PYTHONPATH', '')
print('cwd:', Path.cwd(), flush=True)
print('runner exists:', Path('projects/remote-kaggle-runs/scripts/kaggle_wall_planter_runner.py').exists(), flush=True)


def patch_repo_for_kaggle(repo: Path) -> None:
    provider_path = repo / 'projects' / 'local-training' / 'cadybara' / 'providers' / 'ollama.py'
    provider_path.write_text({json.dumps(provider_text)}, encoding='utf-8')

    runner_path = repo / 'projects' / 'local-training' / 'cadybara' / 'runner.py'
    runner_path.write_text({json.dumps(runner_text)}, encoding='utf-8')

    kaggle_runner_path = repo / 'projects' / 'remote-kaggle-runs' / 'scripts' / 'kaggle_wall_planter_runner.py'
    kaggle_runner_path.write_text({json.dumps(kaggle_runner_text)}, encoding='utf-8')

    config_path = repo / 'projects' / 'wall-planter-cad-study' / 'configs' / 'kaggle_heavy_vision_repair.yaml'
    config_path.write_text({json.dumps(config_text)}, encoding='utf-8')

    cad_path = repo / 'projects' / 'local-training' / 'cadybara' / 'cadquery_runner.py'
    cad_text = cad_path.read_text(encoding='utf-8')
    if 'Do not think out loud, include reasoning, narrate, or wrap the answer in Markdown.' not in cad_text:
        cad_text = cad_text.replace(
            'Return only Python CadQuery code. Do not explain the design in prose.\\n',
            'Return only Python CadQuery code. Do not explain the design in prose.\\n'
            'Do not think out loud, include reasoning, narrate, or wrap the answer in Markdown.\\n',
        )
    cad_path.write_text(cad_text, encoding='utf-8')


patch_repo_for_kaggle(repo_dst)

if subprocess.run(['bash', '-lc', 'command -v zstd'], check=False).returncode != 0:
    subprocess.run(['apt-get', 'update'], check=True)
    subprocess.run(['apt-get', 'install', '-y', 'zstd'], check=True)

os.environ['KAGGLE_MODEL_NAMES'] = '{model}'
os.environ['KAGGLE_EXPERIMENT_ID'] = '{experiment_id}'
os.environ['KAGGLE_LIMIT'] = '{LIMIT_ROWS}'
os.environ['KAGGLE_REMOVE_MODEL_AFTER'] = '1'
os.environ['CADYBARA_OLLAMA_USE_CHAT'] = '{use_chat}'
os.environ['CADYBARA_OLLAMA_NUM_CTX'] = '{num_ctx}'
os.environ['CADYBARA_SKIP_CAD_ARTIFACTS'] = '1'
os.environ['CADYBARA_OLLAMA_PROMPT_PREFIX'] = '{prompt_prefix}'
os.environ['CADYBARA_OLLAMA_PROMPT_SUFFIX'] = '{prompt_suffix}'
os.environ['KAGGLE_MAX_TOKENS'] = '{max_tokens}'

print('model:', os.environ['KAGGLE_MODEL_NAMES'], flush=True)
print('experiment:', os.environ['KAGGLE_EXPERIMENT_ID'], flush=True)
print('limit:', os.environ['KAGGLE_LIMIT'], flush=True)
print('use_chat:', os.environ['CADYBARA_OLLAMA_USE_CHAT'], flush=True)
print('num_ctx:', os.environ['CADYBARA_OLLAMA_NUM_CTX'], flush=True)
print('max_tokens:', os.environ['KAGGLE_MAX_TOKENS'], flush=True)
print('prompt_prefix:', repr(os.environ['CADYBARA_OLLAMA_PROMPT_PREFIX']), flush=True)
print('prompt_suffix:', repr(os.environ['CADYBARA_OLLAMA_PROMPT_SUFFIX']), flush=True)
subprocess.run([sys.executable, 'projects/remote-kaggle-runs/scripts/kaggle_wall_planter_runner.py'], check=True)
"""
    (SUBMIT_DIR / "wall_planter_kaggle_heavy.py").write_text(script, encoding="utf-8")

    metadata = {
        "id": f"{OWNER}/{slug}",
        "title": slug.replace("-", " "),
        "code_file": "wall_planter_kaggle_heavy.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": "true",
        "enable_gpu": "true",
        "enable_tpu": "false",
        "enable_internet": "true",
        "dataset_sources": [DATASET],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (SUBMIT_DIR / "kernel-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    return f"{OWNER}/{slug}"


def status_for_kernel(kernel: str) -> str:
    completed = run(["kaggle", "kernels", "status", kernel], timeout=120)
    print(completed.stdout, end="", flush=True)
    match = re.search(r'has status "([^"]+)"', completed.stdout)
    return match.group(1) if match else completed.stdout.strip()


def wait_for_kernel(kernel: str) -> str:
    while True:
        time.sleep(POLL_SECONDS)
        status = status_for_kernel(kernel)
        upper = status.upper()
        if any(done in upper for done in ("COMPLETE", "ERROR", "CANCEL")):
            return status


def download_outputs(kernel: str, model: str) -> Path:
    out_dir = DOWNLOAD_ROOT / slug_for_model(model)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        completed = run(
            [
                "kaggle",
                "kernels",
                "output",
                kernel,
                "-p",
                str(out_dir),
                "-o",
                "--file-pattern",
                ".*(results\\.jsonl|cadybara_kaggle_outputs\\.zip|ollama_serve\\.log).*",
            ],
            timeout=600,
        )
        print(completed.stdout, end="", flush=True)
    except subprocess.CalledProcessError as exc:
        print(exc.stdout or "", end="", flush=True)
        if find_results(out_dir) is None:
            raise
        print("kaggle output returned nonzero, but results.jsonl was downloaded; continuing.", flush=True)
    return out_dir


def find_results(download_dir: Path) -> Path | None:
    matches = sorted(download_dir.rglob("results.jsonl"))
    return matches[0] if matches else None


def validate_results(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {"ok": False, "reason": "missing results.jsonl"}
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    nonempty = sum(1 for row in rows if str(row.get("output", "")).strip())
    stl_ready = sum(1 for row in rows if (row.get("artifacts") or {}).get("stl"))
    errors = sum(1 for row in rows if row.get("error"))
    render_errors = sum(1 for row in rows if row.get("render_error"))
    return {
        "ok": nonempty > 0,
        "rows": len(rows),
        "nonempty": nonempty,
        "stl_ready": stl_ready,
        "errors": errors,
        "render_errors": render_errors,
        "path": str(path),
    }


def write_summary(summary: list[dict]) -> None:
    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    (DOWNLOAD_ROOT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )


def already_attempted(model: str, summary: Iterable[dict]) -> bool:
    return any(item.get("model") == model for item in summary)


def load_summary() -> list[dict]:
    path = DOWNLOAD_ROOT / "summary.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        return [data]
    return data


def main() -> None:
    summary = load_summary()
    for model in MODELS:
        if already_attempted(model, summary):
            print(f"SKIP already attempted: {model}", flush=True)
            continue

        kernel = write_submission(model)
        print(f"=== launching {model} as {kernel} ===", flush=True)
        push = run(["kaggle", "kernels", "push", "-p", str(SUBMIT_DIR), "--accelerator", "NvidiaTeslaT4"], timeout=180)
        print(push.stdout, end="", flush=True)
        status = wait_for_kernel(kernel)
        print(f"terminal status for {model}: {status}", flush=True)
        out_dir = download_outputs(kernel, model)
        validation = validate_results(find_results(out_dir))
        print(f"validation for {model}: {validation}", flush=True)
        item = {
            "model": model,
            "kernel": kernel,
            "status": status,
            "validation": validation,
            "download_dir": str(out_dir),
            "checked_at_epoch": time.time(),
        }
        summary = [row for row in summary if row.get("model") != model]
        summary.append(item)
        write_summary(summary)

        if not validation.get("ok"):
            print(f"No non-empty output for {model}; continuing to next model and leaving this recorded.", flush=True)

    print("=== heavy loop complete ===", flush=True)
    write_summary(summary)


if __name__ == "__main__":
    main()
