#!/usr/bin/env bash
set -euo pipefail

LAB_PORT="${LAB_PORT:-8787}"
LAB_HOST="${LAB_HOST:-0.0.0.0}"
CADYBARA_OLLAMA_NUM_CTX="${CADYBARA_OLLAMA_NUM_CTX:-4096}"
CADYBARA_OLLAMA_NUM_THREAD="${CADYBARA_OLLAMA_NUM_THREAD:-4}"
INSTALL_TEST_DEPS="${INSTALL_TEST_DEPS:-1}"
PULL_MODELS=""
WORKER_HOSTNAME=""

usage() {
  cat <<'EOF'
Usage: bash setup_worker.sh [--hostname cadybara-worker] [--models model_a,model_b]

Sets up this Linux Mint box as a Cadybara worker:
  - installs required apt packages and Ollama
  - updates this git checkout with git pull --ff-only when clean
  - creates .venv and installs the repo
  - keeps Ollama bound to 127.0.0.1
  - starts a systemd user service for the LAN lab UI on port 8787
  - enables lingering so the user service survives logout/reboot

Options:
  --hostname NAME Set the Linux hostname so the lab is reachable at http://NAME.local:8787/lab/.
  --models LIST   Explicit comma-separated Ollama models to pull now.
  --help          Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --models)
      PULL_MODELS="${2:-}"
      shift 2
      ;;
    --models=*)
      PULL_MODELS="${1#--models=}"
      shift
      ;;
    --hostname)
      WORKER_HOSTNAME="${2:-}"
      shift 2
      ;;
    --hostname=*)
      WORKER_HOSTNAME="${1#--hostname=}"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

step() {
  printf '\n==> %s\n' "$1"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command after setup step: $1" >&2
    exit 1
  fi
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

if [[ ! -f "pyproject.toml" || ! -d "projects/local-running" ]]; then
  echo "Run this script from the cadybara-kitchen repository root." >&2
  exit 1
fi

expected_root="$HOME/cadybara-kitchen"
if [[ "$repo_root" != "$expected_root" ]]; then
  echo "Note: repo is at $repo_root; expected worker path is $expected_root."
  echo "The service will use the current repo path."
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required for apt packages, Ollama service setup, ufw, and lingering." >&2
  exit 1
fi

APT_PACKAGES=(
  avahi-daemon
  build-essential
  ca-certificates
  curl
  git
  iproute2
  logrotate
  pciutils
  python3-dev
  python3-venv
  openssh-server
  ufw
)

step "Installing apt packages"
echo "Packages: ${APT_PACKAGES[*]}"
sudo apt-get update
sudo apt-get install -y "${APT_PACKAGES[@]}"

if [[ -n "$WORKER_HOSTNAME" ]]; then
  if [[ ! "$WORKER_HOSTNAME" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,62}$ ]]; then
    echo "Invalid hostname: $WORKER_HOSTNAME" >&2
    echo "Use letters, numbers, and hyphens; start with a letter or number." >&2
    exit 2
  fi
  step "Setting worker hostname"
  sudo hostnamectl set-hostname "$WORKER_HOSTNAME"
fi

step "Enabling LAN discovery and SSH"
sudo systemctl enable --now avahi-daemon
sudo systemctl enable --now ssh

step "Updating git checkout"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Working tree is dirty; skipping git pull so local edits are preserved."
  else
    if git remote get-url origin >/dev/null 2>&1; then
      git pull --ff-only
    else
      echo "No origin remote is configured; skipping git pull."
    fi
  fi
else
  echo "This directory is not a git checkout; skipping git pull."
fi

step "Installing or verifying Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  tmp_installer="$(mktemp)"
  curl -fsSL https://ollama.com/install.sh -o "$tmp_installer"
  sh "$tmp_installer"
  rm -f "$tmp_installer"
fi
require_command ollama
ollama --version || {
  echo "Ollama is installed but did not report a version. Stop here and inspect the install." >&2
  exit 1
}

step "Configuring Ollama local-only service"
sudo install -d -m 0755 /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/10-cadybara-worker.conf >/dev/null <<EOF
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_NUM_PARALLEL=1"
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ollama

step "Waiting for Ollama API"
for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:11434/api/version >/dev/null || {
  echo "Ollama did not respond on http://127.0.0.1:11434/api/version." >&2
  echo "Diagnostics:" >&2
  systemctl status ollama --no-pager >&2 || true
  journalctl -u ollama -n 80 --no-pager >&2 || true
  exit 1
}

step "Creating Python virtual environment"
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
if [[ "$INSTALL_TEST_DEPS" == "1" ]]; then
  .venv/bin/python -m pip install -e ".[test]"
else
  .venv/bin/python -m pip install -e .
fi

step "Running fast health check"
.venv/bin/python - <<'PY'
from pathlib import Path
import httpx

from cadybara.config import load_config

config = load_config("projects/local-running/configs/example.yaml")
assert config.experiment_id == "example_dry_run_001"
response = httpx.get("http://127.0.0.1:11434/api/version", timeout=5)
response.raise_for_status()
print("imports ok; config parse ok; Ollama API ok")
PY

step "Writing Cadybara user service"
mkdir -p "$HOME/.config/systemd/user"
service_path="$HOME/.config/systemd/user/cadybara-worker.service"
cat > "$service_path" <<EOF
[Unit]
Description=Cadybara LAN worker lab

[Service]
Type=simple
WorkingDirectory=$repo_root
Environment="PYTHONUNBUFFERED=1"
Environment="CADYBARA_OLLAMA_NUM_CTX=$CADYBARA_OLLAMA_NUM_CTX"
Environment="CADYBARA_OLLAMA_NUM_THREAD=$CADYBARA_OLLAMA_NUM_THREAD"
Environment="CADYBARA_DISABLE_MODEL_CLEANUP=1"
Environment="CADYBARA_LAB_DISABLE_AUTO_PULL=1"
ExecStartPre=/usr/bin/mkdir -p $repo_root/projects/local-running/workspace/logs
ExecStart=/usr/bin/bash -lc 'set -o pipefail; "$repo_root/.venv/bin/cadybara" lab --host "$LAB_HOST" --port "$LAB_PORT" 2>&1 | tee -a "$repo_root/projects/local-running/workspace/logs/cadybara-worker.log"'
Restart=always
RestartSec=5
TimeoutStopSec=1800

[Install]
WantedBy=default.target
EOF

step "Enabling lingering and starting Cadybara"
sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now cadybara-worker.service

step "Configuring log rotation"
sudo tee /etc/logrotate.d/cadybara-worker >/dev/null <<EOF
$repo_root/projects/local-running/workspace/logs/*.log {
    size 100M
    rotate 10
    compress
    missingok
    notifempty
    copytruncate
}
EOF

step "Configuring LAN firewall rule for lab UI"
lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
default_iface="$(ip route show default 2>/dev/null | awk '{print $5; exit}' || true)"
lan_cidr=""
if [[ -n "$default_iface" ]]; then
  lan_cidr="$(ip -o -4 addr show dev "$default_iface" | awk '{print $4; exit}' || true)"
fi
if command -v ufw >/dev/null 2>&1 && [[ -n "$lan_cidr" ]]; then
  sudo ufw allow from "$lan_cidr" to any port "$LAB_PORT" proto tcp comment "Cadybara worker lab" || true
  sudo ufw allow from "$lan_cidr" to any port 22 proto tcp comment "Cadybara worker SSH" || true
  echo "Allowed TCP $LAB_PORT from LAN scope $lan_cidr in ufw."
  echo "Allowed TCP 22 from LAN scope $lan_cidr in ufw."
else
  echo "Could not determine LAN CIDR for ufw; if ufw is enabled, allow TCP $LAB_PORT and 22 manually."
fi

if [[ -n "$PULL_MODELS" ]]; then
  step "Pulling explicitly requested models"
  mkdir -p projects/local-running/workspace/worker
  explicit_queue="projects/local-running/workspace/worker/explicit_models.yaml"
  {
    echo 'min_free_disk_gb: 50'
    echo 'cleanup_models: []'
    echo 'manifest_path: "projects/local-running/workspace/worker/explicit_model_pull_manifest.jsonl"'
    echo 'models:'
    IFS=',' read -r -a model_names <<< "$PULL_MODELS"
    priority=1
    for raw_model in "${model_names[@]}"; do
      model="$(echo "$raw_model" | xargs)"
      if [[ -z "$model" ]]; then
        continue
      fi
      echo "  - name: \"$model\""
      echo '    family: "explicit"'
      echo '    role: "explicit-worker-pull"'
      echo "    priority: $priority"
      priority=$((priority + 1))
    done
  } > "$explicit_queue"
  CADYBARA_DISABLE_MODEL_CLEANUP=1 .venv/bin/cadybara pull-models "$explicit_queue"
fi

step "Worker setup complete"
systemctl --user --no-pager status cadybara-worker.service || true
echo ""
echo "Local URL:   http://127.0.0.1:$LAB_PORT/lab/"
worker_host="$(hostname)"
if [[ -n "$worker_host" ]]; then
  echo "mDNS URL:    http://$worker_host.local:$LAB_PORT/lab/"
fi
if [[ -n "$lan_ip" ]]; then
  echo "Network URL: http://$lan_ip:$LAB_PORT/lab/"
else
  echo "Network URL: http://WORKER_LAN_IP:$LAB_PORT/lab/"
fi
if [[ -n "$worker_host" ]]; then
  echo "SSH:         ssh $USER@$worker_host.local"
fi
echo ""
echo "Useful commands:"
echo "  systemctl --user status cadybara-worker.service"
echo "  journalctl --user -u cadybara-worker.service -f"
echo "  tail -f projects/local-running/workspace/logs/cadybara-worker.log"
