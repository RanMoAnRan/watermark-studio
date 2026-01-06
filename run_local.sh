#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PY="$ROOT_DIR/.venv/bin/python"
PIP="$ROOT_DIR/.venv/bin/pip"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3 || true)"
  if [[ -z "$PY" ]]; then
    echo "Python not found. Please install Python 3 or create .venv." >&2
    exit 1
  fi
  echo "Using system python: $PY"
else
  echo "Using venv python: $PY"
fi

if [[ -x "$PIP" ]]; then
  echo "Installing deps from requirements.txt (if needed)..."
  "$PIP" install -r requirements.txt
else
  echo "Tip: create a venv for better isolation: python3 -m venv .venv"
fi

echo
echo "Starting server (PORT defaults to 5050; will auto-pick next free port if occupied)"
echo "Press CTRL+C to stop."
echo
"$PY" app.py
