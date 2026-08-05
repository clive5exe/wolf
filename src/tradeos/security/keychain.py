"""macOS Keychain access (ADR-0010).

Retained for continuity. The cross-platform entry point is
``tradeos.security.store.default_secret_store``. Secrets live ONLY in an OS
credential store. Never in files, SQLite, events, logs, or prompts.
"""

from __future__ import annotations

from tradeos.security.store import KeychainStore, SecretStoreError

KeychainError = SecretStoreError
_store = KeychainStore()


def set_secret(name: str, value: str, account: str = "wolf") -> None:
    _store.set_secret(name, value, account)


def get_secret(name: str, account: str = "wolf") -> str | None:
    return _store.get_secret(name, account)


def delete_secret(name: str, account: str = "wolf") -> bool:
    return _store.delete_secret(name, account)
