from __future__ import annotations

import hashlib
import os
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO
from uuid import uuid4

from pydantic import ValidationError

from cadybara.cadquery_runner import cadquery_prompt, write_cadquery_artifacts
from cadybara.config import ExperimentConfig, ModelConfig, config_hash, load_config
from cadybara.providers.base import GenerationStopped, ModelProvider, ProviderResponse
from cadybara.providers.cadybara_api import CadybaraApiProvider
from cadybara.providers.dry_run import DryRunProvider
from cadybara.providers.ollama import OllamaProvider
from cadybara.records import RunRecord, resume_key
from cadybara.scoring.base import Scorer
from cadybara.scoring.stub import StubScorer
from cadybara.snapshot import SnapshotBuffer
from cadybara.strategies.base import Strategy, Variant
from cadybara.strategies.identity import IdentityStrategy


@dataclass(frozen=True)
class RunCell:
    model: ModelConfig
    seed_id: str
    seed_text: str
    seed_metadata: dict
    strategy: Strategy
    variant: Variant
    temperature: float
    repetition: int


@dataclass
class JsonlReadResult:
    records: list[RunRecord]
    malformed_count: int


@dataclass
class RunSummary:
    total_cells: int
    executed: int
    skipped: int
    errors: int
    malformed_rows: int
    output_path: Path
    stopped: bool = False


class MalformedJsonlError(ValueError):
    pass


class ConfigMismatchError(ValueError):
    pass


def read_jsonl_records(path: Path, *, strict_jsonl: bool = False) -> JsonlReadResult:
    records: list[RunRecord] = []
    malformed_count = 0
    if not path.exists():
        return JsonlReadResult(records=records, malformed_count=malformed_count)

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(RunRecord.model_validate_json(line))
            except (ValueError, ValidationError) as exc:
                if strict_jsonl:
                    raise MalformedJsonlError(
                        f"{path}:{line_number} is not a valid RunRecord: {exc}"
                    ) from exc
                malformed_count += 1
    return JsonlReadResult(records=records, malformed_count=malformed_count)


def build_cells(config: ExperimentConfig) -> list[RunCell]:
    cells: list[RunCell] = []
    for model in config.models:
        for seed in config.seeds:
            for strategy_config in config.strategies:
                strategy = strategy_from_name(strategy_config.name)
                variants = strategy.variants(seed.id, seed.text, seed.metadata)
                for variant in variants:
                    for temperature in config.sampling.temperatures:
                        for repetition in range(config.sampling.repetitions):
                            cells.append(
                                RunCell(
                                    model=model,
                                    seed_id=seed.id,
                                    seed_text=seed.text,
                                    seed_metadata=seed.metadata,
                                    strategy=strategy,
                                    variant=variant,
                                    temperature=temperature,
                                    repetition=repetition,
                                )
                            )
    return cells


def strategy_from_name(name: str) -> Strategy:
    if name == "identity":
        return IdentityStrategy()
    raise ValueError(f"Unsupported strategy: {name}")


def provider_for_model(model: ModelConfig, *, dry_run: bool) -> tuple[str, ModelProvider]:
    if dry_run:
        return "dry_run", DryRunProvider()
    if model.provider == "ollama":
        return (
            model.provider,
            OllamaProvider(
                model_name=model.name,
                base_url=model.base_url,
                timeout=model.timeout_seconds,
                num_thread=model.num_thread,
            ),
        )
    if model.provider == "cadybara_api":
        return (
            model.provider,
            CadybaraApiProvider(
                model_name=model.name,
                base_url=model.base_url,
                timeout=model.timeout_seconds,
                api_key_env=model.api_key_env,
                hosted_model_id=model.hosted_model_id,
                response_mode=model.response_mode,
                export_format=model.export_format,
                linear_deflection=model.linear_deflection,
                angular_deflection=model.angular_deflection,
                unwrap_prompt=model.unwrap_cadquery_prompt,
            ),
        )
    raise ValueError(f"Unsupported provider: {model.provider}")


def cell_key(
    experiment_id: str,
    cell: RunCell,
) -> tuple[str, str, str, str, float, int]:
    return (
        experiment_id,
        cell.model.name,
        cell.seed_id,
        cell.variant.variant_id,
        float(cell.temperature),
        cell.repetition,
    )


def sampling_seed(key: tuple[str, str, str, str, float, int]) -> int:
    payload = "|".join(str(part) for part in key)
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16)


def sampling_seed_for_attempt(key: tuple[str, str, str, str, float, int], attempt: int) -> int:
    if attempt <= 1:
        return sampling_seed(key)
    payload = "|".join(str(part) for part in key) + f"|attempt={attempt}"
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16)


def timestamp_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def append_record(handle: TextIO, record: RunRecord) -> None:
    handle.write(record.model_dump_json())
    handle.write("\n")
    handle.flush()


def skip_cad_artifacts() -> bool:
    return os.environ.get("CADYBARA_SKIP_CAD_ARTIFACTS", "").lower() in {"1", "true", "yes"}


def provider_prompt(config: ExperimentConfig, model: ModelConfig, variant_text: str) -> str:
    if config.output_mode == "cadquery":
        if model.provider == "cadybara_api":
            return variant_text
        return cadquery_prompt(variant_text)
    return variant_text


def artifact_root_for_config(config: ExperimentConfig) -> Path:
    if config.artifact_root:
        return Path(config.artifact_root)
    output_parent = Path(config.output_path).parent
    if output_parent.name and output_parent.parent.name == "runs":
        return output_parent / "artifacts"
    return Path("workspace") / "artifacts" / config.experiment_id


def condition_name(cell: RunCell) -> str:
    return (
        f"{cell.model.name}|{cell.seed_id}|{cell.strategy.name}|"
        f"{cell.variant.variant_id}|t={cell.temperature}|r={cell.repetition}"
    )


def validate_config_hashes(
    records: list[RunRecord],
    current_hash: str,
    *,
    allow_config_mismatch: bool,
) -> None:
    mismatches = sorted({record.config_hash for record in records if record.config_hash != current_hash})
    if mismatches and not allow_config_mismatch:
        raise ConfigMismatchError(
            "Existing JSONL contains rows from a different config hash: "
            f"{', '.join(mismatches)}. Use --allow-config-mismatch to override."
        )


def completed_keys(
    records: list[RunRecord],
    *,
    retry_errors: bool,
    include_dry_run: bool = True,
) -> set[tuple[str, str, str, str, float, int]]:
    return {
        resume_key(record)
        for record in records
        if (include_dry_run or record.provider != "dry_run") and record_is_complete(record)
    }


def record_is_complete(record: RunRecord) -> bool:
    if record.repair_total_rounds is not None or record.repair_round is not None:
        return (
            record.repair_total_rounds is not None
            and record.repair_round is not None
            and record.repair_round >= record.repair_total_rounds
        )
    if record.error is not None:
        return False
    if record.provider == "dry_run":
        return True
    if record.output_mode == "cadquery":
        if record.provider == "cadybara_api" and record.error is None:
            return bool((record.artifacts or {}).get("stl"))
        return record.render_error is None and bool((record.artifacts or {}).get("stl"))
    return True


def attempt_counts(
    records: list[RunRecord],
    *,
    retry_errors: bool,
    include_dry_run: bool = True,
) -> Counter[tuple[str, str, str, str, float, int]]:
    if retry_errors:
        return Counter(
            resume_key(record)
            for record in records
            if (include_dry_run or record.provider != "dry_run") and record_is_complete(record)
        )
    return Counter(
        resume_key(record)
        for record in records
        if include_dry_run or record.provider != "dry_run"
    )


def generate_with_retries(
    provider: ModelProvider,
    prompt: str,
    *,
    temperature: float,
    max_tokens: int,
    seed: int,
    provider_retries: int,
    should_stop: Callable[[], bool] | None = None,
    snapshot_buffer: SnapshotBuffer | None = None,
    images: list[str] | None = None,
) -> tuple[ProviderResponse | None, str | None, int]:
    started = time.perf_counter()
    last_error: str | None = None
    for attempt in range(provider_retries + 1):
        try:
            if should_stop is not None and should_stop():
                raise GenerationStopped("generation stopped by user")
            if should_stop is not None and hasattr(provider, "generate_interruptible"):
                kwargs = {
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "seed": seed,
                    "should_stop": should_stop,
                    "snapshot_buffer": snapshot_buffer,
                }
                if images is not None:
                    kwargs["images"] = images
                return (
                    provider.generate_interruptible(prompt, **kwargs),  # type: ignore[attr-defined]
                    None,
                    int((time.perf_counter() - started) * 1000),
                )
            kwargs = {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "seed": seed,
            }
            if images is not None:
                kwargs["images"] = images
            return (
                provider.generate(prompt, **kwargs),
                None,
                int((time.perf_counter() - started) * 1000),
            )
        except GenerationStopped:
            raise
        except Exception as exc:  # noqa: BLE001 - provider failures are recorded as data.
            last_error = str(exc)
            if attempt >= provider_retries:
                break
    return None, last_error, int((time.perf_counter() - started) * 1000)


def make_record(
    *,
    run_id: str,
    config: ExperimentConfig,
    config_hash_value: str,
    cell: RunCell,
    provider_name: str,
    seed: int,
    attempt: int,
    prompt_sent: str,
    response: ProviderResponse | None,
    error: str | None,
    elapsed_ms: int,
    scorer: Scorer,
    artifacts: dict | None = None,
    render_error: str | None = None,
    repair_round: int | None = None,
    repair_total_rounds: int | None = None,
    parent_run_id: str | None = None,
    feedback_image_path: str | None = None,
    feedback_source_run_id: str | None = None,
) -> RunRecord:
    output = response.output if response is not None else ""
    scores = scorer.score(cell.seed_text, cell.variant, output)
    return RunRecord(
        run_id=run_id,
        experiment_id=config.experiment_id,
        timestamp_utc=timestamp_utc(),
        model_name=cell.model.name,
        provider=provider_name,
        seed_id=cell.seed_id,
        seed_text=cell.seed_text,
        seed_metadata=cell.seed_metadata,
        strategy=cell.strategy.name,
        variant_id=cell.variant.variant_id,
        variant_text=cell.variant.text,
        variant_metadata=cell.variant.metadata,
        prompt_sent=prompt_sent,
        output_mode=config.output_mode,
        condition_name=condition_name(cell),
        attempt=attempt,
        sampling={
            "temperature": cell.temperature,
            "seed": seed,
            "max_tokens": config.sampling.max_tokens,
        },
        repetition=cell.repetition,
        output=output,
        latency_ms=response.latency_ms if response is not None else elapsed_ms,
        prompt_tokens=response.prompt_tokens if response is not None else None,
        completion_tokens=response.completion_tokens if response is not None else None,
        finish_reason=response.finish_reason if response is not None else None,
        total_duration_ms=response.total_duration_ms if response is not None else None,
        load_duration_ms=response.load_duration_ms if response is not None else None,
        prompt_eval_duration_ms=response.prompt_eval_duration_ms if response is not None else None,
        eval_duration_ms=response.eval_duration_ms if response is not None else None,
        provider_seed=response.provider_seed if response is not None else None,
        provider_metadata=response.provider_metadata if response is not None else {},
        scores=scores,
        artifacts=artifacts or {},
        render_error=render_error,
        error=error,
        repair_round=repair_round,
        repair_total_rounds=repair_total_rounds,
        parent_run_id=parent_run_id,
        feedback_image_path=feedback_image_path,
        feedback_source_run_id=feedback_source_run_id,
        config_hash=config_hash_value,
    )


def repair_enabled(config: ExperimentConfig) -> bool:
    return bool(config.repair and config.repair.enabled and config.repair.rounds > 1)


def repair_round_count(config: ExperimentConfig) -> int:
    return config.repair.rounds if config.repair is not None else 1


def feedback_image_for_record(record: RunRecord) -> str | None:
    preview = (record.artifacts or {}).get("preview_png")
    if isinstance(preview, str) and Path(preview).exists():
        return preview
    return None


def visual_repair_prompt(
    *,
    design_prompt: str,
    previous_record: RunRecord,
    round_number: int,
    total_rounds: int,
    feedback_image_path: str | None,
) -> str:
    code_status = "executed without CAD export errors"
    if previous_record.error:
        code_status = f"provider or generation error was recorded: {previous_record.error}"
    elif previous_record.render_error:
        code_status = f"CadQuery execution/export failed with this error:\n{previous_record.render_error}"
    image_note = (
        "The attached image is the preview of the previous generated model."
        if feedback_image_path
        else "No preview image is attached because the previous code did not produce a renderable model."
    )
    return cadquery_prompt(
        f"""This is repair round {round_number} of {total_rounds}.

Original design request:
{design_prompt}

Previous generated CadQuery source:
{previous_record.output}

Previous result:
{code_status}

{image_note}

Produce a full replacement CadQuery Python source file that better satisfies the original design request.
Return only code and define the final model as `result`.
"""
    )


def repair_parent_run_id(records: list[RunRecord]) -> str | None:
    first_round = next((record for record in records if record.repair_round == 1), None)
    return first_round.run_id if first_round is not None else None


def run_visual_repair_config(
    config: ExperimentConfig,
    *,
    limit: int | None = None,
    retry_errors: bool = False,
    dry_run: bool = False,
    provider_retries: int = 1,
    strict_jsonl: bool = False,
    allow_config_mismatch: bool = False,
    should_stop: Callable[[], bool] | None = None,
    snapshot_buffer: SnapshotBuffer | None = None,
    on_cell_start: Callable[[RunCell, int], None] | None = None,
    on_record: Callable[[RunRecord], None] | None = None,
    stream: TextIO | None = None,
) -> RunSummary:
    if provider_retries < 0:
        raise ValueError("provider_retries must be >= 0")
    output_stream = stream or sys.stdout
    output_path = Path(config.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    hash_value = config_hash(config)
    existing = read_jsonl_records(output_path, strict_jsonl=strict_jsonl)
    if existing.malformed_count:
        print(
            f"Warning: skipped {existing.malformed_count} malformed JSONL row(s) in {output_path}.",
            file=output_stream,
        )
    validate_config_hashes(
        existing.records,
        hash_value,
        allow_config_mismatch=allow_config_mismatch,
    )

    rounds = repair_round_count(config)
    grouped: dict[tuple[str, str, str, str, float, int], list[RunRecord]] = defaultdict(list)
    for record in existing.records:
        if dry_run or record.provider != "dry_run":
            grouped[resume_key(record)].append(record)
    for rows in grouped.values():
        rows.sort(key=lambda record: record.repair_round or 1)

    cells = build_cells(config)
    scorer = StubScorer()
    executed = 0
    skipped = 0
    errors = 0
    stopped = False

    with output_path.open("a", encoding="utf-8") as handle:
        for index, cell in enumerate(cells, start=1):
            if should_stop is not None and should_stop():
                stopped = True
                print(
                    f"[{index}/{len(cells)}] STOP requested; no new generation started.",
                    file=output_stream,
                )
                break
            if limit is not None and executed >= limit:
                break

            key = cell_key(config.experiment_id, cell)
            cell_records = grouped[key]
            if any(record_is_complete(record) for record in cell_records):
                skipped += 1
                print(
                    f"[{index}/{len(cells)}] SKIP (repair complete) "
                    f"{cell.model.name} {cell.seed_id} {cell.strategy.name} "
                    f"t={cell.temperature} r={cell.repetition}",
                    file=output_stream,
                )
                continue

            completed_rounds = {
                record.repair_round
                for record in cell_records
                if record.repair_round is not None
            }
            parent_run = repair_parent_run_id(cell_records)
            previous_record = cell_records[-1] if cell_records else None

            for round_number in range(1, rounds + 1):
                if round_number in completed_rounds:
                    continue
                if should_stop is not None and should_stop():
                    stopped = True
                    print(
                        f"[{index}/{len(cells)}] STOP requested; no repair round started.",
                        file=output_stream,
                    )
                    break
                if limit is not None and executed >= limit:
                    break

                if round_number == 1:
                    prompt_sent = provider_prompt(config, cell.model, cell.variant.text)
                    feedback_image_path = None
                    feedback_source_run_id = None
                    images = None
                else:
                    if previous_record is None:
                        raise ValueError(
                            f"Cannot run repair round {round_number} before round 1 for {condition_name(cell)}."
                        )
                    feedback_image_path = feedback_image_for_record(previous_record)
                    feedback_source_run_id = previous_record.run_id
                    prompt_sent = visual_repair_prompt(
                        design_prompt=cell.variant.text,
                        previous_record=previous_record,
                        round_number=round_number,
                        total_rounds=rounds,
                        feedback_image_path=feedback_image_path,
                    )
                    images = [feedback_image_path] if feedback_image_path else None

                seed = sampling_seed_for_attempt(key, round_number)
                provider_name, provider = provider_for_model(cell.model, dry_run=dry_run)
                if on_cell_start is not None:
                    on_cell_start(cell, 1)
                if snapshot_buffer is not None and not dry_run:
                    snapshot_buffer.start(
                        model_name=cell.model.name,
                        prompt_id=cell.seed_id,
                        prompt_text=cell.seed_text,
                        repetition=cell.repetition,
                        repair_round=round_number,
                        repair_total_rounds=rounds,
                    )
                try:
                    response, error, elapsed_ms = generate_with_retries(
                        provider,
                        prompt_sent,
                        temperature=cell.temperature,
                        max_tokens=config.sampling.max_tokens,
                        seed=seed,
                        provider_retries=provider_retries,
                        should_stop=should_stop,
                        snapshot_buffer=snapshot_buffer,
                        images=images,
                    )
                except GenerationStopped:
                    if snapshot_buffer is not None:
                        snapshot_buffer.finish()
                    stopped = True
                    print(
                        f"[{index}/{len(cells)}] STOP requested; current repair generation was cancelled.",
                        file=output_stream,
                    )
                    break
                if snapshot_buffer is not None:
                    snapshot_buffer.finish()

                run_id = str(uuid4())
                record = make_record(
                    run_id=run_id,
                    config=config,
                    config_hash_value=hash_value,
                    cell=cell,
                    provider_name=provider_name,
                    seed=seed,
                    attempt=1,
                    prompt_sent=prompt_sent,
                    response=response,
                    error=error,
                    elapsed_ms=elapsed_ms,
                    scorer=scorer,
                    repair_round=round_number,
                    repair_total_rounds=rounds,
                    parent_run_id=parent_run,
                    feedback_image_path=feedback_image_path,
                    feedback_source_run_id=feedback_source_run_id,
                )
                if parent_run is None:
                    parent_run = record.run_id
                if (
                    error is None
                    and response is not None
                    and config.output_mode == "cadquery"
                    and not dry_run
                    and not skip_cad_artifacts()
                ):
                    artifacts, render_error = write_cadquery_artifacts(
                        record=record,
                        prompt_sent=prompt_sent,
                        artifact_root=artifact_root_for_config(config),
                        hosted_stl_base64=response.hosted_stl_base64,
                    )
                    record = record.model_copy(
                        update={"artifacts": artifacts, "render_error": render_error},
                    )

                append_record(handle, record)
                if on_record is not None:
                    on_record(record)
                grouped[key].append(record)
                previous_record = record
                executed += 1
                if error is not None:
                    errors += 1
                status = "repair round recorded"
                if (
                    record.provider == "cadybara_api"
                    and record.render_error
                    and (record.artifacts or {}).get("stl")
                ):
                    status = "repair round hosted STL ready; local source failed"
                elif record.render_error:
                    status = "repair round render failed"
                elif (record.artifacts or {}).get("stl"):
                    status = "repair round STL ready"
                print(
                    f"[{index}/{len(cells)}] {cell.model.name} {cell.seed_id} "
                    f"{cell.strategy.name} t={cell.temperature} r={cell.repetition} "
                    f"repair={round_number}/{rounds} {status} "
                    f"({record.latency_ms / 1000:.1f}s)",
                    file=output_stream,
                )
            if stopped or (limit is not None and executed >= limit):
                break

    print(
        "Summary: "
        f"executed={executed} skipped={skipped} errors={errors} "
        f"malformed_rows={existing.malformed_count} stopped={stopped}",
        file=output_stream,
    )
    return RunSummary(
        total_cells=len(cells),
        executed=executed,
        skipped=skipped,
        errors=errors,
        malformed_rows=existing.malformed_count,
        output_path=output_path,
        stopped=stopped,
    )


def run_config(
    config: ExperimentConfig,
    *,
    limit: int | None = None,
    retry_errors: bool = False,
    dry_run: bool = False,
    provider_retries: int = 1,
    strict_jsonl: bool = False,
    allow_config_mismatch: bool = False,
    should_stop: Callable[[], bool] | None = None,
    snapshot_buffer: SnapshotBuffer | None = None,
    on_cell_start: Callable[[RunCell, int], None] | None = None,
    on_record: Callable[[RunRecord], None] | None = None,
    stream: TextIO | None = None,
) -> RunSummary:
    if repair_enabled(config):
        return run_visual_repair_config(
            config,
            limit=limit,
            retry_errors=retry_errors,
            dry_run=dry_run,
            provider_retries=provider_retries,
            strict_jsonl=strict_jsonl,
            allow_config_mismatch=allow_config_mismatch,
            should_stop=should_stop,
            snapshot_buffer=snapshot_buffer,
            on_cell_start=on_cell_start,
            on_record=on_record,
            stream=stream,
        )
    if provider_retries < 0:
        raise ValueError("provider_retries must be >= 0")
    output_stream = stream or sys.stdout
    output_path = Path(config.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    hash_value = config_hash(config)
    existing = read_jsonl_records(output_path, strict_jsonl=strict_jsonl)
    if existing.malformed_count:
        print(
            f"Warning: skipped {existing.malformed_count} malformed JSONL row(s) in {output_path}.",
            file=output_stream,
        )
    validate_config_hashes(
        existing.records,
        hash_value,
        allow_config_mismatch=allow_config_mismatch,
    )
    completed = completed_keys(
        existing.records,
        retry_errors=retry_errors,
        include_dry_run=dry_run,
    )
    attempts_by_key = attempt_counts(
        existing.records,
        retry_errors=retry_errors,
        include_dry_run=dry_run,
    )
    cells = build_cells(config)
    scorer = StubScorer()
    executed = 0
    skipped = 0
    errors = 0
    stopped = False

    with output_path.open("a", encoding="utf-8") as handle:
        for index, cell in enumerate(cells, start=1):
            if should_stop is not None and should_stop():
                stopped = True
                print(
                    f"[{index}/{len(cells)}] STOP requested; no new generation started.",
                    file=output_stream,
                )
                break
            if limit is not None and executed >= limit:
                break
            key = cell_key(config.experiment_id, cell)
            if key in completed:
                skipped += 1
                print(
                    f"[{index}/{len(cells)}] SKIP (already done) "
                    f"{cell.model.name} {cell.seed_id} {cell.strategy.name} "
                    f"t={cell.temperature} r={cell.repetition}",
                    file=output_stream,
                )
                continue

            attempts_so_far = attempts_by_key[key]
            if attempts_so_far >= config.sampling.max_attempts_per_cell:
                skipped += 1
                print(
                    f"[{index}/{len(cells)}] MAX ATTEMPTS "
                    f"{cell.model.name} {cell.seed_id} {cell.strategy.name} "
                    f"t={cell.temperature} r={cell.repetition} "
                    f"attempts={attempts_so_far}",
                    file=output_stream,
                )
                continue

            while attempts_by_key[key] < config.sampling.max_attempts_per_cell:
                if should_stop is not None and should_stop():
                    stopped = True
                    print(
                        f"[{index}/{len(cells)}] STOP requested; no retry generation started.",
                        file=output_stream,
                    )
                    break
                if limit is not None and executed >= limit:
                    break

                attempt = attempts_by_key[key] + 1
                seed = sampling_seed_for_attempt(key, attempt)
                provider_name, provider = provider_for_model(cell.model, dry_run=dry_run)
                prompt_sent = provider_prompt(config, cell.model, cell.variant.text)
                if on_cell_start is not None:
                    on_cell_start(cell, attempt)
                if snapshot_buffer is not None and not dry_run:
                    snapshot_buffer.start(
                        model_name=cell.model.name,
                        prompt_id=cell.seed_id,
                        prompt_text=cell.seed_text,
                        repetition=cell.repetition,
                    )
                try:
                    response, error, elapsed_ms = generate_with_retries(
                        provider,
                        prompt_sent,
                        temperature=cell.temperature,
                        max_tokens=config.sampling.max_tokens,
                        seed=seed,
                        provider_retries=provider_retries,
                        should_stop=should_stop,
                        snapshot_buffer=snapshot_buffer,
                    )
                except GenerationStopped:
                    if snapshot_buffer is not None:
                        snapshot_buffer.finish()
                    stopped = True
                    print(
                        f"[{index}/{len(cells)}] STOP requested; current generation was cancelled.",
                        file=output_stream,
                    )
                    break
                if snapshot_buffer is not None:
                    snapshot_buffer.finish()
                run_id = str(uuid4())
                record = make_record(
                    run_id=run_id,
                    config=config,
                    config_hash_value=hash_value,
                    cell=cell,
                    provider_name=provider_name,
                    seed=seed,
                    attempt=attempt,
                    prompt_sent=prompt_sent,
                    response=response,
                    error=error,
                    elapsed_ms=elapsed_ms,
                    scorer=scorer,
                )
                if (
                    error is None
                    and response is not None
                    and config.output_mode == "cadquery"
                    and not dry_run
                    and not skip_cad_artifacts()
                ):
                    artifacts, render_error = write_cadquery_artifacts(
                        record=record,
                        prompt_sent=prompt_sent,
                        artifact_root=artifact_root_for_config(config),
                        hosted_stl_base64=response.hosted_stl_base64,
                    )
                    record = record.model_copy(
                        update={"artifacts": artifacts, "render_error": render_error},
                    )
                append_record(handle, record)
                if on_record is not None:
                    on_record(record)
                attempts_by_key[key] += 1
                executed += 1
                if error is not None:
                    errors += 1
                if record_is_complete(record):
                    if (
                        record.provider == "cadybara_api"
                        and record.render_error
                        and (record.artifacts or {}).get("stl")
                    ):
                        status = "hosted STL ready; local source failed"
                    else:
                        status = "STL ready" if config.output_mode == "cadquery" and not dry_run else "complete"
                else:
                    status = "attempt failed"
                print(
                    f"[{index}/{len(cells)}] {cell.model.name} {cell.seed_id} "
                    f"{cell.strategy.name} t={cell.temperature} r={cell.repetition} "
                    f"attempt={attempt}/{config.sampling.max_attempts_per_cell} "
                    f"{status} ({record.latency_ms / 1000:.1f}s)",
                    file=output_stream,
                )
                if record_is_complete(record):
                    completed.add(key)
                    break
            if stopped or (limit is not None and executed >= limit):
                break

    print(
        "Summary: "
        f"executed={executed} skipped={skipped} errors={errors} "
        f"malformed_rows={existing.malformed_count} stopped={stopped}",
        file=output_stream,
    )
    return RunSummary(
        total_cells=len(cells),
        executed=executed,
        skipped=skipped,
        errors=errors,
        malformed_rows=existing.malformed_count,
        output_path=output_path,
        stopped=stopped,
    )


def run_config_path(
    config_path: str | Path,
    *,
    limit: int | None = None,
    retry_errors: bool = False,
    dry_run: bool = False,
    provider_retries: int = 1,
    strict_jsonl: bool = False,
    allow_config_mismatch: bool = False,
    should_stop: Callable[[], bool] | None = None,
    snapshot_buffer: SnapshotBuffer | None = None,
    on_cell_start: Callable[[RunCell, int], None] | None = None,
    on_record: Callable[[RunRecord], None] | None = None,
    stream: TextIO | None = None,
) -> RunSummary:
    return run_config(
        load_config(config_path),
        limit=limit,
        retry_errors=retry_errors,
        dry_run=dry_run,
        provider_retries=provider_retries,
        strict_jsonl=strict_jsonl,
        allow_config_mismatch=allow_config_mismatch,
        should_stop=should_stop,
        snapshot_buffer=snapshot_buffer,
        on_cell_start=on_cell_start,
        on_record=on_record,
        stream=stream,
    )
