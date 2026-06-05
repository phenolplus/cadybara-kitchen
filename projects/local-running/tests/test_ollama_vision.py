from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import respx

from cadybara.providers.ollama import OllamaProvider


@respx.mock
def test_ollama_provider_sends_images_and_threads(tmp_path: Path) -> None:
    image_path = tmp_path / "preview.png"
    image_path.write_bytes(b"fake-png")
    route = respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": "fixed code",
                "eval_count": 3,
                "prompt_eval_count": 4,
                "total_duration": 1_000_000,
            },
        )
    )
    provider = OllamaProvider(
        model_name="qwen3-vl:235b",
        base_url="http://localhost:11434",
        num_thread=12,
    )

    response = provider.generate(
        "fix this",
        temperature=0.2,
        max_tokens=4096,
        seed=99,
        images=[str(image_path)],
    )

    assert response.output == "fixed code"
    body = json.loads(route.calls.last.request.read())
    assert body["images"] == [base64.b64encode(b"fake-png").decode("ascii")]
    assert body["options"]["num_thread"] == 12
