"""Unit tests for the TUI's pure renderers.

These carry real weight: the drift gauge and freshness glyphs are how a human
reads risk at a glance, so their edge cases are correctness concerns, not
cosmetics.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradeos.tui.glyphs import (
    AGING,
    EXPIRED,
    FRESH,
    GAUGE_TARGET_INDEX,
    GAUGE_WIDTH,
    STALE,
    drift_gauge,
    fmt_age,
    fmt_completeness,
    fmt_money,
    fmt_pct,
    fmt_qty,
    fmt_signed_pct,
    freshness_glyph,
    sparkline,
    truncate,
)
from tradeos.tui.markup import escape, plain, visible_len
from tradeos.tui.theme import key


class TestDriftGauge:
    def test_target_marker_never_moves(self) -> None:
        """Every row must align on the same target column to read as one ruler."""
        for drift in ("-0.01", "-0.001", "0", "0.001", "0.01"):
            gauge = drift_gauge(Decimal(drift))
            assert len(gauge) == GAUGE_WIDTH
            assert "┼" in gauge or gauge[GAUGE_TARGET_INDEX] == "◆"

    def test_on_target_puts_marker_on_the_target_column(self) -> None:
        assert drift_gauge(Decimal("0"))[GAUGE_TARGET_INDEX] == "◆"

    def test_under_and_over_target_are_visually_opposite(self) -> None:
        under = drift_gauge(Decimal("-0.007"))
        over = drift_gauge(Decimal("0.007"))
        assert under.index("◆") < GAUGE_TARGET_INDEX
        assert over.index("◆") > GAUGE_TARGET_INDEX

    def test_scales_to_the_rebalance_band(self) -> None:
        """Full scale is the action threshold, so the edge means 'about to trade'."""
        assert drift_gauge(Decimal("-0.02"), full_scale=Decimal("0.02")) == "◆──┼────"

    def test_off_scale_is_marked_not_silently_clamped(self) -> None:
        assert drift_gauge(Decimal("-0.5"))[0] == "◀"
        assert drift_gauge(Decimal("0.5"))[-1] == "▶"

    def test_no_target_renders_blank_not_a_misleading_zero(self) -> None:
        assert drift_gauge(None).strip() == ""

    def test_rejects_a_nonsense_scale(self) -> None:
        with pytest.raises(ValueError, match="full_scale"):
            drift_gauge(Decimal("0.01"), full_scale=Decimal("0"))


class TestFreshness:
    def test_freshness_ladder(self) -> None:
        assert freshness_glyph(0, 60) == FRESH
        assert freshness_glyph(30, 60) == FRESH
        assert freshness_glyph(45, 60) == AGING
        assert freshness_glyph(61, 60) == STALE

    def test_missing_data_is_louder_than_old_data(self) -> None:
        assert freshness_glyph(None, 60) == EXPIRED


class TestSparkline:
    def test_flat_series_sits_mid_height(self) -> None:
        """A bottomed-out line would read as a crash that never happened."""
        assert set(sparkline([Decimal("100")] * 5)) == {"▅"}

    def test_rising_series_ends_higher_than_it_starts(self) -> None:
        line = sparkline([Decimal(n) for n in range(10)])
        assert line[0] == "▁"
        assert line[-1] == "█"

    def test_empty_series_renders_nothing(self) -> None:
        assert sparkline([]) == ""

    def test_respects_width(self) -> None:
        assert len(sparkline([Decimal(n) for n in range(100)], width=10)) == 10


class TestNumberFormatting:
    def test_share_counts_never_use_scientific_notation(self) -> None:
        assert fmt_qty(Decimal("140")) == "140"
        assert fmt_qty(Decimal("1.5")) == "1.5"

    def test_money_and_percentages(self) -> None:
        assert fmt_money(Decimal("99955.45")) == "$99,955.45"
        assert fmt_pct(Decimal("0.399")) == "39.9%"

    def test_signed_percent_uses_a_true_minus_for_column_alignment(self) -> None:
        assert fmt_signed_pct(Decimal("-0.001")) == "−0.1%"
        assert fmt_signed_pct(Decimal("0.001")) == "+0.1%"

    def test_completeness_renders_as_a_percentage(self) -> None:
        assert fmt_completeness("1") == "100%"
        assert fmt_completeness("0.5") == "50%"
        assert fmt_completeness("") == "·"
        assert fmt_completeness("not-a-number") == "not-a-number"

    def test_age(self) -> None:
        assert fmt_age(30) == "30s"
        assert fmt_age(600) == "10m"
        assert fmt_age(None) == "no data"

    def test_truncate_marks_that_it_truncated(self) -> None:
        assert truncate("abcdef", 4) == "abc…"
        assert truncate("abc", 10) == "abc"


class TestMarkup:
    def test_key_hints_survive_the_markup_parser(self) -> None:
        """Unescaped ``[c]`` is eaten as a style tag. The footer would go blank."""
        assert plain(key("c", "ycle")) == "[c]ycle"

    def test_visible_len_ignores_style_tags(self) -> None:
        assert visible_len("[#FF2247]abc[/]") == 3

    def test_escape_protects_literal_brackets(self) -> None:
        assert plain(escape("[watching]")) == "[watching]"


class TestDirectionSurvivesWithoutColour:
    """The brand hue is 350, which is red, and measurement showed no money-down
    red separates from it (1.04 to 1.62 contrast across every candidate). So
    direction cannot rest on colour alone."""

    def test_arrows_mark_direction(self) -> None:
        from tradeos.tui.glyphs import direction

        assert direction(Decimal("1")) == "▲"
        assert direction(Decimal("-1")) == "▼"
        assert direction(Decimal("0")) == "·"
        assert direction(None) == "·"

    def test_signed_values_can_carry_their_arrow(self) -> None:
        from tradeos.tui.glyphs import fmt_signed, fmt_signed_pct

        assert fmt_signed(Decimal("12.5"), arrow=True).startswith("▲")
        assert fmt_signed(Decimal("-12.5"), arrow=True).startswith("▼")
        assert fmt_signed_pct(Decimal("0.075"), arrow=True) == "▲ +7.5%"

    def test_arrows_are_opt_in_so_columns_stay_narrow(self) -> None:
        from tradeos.tui.glyphs import fmt_signed

        assert fmt_signed(Decimal("12.5")) == "+12.50"
