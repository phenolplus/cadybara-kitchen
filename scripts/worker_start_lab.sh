#!/usr/bin/env bash
set -euo pipefail

HOST_ADDRESS="${HOST_ADDRESS:-0.0.0.0}"
PORT="${PORT:-8787}"

if [ ! -d ".venv" ]; then
  echo ".venv is missing. Run scripts/worker_setup.sh first." >&2
  exit 1
fi

LOCAL_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"

echo "Starting cadybara worker lab..."
echo "Local URL:   http://127.0.0.1:${PORT}/lab/"
if [ -n "$LOCAL_IP" ]; then
  echo "Network URL: http://${LOCAL_IP}:${PORT}/lab/"
fi
echo "Use Stop After Current in the UI to pause a run safely."

.venv/bin/cadybara lab --host "$HOST_ADDRESS" --port "$PORT"
