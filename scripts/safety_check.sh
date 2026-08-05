#!/usr/bin/env bash
# Safety gate: secrets scan, forbidden-pattern scan, architecture-boundary
# scan, then (unless --quick) the safety test suite.
# Enforces THREAT_MODEL.md standing requirements and ARCHITECTURE.md §2 edges.
set -uo pipefail
cd "$(dirname "$0")/.."

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1
FAIL=0

say_fail() { echo "SAFETY FAIL: $1" >&2; FAIL=1; }

# Files under version control (or all tracked-ish files pre-init)
FILES=$(git ls-files 2>/dev/null || find src tests scripts specs -type f 2>/dev/null)

# --- 1. Secrets scan -------------------------------------------------------
# Lines tagged `safety-scan-allow` are deliberate scanner/redactor fixtures —
# the tag makes every exemption grep-able and reviewable.
SECRET_HITS=$(echo "$FILES" | xargs grep -InE \
  '(AKIA[0-9A-Z]{16}|-----BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY|xox[baprs]-[0-9A-Za-z-]{10,}|sk-[A-Za-z0-9]{20,}|rh-api-[A-Za-z0-9-]{8,})' \
  2>/dev/null | grep -v 'safety_check.sh' | grep -v 'safety-scan-allow' || true)
if [ -n "$SECRET_HITS" ]; then
  echo "$SECRET_HITS" >&2
  say_fail "credential-shaped strings found in tracked files"
fi

ASSIGN_HITS=$(echo "$FILES" | grep -E '\.(py|toml|json|yaml|yml|sh)$' | xargs grep -InE \
  '(api_key|apikey|secret|token|passwd|password)["'"'"']?\s*[:=]\s*["'"'"'][A-Za-z0-9+/_-]{16,}["'"'"']' \
  2>/dev/null | grep -viE '(example|placeholder|redact|fake|dummy|test)' || true)
if [ -n "$ASSIGN_HITS" ]; then
  echo "$ASSIGN_HITS" >&2
  say_fail "hard-coded secret-like assignment found"
fi

# --- 2. Forbidden code patterns -------------------------------------------
if [ -d src ]; then
  H=$(grep -rn "shell=True" src/ 2>/dev/null || true)
  [ -n "$H" ] && { echo "$H" >&2; say_fail "shell=True is forbidden"; }

  H=$(grep -rnE '(^|[^A-Za-z_.])eval\(' src/ 2>/dev/null || true)
  [ -n "$H" ] && { echo "$H" >&2; say_fail "eval() is forbidden"; }

  # ValidatedOrder may be constructed only inside the risk engine (ADR-0008)
  H=$(grep -rn "ValidatedOrder(" src/ 2>/dev/null | grep -v "src/tradeos/risk/" | grep -v "src/tradeos/domain/" || true)
  [ -n "$H" ] && { echo "$H" >&2; say_fail "ValidatedOrder constructed outside risk engine"; }

  # submit_order may be *called* only from the execution layer
  H=$(grep -rnE '\.submit_order\(' src/ 2>/dev/null | grep -v "src/tradeos/execution/" || true)
  [ -n "$H" ] && { echo "$H" >&2; say_fail "submit_order called outside execution layer"; }

  # Interfaces must not import core internals (ARCHITECTURE §2)
  H=$(grep -rnE 'from tradeos\.(brokers|providers|risk|execution|storage)' src/tradeos/cli src/tradeos/tui 2>/dev/null || true)
  [ -n "$H" ] && { echo "$H" >&2; say_fail "interface layer imports core internals directly"; }

  # Strategies and providers must not reach brokers
  H=$(grep -rnE 'from tradeos\.brokers' src/tradeos/strategies src/tradeos/providers 2>/dev/null || true)
  [ -n "$H" ] && { echo "$H" >&2; say_fail "strategies/providers import brokers"; }
fi

# --- 3. Safety test suite --------------------------------------------------
if [ "$QUICK" -eq 0 ] && [ -d tests/safety ]; then
  PY="${TRADEOS_PYTHON:-.venv/bin/python}"
  if [ -x "$PY" ]; then
    if ! "$PY" -m pytest tests/safety -q; then
      say_fail "safety test suite failed"
    fi
  else
    say_fail "no interpreter for safety tests (run ./scripts/dev_setup.sh)"
  fi
fi

if [ "$FAIL" -ne 0 ]; then
  echo "safety_check: FAILED" >&2
  exit 1
fi
echo "safety_check: PASSED$( [ $QUICK -eq 1 ] && echo ' (quick)' )"
