#!/usr/bin/env sh
# WOLF installer.
#
# Piping a script from the internet into a shell deserves suspicion, so this
# one is written to be read first and to say what it will do before doing it:
#
#     curl -fsSL https://wolf.clive5.com/install.sh | less
#     curl -fsSL https://wolf.clive5.com/install.sh | sh
#
# It touches exactly two paths, both printed below, and installs nothing
# system-wide. Set WOLF_HOME to relocate it, or WOLF_REF to pin a tag.

set -eu

WOLF_HOME="${WOLF_HOME:-$HOME/.wolf}"
WOLF_REF="${WOLF_REF:-main}"
WOLF_REPO="${WOLF_REPO:-https://github.com/clive5exe/wolf.git}"
BIN_DIR="${WOLF_BIN_DIR:-$HOME/.local/bin}"

AMBER='\033[38;2;240;180;92m'
GREEN='\033[38;2;126;212;145m'
RED='\033[38;2;240;140;140m'
DIM='\033[38;2;87;97;111m'
BRIGHT='\033[1;97m'
OFF='\033[0m'

say()  { printf '%b\n' "$*"; }
step() { printf '  %b▸%b %s\n' "$AMBER" "$OFF" "$1"; }
ok()   { printf '  %b✓%b %s\n' "$GREEN" "$OFF" "$1"; }
die()  { printf '  %b✗%b %s\n' "$RED" "$OFF" "$1" >&2; exit 1; }

say ""
say "${BRIGHT}    ██╗    ██╗ ██████╗ ██╗     ███████╗${OFF}"
say "${BRIGHT}    ██║    ██║██╔═══██╗██║     ██╔════╝${OFF}"
say "${BRIGHT}    ██║ █╗ ██║██║   ██║██║     █████╗  ${OFF}"
say "${BRIGHT}    ██║███╗██║██║   ██║██║     ██╔══╝  ${OFF}"
say "${BRIGHT}    ╚███╔███╔╝╚██████╔╝███████╗██║     ${OFF}"
say "${DIM}     ╚══╝╚══╝  ╚═════╝ ╚══════╝╚═╝     ${OFF}"
say ""
say "    ${AMBER}watches obsessively, lacks feelings${OFF}"
say "    ${DIM}the model advises · your machine decides${OFF}"
say ""
say "    ${DIM}experimental · paper trading only · not investment advice${OFF}"
say ""

# -- say what will happen, before it happens ---------------------------------
say "  ${DIM}This will:${OFF}"
say "    ${DIM}· clone ${WOLF_REPO} (${WOLF_REF}) into${OFF} $WOLF_HOME"
say "    ${DIM}· create a virtualenv there and install WOLF into it${OFF}"
say "    ${DIM}· link the${OFF} wolf ${DIM}command into${OFF} $BIN_DIR"
say "    ${DIM}· nothing system-wide, no sudo, no account with anyone${OFF}"
say ""
say "  ${DIM}WOLF does use the network when running — your AI provider, your broker,${OFF}"
say "  ${DIM}public filings. Your portfolio and decisions stay in a file you own.${OFF}"
say ""

# -- checks ------------------------------------------------------------------
step "checking your system"

case "$(uname -s)" in
  Darwin) PLATFORM="macOS" ;;
  Linux)  PLATFORM="Linux" ;;
  *)      PLATFORM="$(uname -s)"
          say "  ${DIM}note: ${PLATFORM} is untested — macOS and Linux are covered by CI${OFF}" ;;
esac
ok "$PLATFORM"

PYTHON=""
for candidate in python3.13 python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
  then PYTHON="$candidate"; break; fi
done
[ -n "$PYTHON" ] || die "Python 3.12+ not found. Install it, then re-run this."
ok "$($PYTHON --version)"

command -v git >/dev/null 2>&1 || die "git not found. Install it, then re-run this."
ok "git"

# -- install -----------------------------------------------------------------
if [ -d "$WOLF_HOME/.git" ]; then
  step "updating $WOLF_HOME"
  git -C "$WOLF_HOME" fetch --quiet origin "$WOLF_REF"
  git -C "$WOLF_HOME" checkout --quiet FETCH_HEAD
else
  step "cloning into $WOLF_HOME"
  git clone --quiet --depth 1 --branch "$WOLF_REF" "$WOLF_REPO" "$WOLF_HOME" 2>/dev/null \
    || git clone --quiet "$WOLF_REPO" "$WOLF_HOME"
fi
ok "source ready"

step "creating an isolated environment"
"$PYTHON" -m venv "$WOLF_HOME/.venv"
"$WOLF_HOME/.venv/bin/python" -m pip install --quiet --upgrade pip
ok "virtualenv"

step "installing WOLF"
"$WOLF_HOME/.venv/bin/python" -m pip install --quiet -e "$WOLF_HOME"
ok "installed"

step "linking the wolf command"
mkdir -p "$BIN_DIR"
ln -sf "$WOLF_HOME/.venv/bin/wolf" "$BIN_DIR/wolf"
ok "$BIN_DIR/wolf"

# -- hand off ----------------------------------------------------------------
say ""
if ! command -v wolf >/dev/null 2>&1; then
  say "  ${AMBER}$BIN_DIR is not on your PATH.${OFF} Add this to your shell profile:"
  say "      ${BRIGHT}export PATH=\"\$PATH:$BIN_DIR\"${OFF}"
  say ""
fi

say "  ${GREEN}ready${OFF}${DIM} — next:${OFF}"
say "      ${BRIGHT}wolf setup${OFF}    ${DIM}describe your goals; confirm every limit yourself${OFF}"
say "      ${BRIGHT}wolf doctor${OFF}   ${DIM}check the environment${OFF}"
say "      ${BRIGHT}wolf tui${OFF}      ${DIM}enter the den${OFF}"
say ""
say "  ${DIM}WOLF ships with no real-money path. v0.1 is paper trading by design.${OFF}"
say ""
