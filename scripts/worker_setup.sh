#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${CONFIG_PATH:-projects/wall-planter-cad-study/configs/family_sweep.yaml}"
PULL_MODELS="${PULL_MODELS:-1}"
RUN_TESTS="${RUN_TESTS:-1}"

step() {
  printf '\n==> %s\n' "$1"
}

step "Checking GitHub remote"
git remote -v

step "Creating Python virtual environment"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

step "Installing Python dependencies"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[test]"

if [ "$RUN_TESTS" = "1" ]; then
  step "Running tests"
  .venv/bin/pytest -v
fi

step "Checking Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not on PATH. Install it from https://ollama.com/download and rerun this script." >&2
  exit 1
fi
ollama --version

if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null; then
  echo "Ollama is installed but not responding on http://127.0.0.1:11434." >&2
  echo "Start Ollama, then rerun this script or run: ollama serve" >&2
fi

if [ "$PULL_MODELS" = "1" ]; then
  step "Pulling configured model queue"
  .venv/bin/cadybara pull-models
fi

step "Worker setup complete"
.venv/bin/cadybara model-status
echo ""
echo "Next: bash scripts/worker_start_lab.sh"
