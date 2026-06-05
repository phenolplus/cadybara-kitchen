from __future__ import annotations

from pathlib import Path


def test_linux_worker_setup_script_preserves_worker_contract() -> None:
    script = Path("setup_worker.sh").read_text(encoding="utf-8")

    required_fragments = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "--hostname",
        "--models",
        "avahi-daemon",
        "openssh-server",
        "hostnamectl set-hostname",
        "systemctl enable --now avahi-daemon",
        "systemctl enable --now ssh",
        'Environment="OLLAMA_HOST=127.0.0.1:11434"',
        'Environment="OLLAMA_NUM_PARALLEL=1"',
        "loginctl enable-linger",
        "systemctl --user enable --now cadybara-worker.service",
        'Environment="CADYBARA_DISABLE_MODEL_CLEANUP=1"',
        'Environment="CADYBARA_LAB_DISABLE_AUTO_PULL=1"',
        "CADYBARA_DISABLE_MODEL_CLEANUP=1 .venv/bin/cadybara pull-models",
        "/etc/logrotate.d/cadybara-worker",
        'to any port "$LAB_PORT"',
        "to any port 22",
        ".local",
    ]

    for fragment in required_fragments:
        assert fragment in script


def test_linux_worker_setup_does_not_expose_ollama_to_lan() -> None:
    script = Path("setup_worker.sh").read_text(encoding="utf-8")

    assert "OLLAMA_HOST=0.0.0.0" not in script
    assert "to any port 11434" not in script
    assert "11434 proto tcp" not in script
