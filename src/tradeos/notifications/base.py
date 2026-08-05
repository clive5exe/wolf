"""Notifier protocol. Message contract (COMMS requirement): bodies must carry
the exact action, quantities, mode, strategy version, and an audit identifier
the cycle composes these. Adapters only deliver."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    name: str

    def notify(self, title: str, body: str) -> bool: ...


class NullNotifier:
    """Records instead of delivering. For tests and headless CI."""

    name = "null"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def notify(self, title: str, body: str) -> bool:
        self.sent.append((title, body))
        return True
