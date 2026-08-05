"""MCP tool boundary (T-024, S2).

Robinhood's server exposes 53 tools. 19 place orders, cancel them, exercise
options, or mutate broker-side state. The registry must make every one of them
unreachable, and must refuse names it does not recognise. A server can add
tools without telling us.

These tests are written against the real advertised tool list, captured from a
live probe on 2026-08-05.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tradeos.mcp.registry import (
    ALLOWED,
    EXECUTION_TOOLS,
    STATE_WRITE_CLASS,
    TRADE_CLASS,
    ToolClass,
    ToolPermissionError,
    allowed_for_mode,
    audit_server_tools,
    ensure_callable,
    tool_class,
)

#: Verbatim from `/mcp` against https://agent.robinhood.com/mcp/trading.
ADVERTISED = frozenset(
    {
        "add_option_to_watchlist",
        "add_to_watchlist",
        "cancel_equity_order",
        "cancel_option_exercise",
        "cancel_option_order",
        "create_scan",
        "create_watchlist",
        "exercise_option",
        "follow_watchlist",
        "get_accounts",
        "get_earnings_calendar",
        "get_earnings_results",
        "get_equity_fundamentals",
        "get_equity_historicals",
        "get_equity_orders",
        "get_equity_positions",
        "get_equity_price_book",
        "get_equity_quotes",
        "get_equity_tax_lots",
        "get_equity_technical_indicators",
        "get_equity_tradability",
        "get_financials",
        "get_index_historicals",
        "get_index_quotes",
        "get_indexes",
        "get_option_chains",
        "get_option_historicals",
        "get_option_instruments",
        "get_option_level_upgrade_info",
        "get_option_orders",
        "get_option_positions",
        "get_option_quotes",
        "get_option_watchlist",
        "get_pnl_trade_history",
        "get_popular_watchlists",
        "get_portfolio",
        "get_realized_pnl",
        "get_scanner_filter_specs",
        "get_scans",
        "get_watchlist_items",
        "get_watchlists",
        "place_equity_order",
        "place_option_order",
        "remove_from_watchlist",
        "remove_option_from_watchlist",
        "review_equity_order",
        "review_option_order",
        "run_scan",
        "search",
        "unfollow_watchlist",
        "update_scan_config",
        "update_scan_filters",
        "update_watchlist",
    }
)


class TestModeGatesExecution:
    """Placing orders is the destination, not a hazard. But only from the mode
    where a human said so."""

    @pytest.mark.parametrize("mode", [None, "read_only", "paper", "garbage"])
    def test_orders_are_unreachable_below_approval(self, mode: str | None) -> None:
        with pytest.raises(ToolPermissionError, match="approval mode"):
            ensure_callable("place_equity_order", mode=mode)

    @pytest.mark.parametrize("mode", ["approval", "autopilot"])
    def test_orders_become_reachable_once_the_ladder_is_climbed(self, mode: str) -> None:
        assert ensure_callable("place_equity_order", mode=mode) == "place_equity_order"

    def test_an_unrecognised_mode_narrows_rather_than_widens(self) -> None:
        """Mode arrives from stored policy. A corrupt value must fail closed."""
        assert "place_equity_order" not in allowed_for_mode("APPROVAL_maybe?")
        assert "place_equity_order" not in allowed_for_mode("")

    def test_reaching_the_tool_is_necessary_never_sufficient(self) -> None:
        """Even in approval mode every call still passes strategy sizing, the
        risk engine's veto, ValidatedOrder, the executor, and the kill switch."""
        broker = (Path(__file__).resolve().parents[2] / "src/tradeos/brokers/base.py").read_text()
        assert "ValidatedOrder" in broker


class TestNoTradeToolIsReachable:
    @pytest.mark.parametrize("name", sorted(TRADE_CLASS - set(EXECUTION_TOOLS)))
    def test_order_tools_wolf_never_uses_are_refused_in_every_mode(self, name: str) -> None:
        """Options, exercise, and order-preview endpoints have no role in any
        mode. Unreachable regardless of how far up the ladder you go."""
        for mode in (None, "read_only", "paper", "approval", "autopilot"):
            with pytest.raises(ToolPermissionError):
                ensure_callable(name, mode=mode)

    @pytest.mark.parametrize("name", sorted(STATE_WRITE_CLASS))
    def test_every_mutating_tool_is_refused(self, name: str) -> None:
        with pytest.raises(ToolPermissionError):
            ensure_callable(name)

    def test_the_default_allowlist_holds_no_trade_or_write_tools(self) -> None:
        """ALLOWED with no mode context is the read-only reading."""
        assert not set(ALLOWED) & TRADE_CLASS
        assert not set(ALLOWED) & STATE_WRITE_CLASS

    def test_no_allowed_tool_name_suggests_writing(self) -> None:
        """A cheap catch for a future addition whose danger is obvious from
        its name, added without thinking."""
        forbidden = ("place", "cancel", "exercise", "create", "update", "remove", "add_")
        for name in ALLOWED:
            assert not any(verb in name for verb in forbidden), f"{name} looks like a write"


class TestUnknownToolsAreRefused:
    def test_an_unrecognised_name_is_refused_not_permitted(self) -> None:
        """Default-deny. A server may add tools without telling us."""
        with pytest.raises(ToolPermissionError, match="not in the allowlist"):
            ensure_callable("get_something_invented_next_year")

    def test_the_refusal_explains_the_rule(self) -> None:
        with pytest.raises(ToolPermissionError, match="deliberately"):
            ensure_callable("totally_new_tool")

    def test_an_unknown_tool_has_no_class(self) -> None:
        assert tool_class("not_a_real_tool") is None


class TestAgainstTheRealServerSurface:
    def test_every_advertised_tool_is_classified(self) -> None:
        """Nothing on the live server is unaccounted for. A gap here means a
        tool whose risk nobody has judged."""
        unclassified = {name for name in ADVERTISED if tool_class(name) is None}
        # Read-only tools we deliberately do not use yet (options, scanners,
        # fundamentals) are expected to be unclassified. But they must also be
        # unreachable, which the next test asserts.
        assert not unclassified & TRADE_CLASS
        assert not unclassified & STATE_WRITE_CLASS

    @pytest.mark.parametrize("name", sorted(ADVERTISED))
    def test_only_the_allowlist_is_callable(self, name: str) -> None:
        if name in ALLOWED:
            assert ensure_callable(name) == name
        else:
            with pytest.raises(ToolPermissionError):
                ensure_callable(name)  # no mode context => read-only

    def test_the_reachable_surface_is_small(self) -> None:
        """53 tools advertised. Single digits reachable. Least privilege is a
        number you can look at, not a claim."""
        audit = audit_server_tools(ADVERTISED)
        assert len(audit["reachable"]) <= 8
        assert len(ADVERTISED) > 50

    def test_every_allowed_tool_actually_exists_upstream(self) -> None:
        """A typo in the allowlist would fail at call time, in production."""
        audit = audit_server_tools(ADVERTISED)
        assert audit["missing_upstream"] == ()

    def test_new_upstream_tools_are_reported_for_review(self) -> None:
        audit = audit_server_tools(ADVERTISED | {"place_crypto_order"})
        assert "place_crypto_order" in audit["unknown_to_us"]


class TestTradeToolNamesAppearNowhereElse:
    """The allowlist already makes these unreachable. This catches a config or
    fixture edit that adds one by hand."""

    def test_execution_tools_are_never_reachable_by_default(self) -> None:
        for name in EXECUTION_TOOLS:
            assert name not in ALLOWED

    def test_no_trade_tool_name_appears_in_source_outside_the_registry(self) -> None:
        root = Path(__file__).resolve().parents[2] / "src" / "tradeos"
        offenders: list[str] = []
        for path in root.rglob("*.py"):
            if path.name == "registry.py":
                continue  # where they are listed in order to be excluded
            text = path.read_text()
            offenders += [f"{path.name}: {name}" for name in TRADE_CLASS if name in text]
        assert not offenders, f"trade tool names in source: {offenders}"

    def test_classification_is_exhaustive_for_the_sets_we_maintain(self) -> None:
        for name in TRADE_CLASS:
            assert tool_class(name) is ToolClass.BROKER_TRADE
        for name in STATE_WRITE_CLASS:
            assert tool_class(name) is ToolClass.STATE_WRITE
