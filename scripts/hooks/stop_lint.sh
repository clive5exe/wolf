#!/usr/bin/env bash
# Stop hook: fast lint gate before the agent declares itself done.
# Exit 2 sends the errors back so the agent fixes them before stopping.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || exit 0
[ -d "$ROOT/src" ] || exit 0

OUT=$("$PY" -m ruff check "$ROOT/src" "$ROOT/tests" 2>&1)
if [ $? -ne 0 ]; then
  echo "Ruff findings outstanding — fix before finishing:" >&2
  echo "$OUT" | head -n 40 >&2
  exit 2
fi
exit 0
