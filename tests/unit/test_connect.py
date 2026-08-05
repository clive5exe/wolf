"""The link must survive a browser that never opened.

Most of these exist because `webbrowser.open` returning True proves nothing.
It reports success on headless boxes, SSH sessions and sandboxes where no
window appeared, so a flow that trusts it strands exactly the users who most
need the URL printed.
"""

from __future__ import annotations

import pytest

from tradeos.runtime.connect import (
    ALPACA_KEY_ID,
    ALPACA_SECRET,
    BrowserPrompt,
    ConnectError,
    alpaca_status,
    alpaca_steps,
    forget_alpaca,
    save_alpaca,
)


class FakeStore:
    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self.secrets: dict[str, str] = {}

    def available(self) -> bool:
        return self._available

    def set_secret(self, name: str, value: str, account: str = "wolf") -> None:
        self.secrets[name] = value

    def get_secret(self, name: str, account: str = "wolf") -> str | None:
        return self.secrets.get(name)

    def delete_secret(self, name: str, account: str = "wolf") -> bool:
        return self.secrets.pop(name, None) is not None


class TestTheLinkAlwaysAppears:
    PROMPT = BrowserPrompt("https://example.com/keys", "Do the thing.")

    def test_url_is_shown_when_the_browser_opened(self) -> None:
        message = self.PROMPT.show(opener=lambda _: True)
        assert "https://example.com/keys" in message
        assert "Opened your browser" in message

    def test_url_is_shown_when_the_browser_did_not_open(self) -> None:
        message = self.PROMPT.show(opener=lambda _: False)
        assert "https://example.com/keys" in message
        assert "Open this in a browser" in message

    def test_url_is_shown_when_the_opener_raises(self) -> None:
        """A machine with no browser at all is the case that matters most."""

        def explode(_: str) -> bool:
            raise RuntimeError("no display")

        message = self.PROMPT.show(opener=explode)
        assert "https://example.com/keys" in message
        assert "Open this in a browser" in message

    def test_the_instruction_travels_with_the_link(self) -> None:
        assert "Do the thing." in self.PROMPT.show(opener=lambda _: False)


class TestAlpacaSteps:
    def test_signup_comes_before_key_generation(self) -> None:
        signup, keys = alpaca_steps()
        assert "signup" in signup.url
        assert "dashboard" in keys.url

    def test_the_user_is_warned_the_secret_is_shown_once(self) -> None:
        _, keys = alpaca_steps()
        assert "once" in keys.what


class TestSavingCredentials:
    def test_stores_both_halves(self) -> None:
        store = FakeStore()
        save_alpaca(store, "PKTEST1234", "s" * 40)
        assert store.secrets[ALPACA_KEY_ID] == "PKTEST1234"
        assert store.secrets[ALPACA_SECRET] == "s" * 40

    def test_whitespace_from_a_paste_is_trimmed(self) -> None:
        store = FakeStore()
        save_alpaca(store, "  PKTEST1234\n", f"  {'s' * 40}\n")
        assert store.secrets[ALPACA_KEY_ID] == "PKTEST1234"

    @pytest.mark.parametrize(("key_id", "secret"), [("", "s" * 40), ("PK1", ""), ("   ", "s" * 40)])
    def test_both_halves_are_required(self, key_id: str, secret: str) -> None:
        with pytest.raises(ConnectError, match="required"):
            save_alpaca(FakeStore(), key_id, secret)

    def test_a_truncated_secret_is_caught_before_it_is_stored(self) -> None:
        """Rejected here it reads as a typo. Rejected at first use it reads as
        a broken integration."""
        store = FakeStore()
        with pytest.raises(ConnectError, match="too short"):
            save_alpaca(store, "PKTEST1234", "abc")
        assert store.secrets == {}

    def test_refuses_to_store_anything_without_a_keystore(self) -> None:
        """A broker credential must never fall back to a file."""
        store = FakeStore(available=False)
        with pytest.raises(ConnectError, match="keystore"):
            save_alpaca(store, "PKTEST1234", "s" * 40)
        assert store.secrets == {}


class TestStatus:
    def test_reports_not_connected_when_empty(self) -> None:
        assert alpaca_status(FakeStore()) == "not connected"

    def test_reports_not_connected_when_only_half_is_present(self) -> None:
        store = FakeStore()
        store.secrets[ALPACA_KEY_ID] = "PKTEST1234"
        assert alpaca_status(store) == "not connected"

    def test_never_reveals_the_secret(self) -> None:
        store = FakeStore()
        save_alpaca(store, "PKTESTABCD1234", "s" * 40)
        status = alpaca_status(store)
        assert "s" * 40 not in status
        assert "…" in status, "the key id should be abbreviated, not printed whole"

    def test_says_so_when_there_is_no_keystore(self) -> None:
        assert alpaca_status(FakeStore(available=False)) == "no keystore available"


class TestForget:
    def test_removes_both_halves(self) -> None:
        store = FakeStore()
        save_alpaca(store, "PKTEST1234", "s" * 40)
        assert forget_alpaca(store) is True
        assert store.secrets == {}

    def test_reports_false_when_there_was_nothing_to_remove(self) -> None:
        assert forget_alpaca(FakeStore()) is False
