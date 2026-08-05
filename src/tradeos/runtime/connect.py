"""Connecting an account: open a browser, and always print the link too.

Every provider WOLF talks to needs the user to authorise it somewhere only a
browser can reach. The mechanics differ (Alpaca issues a key you paste,
Robinhood runs an OAuth round trip) but the human part is identical, so it is
written once here.

Two rules the whole module exists to enforce:

**The link is always printed.** ``webbrowser.open`` returns True on plenty of
systems where nothing actually appeared: a headless box, an SSH session, a
sandbox, a Linux install with no default handler. A flow that only opens a
browser strands those users with no way forward and no error. So the URL is
shown every time, whether or not the open reported success.

**Secrets go to the OS keystore, never to disk.** They are read back through
the same store, so nothing ever writes a key into the repo, a dotfile, or the
event log.
"""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from tradeos.security.store import SecretStore, SecretStoreError

#: Where each provider sends the user. Alpaca's dashboard is the page that
#: actually issues keys, rather than the marketing site.
ALPACA_SIGNUP: Final = "https://app.alpaca.markets/signup"
ALPACA_KEYS: Final = "https://app.alpaca.markets/paper/dashboard/overview"

#: Keystore entry names. Stable, because renaming one orphans a live secret.
ALPACA_KEY_ID: Final = "alpaca_key_id"
ALPACA_SECRET: Final = "alpaca_secret_key"


class ConnectError(RuntimeError):
    """The account could not be connected, with a reason worth showing."""


@dataclass(frozen=True, slots=True)
class BrowserPrompt:
    """One step a user completes in a browser."""

    url: str
    what: str

    def show(self, *, opener: Callable[[str], bool] = webbrowser.open) -> str:
        """Try to open ``url``, and return the message to print regardless.

        The return value is deliberately not conditional on whether the open
        succeeded. A user on a headless machine needs the link *more* than one
        with a working browser, not less.
        """
        opened = False
        try:
            opened = bool(opener(self.url))
        except Exception:
            opened = False
        lead = "Opened your browser to" if opened else "Open this in a browser"
        return f"{lead}:\n\n    {self.url}\n\n{self.what}"


def alpaca_steps() -> tuple[BrowserPrompt, BrowserPrompt]:
    """The two pages a user needs, in order.

    Account creation is not automated and will not be. Alpaca is a brokerage,
    identity verification is a legal requirement, and any tool that fills in
    that form is either scraping it or handling somebody's identity documents.
    Neither belongs here. What is removed instead is every step that is *not*
    legally required.
    """
    return (
        BrowserPrompt(
            ALPACA_SIGNUP,
            "Create a free account. A paper account is enough and needs no funding.",
        ),
        BrowserPrompt(
            ALPACA_KEYS,
            "Generate an API key, then paste the key id and secret below.\n"
            "The secret is shown once and cannot be retrieved later.",
        ),
    )


def save_alpaca(store: SecretStore, key_id: str, secret: str) -> None:
    """Validate and store an Alpaca credential pair.

    Validated before storing rather than after, because a key rejected at first
    use looks like a broken integration, whereas one rejected here looks like a
    typo, which is what it usually is.
    """
    key_id, secret = key_id.strip(), secret.strip()
    if not key_id or not secret:
        raise ConnectError("both the key id and the secret are required")
    if len(secret) < 20:
        raise ConnectError(
            "that secret looks too short. Alpaca shows it once at creation, "
            "so if it was lost, generate a new key rather than guessing"
        )
    if not store.available():
        raise ConnectError(
            "no OS keystore is available, and WOLF will not write a broker "
            "credential to disk. On Linux install libsecret, on macOS the "
            "Keychain is built in"
        )
    try:
        store.set_secret(ALPACA_KEY_ID, key_id)
        store.set_secret(ALPACA_SECRET, secret)
    except SecretStoreError as exc:
        raise ConnectError(f"could not write to the keystore: {exc}") from exc


def alpaca_status(store: SecretStore) -> str:
    """A one-line summary, with the secret never reconstructed for display."""
    if not store.available():
        return "no keystore available"
    key_id = store.get_secret(ALPACA_KEY_ID)
    if not key_id or not store.get_secret(ALPACA_SECRET):
        return "not connected"
    # Enough to recognise which key is in use, not enough to use it.
    return f"connected as {key_id[:4]}…{key_id[-4:]}"


def forget_alpaca(store: SecretStore) -> bool:
    """Remove both halves. Returns True if anything was actually removed."""
    removed = store.delete_secret(ALPACA_KEY_ID)
    removed |= store.delete_secret(ALPACA_SECRET)
    return removed
