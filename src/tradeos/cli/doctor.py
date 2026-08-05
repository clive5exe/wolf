"""`tradeos doctor` — environment diagnosis with fix hints, not stack traces."""

from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass
from enum import StrEnum

from tradeos.runtime.facade import TradeOSRuntime


class CheckStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: CheckStatus
    detail: str
    hint: str = ""


def run_checks(runtime: TradeOSRuntime, *, full: bool = False) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []

    if sys.platform == "darwin":
        checks.append(DoctorCheck("macOS", CheckStatus.OK, platform.mac_ver()[0]))
    else:
        checks.append(
            DoctorCheck(
                "macOS",
                CheckStatus.WARN,
                f"platform is {sys.platform}",
                "TradeOS targets macOS; notifications and Keychain need it",
            )
        )

    version_info = sys.version_info
    if version_info >= (3, 12):
        checks.append(DoctorCheck("Python", CheckStatus.OK, platform.python_version()))
    else:
        checks.append(
            DoctorCheck(
                "Python",
                CheckStatus.FAIL,
                platform.python_version(),
                "install Python 3.12+ and re-run ./scripts/dev_setup.sh",
            )
        )

    try:
        count = sum(1 for _ in runtime.events.iter_events())
        checks.append(DoctorCheck("Event store", CheckStatus.OK, f"open, {count} events recorded"))
    except Exception as exc:  # doctor reports, never crashes
        checks.append(
            DoctorCheck(
                "Event store",
                CheckStatus.FAIL,
                str(exc)[:120],
                "check TRADEOS_DATA_DIR permissions; delete only if you accept losing history",
            )
        )

    status = runtime.provider_status()
    if not status.installed:
        checks.append(
            DoctorCheck(
                "Claude Code",
                CheckStatus.FAIL,
                "not found on PATH",
                "install Claude Code (https://code.claude.com) and run `claude` once to log in",
            )
        )
    elif status.authenticated is False:
        checks.append(
            DoctorCheck(
                "Claude Code",
                CheckStatus.WARN,
                f"installed ({status.version}) but not logged in",
                "run `claude` and complete the login flow",
            )
        )
    else:
        auth = "authenticated" if status.authenticated else "auth state unknown"
        checks.append(DoctorCheck("Claude Code", CheckStatus.OK, f"{status.version} — {auth}"))

    if full and status.installed and status.authenticated is not False:
        result = runtime.provider_health()
        ok = bool(getattr(result, "ok", False))
        if ok:
            duration = getattr(result, "duration_ms", 0)
            cost = getattr(result, "cost_usd", None)
            detail = f"structured round-trip passed in {duration}ms"
            if cost is not None:
                detail += f" (cost ${cost})"
            checks.append(DoctorCheck("Provider probe", CheckStatus.OK, detail))
        else:
            error = getattr(result, "error", None)
            checks.append(
                DoctorCheck(
                    "Provider probe",
                    CheckStatus.FAIL,
                    f"{getattr(error, 'value', error)}: {getattr(result, 'error_detail', '')[:80]}",
                    "check `claude auth status` and your subscription's programmatic usage",
                )
            )

    policy = runtime.active_policy()
    if policy is None:
        checks.append(
            DoctorCheck(
                "Investment policy",
                CheckStatus.WARN,
                "none configured",
                "run `tradeos policy-init-sample` or the TUI onboarding",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "Investment policy",
                CheckStatus.OK,
                f"v{policy.version} active, mode={policy.mode.value}",
            )
        )

    if runtime.kill_switch.is_engaged():
        checks.append(
            DoctorCheck(
                "Kill switch",
                CheckStatus.WARN,
                "ENGAGED — all execution refused",
                "run `tradeos unkill` after reviewing why it was engaged",
            )
        )
    else:
        checks.append(DoctorCheck("Kill switch", CheckStatus.OK, "disengaged"))

    for binary, name, hint in (
        ("osascript", "Notifications", "part of macOS; non-mac platforms lack banners"),
        ("git", "git", "install Xcode command line tools"),
    ):
        if shutil.which(binary):
            checks.append(DoctorCheck(name, CheckStatus.OK, f"{binary} available"))
        else:
            checks.append(DoctorCheck(name, CheckStatus.WARN, f"{binary} missing", hint))

    return checks
