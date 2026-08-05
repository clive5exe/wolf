"""macOS notifications via `osascript display notification` (RESEARCH_NOTES §3).

Chosen for zero dependencies; limitation: Notification Center attributes the
banner to the scripting process, not "WOLF". terminal-notifier is a
documented optional upgrade. Approvals NEVER happen through notifications
(THREAT_MODEL T9) — banners are informational.
"""

from __future__ import annotations

import subprocess

from tradeos.telemetry.logging import get_logger

_log = get_logger("notifications.macos")


class MacNotifier:
    name = "macos"

    def notify(self, title: str, body: str) -> bool:
        # AppleScript string literals: escape backslashes and double quotes.
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
        safe_body = body.replace("\\", "\\\\").replace('"', '\\"')
        script = f'display notification "{safe_body}" with title "{safe_title}"'
        try:
            proc = subprocess.run(
                ["/usr/bin/osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            _log.warning("notification failed: %s", exc)
            return False
        if proc.returncode != 0:
            _log.warning("osascript exit %s: %s", proc.returncode, proc.stderr.strip())
            return False
        return True
