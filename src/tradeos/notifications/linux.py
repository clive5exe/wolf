"""Linux desktop notifications via `notify-send` (libnotify).

Same contract as the macOS adapter: the cycle composes the message, the adapter
only delivers. Approvals NEVER happen through a notification (THREAT_MODEL T9)
— banners are informational, so a delivery failure is logged and swallowed
rather than propagated into a decision.
"""

from __future__ import annotations

import subprocess

from tradeos.telemetry.logging import get_logger

_log = get_logger("notifications.linux")


class LinuxNotifier:
    name = "linux"

    def notify(self, title: str, body: str) -> bool:
        try:
            proc = subprocess.run(
                # `--` stops a title or body beginning with "-" being read as a flag.
                ["notify-send", "--app-name=WOLF", "--", title, body],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            _log.warning("notification failed: %s", exc)
            return False
        if proc.returncode != 0:
            _log.warning("notify-send exit %s: %s", proc.returncode, proc.stderr.strip())
            return False
        return True
