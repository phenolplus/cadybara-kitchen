from __future__ import annotations

import csv
from collections import defaultdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import typer

from cadybara.artifacts import sample_mounting_plate, write_part_scene
from cadybara.cadquery_runner import sample_wall_planter_code, write_cadquery_artifacts
from cadybara.lab_server import serve_lab
from cadybara.model_queue import (
    DEFAULT_MODEL_QUEUE_PATH,
    DEFAULT_MODEL_STATE_PATH,
    load_model_queue,
    model_status_rows,
    ollama_path,
    ollama_version,
    pull_model_queue,
)
from cadybara.runner import (
    ConfigMismatchError,
    MalformedJsonlError,
    append_record,
    read_jsonl_records,
    run_config_path,
    timestamp_utc,
)
from cadybara.records import RunRecord
from cadybara.training import export_training_pairs

app = typer.Typer(help="Run and inspect cadybara prompt-sensitivity experiments.")


@app.command()
def run(
    config_path: Path,
    limit: int | None = typer.Option(None, "--limit", min=1),
    retry_errors: bool = typer.Option(False, "--retry-errors"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    provider_retries: int = typer.Option(1, "--provider-retries", min=0),
    strict_jsonl: bool = typer.Option(False, "--strict-jsonl"),
    allow_config_mismatch: bool = typer.Option(False, "--allow-config-mismatch"),
) -> None:
    try:
        run_config_path(
            config_path,
            limit=limit,
            retry_errors=retry_errors,
            dry_run=dry_run,
            provider_retries=provider_retries,
            strict_jsonl=strict_jsonl,
            allow_config_mismatch=allow_config_mismatch,
        )
    except (ConfigMismatchError, MalformedJsonlError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def inspect(
    jsonl_path: Path,
    strict_jsonl: bool = typer.Option(False, "--strict-jsonl"),
) -> None:
    try:
        result = read_jsonl_records(jsonl_path, strict_jsonl=strict_jsonl)
    except MalformedJsonlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    by_model: dict[str, list] = defaultdict(list)
    triples: set[tuple[str, str, str]] = set()
    for record in result.records:
        by_model[record.model_name].append(record)
        triples.add((record.model_name, record.seed_id, record.variant_id))

    typer.echo(f"Total valid rows: {len(result.records)}")
    typer.echo(f"Malformed rows: {result.malformed_count}")
    typer.echo(f"Unique model/seed/variant triples: {len(triples)}")
    typer.echo("Per-model summary:")
    for model_name in sorted(by_model):
        rows = by_model[model_name]
        error_count = sum(1 for row in rows if row.error is not None)
        error_rate = error_count / len(rows) if rows else 0.0
        mean_latency = sum(row.latency_ms for row in rows) / len(rows) if rows else 0.0
        typer.echo(
            f"- {model_name}: rows={len(rows)} "
            f"error_rate={error_rate:.3f} mean_latency_ms={mean_latency:.1f}"
        )


@app.command("export-csv")
def export_csv(
    input_jsonl: Path,
    output_csv: Path,
    strict_jsonl: bool = typer.Option(False, "--strict-jsonl"),
) -> None:
    try:
        result = read_jsonl_records(input_jsonl, strict_jsonl=strict_jsonl)
    except MalformedJsonlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "run_id",
        "experiment_id",
        "timestamp_utc",
        "model_name",
        "provider",
        "seed_id",
        "prompt_level",
        "detail",
        "strategy",
        "variant_id",
        "temperature",
        "repetition",
        "attempt",
        "sampling_seed",
        "max_tokens",
        "output_mode",
        "is_product",
        "provider_error",
        "render_error",
        "latency_ms",
        "prompt_tokens",
        "completion_tokens",
        "total_duration_ms",
        "load_duration_ms",
        "prompt_eval_duration_ms",
        "eval_duration_ms",
        "cadquery_code_path",
        "stl_path",
        "step_path",
        "output_length",
        "condition_name",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in result.records:
            metadata = record.seed_metadata or record.variant_metadata or {}
            artifacts = record.artifacts or {}
            is_product = (
                record.error is None
                and record.render_error is None
                and bool(artifacts.get("stl"))
            )
            writer.writerow(
                {
                    "run_id": record.run_id,
                    "experiment_id": record.experiment_id,
                    "timestamp_utc": record.timestamp_utc,
                    "model_name": record.model_name,
                    "provider": record.provider,
                    "seed_id": record.seed_id,
                    "prompt_level": metadata.get("prompt_level"),
                    "detail": metadata.get("detail"),
                    "strategy": record.strategy,
                    "variant_id": record.variant_id,
                    "temperature": record.sampling.get("temperature"),
                    "repetition": record.repetition,
                    "attempt": record.attempt,
                    "sampling_seed": record.sampling.get("seed"),
                    "max_tokens": record.sampling.get("max_tokens"),
                    "output_mode": record.output_mode,
                    "is_product": is_product,
                    "provider_error": record.error or "",
                    "render_error": (
                        (record.render_error or "").splitlines()[0]
                        if (record.render_error or "").splitlines()
                        else ""
                    ),
                    "latency_ms": record.latency_ms,
                    "prompt_tokens": record.prompt_tokens,
                    "completion_tokens": record.completion_tokens,
                    "total_duration_ms": record.total_duration_ms,
                    "load_duration_ms": record.load_duration_ms,
                    "prompt_eval_duration_ms": record.prompt_eval_duration_ms,
                    "eval_duration_ms": record.eval_duration_ms,
                    "cadquery_code_path": artifacts.get("cadquery_code", ""),
                    "stl_path": artifacts.get("stl", ""),
                    "step_path": artifacts.get("step", ""),
                    "output_length": len(record.output),
                    "condition_name": record.condition_name,
                }
            )
    typer.echo(f"Wrote {len(result.records)} row(s) to {output_csv}")
    if result.malformed_count:
        typer.echo(f"Skipped malformed rows: {result.malformed_count}")


@app.command("sample-part")
def sample_part(
    output_path: Path = typer.Argument(Path("workspace/sample_part.json")),
) -> None:
    path = write_part_scene(sample_mounting_plate(), output_path)
    typer.echo(f"Wrote sample part artifact: {path}")


def next_available_dir(base_dir: Path) -> Path:
    if not base_dir.exists():
        return base_dir
    index = 2
    while base_dir.with_name(f"{base_dir.name}_{index:03d}").exists():
        index += 1
    return base_dir.with_name(f"{base_dir.name}_{index:03d}")


@app.command("cad-smoke")
def cad_smoke(
    output_dir: Path = typer.Argument(Path("workspace/runs/cad_smoke_001")),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port", min=1, max=65535),
) -> None:
    run_dir = next_available_dir(output_dir)
    jsonl_path = run_dir / "results.jsonl"
    artifact_root = run_dir / "artifacts"
    code = sample_wall_planter_code()
    record = RunRecord(
        run_id=str(uuid4()),
        experiment_id=run_dir.name,
        timestamp_utc=timestamp_utc(),
        model_name="cadquery-smoke-fixture",
        provider="local_fixture",
        seed_id="smoke_wall_planter",
        seed_text="Known-good wall planter fixture used to test CAD export and viewer plumbing.",
        strategy="fixture",
        variant_id="sample-wall-planter",
        variant_text="Known-good wall planter fixture used to test CAD export and viewer plumbing.",
        variant_metadata={"source": "cad-smoke"},
        prompt_sent="Local deterministic CadQuery smoke fixture.",
        output_mode="cadquery",
        condition_name="cadquery-smoke-fixture|smoke_wall_planter|fixture|t=0|r=0",
        sampling={"temperature": 0, "seed": 0, "max_tokens": 0},
        repetition=0,
        output=code,
        latency_ms=0,
        prompt_tokens=None,
        completion_tokens=None,
        finish_reason="fixture",
        total_duration_ms=0,
        load_duration_ms=0,
        prompt_eval_duration_ms=0,
        eval_duration_ms=0,
        provider_seed=None,
        scores={"output_length": float(len(code))},
        artifacts={},
        render_error=None,
        error=None,
        config_hash="cad-smoke-fixture",
    )
    artifacts, render_error = write_cadquery_artifacts(
        record=record,
        prompt_sent=record.prompt_sent or "",
        artifact_root=artifact_root,
    )
    record = record.model_copy(update={"artifacts": artifacts, "render_error": render_error})
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("a", encoding="utf-8") as handle:
        append_record(handle, record)
    stl_path = artifacts.get("stl")
    typer.echo(f"Wrote smoke JSONL: {jsonl_path}")
    typer.echo(f"Wrote smoke STL: {stl_path}")
    if render_error:
        typer.echo(f"Render failed: {render_error}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Open viewer: http://{host}:{port}/viewer/?stl=/{quote(str(stl_path).replace(chr(92), '/'))}")


@app.command()
def view(
    artifact_path: Path = typer.Argument(Path("workspace/sample_part.json")),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
) -> None:
    root = Path.cwd().resolve()
    artifact = artifact_path.resolve()
    if not artifact.exists():
        write_part_scene(sample_mounting_plate(), artifact)
    try:
        artifact_url_path = "/" + artifact.relative_to(root).as_posix()
    except ValueError as exc:
        raise typer.BadParameter(
            f"Artifact must be inside the current workspace: {root}"
        ) from exc

    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/viewer/?artifact={quote(artifact_url_path)}"
    typer.echo(f"Serving 3D viewer: {url}")
    typer.echo("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        typer.echo("Stopped viewer.")
    finally:
        server.server_close()


@app.command("export-training")
def export_training(
    input_jsonl: Path,
    output_jsonl: Path,
    include_errors: bool = typer.Option(False, "--include-errors"),
    strict_jsonl: bool = typer.Option(False, "--strict-jsonl"),
) -> None:
    try:
        written, skipped = export_training_pairs(
            input_jsonl,
            output_jsonl,
            include_errors=include_errors,
            strict_jsonl=strict_jsonl,
            stream=None,
        )
    except MalformedJsonlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Wrote {written} training row(s) to {output_jsonl}; skipped={skipped}")


@app.command("model-status")
def model_status(
    queue_path: Path = typer.Argument(DEFAULT_MODEL_QUEUE_PATH),
) -> None:
    config = load_model_queue(queue_path)
    typer.echo(f"Ollama: {ollama_version() or 'not found'}")
    typer.echo(f"Ollama path: {ollama_path() or 'missing'}")
    for row in model_status_rows(config, state_path=DEFAULT_MODEL_STATE_PATH):
        percent = row["percent"]
        percent_text = f" {percent}%" if percent is not None else ""
        typer.echo(
            f"{row['status']:<10} {row['name']:<24} "
            f"{row['family']:<16} {row['role']}{percent_text}"
        )


@app.command("pull-models")
def pull_models(
    queue_path: Path = typer.Argument(DEFAULT_MODEL_QUEUE_PATH),
    limit: int | None = typer.Option(None, "--limit", min=1),
    family: str | None = typer.Option(None, "--family"),
) -> None:
    config = load_model_queue(queue_path)
    summary = pull_model_queue(
        config,
        limit=limit,
        family=family,
        state_path=DEFAULT_MODEL_STATE_PATH,
        stream=None,
    )
    typer.echo(
        f"attempted={summary.attempted} installed={summary.installed} "
        f"skipped={summary.skipped} errors={summary.errors}"
    )


@app.command()
def lab(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port", min=1, max=65535),
) -> None:
    serve_lab(host=host, port=port)
