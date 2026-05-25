from __future__ import annotations

from pathlib import Path

import pytest

from cadybara.config import load_config
from cadybara.providers.base import ModelProvider, ProviderResponse
from cadybara.records import RunRecord
from cadybara.runner import (
    ConfigMismatchError,
    MalformedJsonlError,
    provider_for_model,
    read_jsonl_records,
    run_config,
)


class RaisingProvider(ModelProvider):
    calls = 0

    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        seed: int | None,
    ) -> ProviderResponse:
        self.calls += 1
        raise RuntimeError("boom")


def read_records(path: Path) -> list[RunRecord]:
    return [
        RunRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_runner_error_rows_retry_and_retry_errors(
    tiny_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers: list[RaisingProvider] = []

    def fake_provider_for_model(model, *, dry_run: bool):
        provider = RaisingProvider()
        providers.append(provider)
        return "raising", provider

    monkeypatch.setattr("cadybara.runner.provider_for_model", fake_provider_for_model)
    config = load_config(tiny_config_path)
    summary = run_config(config, provider_retries=1)
    output_path = Path(config.output_path)
    records = read_records(output_path)
    assert summary.executed == 8
    assert len(records) == 8
    assert all(record.error == "boom" for record in records)
    assert all(record.output == "" for record in records)
    assert sum(provider.calls for provider in providers) == 16

    retry = run_config(config, provider_retries=0, retry_errors=True)
    assert retry.executed == 8
    assert len(read_records(output_path)) == 16


def test_malformed_jsonl_skips_by_default_and_strict_fails(tiny_config_path: Path) -> None:
    config = load_config(tiny_config_path)
    run_config(config, dry_run=True, limit=1)
    output_path = Path(config.output_path)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write('{"truncated":\n')
    result = read_jsonl_records(output_path)
    assert result.malformed_count == 1
    summary = run_config(config, dry_run=True)
    assert summary.malformed_rows == 1
    with pytest.raises(MalformedJsonlError):
        read_jsonl_records(output_path, strict_jsonl=True)


def test_config_hash_mismatch_refuses_resume(tiny_config_path: Path) -> None:
    config = load_config(tiny_config_path)
    run_config(config, dry_run=True, limit=1)
    changed = config.model_copy(
        deep=True,
        update={"sampling": config.sampling.model_copy(update={"max_tokens": 64})},
    )
    with pytest.raises(ConfigMismatchError):
        run_config(changed, dry_run=True)
    summary = run_config(changed, dry_run=True, allow_config_mismatch=True, limit=1)
    assert summary.executed == 1


def test_provider_for_model_import_kept_for_lint() -> None:
    assert provider_for_model is not None
