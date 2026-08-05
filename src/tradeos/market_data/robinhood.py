"""Live quotes from Robinhood, through the Agentic MCP server.

WOLF does not speak MCP itself. It shells to the ``claude`` CLI, which already
holds an authenticated connection to Robinhood's server, so the credential
never enters this process, never lands in the keystore, and never appears in
the event log. Authorisation is the user's existing browser session.

Two constraints shape everything here.

**The MCP is project-scoped.** It is registered against a specific directory,
so the CLI only sees it when run from there. That is not a quirk to work
around, it is the safety boundary: the same server also exposes order-placing
tools, and registering it to the WOLF directory would put one of those an
unguarded call away. The working directory is therefore required, explicit,
and never guessed. The tools themselves are named only in
:mod:`tradeos.mcp.registry`, which a safety test enforces.

**Only allowlisted tools are ever passed.** ``--allowedTools`` is constructed
from :mod:`tradeos.mcp.registry`, so a tool absent from the allowlist cannot be
reached even if a prompt asks for it. The CLI refuses what was not granted.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

from tradeos.domain.market import Quote
from tradeos.telemetry.logging import get_logger

_log = get_logger(__name__)

#: The read-only market data tool. Named explicitly rather than derived, so
#: adding a tool here is a visible diff on a safety-critical surface.
QUOTE_TOOL: Final = "mcp__robinhood-trading__get_equity_quotes"

#: Deliberately terse. The model is a transport here, not an analyst: it calls
#: one tool and returns the payload. Anything it adds is noise we then parse.
_PROMPT: Final = (
    "Call {tool} for {symbols}. Return ONLY a JSON object mapping each symbol "
    'to its last trade price as a string, like {{"AAPL": "312.85"}}. '
    "No prose, no markdown fence, no explanation."
)


class RobinhoodUnavailable(RuntimeError):
    """The CLI or the MCP connection is not usable, with a reason to show."""


def _decimal(raw: Any) -> Decimal | None:
    # str() first: a float from JSON must not become a binary float on the way
    # to Decimal, or a quoted price acquires digits nobody published.
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return value if value > 0 else None


@dataclass(slots=True)
class RobinhoodQuoteSource:
    """A :class:`QuoteSource` backed by the Robinhood MCP server."""

    #: Directory the MCP is registered against. Required: see module docstring.
    mcp_dir: Path
    exe: str = "claude"
    timeout_s: int = 90
    name: str = "robinhood_mcp"
    #: Prices from the last prime(), so one cycle is one CLI call.
    _cache: dict[str, Decimal] = field(default_factory=dict)

    def available(self) -> tuple[bool, str]:
        """Whether a quote could be fetched, and why not if it could not."""
        if not self.mcp_dir.is_dir():
            return False, f"MCP directory does not exist: {self.mcp_dir}"
        try:
            proc = subprocess.run(
                [self.exe, "mcp", "list"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.mcp_dir,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"could not run the claude CLI: {exc}"
        out = proc.stdout
        if "robinhood-trading" not in out:
            return False, f"robinhood-trading is not registered in {self.mcp_dir}"
        # The CLI prints a health check per server. Connected is the only state
        # from which a tool call will succeed.
        for line in out.splitlines():
            if "robinhood-trading" in line:
                return ("Connected" in line, line.strip())
        return False, "robinhood-trading found but its health line was unreadable"

    def fetch(self, symbols: tuple[str, ...]) -> dict[str, Decimal]:
        """Last trade price per symbol. Missing symbols are simply absent.

        A symbol that could not be priced is omitted rather than defaulted.
        Every risk rule downstream treats an absent quote as a reason to
        refuse, and a placeholder would turn that into a trade.
        """
        if not symbols:
            return {}
        argv = [
            self.exe,
            "-p",
            _PROMPT.format(tool=QUOTE_TOOL, symbols=", ".join(symbols)),
            "--allowedTools",
            QUOTE_TOOL,
            "--max-turns",
            "4",
        ]
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=self.timeout_s, cwd=self.mcp_dir
            )
        except subprocess.TimeoutExpired as exc:
            raise RobinhoodUnavailable(f"quote fetch exceeded {self.timeout_s}s") from exc
        except OSError as exc:
            raise RobinhoodUnavailable(f"could not run the claude CLI: {exc}") from exc

        if proc.returncode != 0:
            raise RobinhoodUnavailable(f"claude CLI exited {proc.returncode}: {proc.stderr[:200]}")

        return parse_prices(proc.stdout, symbols)

    def prime(self, symbols: tuple[str, ...]) -> None:
        """Fetch a whole universe in one call and cache it for this cycle.

        Without this a five symbol cycle spawns five CLI processes and takes
        over a minute, because each ``get_quote`` is an independent model call.
        The cycle asks per symbol, so batching has to happen here.
        """
        self._cache.clear()
        self._cache.update(self.fetch(symbols))

    def get_quote(self, symbol: str, *, now: datetime) -> Quote | None:
        symbol = symbol.upper()
        price = self._cache.get(symbol)
        if price is None:
            # Not primed, or primed without this symbol. One call rather than
            # returning nothing, since an absent quote blocks the whole cycle.
            price = self.fetch((symbol,)).get(symbol)
        if price is None:
            return None
        return Quote(symbol=symbol, price=price, as_of=now, source=self.name)


def parse_prices(stdout: str, symbols: tuple[str, ...]) -> dict[str, Decimal]:
    """Pull the price map out of whatever the model actually returned.

    Kept pure and separate because this is the fragile part. The instruction
    asks for bare JSON, and models still wrap it in a markdown fence or add a
    sentence, so the object is located rather than assumed to be the whole
    output. A symbol that cannot be parsed is dropped, never guessed.
    """
    text = stdout.strip()
    if "```" in text:
        # Take the fenced block's contents, ignoring any language tag.
        parts = text.split("```")
        for part in parts[1::2]:
            body = part.split("\n", 1)[-1] if "\n" in part else part
            found = _load_object(body)
            if found is not None:
                text = json.dumps(found)
                break

    payload = _load_object(text)
    if payload is None:
        # Last resort: the first balanced object anywhere in the output.
        start = text.find("{")
        while start != -1 and payload is None:
            depth = 0
            for i in range(start, len(text)):
                depth += (text[i] == "{") - (text[i] == "}")
                if depth == 0:
                    payload = _load_object(text[start : i + 1])
                    break
            start = text.find("{", start + 1)

    if payload is None:
        _log.warning("robinhood quote output had no JSON object")
        return {}

    wanted = {s.upper() for s in symbols}
    out: dict[str, Decimal] = {}
    for key, raw in payload.items():
        symbol = str(key).upper()
        if symbol not in wanted:
            continue
        value = _decimal(raw.get("price") if isinstance(raw, dict) else raw)
        if value is not None:
            out[symbol] = value
    return out


def _load_object(text: str) -> dict[str, Any] | None:
    try:
        loaded = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def default_source(mcp_dir: str | Path) -> RobinhoodQuoteSource:
    return RobinhoodQuoteSource(mcp_dir=Path(mcp_dir).expanduser())


__all__ = [
    "QUOTE_TOOL",
    "RobinhoodQuoteSource",
    "RobinhoodUnavailable",
    "default_source",
    "parse_prices",
]
