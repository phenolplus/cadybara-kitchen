from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from cadybara_cad_diffusion import CadProgram, ExtrudeOp, program_to_tokens
from cadybara_online_testing import lab_server
from cadybara_online_testing.lab_server import LabState, make_handler


class AliveThread:
    def is_alive(self) -> bool:
        return True


def get_json(url: str) -> dict:
    with urlopen(url, timeout=5) as response:  # noqa: S310 - local test server.
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict | None = None) -> tuple[int, dict]:
    request = Request(
        url,
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:  # noqa: S310 - local test server.
        return response.status, json.loads(response.read().decode("utf-8"))


def write_tiny_cad_dataset(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    program = CadProgram(ops=[ExtrudeOp(profile="rect", mode="new", width=20, height=10, distance=5)])
    tokens = program_to_tokens(program, max_len=32)
    example = {
        "example_id": "tiny",
        "split": "train",
        "source_path": "tiny.json",
        "program": program.model_dump(mode="json"),
        "tokens": tokens,
        "token_count": len(tokens),
    }
    (data_dir / "train.jsonl").write_text(json.dumps(example) + "\n", encoding="utf-8")
    (data_dir / "test.jsonl").write_text(json.dumps({**example, "split": "test"}) + "\n", encoding="utf-8")
    (data_dir / "manifest.json").write_text(
        json.dumps({"written": 1, "scanned_json": 1, "unsupported": 0}) + "\n",
        encoding="utf-8",
    )


@dataclass(frozen=True)
class FakeTrainSummary:
    steps: int
    checkpoint_path: Path
    device: str
    examples: int
    elapsed_seconds: float


def test_lab_snapshot_and_run_status_endpoints(tmp_path: Path) -> None:
    state = LabState(tmp_path)
    state.snapshot_buffer.start(
        model_name="qwen2.5-coder:3b",
        prompt_id="planter_01_minimal",
        prompt_text="Make a planter.",
        repetition=0,
    )
    state.snapshot_buffer.append("import cadquery as cq\n")
    state.run_thread = AliveThread()  # type: ignore[assignment]
    state.run_status_cache = {
        "experiment_id": "stub",
        "model_count": 1,
        "prompt_count": 1,
        "repetitions": 1,
        "condition_count": 1,
        "progress": {"weighted_progress": 0.5, "eta_seconds": 12},
        "models": [],
        "recent_renders": [],
    }

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        snapshot = get_json(f"{base}/api/current_snapshot")
        assert snapshot["is_running"] is True
        assert snapshot["tokens_so_far"] == 4
        assert snapshot["last_lines"] == ["import cadquery as cq"]

        status = get_json(f"{base}/api/run_status")
        assert status["experiment_id"] == "stub"
        assert status["progress"]["weighted_progress"] == 0.5
    finally:
        server.shutdown()
        server.server_close()


def test_cad_diffusion_status_endpoint_reports_blocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        lab_server,
        "CAD_DIFFUSION_DEFAULTS",
        {
            **lab_server.CAD_DIFFUSION_DEFAULTS,
            "data_dir": str(tmp_path / "missing_tokens"),
            "model_dir": str(tmp_path / "models"),
            "max_len": 32,
        },
    )
    monkeypatch.setattr(
        lab_server,
        "cad_torch_status",
        lambda: {
            "available": True,
            "version": "test",
            "cuda_available": False,
            "cuda_device_count": 0,
            "device": "cpu",
            "message": "CPU-only PyTorch detected; overnight training is expected.",
        },
    )
    state = LabState(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status = get_json(f"http://127.0.0.1:{server.server_port}/api/cad-diffusion/status")
        assert status["ready"] is False
        assert status["job"]["status"] == "idle"
        assert "Prepared dataset is missing" in status["blockers"][0]
    finally:
        server.shutdown()
        server.server_close()


def test_cad_diffusion_start_endpoint_rejects_conflicting_run(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "tokens"
    model_dir = tmp_path / "models"
    write_tiny_cad_dataset(data_dir)
    monkeypatch.setattr(
        lab_server,
        "CAD_DIFFUSION_DEFAULTS",
        {
            **lab_server.CAD_DIFFUSION_DEFAULTS,
            "data_dir": str(data_dir),
            "model_dir": str(model_dir),
            "max_len": 32,
            "max_steps": 5,
            "checkpoint_interval": 100,
        },
    )
    monkeypatch.setattr(
        lab_server,
        "cad_torch_status",
        lambda: {
            "available": True,
            "version": "test",
            "cuda_available": False,
            "cuda_device_count": 0,
            "device": "cpu",
            "message": "CPU-only PyTorch detected; overnight training is expected.",
        },
    )
    entered = threading.Event()

    def fake_train(data_dir_arg, model_dir_arg, **kwargs):
        model_dir_arg.mkdir(parents=True, exist_ok=True)
        kwargs["on_progress"](
            {
                "phase": "started",
                "step": 0,
                "max_steps": kwargs["max_steps"],
                "checkpoint_path": (model_dir_arg / "checkpoint_step_000000.pt").as_posix(),
                "device": "cpu",
                "examples": 1,
                "loss": None,
                "elapsed_seconds": 0.0,
            }
        )
        entered.set()
        while not kwargs["should_stop"]():
            time.sleep(0.01)
        checkpoint = model_dir_arg / "checkpoint_step_000001.pt"
        checkpoint.write_bytes(b"fake")
        return FakeTrainSummary(
            steps=1,
            checkpoint_path=checkpoint,
            device="cpu",
            examples=1,
            elapsed_seconds=0.1,
        )

    monkeypatch.setattr(lab_server, "train_diffusion_model", fake_train)
    state = LabState(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        status_code, payload = post_json(f"{base}/api/cad-diffusion/train/start")
        assert status_code == 202
        assert payload["started"] is True
        assert entered.wait(timeout=2)
        status = get_json(f"{base}/api/cad-diffusion/status")
        assert status["job"]["status"] == "running"

        conflict_request = Request(
            f"{base}/api/cad-diffusion/train/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(conflict_request, timeout=5)  # noqa: S310 - local test server.
        except Exception as exc:  # noqa: BLE001 - urllib exposes 409 as an exception.
            assert "HTTP Error 409" in str(exc)
        else:  # pragma: no cover - the conflict must reject.
            raise AssertionError("conflicting CAD diffusion train start unexpectedly succeeded")

        stop_code, stop_payload = post_json(f"{base}/api/cad-diffusion/train/stop")
        assert stop_code == 202
        assert stop_payload["stop_requested"] is True
    finally:
        server.shutdown()
        server.server_close()
