"""Communication layer: notifier protocol + macOS adapter."""

from tradeos.notifications.base import Notifier, NullNotifier
from tradeos.notifications.macos import MacNotifier

__all__ = ["MacNotifier", "Notifier", "NullNotifier"]
