from __future__ import annotations

from collections import defaultdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import typer

from cadybara.artifacts import sample_mounting_plate, write_part_scene
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
    read_jsonl_records,
    run_config_path,
)
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


@app.command("sample-part")
def sample_part(
    output_path: Path = typer.Argument(Path("workspace/sample_part.json")),
) -> None:
    path = write_part_scene(sample_mounting_plate(), output_path)
    typer.echo(f"Wrote sample part artifact: {path}")


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
