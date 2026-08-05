"""Parsing what a model returns, which is the fragile half of this adapter.

The prompt asks for bare JSON. Models still wrap it in a fence, prepend a
sentence, or answer with a nested object. Every case here was chosen because it
would silently produce a wrong price or no price at all, and a wrong price
reaches the risk engine as fact.
"""

from __future__ import annotations

from decimal import Decimal

from tradeos.market_data.robinhood import QUOTE_TOOL, parse_prices

SYMBOLS = ("AAPL", "MSFT")


class TestParsingShapes:
    def test_bare_json(self) -> None:
        out = parse_prices('{"AAPL": "312.85", "MSFT": "487.47"}', SYMBOLS)
        assert out == {"AAPL": Decimal("312.85"), "MSFT": Decimal("487.47")}

    def test_markdown_fenced(self) -> None:
        text = 'Here you go:\n```json\n{"AAPL": "312.85"}\n```\n'
        assert parse_prices(text, SYMBOLS) == {"AAPL": Decimal("312.85")}

    def test_prose_wrapped_around_the_object(self) -> None:
        text = 'The current price is {"AAPL": "312.85"} as of now.'
        assert parse_prices(text, SYMBOLS) == {"AAPL": Decimal("312.85")}

    def test_nested_object_per_symbol(self) -> None:
        text = '{"AAPL": {"price": "312.85", "volume": 1000}}'
        assert parse_prices(text, SYMBOLS) == {"AAPL": Decimal("312.85")}

    def test_numeric_rather_than_string(self) -> None:
        assert parse_prices('{"AAPL": 312.85}', SYMBOLS) == {"AAPL": Decimal("312.85")}

    def test_lowercase_symbols_are_matched(self) -> None:
        assert parse_prices('{"aapl": "312.85"}', SYMBOLS) == {"AAPL": Decimal("312.85")}


class TestRefusingBadData:
    """A missing price must stay missing. Downstream, every staleness and
    quote rule treats absence as a reason to refuse, so a defaulted value
    converts a refusal into a trade."""

    def test_unparseable_output_yields_nothing(self) -> None:
        assert parse_prices("I could not reach the market data tool.", SYMBOLS) == {}

    def test_empty_output_yields_nothing(self) -> None:
        assert parse_prices("", SYMBOLS) == {}

    def test_symbols_we_did_not_ask_for_are_dropped(self) -> None:
        out = parse_prices('{"AAPL": "312.85", "TSLA": "400.00"}', SYMBOLS)
        assert "TSLA" not in out

    def test_non_numeric_price_is_dropped_not_guessed(self) -> None:
        out = parse_prices('{"AAPL": "unavailable", "MSFT": "487.47"}', SYMBOLS)
        assert out == {"MSFT": Decimal("487.47")}

    def test_zero_and_negative_prices_are_rejected(self) -> None:
        assert parse_prices('{"AAPL": "0", "MSFT": "-5"}', SYMBOLS) == {}

    def test_null_price_is_dropped(self) -> None:
        assert parse_prices('{"AAPL": null}', SYMBOLS) == {}

    def test_a_json_array_is_not_mistaken_for_a_price_map(self) -> None:
        assert parse_prices('["AAPL", "312.85"]', SYMBOLS) == {}


class TestPrecision:
    def test_prices_are_decimal_via_string(self) -> None:
        """A float on the way to Decimal gains digits nobody published."""
        (price,) = parse_prices('{"AAPL": 312.85}', SYMBOLS).values()
        assert isinstance(price, Decimal)
        assert price == Decimal("312.85")
        assert str(price) == "312.85"


def test_only_the_read_tool_is_named() -> None:
    """The allowlisted tool is stated literally, so widening it is a visible
    diff on a safety-critical surface rather than a derived value."""
    assert QUOTE_TOOL == "mcp__robinhood-trading__get_equity_quotes"
    assert "order" not in QUOTE_TOOL
