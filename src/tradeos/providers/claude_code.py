"""Claude Code provider adapter (ADR-0003, PROVIDER_SPEC §3).

Uses only documented CLI behavior (RESEARCH_NOTES §1):
- detection: `claude --version`, `claude auth status`
- structured query: `claude -p <prompt> --output-format json --json-schema <schema>`
  → envelope fields `structured_output` / `result` / `is_error` /
  `total_cost_usd` / `session_id`

The adapter never reads or writes credentials — authentication belongs to the
user's own `claude` login. No tools are granted; `--max-turns` defaults to 1.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from decimal import Decimal
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from tradeos.domain.common import new_ulid
from tradeos.domain.thesis import HealthProbe
from tradeos.events.store import EventStore
from tradeos.events.types import EventType
from tradeos.providers.base import (
    ProviderCapability,
    ProviderErrorKind,
    ProviderResult,
    ProviderStatus,
)
from tradeos.telemetry.logging import get_logger, redact

T = TypeVar("T", bound=BaseModel)

_log = get_logger("providers.claude_code")
_EXCERPT_LIMIT = 2000
_RATE_LIMIT_MARKERS = ("rate limit", "usage limit", "429", "overloaded")
_NOT_AUTH_MARKERS = ("not logged in", "logged out", "please log in", "please run /login")


class ClaudeCodeProvider:
    name = "claude_code"

    def __init__(
        self,
        *,
        executable: str | None = None,
        event_store: EventStore | None = None,
        default_model: str | None = None,
    ) -> None:
        self._executable_override = executable
        self._events = event_store
        self._default_model = default_model

    # -- protocol --------------------------------------------------------------

    def capabilities(self) -> frozenset[ProviderCapability]:
        # Only documented capabilities are declared (PROVIDER_SPEC §4):
        # native --json-schema structured output; --resume sessions.
        return frozenset({ProviderCapability.STRUCTURED_OUTPUT, ProviderCapability.SESSIONS})

    def detect(self) -> ProviderStatus:
        exe = self._find_executable()
        if exe is None:
            return ProviderStatus(
                installed=False,
                detail="claude CLI not found on PATH — install Claude Code and run `claude` once",
            )
        version = self._read_version(exe)
        authenticated, auth_detail = self._read_auth_status(exe)
        return ProviderStatus(
            installed=True,
            version=version,
            authenticated=authenticated,
            detail=auth_detail,
        )

    def health_check(self) -> ProviderResult[HealthProbe]:
        nonce = new_ulid()[:8]
        result = self.query_structured(
            prompt=(
                "This is an automated health probe. Respond with structured output: "
                f'set status to exactly "ok" and echo to exactly "{nonce}".'
            ),
            schema=HealthProbe,
            timeout_s=120,
            max_turns=1,
        )
        if result.ok and result.value is not None and result.value.echo != nonce:
            return ProviderResult(
                ok=False,
                error=ProviderErrorKind.INVALID_OUTPUT,
                error_detail=f"echo mismatch: expected {nonce}, got {result.value.echo}",
                duration_ms=result.duration_ms,
            )
        return result

    def query_structured(
        self,
        *,
        prompt: str,
        schema: type[T],
        timeout_s: int = 120,
        max_turns: int = 1,
        model: str | None = None,
    ) -> ProviderResult[T]:
        exe = self._find_executable()
        if exe is None:
            return ProviderResult(
                ok=False,
                error=ProviderErrorKind.NOT_INSTALLED,
                error_detail="claude CLI not found on PATH",
            )
        schema_json = json.dumps(schema.model_json_schema())
        self._record(
            EventType.PROVIDER_QUERY,
            {
                "provider": self.name,
                "schema": schema.__name__,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "prompt_chars": len(prompt),
                "max_turns": max_turns,
            },
        )

        attempt_prompt = prompt
        last_error_detail = ""
        started = time.monotonic()
        for attempt in (1, 2):
            outcome = self._invoke(
                exe,
                attempt_prompt,
                schema_json,
                timeout_s=timeout_s,
                max_turns=max_turns,
                model=model or self._default_model,
            )
            if isinstance(outcome, ProviderResult):
                self._record_error(outcome)
                return outcome  # transport-level failure: no retry value in-cycle

            envelope = outcome
            duration_ms = int((time.monotonic() - started) * 1000)
            structured = self._extract_structured(envelope)
            try:
                value = schema.model_validate(structured)
            except (ValidationError, TypeError, ValueError) as exc:
                last_error_detail = redact(str(exc))[:_EXCERPT_LIMIT]
                if attempt == 1:
                    attempt_prompt = (
                        f"{prompt}\n\nYour previous response failed schema validation "
                        f"with these errors — respond again, strictly matching the "
                        f"schema:\n{last_error_detail}"
                    )
                    continue
                failure: ProviderResult[T] = ProviderResult(
                    ok=False,
                    error=ProviderErrorKind.INVALID_OUTPUT,
                    error_detail=last_error_detail,
                    raw_excerpt=redact(json.dumps(structured)[:_EXCERPT_LIMIT])
                    if structured is not None
                    else None,
                    duration_ms=duration_ms,
                    cost_usd=self._cost(envelope),
                    session_id=envelope.get("session_id"),
                )
                self._record_error(failure)
                return failure

            success: ProviderResult[T] = ProviderResult(
                ok=True,
                value=value,
                duration_ms=duration_ms,
                cost_usd=self._cost(envelope),
                session_id=envelope.get("session_id"),
            )
            self._record(
                EventType.PROVIDER_RESPONSE,
                {
                    "provider": self.name,
                    "schema": schema.__name__,
                    "duration_ms": success.duration_ms,
                    "cost_usd": str(success.cost_usd) if success.cost_usd is not None else None,
                    "attempt": attempt,
                },
            )
            return success

        raise AssertionError("unreachable")  # pragma: no cover

    # -- internals -------------------------------------------------------------

    def _find_executable(self) -> str | None:
        return self._executable_override or shutil.which("claude")

    @staticmethod
    def _read_version(exe: str) -> str | None:
        try:
            proc = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return proc.stdout.strip() or None if proc.returncode == 0 else None

    @staticmethod
    def _read_auth_status(exe: str) -> tuple[bool | None, str]:
        """`claude auth status` exit-code semantics are undocumented
        (RESEARCH_NOTES §6.2) — parse output defensively; unknown stays None."""
        try:
            proc = subprocess.run(
                [exe, "auth", "status"], capture_output=True, text=True, timeout=15
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, "auth status probe failed to run"
        text = f"{proc.stdout}\n{proc.stderr}".lower()
        if any(marker in text for marker in _NOT_AUTH_MARKERS):
            return False, "claude CLI is installed but not logged in — run `claude` to log in"
        if proc.returncode == 0 and text.strip():
            return True, "claude CLI authenticated"
        return None, "authentication state unknown — health check will probe"

    def _invoke(
        self,
        exe: str,
        prompt: str,
        schema_json: str,
        *,
        timeout_s: int,
        max_turns: int,
        model: str | None,
    ) -> dict[str, Any] | ProviderResult[Any]:
        argv = [
            exe,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--json-schema",
            schema_json,
            "--max-turns",
            str(max_turns),
        ]
        if model:
            argv += ["--model", model]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return ProviderResult(
                ok=False,
                error=ProviderErrorKind.TIMEOUT,
                error_detail=f"claude CLI exceeded {timeout_s}s and was killed",
            )
        except OSError as exc:
            return ProviderResult(
                ok=False, error=ProviderErrorKind.CRASHED, error_detail=redact(str(exc))
            )

        combined = f"{proc.stdout}\n{proc.stderr}".lower()
        if proc.returncode != 0:
            if any(marker in combined for marker in _RATE_LIMIT_MARKERS):
                kind = ProviderErrorKind.RATE_LIMITED
            elif any(marker in combined for marker in _NOT_AUTH_MARKERS):
                kind = ProviderErrorKind.NOT_AUTHENTICATED
            else:
                kind = ProviderErrorKind.CRASHED
            return ProviderResult(
                ok=False,
                error=kind,
                error_detail=f"exit code {proc.returncode}",
                raw_excerpt=redact(proc.stderr[:_EXCERPT_LIMIT]),
            )
        try:
            envelope: dict[str, Any] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return ProviderResult(
                ok=False,
                error=ProviderErrorKind.CRASHED,
                error_detail="stdout was not the documented JSON envelope",
                raw_excerpt=redact(proc.stdout[:_EXCERPT_LIMIT]),
            )
        if envelope.get("is_error"):
            return ProviderResult(
                ok=False,
                error=ProviderErrorKind.CRASHED,
                error_detail="envelope reported is_error",
                raw_excerpt=redact(json.dumps(envelope)[:_EXCERPT_LIMIT]),
            )
        return envelope

    @staticmethod
    def _extract_structured(envelope: dict[str, Any]) -> Any:
        """Prefer the documented `structured_output` field; fall back to parsing
        `result` text as JSON (older CLIs), stripping markdown fences."""
        if "structured_output" in envelope and envelope["structured_output"] is not None:
            return envelope["structured_output"]
        result = envelope.get("result")
        if not isinstance(result, str):
            return result
        text = result.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _cost(envelope: dict[str, Any]) -> Decimal | None:
        raw = envelope.get("total_cost_usd")
        if raw is None:
            return None
        try:
            return Decimal(str(raw))
        except ArithmeticError:
            return None

    def _record(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._events is not None:
            self._events.append(event_type, payload)

    def _record_error(self, result: ProviderResult[Any]) -> None:
        self._record(
            EventType.PROVIDER_ERROR,
            {
                "provider": self.name,
                "error": result.error.value if result.error else "unknown",
                "detail": result.error_detail[:500],
            },
        )
        _log.warning("provider error: %s (%s)", result.error, result.error_detail[:200])
