"""Journal reducer tests.

The journal is how a human audits the machine, so the properties that matter
are: a no-action is a record, a veto is a record, and fills attach to the cycle
that caused them even though they correlate by proposal id.
"""

from __future__ import annotations

from decimal import Decimal

from tradeos.domain.common import utc_now
from tradeos.notifications.base import NullNotifier
from tradeos.runtime.facade import RuntimeConfig, TradeOSRuntime
from tradeos.runtime.journal import (
    EquityPoint,
    FillRecord,
    build_journal,
    day_change,
    equity_history,
    max_drawdown,
)


def _runtime() -> TradeOSRuntime:
    runtime = TradeOSRuntime(RuntimeConfig(in_memory=True, notifier=NullNotifier()))
    runtime.ensure_sample_policy()
    return runtime


class TestBuildJournal:
    def test_a_filled_cycle_becomes_one_record_with_its_fills(self) -> None:
        runtime = _runtime()
        outcome = runtime.run_cycle(trigger="test")
        records = runtime.journal()

        assert len(records) == 1
        record = records[0]
        assert record.correlation_id == outcome.correlation_id
        assert record.status == "completed"
        assert record.filled_count == 5
        assert record.headline == "5 fills"
        assert {f.symbol for f in record.fills} == {"VTI", "AAPL", "MSFT", "JNJ", "XOM"}

    def test_fills_attach_to_their_cycle_despite_correlating_by_proposal(self) -> None:
        """Order events carry the proposal id. The reducer must bridge the two."""
        runtime = _runtime()
        runtime.run_cycle(trigger="first")
        record = runtime.journal()[0]
        assert record.proposal_id is not None
        assert all(f.client_order_id for f in record.fills)

    def test_a_no_action_is_a_first_class_record(self) -> None:
        runtime = _runtime()
        runtime.run_cycle(trigger="first")  # trades into the targets
        runtime.run_cycle(trigger="second")  # nothing left to do

        records = runtime.journal()
        assert len(records) == 2
        latest = records[0]
        assert latest.status == "no_action"
        assert latest.headline == "no action"
        assert latest.filled_count == 0
        assert latest.reason  # a no-action always explains itself

    def test_records_are_newest_first(self) -> None:
        runtime = _runtime()
        for i in range(3):
            runtime.run_cycle(trigger=f"cycle-{i}")
        records = runtime.journal()
        times = [r.occurred_at for r in records]
        assert times == sorted(times, reverse=True)

    def test_limit_returns_the_most_recent(self) -> None:
        runtime = _runtime()
        for i in range(3):
            runtime.run_cycle(trigger=f"cycle-{i}")
        assert len(runtime.journal(2)) == 2

    def test_every_rule_result_is_preserved(self) -> None:
        """The verdict screen promises 'all rules, every time'. The data must back it."""
        runtime = _runtime()
        runtime.run_cycle(trigger="test")
        verdict = runtime.journal()[0].verdicts[0]
        configured = set(runtime.risk_rule_ids())
        recorded = {r.rule_id for r in verdict.results}
        assert configured <= recorded
        assert verdict.rules_total == len(verdict.results)

    def test_advisory_failures_do_not_count_as_vetoes(self) -> None:
        runtime = _runtime()
        runtime.run_cycle(trigger="test")
        record = runtime.journal()[0]
        for verdict in record.verdicts:
            for rule in verdict.results:
                if not rule.blocking:
                    assert not rule.is_veto

    def test_empty_log_yields_no_records(self) -> None:
        assert build_journal([]) == ()

    def test_cycle_detail_finds_a_specific_decision(self) -> None:
        runtime = _runtime()
        outcome = runtime.run_cycle(trigger="test")
        found = runtime.cycle_detail(outcome.correlation_id)
        assert found is not None
        assert found.correlation_id == outcome.correlation_id
        assert runtime.cycle_detail("does-not-exist") is None


class TestSlippage:
    def test_slippage_drag_is_a_cost_on_both_sides_of_a_trade(self) -> None:
        """Signing it would render half of all slippage as a gain."""
        buy = FillRecord(
            symbol="VTI",
            side="buy",
            quantity=Decimal("10"),
            fill_price=Decimal("101"),
            quote_price=Decimal("100"),
        )
        sell = FillRecord(
            symbol="VTI",
            side="sell",
            quantity=Decimal("10"),
            fill_price=Decimal("99"),
            quote_price=Decimal("100"),
        )
        assert buy.slippage_cost == Decimal("10.00")
        assert sell.slippage_cost == Decimal("-10.00")
        assert buy.slippage_drag == sell.slippage_drag == Decimal("10.00")

    def test_unpriced_fill_reports_no_slippage_rather_than_zero(self) -> None:
        fill = FillRecord(symbol="VTI", side="buy", quantity=Decimal("10"))
        assert fill.slippage_cost is None
        assert fill.slippage_drag is None


class TestEquityStats:
    def _points(self, *values: str) -> tuple[EquityPoint, ...]:
        now = utc_now()
        return tuple(EquityPoint(at=now, equity=Decimal(v)) for v in values)

    def test_max_drawdown_measures_peak_to_trough(self) -> None:
        points = self._points("100", "120", "90", "110")
        assert max_drawdown(points) == Decimal("0.25")  # 120 -> 90

    def test_monotonic_rise_has_no_drawdown(self) -> None:
        assert max_drawdown(self._points("100", "110", "120")) == Decimal("0")

    def test_no_history_is_none_not_zero(self) -> None:
        assert max_drawdown([]) is None

    def test_day_change_needs_two_points_in_the_same_day(self) -> None:
        assert day_change(self._points("100"), now=utc_now()) is None
        assert day_change(self._points("100", "110"), now=utc_now()) == Decimal("0.1")

    def test_equity_history_reads_snapshots_from_the_log(self) -> None:
        runtime = _runtime()
        runtime.run_cycle(trigger="test")
        points = equity_history(runtime.events.iter_events())
        assert points
        assert all(p.equity > 0 for p in points)
