from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Iterable
from typing import Any, Literal

import httpx

from cadybara.providers.base import ModelProvider, ProviderResponse


DESIGN_MARKER = "\nDesign request:\n"
DEFAULT_MODEL_NAMES = {"cadybara-agent-default", "tier-default", "default"}


def _read_windows_user_env(name: str) -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _value_type = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return str(value) if value else None


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    return _read_windows_user_env(name)


def unwrap_cadquery_prompt(prompt: str) -> str:
    if DESIGN_MARKER not in prompt:
        return prompt.strip()
    return prompt.split(DESIGN_MARKER, 1)[1].strip()


def _response_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:500]
    return str(data)[:500]


class CadybaraApiProvider(ModelProvider):
    def __init__(
        self,
        *,
        model_name: str,
        base_url: str,
        timeout: float = 180.0,
        api_key_env: str = "CADYBARA_API_KEY",
        hosted_model_id: str | None = None,
        response_mode: Literal["json", "stl", "sse"] = "json",
        linear_deflection: float = 0.1,
        angular_deflection: float = 0.1,
        unwrap_prompt: bool = True,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key_env = api_key_env
        self.hosted_model_id = hosted_model_id
        self.response_mode = response_mode
        self.linear_deflection = linear_deflection
        self.angular_deflection = angular_deflection
        self.unwrap_prompt = unwrap_prompt

    def _api_key(self) -> str:
        api_key = _env_value(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{self.api_key_env} is not set. Set it in the process environment "
                "or Windows User environment before running hosted Cadybara API tests."
            )
        return api_key

    def _model_id(self) -> str | None:
        if self.hosted_model_id:
            return self.hosted_model_id
        if self.model_name in DEFAULT_MODEL_NAMES:
            return None
        return self.model_name

    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        seed: int | None,
        images: list[str] | None = None,
    ) -> ProviderResponse:
        del temperature, max_tokens, seed, images
        prompt_to_send = unwrap_cadquery_prompt(prompt) if self.unwrap_prompt else prompt.strip()
        payload: dict[str, object] = {
            "prompt": prompt_to_send,
            "response_mode": self.response_mode,
            "linear_deflection": self.linear_deflection,
            "angular_deflection": self.angular_deflection,
        }
        model_id = self._model_id()
        if model_id is not None:
            payload["model"] = model_id

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self._api_key(),
        }
        if self.response_mode == "sse":
            return self._generate_sse(payload=payload, headers=headers)

        started = time.perf_counter()
        response = httpx.post(
            f"{self.base_url}/api/agent/generate",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        wall_latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _response_detail(response)
            raise RuntimeError(
                "Cadybara API POST /api/agent/generate failed with "
                f"HTTP {response.status_code}: {detail}"
            ) from exc

        if self.response_mode == "stl" or response.headers.get("content-type", "").startswith(
            "application/octet-stream"
        ):
            encoded = base64.b64encode(response.content).decode("ascii")
            return ProviderResponse(
                output=f"STL_BINARY_RESPONSE bytes={len(response.content)}\n",
                latency_ms=wall_latency_ms,
                prompt_tokens=None,
                completion_tokens=None,
                finish_reason="stl",
                total_duration_ms=wall_latency_ms,
                provider_metadata={
                    "response_mode": "stl",
                    "hosted_stl_base64_chars": len(encoded),
                },
                hosted_stl_base64=encoded,
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("Cadybara API returned non-JSON response for response_mode=json.") from exc
        return self._provider_response_from_result(data, wall_latency_ms=wall_latency_ms)

    def _generate_sse(
        self,
        *,
        payload: dict[str, object],
        headers: dict[str, str],
    ) -> ProviderResponse:
        started = time.perf_counter()
        event_counts: dict[str, int] = {}
        result_payload: dict[str, Any] | None = None
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/api/agent/generate",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    response.read()
                    detail = _response_detail(response)
                    raise RuntimeError(
                        "Cadybara API POST /api/agent/generate failed with "
                        f"HTTP {response.status_code}: {detail}"
                    ) from exc

                for event_name, data_text in _iter_sse_events(response.iter_lines()):
                    if data_text == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_text)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(f"Cadybara API SSE event was not JSON: {data_text[:200]}") from exc
                    if not isinstance(event, dict):
                        continue
                    event_type = str(event.get("type") or event_name or "message")
                    event_counts[event_type] = event_counts.get(event_type, 0) + 1
                    if event_type == "error":
                        code = event.get("code") or event.get("status_code") or "SSE_ERROR"
                        message = event.get("error") or event.get("detail") or event
                        raise RuntimeError(f"Cadybara API SSE error {code}: {message}")
                    if event_type == "result":
                        result_payload = event
                        break
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Cadybara API SSE request failed: {exc}") from exc

        wall_latency_ms = int((time.perf_counter() - started) * 1000)
        if result_payload is None:
            seen = ", ".join(sorted(event_counts)) if event_counts else "none"
            raise RuntimeError(f"Cadybara API SSE stream ended without a result event; saw events: {seen}.")
        response = self._provider_response_from_result(result_payload, wall_latency_ms=wall_latency_ms)
        metadata = dict(response.provider_metadata)
        metadata["sse_event_counts"] = event_counts
        return response.model_copy(update={"provider_metadata": metadata})

    def _provider_response_from_result(
        self,
        data: object,
        *,
        wall_latency_ms: int,
    ) -> ProviderResponse:
        if not isinstance(data, dict):
            raise RuntimeError("Cadybara API JSON response was not an object.")
        generated_code = data.get("generated_code")
        if not isinstance(generated_code, str) or not generated_code.strip():
            raise RuntimeError("Cadybara API JSON response did not include non-empty generated_code.")
        validation = data.get("validation") if isinstance(data, dict) else None
        validation_valid = validation.get("valid") if isinstance(validation, dict) else None
        stl_base64 = data.get("stl_base64")
        if not isinstance(stl_base64, str):
            stl_base64 = None
        finish_reason = "validation_valid" if validation_valid is True else "validation_invalid"
        return ProviderResponse(
            output=generated_code.strip() + "\n",
            latency_ms=wall_latency_ms,
            prompt_tokens=None,
            completion_tokens=None,
            finish_reason=finish_reason,
            total_duration_ms=wall_latency_ms,
            provider_metadata={
                "response_mode": data.get("response_mode"),
                "validation": validation if isinstance(validation, dict) else None,
                "hosted_stl_base64_chars": len(stl_base64) if stl_base64 else None,
                "generated_code_chars": len(generated_code),
            },
            hosted_stl_base64=stl_base64,
        )


def _iter_sse_events(lines: Iterable[str]) -> Iterable[tuple[str | None, str]]:
    event_name: str | None = None
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if not line:
            if data_lines:
                yield event_name, "\n".join(data_lines)
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, sep, value = line.partition(":")
        if not sep:
            continue
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)
    if data_lines:
        yield event_name, "\n".join(data_lines)
