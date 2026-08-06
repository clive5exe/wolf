"""Telegram delivery, and the escaping that decides whether it arrives at all.

MarkdownV2 rejects a whole message for one unescaped special character, and
prices and tickers are made of dots, dashes and parentheses. So an escaping bug
here does not render oddly, it means the alert never arrives, silently, at the
moment it mattered.
"""

from __future__ import annotations

import pytest

from tradeos.notifications.telegram import (
    MAX_BODY,
    TelegramError,
    TelegramNotifier,
    _escape,
    pairing_steps,
)


class TestEscaping:
    @pytest.mark.parametrize("char", list(r"_*[]()~`>#+-=|{}.!"))
    def test_every_special_character_is_escaped(self, char: str) -> None:
        assert _escape(char) == f"\\{char}"

    def test_a_real_alert_survives(self) -> None:
        """The text WOLF actually sends is dense with specials."""
        raw = "AAPL -2.1% (was $312.85) [position_cap 61%] . sell 40?"
        escaped = _escape(raw)
        for char in ".-()[]%!".replace("%", ""):
            assert f"\\{char}" in escaped or char not in raw

    def test_plain_text_is_untouched(self) -> None:
        assert _escape("AAPL up today") == "AAPL up today"


class TestDeliveryNeverRaises:
    """A notifier that throws can abort a cycle, which turns a failed message
    into a missed trade. The decision is already in the event log."""

    def test_a_transport_failure_returns_false_rather_than_raising(self, monkeypatch) -> None:
        def boom(*_args, **_kwargs):
            raise TelegramError("network down")

        monkeypatch.setattr("tradeos.notifications.telegram._call", boom)
        assert TelegramNotifier(token="t", chat_id=1).notify("x", "y") is False

    def test_success_returns_true(self, monkeypatch) -> None:
        monkeypatch.setattr("tradeos.notifications.telegram._call", lambda *a, **k: {"ok": True})
        assert TelegramNotifier(token="t", chat_id=1).notify("x", "y") is True

    def test_an_overlong_body_is_truncated_with_a_marker(self, monkeypatch) -> None:
        """Telegram cuts at 4096. Truncating ourselves is visible; letting the
        tail vanish mid-sentence is not."""
        sent: list[dict] = []
        monkeypatch.setattr(
            "tradeos.notifications.telegram._call",
            lambda token, method, payload=None, **k: sent.append(payload or {}) or {"ok": True},
        )
        TelegramNotifier(token="t", chat_id=1).notify("t", "x" * 9000)
        text = sent[0]["text"]
        assert len(text) <= MAX_BODY + 40
        assert "truncated" in text

    def test_link_previews_are_disabled(self, monkeypatch) -> None:
        sent: list[dict] = []
        monkeypatch.setattr(
            "tradeos.notifications.telegram._call",
            lambda token, method, payload=None, **k: sent.append(payload or {}) or {"ok": True},
        )
        TelegramNotifier(token="t", chat_id=1).notify("t", "see https://example.com")
        assert sent[0]["disable_web_page_preview"] == "true"


class TestPairingInstructions:
    def test_the_first_step_names_the_command(self) -> None:
        first, _ = pairing_steps()
        assert "/newbot" in first

    def test_the_second_step_links_the_users_own_bot(self) -> None:
        _, second = pairing_steps("my_wolf_bot")
        assert "t.me/my_wolf_bot" in second
        assert "/start" in second

    def test_it_still_instructs_without_a_username(self) -> None:
        _, second = pairing_steps()
        assert "/start" in second


def test_the_bot_token_is_never_placed_in_a_url_we_log() -> None:
    """The token is path-embedded in Telegram's API, so any logged URL leaks
    the credential. Delivery failures log the exception, never the URL."""
    import inspect

    from tradeos.notifications import telegram

    source = inspect.getsource(telegram.TelegramNotifier.notify)
    assert "API.format" not in source
    assert "_log.warning" in source
