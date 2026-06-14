from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml


ROOT = Path(__file__).resolve().parents[2]
LOCAL_RUNNING = ROOT / "projects" / "local-running"
if str(LOCAL_RUNNING) not in sys.path:
    sys.path.insert(0, str(LOCAL_RUNNING))

from cadybara.cadquery_runner import write_cadquery_artifacts  # noqa: E402
from cadybara.records import RunRecord  # noqa: E402


DEFAULT_EXPERIMENT_ID = "codex_direct_wall_planter_v1"
MODEL_NAME = "codex-direct-chat"
PROVIDER = "manual_codex"


def timestamp_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_prompts(path: Path) -> list[dict]:
    prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(prompts, list):
        raise ValueError(f"{path} must contain a YAML list.")
    return prompts


def stable_hash(prompts: list[dict], code_dir: Path) -> str:
    payload = []
    for prompt in prompts:
        prompt_id = prompt["id"]
        code_path = code_dir / f"{prompt_id}.py"
        payload.append(
            {
                "id": prompt_id,
                "text": prompt["text"].strip(),
                "code": code_path.read_text(encoding="utf-8"),
            }
        )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def append_record(path: Path, record: RunRecord) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json())
        handle.write("\n")


def build_record(
    *,
    experiment_id: str,
    prompt: dict,
    code: str,
    code_path: Path,
    config_hash: str,
) -> RunRecord:
    prompt_id = prompt["id"]
    prompt_text = prompt["text"].strip()
    metadata = {key: value for key, value in prompt.items() if key not in {"id", "text"}}
    return RunRecord(
        run_id=str(uuid4()),
        experiment_id=experiment_id,
        timestamp_utc=timestamp_utc(),
        model_name=MODEL_NAME,
        provider=PROVIDER,
        seed_id=prompt_id,
        seed_text=prompt_text,
        seed_metadata=metadata,
        strategy="identity",
        variant_id="identity",
        variant_text=prompt_text,
        variant_metadata={},
        prompt_sent=prompt_text,
        output_mode="cadquery",
        condition_name=f"{MODEL_NAME}|{prompt_id}|identity|identity|t=0.0|r=0",
        attempt=1,
        sampling={"temperature": 0.0, "seed": None, "max_tokens": None},
        repetition=0,
        output=code,
        latency_ms=0,
        prompt_tokens=None,
        completion_tokens=None,
        finish_reason="manual_written",
        total_duration_ms=0,
        load_duration_ms=None,
        prompt_eval_duration_ms=None,
        eval_duration_ms=None,
        provider_seed=None,
        provider_metadata={
            "manual_protocol": "Codex wrote this CadQuery directly in the active chat thread.",
            "source_file": code_path.as_posix(),
        },
        scores={},
        artifacts={},
        render_error=None,
        error=None,
        config_hash=config_hash,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Package direct Codex CadQuery outputs as Cadybara records.")
    parser.add_argument("--append", action="store_true", help="Append to an existing manual baseline JSONL.")
    parser.add_argument(
        "--experiment-id",
        default=DEFAULT_EXPERIMENT_ID,
        help="Experiment id to write into JSONL records and default workspace path.",
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        default=None,
        help="Prompt YAML file. Defaults to prompts/wall_planter_prompts.yaml.",
    )
    parser.add_argument(
        "--code-dir",
        type=Path,
        default=None,
        help="Directory containing one <prompt_id>.py file per prompt. Defaults to manual_outputs/.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    experiment_dir = Path(__file__).resolve().parent
    code_dir = args.code_dir or experiment_dir / "manual_outputs"
    prompts_path = args.prompts or experiment_dir / "prompts" / "wall_planter_prompts.yaml"
    output_root = args.output_root or (
        ROOT / "projects" / "codex-direct-testing" / "workspace" / "runs" / args.experiment_id
    )
    output_path = output_root / "results.jsonl"
    artifact_root = output_root / "artifacts"

    if output_path.exists() and not args.append:
        raise SystemExit(f"{output_path} already exists; pass --append to add another manual run.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompts = read_prompts(prompts_path)
    config_hash = stable_hash(prompts, code_dir)

    executed = 0
    render_errors = 0
    for prompt in prompts:
        prompt_id = prompt["id"]
        code_path = code_dir / f"{prompt_id}.py"
        code = code_path.read_text(encoding="utf-8").strip() + "\n"
        record = build_record(
            experiment_id=args.experiment_id,
            prompt=prompt,
            code=code,
            code_path=code_path,
            config_hash=config_hash,
        )
        artifacts, render_error = write_cadquery_artifacts(
            record=record,
            prompt_sent=record.prompt_sent or record.seed_text,
            artifact_root=artifact_root,
        )
        record = record.model_copy(update={"artifacts": artifacts, "render_error": render_error})
        append_record(output_path, record)
        executed += 1
        if render_error:
            render_errors += 1
            status = "render failed"
        else:
            status = "STL ready"
        print(f"{prompt_id}: {status}")

    print(f"Summary: executed={executed} render_errors={render_errors} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
