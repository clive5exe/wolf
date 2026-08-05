"""macOS Keychain access via the `security` CLI (ADR-0010).

Secrets live ONLY here — never in files, SQLite, events, logs, or prompts.
Service names are namespaced ``tradeos.<purpose>``. We never touch other
applications' items (Claude Code manages its own credentials).
"""

from __future__ import annotations

import subprocess

_SECURITY = "/usr/bin/security"
_SERVICE_PREFIX = "tradeos."


class KeychainError(RuntimeError):
    pass


def _service(name: str) -> str:
    if not name or "/" in name or " " in name:
        raise KeychainError(f"invalid secret name: {name!r}")
    return f"{_SERVICE_PREFIX}{name}"


def set_secret(name: str, value: str, account: str = "tradeos") -> None:
    """Store/replace a secret. Uses -U to update in place."""
    result = subprocess.run(
        [_SECURITY, "add-generic-password", "-U", "-s", _service(name), "-a", account, "-w", value],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        # stderr may mention the service but never the secret value
        raise KeychainError(f"keychain write failed for {name}: {result.stderr.strip()}")


def get_secret(name: str, account: str = "tradeos") -> str | None:
    result = subprocess.run(
        [_SECURITY, "find-generic-password", "-s", _service(name), "-a", account, "-w"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return None
    return result.stdout.rstrip("\n")


def delete_secret(name: str, account: str = "tradeos") -> bool:
    result = subprocess.run(
        [_SECURITY, "delete-generic-password", "-s", _service(name), "-a", account],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0
