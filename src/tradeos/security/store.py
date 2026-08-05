"""Secret storage across operating systems (ADR-0010).

Secrets live ONLY in an OS-provided credential store. Never in files, SQLite,
events, logs, or prompts.

**The load-bearing rule of this module: there is no fallback.** If no OS
keystore is available, every operation raises. It would be trivially easy to
"helpfully" degrade to a dotfile when libsecret is missing, and that single
convenience would silently convert a machine with brokerage credentials from
protected to unprotected. With nothing on screen to say so. A loud failure
that stops the user is the correct outcome. A quiet one that keeps working is
the dangerous one.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Protocol, runtime_checkable

#: Service namespace for stored items. Deliberately NOT renamed alongside the
#: product, for the same reason the database filename was not: this string is
#: the address of state that already exists on a user's machine. Changing it
#: would not migrate secrets, it would orphan them. Leaving WOLF unable to
#: find a credential that is still sitting in the keystore.
_SERVICE_PREFIX = "tradeos."
_TIMEOUT_S = 10


class SecretStoreError(RuntimeError):
    """A secret operation failed, or no secure store exists on this system."""


class NoSecureStore(SecretStoreError):
    """No OS credential store is available. Never downgraded to a warning."""


def validate_name(name: str) -> str:
    if not name or "/" in name or " " in name:
        raise SecretStoreError(f"invalid secret name: {name!r}")
    return f"{_SERVICE_PREFIX}{name}"


@runtime_checkable
class SecretStore(Protocol):
    name: str

    def available(self) -> bool: ...
    def set_secret(self, name: str, value: str, account: str = "wolf") -> None: ...
    def get_secret(self, name: str, account: str = "wolf") -> str | None: ...
    def delete_secret(self, name: str, account: str = "wolf") -> bool: ...


class KeychainStore:
    """macOS Keychain via the `security` CLI."""

    name = "macos-keychain"
    _BIN = "/usr/bin/security"

    def available(self) -> bool:
        return sys.platform == "darwin" and shutil.which(self._BIN) is not None

    def set_secret(self, name: str, value: str, account: str = "wolf") -> None:
        # -U updates in place rather than stacking duplicate items.
        result = subprocess.run(
            [
                self._BIN,
                "add-generic-password",
                "-U",
                "-s",
                validate_name(name),
                "-a",
                account,
                "-w",
                value,
            ],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
        if result.returncode != 0:
            # stderr may name the service. It never contains the value itself.
            raise SecretStoreError(f"keychain write failed for {name}: {result.stderr.strip()}")

    def get_secret(self, name: str, account: str = "wolf") -> str | None:
        result = subprocess.run(
            [self._BIN, "find-generic-password", "-s", validate_name(name), "-a", account, "-w"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
        return None if result.returncode != 0 else result.stdout.rstrip("\n")

    def delete_secret(self, name: str, account: str = "wolf") -> bool:
        result = subprocess.run(
            [self._BIN, "delete-generic-password", "-s", validate_name(name), "-a", account],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
        return result.returncode == 0


class SecretToolStore:
    """Linux keyring via `secret-tool` (libsecret): GNOME Keyring, KWallet."""

    name = "libsecret"
    _BIN = "secret-tool"

    def available(self) -> bool:
        return sys.platform.startswith("linux") and shutil.which(self._BIN) is not None

    def set_secret(self, name: str, value: str, account: str = "wolf") -> None:
        service = validate_name(name)
        result = subprocess.run(
            [self._BIN, "store", "--label", service, "service", service, "account", account],
            input=value,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
        if result.returncode != 0:
            raise SecretStoreError(f"libsecret write failed for {name}: {result.stderr.strip()}")

    def get_secret(self, name: str, account: str = "wolf") -> str | None:
        result = subprocess.run(
            [self._BIN, "lookup", "service", validate_name(name), "account", account],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
        # secret-tool omits the trailing newline that `security` adds.
        return None if result.returncode != 0 else result.stdout.rstrip("\n")

    def delete_secret(self, name: str, account: str = "wolf") -> bool:
        result = subprocess.run(
            [self._BIN, "clear", "service", validate_name(name), "account", account],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
        return result.returncode == 0


class UnavailableStore:
    """Stands in when no OS keystore exists, and refuses every operation.

    Returned rather than raising at import time so `wolf doctor` can still run
    and *explain* the problem instead of crashing on startup.
    """

    name = "none"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def available(self) -> bool:
        return False

    def _refuse(self) -> None:
        raise NoSecureStore(
            f"{self.reason}. WOLF stores secrets only in an OS credential store "
            f"and will not write them to disk. On Linux install libsecret "
            f"(`secret-tool`). On macOS the Keychain is built in."
        )

    def set_secret(self, name: str, value: str, account: str = "wolf") -> None:
        self._refuse()

    def get_secret(self, name: str, account: str = "wolf") -> str | None:
        self._refuse()
        return None

    def delete_secret(self, name: str, account: str = "wolf") -> bool:
        self._refuse()
        return False


def default_secret_store() -> SecretStore:
    """The credential store for this machine, or one that refuses everything."""
    for store in (KeychainStore(), SecretToolStore()):
        if store.available():
            return store
    if sys.platform == "win32":
        return UnavailableStore("Windows credential storage is not implemented yet")
    if sys.platform.startswith("linux"):
        return UnavailableStore("`secret-tool` was not found on PATH")
    return UnavailableStore(f"no supported credential store for {sys.platform}")
