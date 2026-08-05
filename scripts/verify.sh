#!/usr/bin/env bash
# Full local verification pipeline: format check, lint, types, tests.
# This is the definition-of-done gate; CI runs the same steps.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${TRADEOS_PYTHON:-.venv/bin/python}"
if [ ! -x "$PY" ]; then
  echo "error: $PY not found — run ./scripts/dev_setup.sh first" >&2
  exit 1
fi

echo "==> ruff format --check"
"$PY" -m ruff format --check src tests

echo "==> ruff check"
"$PY" -m ruff check src tests

echo "==> mypy"
"$PY" -m mypy src

echo "==> pytest"
"$PY" -m pytest -q

echo "verify: ALL GREEN"
