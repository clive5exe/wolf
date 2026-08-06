"""Telegram delivery, and the pairing flow that connects an account.

**Every user runs their own bot.** WOLF does not operate a shared one, and that
is not laziness. A shared bot means every message routes through a server
somebody has to run and pay for, and that operator holds a list of everyone's
chat ids and everything the system ever told them. The site promises there is
no service behind this, and one bot for everyone would quietly make that false.

A personal bot costs two minutes with @BotFather, needs no account beyond
Telegram itself, and belongs to the user completely. Same posture as the AI
provider and the broker: bring your own credential, and nothing about you
passes through anyone else's machine.

Pairing is deliberately two-sided. WOLF cannot message a stranger, because
Telegram only permits a bot to write to a chat that messaged it first. So the
user sends ``/start``, WOLF reads the resulting update to learn the chat id,
and only then can it deliver. That restriction is Telegram's, and it happens to
be exactly the consent step you would want anyway.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

from tradeos.ingestion.http import HttpTransport, TransportError
from tradeos.telemetry.logging import get_logger

_log = get_logger(__name__)

API: Final = "https://api.telegram.org/bot{token}/{method}"
BOTFATHER: Final = "https://t.me/BotFather"

#: Keystore entries. Renaming one orphans a live credential.
TOKEN_KEY: Final = "telegram_bot_token"
CHAT_KEY: Final = "telegram_chat_id"

#: Telegram truncates at 4096 characters. Truncating ourselves with a marker is
#: better than having the tail silently vanish mid-sentence.
MAX_BODY: Final = 3900


class TelegramError(RuntimeError):
    """Delivery or pairing failed, with something worth showing the user."""


def _call(
    token: str, method: str, payload: dict[str, Any] | None = None, *, timeout_s: float = 20
) -> dict[str, Any]:
    """One Telegram API call. Returns the ``result`` object.

    Telegram answers HTTP 200 with ``ok: false`` for application errors, so the
    status code alone is not enough to know whether anything happened.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(payload or {}).encode() if payload else None
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise TelegramError(f"Telegram returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise TelegramError(f"could not reach Telegram: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise TelegramError("Telegram sent a response we could not parse") from exc

    if not body.get("ok"):
        raise TelegramError(str(body.get("description") or "Telegram refused the request"))
    result = body.get("result")
    return result if isinstance(result, dict) else {"result": result}


def verify_token(token: str) -> str:
    """Confirm the token works and return the bot's username.

    Checked at pairing time rather than at first alert. A bad token discovered
    during setup reads as a typo; discovered when a position is moving against
    you, it reads as the system being broken at the worst possible moment.
    """
    me = _call(token.strip(), "getMe")
    username = me.get("username")
    if not username:
        raise TelegramError("that token authenticated but returned no bot username")
    return str(username)


def wait_for_chat(token: str, *, attempts: int = 30, timeout_s: float = 25) -> int:
    """Long-poll until the user messages the bot, and return their chat id.

    Long polling rather than a webhook, because a webhook needs a public HTTPS
    endpoint, which would mean either a server or a tunnel. Neither belongs in
    a tool that runs on your own machine.
    """
    offset = 0
    for _ in range(attempts):
        payload = {"timeout": int(timeout_s), "offset": offset, "limit": 10}
        result = _call(token, "getUpdates", payload, timeout_s=timeout_s + 10)
        updates = result.get("result") if isinstance(result.get("result"), list) else []
        for update in updates or []:
            offset = max(offset, int(update.get("update_id", 0)) + 1)
            message = update.get("message") or update.get("channel_post") or {}
            chat = message.get("chat") or {}
            if chat.get("id") is not None:
                return int(chat["id"])
    raise TelegramError(
        "no message received. Open the bot in Telegram and send /start, then try again"
    )


@dataclass(frozen=True, slots=True)
class TelegramNotifier:
    """Delivers cycle notifications to one chat."""

    token: str
    chat_id: int
    name: str = "telegram"

    def notify(self, title: str, body: str) -> bool:
        """Deliver, and never raise.

        A notifier that throws can abort a cycle, which would mean a failed
        message costing you a trade. Delivery is best-effort by design: the
        decision is already recorded in the event log, which is the record that
        matters.
        """
        text = f"*{_escape(title)}*\n{_escape(body)}"
        if len(text) > MAX_BODY:
            text = text[:MAX_BODY] + "\n_…truncated_"
        try:
            _call(
                self.token,
                "sendMessage",
                {
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "MarkdownV2",
                    # The alert is the point, not a link preview of some ticker
                    # page Telegram decided to unfurl.
                    "disable_web_page_preview": "true",
                },
            )
            return True
        except TelegramError as exc:
            _log.warning("telegram delivery failed: %s", exc)
            return False


#: MarkdownV2 requires escaping these anywhere they appear, and an unescaped one
#: makes Telegram reject the whole message rather than render it oddly. Prices
#: and tickers are full of dots, dashes and parentheses, so this is not rare.
_SPECIAL: Final = r"_*[]()~`>#+-=|{}.!"


def _escape(text: str) -> str:
    return "".join(f"\\{c}" if c in _SPECIAL else c for c in text)


def pairing_steps(bot_username: str | None = None) -> tuple[str, str]:
    """The two instructions a user needs, and where to send them."""
    first = (
        "Open BotFather and send /newbot. Pick any name. It will reply with a\n"
        "token that looks like 123456789:AAE... Paste it below."
    )
    second = (
        f"Now open your bot at https://t.me/{bot_username} and send /start"
        if bot_username
        else "Now open your new bot in Telegram and send /start"
    )
    return first, second


def check_transport() -> bool:
    """Whether Telegram is reachable at all, for the doctor check."""
    try:
        status, _ = HttpTransport().get("https://api.telegram.org", headers={}, timeout_s=10)
    except TransportError:
        return False
    return status < 500
