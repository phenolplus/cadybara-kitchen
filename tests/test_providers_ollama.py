from __future__ import annotations

import json

import httpx
import respx

from cadybara.providers.ollama import OllamaProvider


@respx.mock
def test_ollama_provider_request_and_response_parsing() -> None:
    route = respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": "model output",
                "eval_count": 11,
                "prompt_eval_count": 7,
                "total_duration": 1_234_000_000,
                "load_duration": 30_000_000,
                "prompt_eval_duration": 200_000_000,
                "eval_duration": 1_004_000_000,
                "done_reason": "stop",
                "seed": 12345,
            },
        )
    )
    provider = OllamaProvider(model_name="qwen2.5:0.5b", base_url="http://localhost:11434")
    response = provider.generate(
        "Prompt",
        temperature=0.7,
        max_tokens=512,
        seed=12345,
    )
    assert route.called
    body = json.loads(route.calls.last.request.read())
    assert body["model"] == "qwen2.5:0.5b"
    assert body["prompt"] == "Prompt"
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0.7
    assert body["options"]["seed"] == 12345
    assert body["options"]["num_predict"] == 512
    assert response.output == "model output"
    assert response.prompt_tokens == 7
    assert response.completion_tokens == 11
    assert response.latency_ms == 1234
    assert response.total_duration_ms == 1234
    assert response.load_duration_ms == 30
    assert response.prompt_eval_duration_ms == 200
    assert response.eval_duration_ms == 1004
    assert response.provider_seed == 12345
    assert response.finish_reason == "stop"
