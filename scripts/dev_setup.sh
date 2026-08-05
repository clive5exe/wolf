#!/usr/bin/env bash
# One-shot developer setup: venv, editable install with dev extras, git hooks.
set -euo pipefail
cd "$(dirname "$0")/.."

PYBIN="${PYTHON:-python3}"
echo "==> creating .venv with $($PYBIN --version)"
"$PYBIN" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
echo "==> installing tradeos (editable) + dev tools"
.venv/bin/python -m pip install --quiet -e ".[dev]"

echo "==> installing git pre-commit hook (quick safety scan)"
mkdir -p .git/hooks
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
exec "$(git rev-parse --show-toplevel)/scripts/safety_check.sh" --quick
HOOK
chmod +x .git/hooks/pre-commit

echo
echo "Setup complete. Next steps:"
echo "  source .venv/bin/activate"
echo "  tradeos doctor        # check your environment"
echo "  ./scripts/verify.sh   # run the full pipeline"
