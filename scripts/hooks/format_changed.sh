#!/usr/bin/env bash
# PostToolUse(Edit|Write) hook: auto-format the touched Python file with Ruff.
# Receives hook JSON on stdin; never blocks (always exits 0).
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || exit 0

FILE=$("$PY" -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("file_path", ""))
except Exception:
    pass
' 2>/dev/null)

case "$FILE" in
  *.py)
    "$PY" -m ruff format --quiet "$FILE" 2>/dev/null || true
    "$PY" -m ruff check --fix-only --quiet "$FILE" 2>/dev/null || true
    ;;
esac
exit 0
