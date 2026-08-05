"""Where WOLF keeps its state, per operating system.

There was never an architectural reason for macOS-only — the risk engine,
event store, strategies, and TUI are all portable. The mac assumption lived in
three unexamined places, and this module removes one of them.

Each platform's convention is followed rather than inventing a cross-platform
directory: a user's backup tooling, permissions model, and cleanup habits all
key off the standard location.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Kept as the primary override for continuity with existing installs; the
#: WOLF-named variable is preferred and wins if both are set.
_LEGACY_ENV = "TRADEOS_DATA_DIR"
_ENV = "WOLF_DATA_DIR"

_APP = "WOLF"


#: The event store's filename. Deliberately NOT renamed alongside the product.
#: The log is append-only and is the audit source of truth, so a rename that
#: leaves an existing install pointing at an empty database would destroy
#: history silently — the precise failure this project exists to prevent.
DB_FILENAME = "tradeos.db"

#: Pre-rename location. Still authoritative when it holds a database.
_LEGACY_MAC_DIR = Path.home() / "Library" / "Application Support" / "TradeOS"


def legacy_data_dir() -> Path | None:
    """An existing pre-rename data directory, if one holds a database."""
    if (_LEGACY_MAC_DIR / DB_FILENAME).exists():
        return _LEGACY_MAC_DIR
    return None


def default_data_dir() -> Path:
    """The event store's home directory.

    macOS   ``~/Library/Application Support/WOLF``
    Linux   ``$XDG_DATA_HOME/wolf`` (default ``~/.local/share/wolf``)
    Windows ``%LOCALAPPDATA%\\WOLF``
    other   ``~/.wolf`` — a documented fallback, not a claim of support

    An existing pre-rename directory wins over all of these. Adopting it in
    place is safer than moving it: nothing is copied, nothing is deleted, and
    a half-finished migration cannot lose an audit log.
    """
    override = os.environ.get(_ENV) or os.environ.get(_LEGACY_ENV)
    if override:
        return Path(override).expanduser()

    legacy = legacy_data_dir()
    if legacy is not None:
        return legacy

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / _APP
    if sys.platform.startswith("linux"):
        xdg = os.environ.get("XDG_DATA_HOME")
        return (Path(xdg) if xdg else Path.home() / ".local" / "share") / _APP.lower()
    return Path.home() / f".{_APP.lower()}"


def platform_label() -> str:
    """Human-readable platform name for diagnostics."""
    return {
        "darwin": "macOS",
        "win32": "Windows",
    }.get(sys.platform, "Linux" if sys.platform.startswith("linux") else sys.platform)


def is_supported_platform() -> bool:
    """macOS and Linux are supported and tested in CI.

    Windows is deliberately *not* claimed: nothing in the codebase is known to
    break there, but no one has run it, and this project has already learned
    once that an untested claim in the README is a claim you get called on.
    """
    return sys.platform == "darwin" or sys.platform.startswith("linux")
