from __future__ import annotations

import json

import httpx
import pytest
import respx

from cadybara.cadquery_runner import cadquery_prompt
from cadybara.providers.cadybara_api import CadybaraApiProvider


@respx.mock
def test_cadybara_api_provider_posts_agent_request_and_returns_code(monkeypatch) -> None:
    monkeypatch.setenv("CADYBARA_API_KEY", "pfk_test")
    route = respx.post("https://api.cadybara.com/api/agent/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "generated_code": 'import cadquery as cq\nresult = cq.Workplane("XY").box(20, 20, 20)\n',
                "stl_base64": "c29saWQK",
                "validation": {"valid": True, "confidence": 1.0},
                "response_mode": "json",
            },
        )
    )
    provider = CadybaraApiProvider(
        model_name="cadybara-agent-default",
        base_url="https://api.cadybara.com",
    )

    response = provider.generate(
        cadquery_prompt("Make a 20 mm cube."),
        temperature=0.0,
        max_tokens=1,
        seed=123,
    )

    assert route.called
    request = route.calls.last.request
    body = json.loads(request.read())
    assert request.headers["X-API-Key"] == "pfk_test"
    assert body == {
        "prompt": "Make a 20 mm cube.",
        "response_mode": "json",
        "linear_deflection": 0.1,
        "angular_deflection": 0.1,
    }
    assert response.output.startswith("import cadquery as cq")
    assert response.finish_reason == "validation_valid"
    assert response.total_duration_ms is not None
    assert response.hosted_stl_base64 == "c29saWQK"
    assert response.provider_metadata["hosted_stl_base64_chars"] == 8


@respx.mock
def test_cadybara_api_provider_can_send_explicit_hosted_model(monkeypatch) -> None:
    monkeypatch.setenv("CADYBARA_API_KEY", "pfk_test")
    route = respx.post("https://api.cadybara.com/api/agent/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "generated_code": 'import cadquery as cq\nresult = cq.Workplane("XY").box(1, 1, 1)\n',
                "validation": {"valid": False},
                "response_mode": "json",
            },
        )
    )
    provider = CadybaraApiProvider(
        model_name="friendly-label",
        hosted_model_id="actual-chat-model",
        base_url="https://api.cadybara.com",
        linear_deflection=0.2,
        angular_deflection=0.3,
    )

    response = provider.generate("Make a tiny cube.", temperature=0.7, max_tokens=512, seed=456)

    body = json.loads(route.calls.last.request.read())
    assert body["model"] == "actual-chat-model"
    assert body["linear_deflection"] == 0.2
    assert body["angular_deflection"] == 0.3
    assert response.finish_reason == "validation_invalid"


@respx.mock
def test_cadybara_api_provider_reads_sse_result(monkeypatch) -> None:
    monkeypatch.setenv("CADYBARA_API_KEY", "pfk_test")
    event_text = "\n".join(
        [
            'data: {"type":"session","session_id":"abc"}',
            "",
            'data: {"type":"export","status":"started"}',
            "",
            (
                'data: {"type":"result","generated_code":"import cadquery as cq\\n'
                'result = cq.Workplane(\\"XY\\").box(2, 2, 2)\\n",'
                '"stl_base64":"c29saWQK","validation":{"valid":true},'
                '"response_mode":"sse"}'
            ),
            "",
        ]
    )
    route = respx.post("https://api.cadybara.com/api/agent/generate").mock(
        return_value=httpx.Response(
            200,
            text=event_text,
            headers={"content-type": "text/event-stream"},
        )
    )
    provider = CadybaraApiProvider(
        model_name="cadybara-agent-default",
        base_url="https://api.cadybara.com",
        response_mode="sse",
    )

    response = provider.generate("Make a cube.", temperature=0.0, max_tokens=1, seed=None)

    body = json.loads(route.calls.last.request.read())
    assert body["response_mode"] == "sse"
    assert response.output.startswith("import cadquery as cq")
    assert response.finish_reason == "validation_valid"
    assert response.hosted_stl_base64 == "c29saWQK"
    assert response.provider_metadata["response_mode"] == "sse"
    assert response.provider_metadata["sse_event_counts"] == {
        "session": 1,
        "export": 1,
        "result": 1,
    }


@respx.mock
def test_cadybara_api_provider_records_sse_error_event(monkeypatch) -> None:
    monkeypatch.setenv("CADYBARA_API_KEY", "pfk_test")
    respx.post("https://api.cadybara.com/api/agent/generate").mock(
        return_value=httpx.Response(
            200,
            text='data: {"type":"error","status_code":500,"code":"LLM_ERROR","error":"boom"}\n\n',
            headers={"content-type": "text/event-stream"},
        )
    )
    provider = CadybaraApiProvider(
        model_name="cadybara-agent-default",
        base_url="https://api.cadybara.com",
        response_mode="sse",
    )

    with pytest.raises(RuntimeError, match="SSE error LLM_ERROR.*boom"):
        provider.generate("Make a planter.", temperature=0.0, max_tokens=1, seed=None)


@respx.mock
def test_cadybara_api_provider_records_http_errors(monkeypatch) -> None:
    monkeypatch.setenv("CADYBARA_API_KEY", "pfk_test")
    respx.post("https://api.cadybara.com/api/agent/generate").mock(
        return_value=httpx.Response(504, json={"detail": "Gateway timeout"})
    )
    provider = CadybaraApiProvider(
        model_name="cadybara-agent-default",
        base_url="https://api.cadybara.com",
    )

    with pytest.raises(RuntimeError, match="HTTP 504.*Gateway timeout"):
        provider.generate("Make a planter.", temperature=0.0, max_tokens=1, seed=None)
