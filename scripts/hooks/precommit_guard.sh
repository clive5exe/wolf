#!/usr/bin/env bash
# PreToolUse(Bash) hook: when the agent attempts `git commit`, require the
# quick safety scan (secrets + forbidden patterns) to pass first.
# Exit 2 blocks the tool call and feeds stderr back to the agent.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

CMD=$(python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("command", ""))
except Exception:
    pass
' 2>/dev/null)

case "$CMD" in
  *"git commit"*)
    if ! "$ROOT/scripts/safety_check.sh" --quick >/tmp/tradeos_guard.log 2>&1; then
      echo "BLOCKED: safety_check.sh --quick failed. Fix before committing:" >&2
      tail -n 30 /tmp/tradeos_guard.log >&2
      exit 2
    fi
    ;;
esac
exit 0
