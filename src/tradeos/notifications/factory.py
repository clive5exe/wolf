"""Pick a notifier for this machine.

Notifications are informational only. Approvals never happen through them
(THREAT_MODEL T9): so an unavailable notifier degrades to silence rather than
blocking a decision cycle. That is the opposite of the secrets rule in
``security.store``, and deliberately so: a missing banner costs you awareness,
a missing keystore would cost you your credentials.
"""

from __future__ import annotations

import shutil
import sys

from tradeos.notifications.base import Notifier, NullNotifier


def default_notifier() -> Notifier:
    """Best available notifier, or a null one that records instead of delivering."""
    if sys.platform == "darwin" and shutil.which("/usr/bin/osascript"):
        from tradeos.notifications.macos import MacNotifier

        return MacNotifier()
    if sys.platform.startswith("linux") and shutil.which("notify-send"):
        from tradeos.notifications.linux import LinuxNotifier

        return LinuxNotifier()
    return NullNotifier()


def notifier_status() -> tuple[bool, str]:
    """(available, explanation): for `wolf doctor`."""
    if sys.platform == "darwin":
        if shutil.which("/usr/bin/osascript"):
            return True, "osascript available"
        return False, "osascript missing (unusual on macOS)"
    if sys.platform.startswith("linux"):
        if shutil.which("notify-send"):
            return True, "notify-send available"
        return False, "notify-send missing, install libnotify for desktop banners"
    return False, f"no desktop notifier for {sys.platform}, cycles still run and record"
