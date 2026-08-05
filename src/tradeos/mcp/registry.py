"""MCP tool registry. What WOLF may call, in which mode.

Robinhood's Agentic Trading server exposes 53 tools, 19 of which place orders,
cancel them, exercise options, or mutate watchlists and scanners.

**Placing orders is the destination, not a hazard.** WOLF is meant to trade.
The mode ladder exists so it does so when a human has decided it should, not
whenever a token happens to permit it. So the reachable tool set is a function
of the active trading mode rather than a constant: read tools in every mode,
order placement only from APPROVAL upward, and nothing at all that WOLF has no
use for.

The registry is an **allowlist**, not a denylist. A tool absent from the set
for the current mode is not callable, so a server that grows a new tool
tomorrow, or renames one, cannot silently become reachable. A denylist fails
the other way: safe by default only for the dangers someone remembered.

Why this matters more here than it usually would: Robinhood advertises a single
opaque OAuth scope (``internal``). There is no read-only token to request, so
during read-only and paper modes *this registry is the only thing distinguishing
"WOLF cannot trade" from "WOLF has not traded yet"*. The authorization server
will not catch a mistake on our side.
"""

from __future__ import annotations

from enum import StrEnum


class ToolClass(StrEnum):
    BROKER_READ = "broker_read"
    BROKER_TRADE = "broker_trade"
    MARKET_DATA = "market_data"
    STATE_WRITE = "state_write"  # watchlists, scanners. Mutation without money


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

#: Read tools, callable in every mode. Deliberately not "every read tool":
#: least privilege means the options chain, tax lots, and scanner reads stay
#: unreachable until something actually requires them.
READ_TOOLS: dict[str, ToolClass] = {
    # Account and portfolio state
    "get_accounts": ToolClass.BROKER_READ,
    "get_portfolio": ToolClass.BROKER_READ,
    "get_equity_positions": ToolClass.BROKER_READ,
    "get_equity_orders": ToolClass.BROKER_READ,
    # Market data
    "get_equity_quotes": ToolClass.MARKET_DATA,
    # OHLCV. The equity curve, and average daily volume for the liquidity
    # signal the outbound projection currently reports as unknown.
    "get_equity_historicals": ToolClass.MARKET_DATA,
    # Unblocks the earnings_blackout risk rule, which ships disabled today for
    # want of a verified calendar source.
    "get_earnings_calendar": ToolClass.MARKET_DATA,
}


#: Order tools, reachable only once a human has moved the policy to APPROVAL or
#: above. Even then every call still passes the full chain: strategy sizing, the
#: risk engine's veto, a ValidatedOrder, the executor's idempotency check, and
#: the kill switch. Reaching the tool is necessary, never sufficient.
EXECUTION_TOOLS: dict[str, ToolClass] = {
    "place_equity_order": ToolClass.BROKER_TRADE,
    "cancel_equity_order": ToolClass.BROKER_TRADE,
}

#: Modes in which order placement is reachable at all.
EXECUTING_MODES: frozenset[str] = frozenset({"approval", "autopilot"})

#: Backwards-compatible view: what is reachable with no mode context, which is
#: the safe reading. Read tools only.
ALLOWED: dict[str, ToolClass] = READ_TOOLS


def allowed_for_mode(mode: str | None) -> dict[str, ToolClass]:
    """The reachable tool set for a trading mode.

    ``None`` or an unrecognised mode yields read tools only. Failing closed on
    an unknown mode matters because the mode arrives from stored policy: a
    corrupt or hand-edited value must narrow the surface, never widen it.
    """
    tools = dict(READ_TOOLS)
    if mode and str(mode).lower() in EXECUTING_MODES:
        tools.update(EXECUTION_TOOLS)
    return tools


def tool_class(name: str) -> ToolClass | None:
    """Classification for a tool name, or None if it is unknown to us."""
    if name in ALLOWED:
        return ALLOWED[name]
    if name in TRADE_CLASS:
        return ToolClass.BROKER_TRADE
    if name in STATE_WRITE_CLASS:
        return ToolClass.STATE_WRITE
    return None


def ensure_callable(name: str, *, mode: str | None = None) -> str:
    """Gate every outbound tool call. Raises unless allowed in this mode.

    Unknown tools are refused with the same force as known-dangerous ones: a
    name we do not recognise is a name whose behaviour we cannot vouch for,
    and the server is free to add tools without telling us.
    """
    permitted = allowed_for_mode(mode)
    if name in permitted:
        return name
    klass = tool_class(name)
    if klass is ToolClass.BROKER_TRADE:
        if name in EXECUTION_TOOLS:
            raise ToolPermissionError(
                f"{name!r} places or cancels orders, which requires approval mode "
                f"or above. The active mode is {mode or 'unset'}. Move up the "
                f"ladder deliberately, it cannot be skipped."
            )
        raise ToolPermissionError(
            f"{name!r} is an order tool WOLF has no use for (options, exercise, "
            f"or order preview). It is unreachable in every mode."
        )
    if klass is ToolClass.STATE_WRITE:
        raise ToolPermissionError(f"{name!r} mutates broker-side state. WOLF v0.1 reads only.")
    raise ToolPermissionError(
        f"{name!r} is not in the allowlist. Tools must be added deliberately, "
        f"with a stated reason, an unrecognised tool is refused by default."
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
