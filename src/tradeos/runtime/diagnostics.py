"""Environment diagnosis with fix hints, not stack traces.

Lives in the runtime layer (not the CLI) because both interfaces need it: the
CLI renders it as `wolf doctor`, and the TUI boot sequence *is* this check list
startup doubles as diagnosis, so a broken environment can never be booted past.
"""

from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from tradeos.notifications.factory import notifier_status
from tradeos.platform_paths import is_supported_platform, platform_label
from tradeos.security.store import default_secret_store

if TYPE_CHECKING:  # avoids a cycle: the facade imports this module lazily
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

    label = platform_label()
    if sys.platform == "darwin":
        checks.append(DoctorCheck("Platform", CheckStatus.OK, f"{label} {platform.mac_ver()[0]}"))
    elif is_supported_platform():
        checks.append(DoctorCheck("Platform", CheckStatus.OK, f"{label} {platform.release()}"))
    else:
        checks.append(
            DoctorCheck(
                "Platform",
                CheckStatus.WARN,
                f"{label} is untested",
                "macOS and Linux are tested in CI. Nothing is known to break here, "
                "but no one has run it",
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
        checks.append(DoctorCheck("Claude Code", CheckStatus.OK, f"{status.version}, {auth}"))

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
                "run `wolf policy-init-sample` or the TUI onboarding",
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

    engine_rules = runtime.risk_rule_ids()
    checks.append(
        DoctorCheck(
            "Risk engine",
            CheckStatus.OK,
            f"{len(engine_rules)} rules armed",
        )
    )

    if runtime.kill_switch.is_engaged():
        checks.append(
            DoctorCheck(
                "Kill switch",
                CheckStatus.WARN,
                "ENGAGED, all execution refused",
                "run `wolf unkill` after reviewing why it was engaged",
            )
        )
    else:
        checks.append(DoctorCheck("Kill switch", CheckStatus.OK, "disengaged"))

    # Secrets are load-bearing: no secure store means credentials cannot be
    # held at all, because WOLF refuses to write them to disk as a fallback.
    store = default_secret_store()
    if store.available():
        checks.append(DoctorCheck("Secret store", CheckStatus.OK, store.name))
    else:
        checks.append(
            DoctorCheck(
                "Secret store",
                CheckStatus.WARN,
                getattr(store, "reason", "unavailable"),
                "paper mode needs no secrets, a live broker will refuse to start "
                "without an OS credential store",
            )
        )

    ok, detail = notifier_status()
    checks.append(
        DoctorCheck(
            "Notifications",
            CheckStatus.OK if ok else CheckStatus.WARN,
            detail,
            "" if ok else "cycles still run and record, you just lose the banner",
        )
    )

    if shutil.which("git"):
        checks.append(DoctorCheck("git", CheckStatus.OK, "available"))
    else:
        checks.append(
            DoctorCheck("git", CheckStatus.WARN, "missing", "needed only for development")
        )

    return checks
