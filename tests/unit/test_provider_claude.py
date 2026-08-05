"""Claude Code adapter tests against a fake `claude` executable (PROVIDER_SPEC §6.1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradeos.domain.thesis import HealthProbe
from tradeos.events.store import InMemoryEventStore
from tradeos.events.types import EventType
from tradeos.providers.base import ProviderCapability, ProviderErrorKind
from tradeos.providers.claude_code import ClaudeCodeProvider


def test_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)
    provider = ClaudeCodeProvider()
    status = provider.detect()
    assert not status.installed and not status.ready
    result = provider.query_structured(prompt="x", schema=HealthProbe)
    assert result.error == ProviderErrorKind.NOT_INSTALLED


def test_detect_authenticated(fake_claude: str) -> None:
    status = ClaudeCodeProvider(executable=fake_claude).detect()
    assert status.installed
    assert status.version is not None and "fake-claude" in status.version
    assert status.authenticated is True
    assert status.ready


def test_detect_logged_out(fake_claude: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_AUTH", "out")
    status = ClaudeCodeProvider(executable=fake_claude).detect()
    assert status.installed and status.authenticated is False and not status.ready


def test_health_check_roundtrip(fake_claude: str) -> None:
    events = InMemoryEventStore()
    provider = ClaudeCodeProvider(executable=fake_claude, event_store=events)
    result = provider.health_check()
    assert result.ok, result.error_detail
    assert result.value is not None and result.value.status == "ok"
    assert result.cost_usd == Decimal("0.0123")
    assert result.session_id == "fake-session-1"
    types = [e.event_type for e in events.iter_events()]
    assert EventType.PROVIDER_QUERY in types and EventType.PROVIDER_RESPONSE in types


def test_invalid_output_retries_once_then_succeeds(
    fake_claude: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "invalid_then_valid")
    monkeypatch.setenv("FAKE_CLAUDE_STRUCTURED", '{"status": "ok", "echo": "retry-win"}')
    result = ClaudeCodeProvider(executable=fake_claude).query_structured(
        prompt="test", schema=HealthProbe
    )
    assert result.ok and result.value is not None and result.value.echo == "retry-win"


def test_always_invalid_is_typed_failure(fake_claude: str, monkeypatch: pytest.MonkeyPatch) -> None:
    events = InMemoryEventStore()
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "always_invalid")
    result = ClaudeCodeProvider(executable=fake_claude, event_store=events).query_structured(
        prompt="test", schema=HealthProbe
    )
    assert not result.ok and result.error == ProviderErrorKind.INVALID_OUTPUT
    assert any(e.event_type == EventType.PROVIDER_ERROR for e in events.iter_events())


def test_rate_limited_maps_to_typed_error(
    fake_claude: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "rate_limited")
    result = ClaudeCodeProvider(executable=fake_claude).query_structured(
        prompt="test", schema=HealthProbe
    )
    assert result.error == ProviderErrorKind.RATE_LIMITED


def test_timeout_kills_and_reports(fake_claude: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "hang")
    result = ClaudeCodeProvider(executable=fake_claude).query_structured(
        prompt="test", schema=HealthProbe, timeout_s=1
    )
    assert result.error == ProviderErrorKind.TIMEOUT


def test_declared_capabilities_are_documented_ones(fake_claude: str) -> None:
    caps = ClaudeCodeProvider(executable=fake_claude).capabilities()
    assert ProviderCapability.STRUCTURED_OUTPUT in caps
    assert ProviderCapability.TOOL_USE not in caps  # never granted in v0.1
