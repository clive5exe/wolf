"""MCP tool registry — what WOLF may call, and what it must never call.

Robinhood's Agentic Trading server exposes 53 tools, 19 of which place orders,
cancel them, exercise options, or mutate watchlists and scanners. v0.1 is a
read-only intelligence and paper-trading runtime, so almost all of that surface
is off limits.

The registry is an **allowlist**, not a denylist. A tool absent from
:data:`ALLOWED` is not callable, which means a server that grows a new tool
tomorrow — or renames one — cannot silently become reachable. A denylist would
fail the other way: safe by default only for the dangers someone remembered.

:data:`TRADE_CLASS` is kept alongside it as belt and braces. The allowlist
already excludes those names; recording them explicitly lets a safety test
assert they never appear in configuration, code, or fixtures, so a future edit
that adds one by hand fails loudly rather than quietly widening the boundary.
"""

from __future__ import annotations

from enum import StrEnum


class ToolClass(StrEnum):
    BROKER_READ = "broker_read"
    BROKER_TRADE = "broker_trade"
    MARKET_DATA = "market_data"
    STATE_WRITE = "state_write"  # watchlists, scanners — mutation without money


class ToolPermissionError(RuntimeError):
    """A tool outside the allowlist was requested. Never downgraded to a warning."""


#: Tools that can move money or change orders. WOLF must never call these in
#: any mode. Listed so their absence can be asserted, not so they can be used.
TRADE_CLASS: frozenset[str] = frozenset(
    {
        "place_equity_order",
        "place_option_order",
        "cancel_equity_order",
        "cancel_option_order",
        "exercise_option",
        "cancel_option_exercise",
        # Order *review* endpoints do not execute, but they take an order as
        # input and exist only as a step toward placing one. Excluded with the
        # rest: the boundary is easier to defend when it sits at "anything
        # shaped like an order" than at "anything that definitely executes".
        "review_equity_order",
        "review_option_order",
    }
)

#: Mutating tools that move no money but change account state. Also excluded:
#: v0.1 reads, it does not write anything to a broker.
STATE_WRITE_CLASS: frozenset[str] = frozenset(
    {
        "add_to_watchlist",
        "add_option_to_watchlist",
        "remove_from_watchlist",
        "remove_option_from_watchlist",
        "create_watchlist",
        "update_watchlist",
        "follow_watchlist",
        "unfollow_watchlist",
        "create_scan",
        "update_scan_config",
        "update_scan_filters",
    }
)

#: The minimum set that satisfies v0.1's needs. Deliberately not "every read
#: tool": least privilege means the options chain, tax lots, and scanner reads
#: stay unreachable until something actually requires them.
ALLOWED: dict[str, ToolClass] = {
    # Account and portfolio state
    "get_accounts": ToolClass.BROKER_READ,
    "get_portfolio": ToolClass.BROKER_READ,
    "get_equity_positions": ToolClass.BROKER_READ,
    "get_equity_orders": ToolClass.BROKER_READ,
    # Market data
    "get_equity_quotes": ToolClass.MARKET_DATA,
    # OHLCV — the equity curve, and average daily volume for the liquidity
    # signal the outbound projection currently reports as unknown.
    "get_equity_historicals": ToolClass.MARKET_DATA,
    # Unblocks the earnings_blackout risk rule, which ships disabled today for
    # want of a verified calendar source.
    "get_earnings_calendar": ToolClass.MARKET_DATA,
}


def tool_class(name: str) -> ToolClass | None:
    """Classification for a tool name, or None if it is unknown to us."""
    if name in ALLOWED:
        return ALLOWED[name]
    if name in TRADE_CLASS:
        return ToolClass.BROKER_TRADE
    if name in STATE_WRITE_CLASS:
        return ToolClass.STATE_WRITE
    return None


def ensure_callable(name: str) -> str:
    """Gate every outbound tool call. Raises unless explicitly allowed.

    Unknown tools are refused with the same force as known-dangerous ones: a
    name we do not recognise is a name whose behaviour we cannot vouch for,
    and the server is free to add tools without telling us.
    """
    if name in ALLOWED:
        return name
    klass = tool_class(name)
    if klass is ToolClass.BROKER_TRADE:
        raise ToolPermissionError(
            f"{name!r} can place, cancel, or exercise orders. WOLF v0.1 is "
            f"read-only and never calls it in any mode."
        )
    if klass is ToolClass.STATE_WRITE:
        raise ToolPermissionError(f"{name!r} mutates broker-side state. WOLF v0.1 reads only.")
    raise ToolPermissionError(
        f"{name!r} is not in the allowlist. Tools must be added deliberately, "
        f"with a stated reason — an unrecognised tool is refused by default."
    )


def audit_server_tools(advertised: frozenset[str]) -> dict[str, tuple[str, ...]]:
    """Compare a server's advertised tools against what we know.

    Called after the tool-list probe. New tools appearing upstream are reported
    rather than ignored: an unexpected addition to a broker's trade surface is
    exactly the sort of change worth a human's attention, even though the
    allowlist already makes it unreachable.
    """
    known = set(ALLOWED) | TRADE_CLASS | STATE_WRITE_CLASS
    return {
        "unknown_to_us": tuple(sorted(advertised - known)),
        "missing_upstream": tuple(sorted(set(ALLOWED) - advertised)),
        "reachable": tuple(sorted(advertised & set(ALLOWED))),
    }
