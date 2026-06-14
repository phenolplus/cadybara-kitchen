from __future__ import annotations

from collections import defaultdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import quote
from uuid import uuid4

import typer

from cadybara.archive import archive_run_dir
from cadybara.artifacts import sample_mounting_plate, write_part_scene
from cadybara.cadquery_runner import sample_wall_planter_code, write_cadquery_artifacts
from cadybara_cad_diffusion import (
    eval_cad_diffusion_run,
    eval_voxel_diffusion_run,
    latest_checkpoint,
    latest_voxel_checkpoint,
    prepare_fusion360_dataset,
    prepare_voxel_dataset,
    sample_diffusion_model,
    sample_voxel_diffusion_model,
    train_diffusion_model,
    train_voxel_diffusion_model,
)
from cadybara.csv_export import export_attempts_csv
from cadybara.config import load_config
from cadybara.model_queue import (
    DEFAULT_MODEL_QUEUE_PATH,
    DEFAULT_MODEL_STATE_PATH,
    load_model_queue,
    load_model_queue_or_experiment,
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
from cadybara_online_testing.grading import grade_run_dir
from cadybara_online_testing.lab_server import missing_ollama_models, serve_lab

app = typer.Typer(help="Run and inspect cadybara prompt-sensitivity experiments.")
cad_diffusion_app = typer.Typer(
    help="Prepare, train, sample, and evaluate CAD-native diffusion pilots."
)
voxel_diffusion_app = typer.Typer(
    help="Prepare, train, sample, and evaluate geometry-native voxel diffusion pilots."
)
app.add_typer(cad_diffusion_app, name="cad-diffusion")
app.add_typer(voxel_diffusion_app, name="voxel-diffusion")


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
        if not dry_run:
            missing = missing_ollama_models(load_config(config_path), limit=limit)
            if missing:
                typer.echo(
                    "Error: missing Ollama models: "
                    + ", ".join(missing)
                    + ". Pull them first with `cadybara pull-models` or `ollama pull <model>`.",
                    err=True,
                )
                raise typer.Exit(code=1)
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
        rows, malformed = export_attempts_csv(
            input_jsonl,
            output_csv,
            strict_jsonl=strict_jsonl,
        )
    except MalformedJsonlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Wrote {rows} row(s) to {output_csv}")
    if malformed:
        typer.echo(f"Skipped malformed rows: {malformed}")


@app.command("sample-part")
def sample_part(
    output_path: Path = typer.Argument(Path("projects/local-running/workspace/examples/sample_part.json")),
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
    output_dir: Path = typer.Argument(Path("projects/local-running/workspace/runs/cad_smoke_001")),
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
    artifact_path: Path = typer.Argument(Path("projects/local-running/workspace/examples/sample_part.json")),
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


@app.command()
def grade(
    run_dir: Path,
    resume: bool = typer.Option(True, "--resume/--no-resume"),
    model: str | None = typer.Option(None, "--model"),
    prompt: str | None = typer.Option(None, "--prompt"),
    repair_round: str = typer.Option("final", "--round", help="Repair round to grade: final, all, or a round number."),
    grader: str = typer.Option("aaroh", "--grader"),
) -> None:
    written, skipped, quit_requested = grade_run_dir(
        run_dir,
        resume=resume,
        model_filter=model,
        prompt_filter=prompt,
        round_filter=repair_round,
        grader=grader,
    )
    status = "quit requested" if quit_requested else "complete"
    typer.echo(f"Grading {status}: wrote={written} skipped={skipped}")


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
    config = load_model_queue_or_experiment(queue_path)
    summary = pull_model_queue(
        config,
        limit=limit,
        family=family,
        state_path=DEFAULT_MODEL_STATE_PATH,
        stream=sys.stdout,
    )
    typer.echo(
        f"attempted={summary.attempted} installed={summary.installed} "
        f"skipped={summary.skipped} errors={summary.errors}"
    )


@app.command()
def archive(
    run_dir: Path,
    name: str = typer.Option(..., "--name"),
) -> None:
    try:
        destination = archive_run_dir(run_dir, name=name)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Archived {run_dir} to {destination}")


@cad_diffusion_app.command("prepare")
def cad_diffusion_prepare(
    dataset_dir: Path = typer.Argument(Path("projects/cad-diffusion/workspace/datasets/fusion360_gallery")),
    output_dir: Path = typer.Option(
        Path("projects/cad-diffusion/workspace/datasets/fusion360_tokens"),
        "--output-dir",
    ),
    max_examples: int | None = typer.Option(None, "--max-examples", min=1),
    max_len: int = typer.Option(256, "--max-len", min=32),
) -> None:
    try:
        manifest = prepare_fusion360_dataset(
            dataset_dir,
            output_dir,
            max_examples=max_examples,
            max_len=max_len,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Scanned JSON files: {manifest.scanned_json}")
    typer.echo(f"Wrote supported examples: {manifest.written}")
    typer.echo(f"Unsupported examples: {manifest.unsupported}")
    typer.echo(f"Prepared dataset: {output_dir / 'manifest.json'}")


@cad_diffusion_app.command("train")
def cad_diffusion_train(
    data_dir: Path = typer.Argument(Path("projects/cad-diffusion/workspace/datasets/fusion360_tokens")),
    output_dir: Path = typer.Option(
        Path("projects/cad-diffusion/workspace/models/cad_diffusion_noise_to_cad"),
        "--output-dir",
    ),
    max_steps: int = typer.Option(1000, "--max-steps", min=1),
    batch_size: int = typer.Option(16, "--batch-size", min=1),
    max_len: int = typer.Option(256, "--max-len", min=32),
    d_model: int = typer.Option(128, "--d-model", min=32),
    layers: int = typer.Option(2, "--layers", min=1),
    heads: int = typer.Option(4, "--heads", min=1),
    learning_rate: float = typer.Option(3e-4, "--learning-rate", min=1e-6),
    checkpoint_interval: int = typer.Option(100, "--checkpoint-interval", min=1),
    time_limit_minutes: float = typer.Option(480.0, "--time-limit-minutes", min=0.1),
    seed: int = typer.Option(0, "--seed"),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
) -> None:
    try:
        summary = train_diffusion_model(
            data_dir,
            output_dir,
            max_steps=max_steps,
            batch_size=batch_size,
            max_len=max_len,
            d_model=d_model,
            layers=layers,
            heads=heads,
            learning_rate=learning_rate,
            checkpoint_interval=checkpoint_interval,
            time_limit_minutes=time_limit_minutes,
            seed=seed,
            resume=resume,
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"trained_steps={summary.steps} examples={summary.examples} "
        f"device={summary.device} elapsed_seconds={summary.elapsed_seconds:.1f}"
    )
    typer.echo(f"checkpoint={summary.checkpoint_path}")


@cad_diffusion_app.command("sample")
def cad_diffusion_sample(
    checkpoint_path: Path | None = typer.Argument(None),
    run_dir: Path = typer.Option(
        Path("projects/cad-diffusion/workspace/runs/cad_diffusion_noise_to_cad_001"),
        "--run-dir",
    ),
    model_dir: Path = typer.Option(
        Path("projects/cad-diffusion/workspace/models/cad_diffusion_noise_to_cad"),
        "--model-dir",
    ),
    data_dir: Path = typer.Option(
        Path("projects/cad-diffusion/workspace/datasets/fusion360_tokens"),
        "--data-dir",
    ),
    count: int = typer.Option(100, "--count", min=1),
    denoise_steps: int = typer.Option(16, "--denoise-steps", min=1),
    temperature: float = typer.Option(1.0, "--temperature", min=0.01),
    seed: int = typer.Option(0, "--seed"),
) -> None:
    resolved_checkpoint = checkpoint_path or latest_checkpoint(model_dir)
    if resolved_checkpoint is None:
        typer.echo(f"Error: no checkpoint found in {model_dir}", err=True)
        raise typer.Exit(code=1)
    try:
        records = sample_diffusion_model(
            resolved_checkpoint,
            run_dir,
            count=count,
            denoise_steps=denoise_steps,
            temperature=temperature,
            seed=seed,
            data_dir=data_dir,
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    renderable = sum(
        1
        for record in records
        if record.parse_error is None
        and record.compile_error is None
        and record.render_error is None
        and record.artifacts.get("stl")
    )
    typer.echo(f"sampled={len(records)} renderable={renderable} run_dir={run_dir}")


@cad_diffusion_app.command("eval")
def cad_diffusion_eval(
    run_dir: Path = typer.Argument(Path("projects/cad-diffusion/workspace/runs/cad_diffusion_noise_to_cad_001")),
) -> None:
    try:
        summary = eval_cad_diffusion_run(run_dir)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"total={summary.total}")
    typer.echo(f"parse_valid={summary.parse_valid}")
    typer.echo(f"compiled={summary.compiled}")
    typer.echo(f"renderable={summary.renderable}")
    typer.echo(f"unique_token_sequences={summary.unique_token_sequences}")
    typer.echo(f"unique_programs={summary.unique_programs}")
    typer.echo(f"mean_nearest_neighbor_distance={summary.mean_nearest_neighbor_distance}")


@voxel_diffusion_app.command("prepare")
def voxel_diffusion_prepare(
    source_dir: Path = typer.Argument(
        Path("projects/cad-diffusion/workspace/datasets/fusion360_gallery/r1.0.1/reconstruction")
    ),
    output_dir: Path = typer.Option(
        Path("projects/cad-diffusion/workspace/datasets/fusion360_voxels_64"),
        "--output-dir",
    ),
    resolution: int = typer.Option(64, "--resolution", min=8),
    max_examples: int | None = typer.Option(None, "--max-examples", min=1),
) -> None:
    try:
        manifest = prepare_voxel_dataset(
            source_dir,
            output_dir,
            resolution=resolution,
            max_examples=max_examples,
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Scanned OBJ files: {manifest.scanned_obj}")
    typer.echo(f"Wrote voxel examples: {manifest.written}")
    typer.echo(f"Failed examples: {manifest.failed}")
    typer.echo(f"Prepared dataset: {output_dir / 'manifest.json'}")


@voxel_diffusion_app.command("train")
def voxel_diffusion_train(
    data_dir: Path = typer.Argument(Path("projects/cad-diffusion/workspace/datasets/fusion360_voxels_64")),
    output_dir: Path = typer.Option(
        Path("projects/cad-diffusion/workspace/models/voxel_diffusion_64_20260608"),
        "--output-dir",
    ),
    resolution: int = typer.Option(64, "--resolution", min=8),
    max_steps: int = typer.Option(1000, "--max-steps", min=1),
    batch_size: int = typer.Option(1, "--batch-size", min=1),
    base_channels: int = typer.Option(16, "--base-channels", min=4),
    timesteps: int = typer.Option(1000, "--timesteps", min=10),
    learning_rate: float = typer.Option(2e-4, "--learning-rate", min=1e-6),
    checkpoint_interval: int = typer.Option(100, "--checkpoint-interval", min=1),
    time_limit_minutes: float = typer.Option(480.0, "--time-limit-minutes", min=0.1),
    seed: int = typer.Option(20260608, "--seed"),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
) -> None:
    try:
        summary = train_voxel_diffusion_model(
            data_dir,
            output_dir,
            resolution=resolution,
            max_steps=max_steps,
            batch_size=batch_size,
            base_channels=base_channels,
            timesteps=timesteps,
            learning_rate=learning_rate,
            checkpoint_interval=checkpoint_interval,
            time_limit_minutes=time_limit_minutes,
            seed=seed,
            resume=resume,
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"trained_steps={summary.steps} examples={summary.examples} "
        f"device={summary.device} elapsed_seconds={summary.elapsed_seconds:.1f}"
    )
    typer.echo(f"checkpoint={summary.checkpoint_path}")


@voxel_diffusion_app.command("sample")
def voxel_diffusion_sample(
    checkpoint_path: Path | None = typer.Argument(None),
    run_dir: Path = typer.Option(
        Path("projects/cad-diffusion/workspace/runs/voxel_diffusion_64_sample_001"),
        "--run-dir",
    ),
    model_dir: Path = typer.Option(
        Path("projects/cad-diffusion/workspace/models/voxel_diffusion_64_20260608"),
        "--model-dir",
    ),
    data_dir: Path = typer.Option(
        Path("projects/cad-diffusion/workspace/datasets/fusion360_voxels_64"),
        "--data-dir",
    ),
    count: int = typer.Option(10, "--count", min=1),
    sample_steps: int = typer.Option(50, "--sample-steps", min=1),
    threshold: float = typer.Option(0.5, "--threshold", min=0.0, max=1.0),
    seed: int = typer.Option(20260608, "--seed"),
) -> None:
    resolved_checkpoint = checkpoint_path or latest_voxel_checkpoint(model_dir)
    if resolved_checkpoint is None:
        typer.echo(f"Error: no checkpoint found in {model_dir}", err=True)
        raise typer.Exit(code=1)
    try:
        records = sample_voxel_diffusion_model(
            resolved_checkpoint,
            run_dir,
            count=count,
            sample_steps=sample_steps,
            threshold=threshold,
            seed=seed,
            data_dir=data_dir,
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    renderable = sum(1 for record in records if record.artifacts.get("stl") and record.export_error is None)
    typer.echo(f"sampled={len(records)} renderable={renderable} run_dir={run_dir}")


@voxel_diffusion_app.command("eval")
def voxel_diffusion_eval(
    run_dir: Path = typer.Argument(Path("projects/cad-diffusion/workspace/runs/voxel_diffusion_64_sample_001")),
) -> None:
    try:
        summary = eval_voxel_diffusion_run(run_dir)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"total={summary.total}")
    typer.echo(f"renderable={summary.renderable}")
    typer.echo(f"nonempty={summary.nonempty}")
    typer.echo(f"mean_occupancy_ratio={summary.mean_occupancy_ratio}")
    typer.echo(f"mean_largest_component_ratio={summary.mean_largest_component_ratio}")
    typer.echo(f"mean_novelty_iou_nearest={summary.mean_novelty_iou_nearest}")


@app.command()
def lab(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port", min=1, max=65535),
) -> None:
    serve_lab(host=host, port=port)
