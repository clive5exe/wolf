"""Per-rule pass/veto/fail-closed tests (RISK_POLICY_SPEC acceptance §7.1).

Exact Decimal arithmetic throughout — no float comparisons.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from tests.conftest import NOW, make_action, make_ctx, make_policy, make_snapshot
from tradeos.domain.orders import OrderSide
from tradeos.domain.policy import AssetType, TradingMode
from tradeos.risk import rules

D = Decimal
BUY = OrderSide.BUY
SELL = OrderSide.SELL


def base_snapshot(**kwargs: object):
    return make_snapshot(
        D("10000"),
        holdings={"AAPL": (D("10"), D("150"))},
        prices={"AAPL": D("200"), "MSFT": D("400")},
        **kwargs,  # type: ignore[arg-type]
    )


# -- kill switch ---------------------------------------------------------------


def test_kill_switch_veto() -> None:
    ctx = make_ctx(make_policy(), base_snapshot(), kill_switch_engaged=True)
    passed, *_ = rules.kill_switch(make_action(BUY, "AAPL", D("1")), 0, ctx)
    assert not passed


def test_kill_switch_pass() -> None:
    ctx = make_ctx(make_policy(), base_snapshot())
    assert rules.kill_switch(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]


# -- mode ----------------------------------------------------------------------


def test_mode_read_only_vetoes_orders() -> None:
    ctx = make_ctx(make_policy(mode=TradingMode.READ_ONLY), base_snapshot())
    assert not rules.mode_permits_orders(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]


def test_mode_paper_permits() -> None:
    ctx = make_ctx(make_policy(), base_snapshot())
    assert rules.mode_permits_orders(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]


# -- asset type / symbol -------------------------------------------------------


def test_asset_type_not_permitted() -> None:
    policy = make_policy(permitted_asset_types=frozenset({AssetType.ETF}))
    ctx = make_ctx(policy, base_snapshot())
    action = make_action(BUY, "AAPL", D("1"), asset_type=AssetType.EQUITY)
    assert not rules.asset_type_permitted(action, 0, ctx)[0]


def test_symbol_denylist_veto() -> None:
    ctx = make_ctx(make_policy(symbol_denylist=("AAPL",)), base_snapshot())
    assert not rules.symbol_allowed(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]


def test_symbol_excluded_sector_veto() -> None:
    ctx = make_ctx(make_policy(excluded_sectors=("TECHNOLOGY",)), base_snapshot())
    assert not rules.symbol_allowed(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]


def test_symbol_unknown_sector_fails_closed_for_buys() -> None:
    ctx = make_ctx(make_policy(excluded_sectors=("UTILITIES",)), base_snapshot(), sector_map={})
    passed, observed, _, _ = rules.symbol_allowed(make_action(BUY, "AAPL", D("1")), 0, ctx)
    assert not passed and "missing" in observed


# -- order value ---------------------------------------------------------------


def test_max_order_value_veto_and_boundary() -> None:
    policy = make_policy(max_order_value_usd=D("1000"))
    ctx = make_ctx(policy, base_snapshot())
    # 5 * 200 == 1000 → boundary passes (<=)
    assert rules.max_order_value(make_action(BUY, "AAPL", D("5")), 0, ctx)[0]
    assert not rules.max_order_value(make_action(BUY, "AAPL", D("6")), 0, ctx)[0]


def test_max_order_value_fails_closed_without_quote() -> None:
    ctx = make_ctx(make_policy(), make_snapshot(D("10000"), prices={}))
    passed, observed, _, _ = rules.max_order_value(make_action(BUY, "AAPL", D("1")), 0, ctx)
    assert not passed and "missing" in observed


# -- position sizing -----------------------------------------------------------


def test_max_position_pct_veto() -> None:
    # portfolio: 10k cash + 10*200 AAPL = 12k total; cap 35% → 4200 max AAPL value.
    # buying 12 more → 22*200 = 4400 → 36.67% → veto
    ctx = make_ctx(make_policy(), base_snapshot())
    assert not rules.max_position_pct(make_action(BUY, "AAPL", D("12")), 0, ctx)[0]
    # 11 more → 21*200 = 4200 → exactly 35% → pass
    assert rules.max_position_pct(make_action(BUY, "AAPL", D("11")), 0, ctx)[0]


def test_max_sector_pct_veto() -> None:
    # TECHNOLOGY currently 2000/12000; cap 20%: buying 2 more AAPL → 2400/12000 = 20% pass;
    # 3 more → 2600/12000 ≈ 21.7% veto
    policy = make_policy(max_sector_pct=D("0.20"))
    ctx = make_ctx(policy, base_snapshot())
    assert rules.max_sector_pct(make_action(BUY, "AAPL", D("2")), 0, ctx)[0]
    assert not rules.max_sector_pct(make_action(BUY, "AAPL", D("3")), 0, ctx)[0]


def test_min_cash_veto() -> None:
    # total 12000, min cash 2% → 240. Cash 10000; buy 49*200=9800 → 200 left → veto
    ctx = make_ctx(make_policy(), base_snapshot())
    assert not rules.min_cash(make_action(BUY, "AAPL", D("49")), 0, ctx)[0]
    # 48*200=9600 → 400 left (3.3%) → pass
    assert rules.min_cash(make_action(BUY, "AAPL", D("48")), 0, ctx)[0]


def test_sufficient_holdings() -> None:
    ctx = make_ctx(make_policy(), base_snapshot())
    assert rules.sufficient_holdings(make_action(SELL, "AAPL", D("10")), 0, ctx)[0]
    assert not rules.sufficient_holdings(make_action(SELL, "AAPL", D("11")), 0, ctx)[0]


# -- rate limits ---------------------------------------------------------------


def test_max_orders_per_day() -> None:
    policy = make_policy(max_orders_per_day=3)
    ctx = make_ctx(policy, base_snapshot(), orders_today=3)
    assert not rules.max_orders_per_day(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]
    ctx2 = make_ctx(policy, base_snapshot(), orders_today=2)
    assert rules.max_orders_per_day(make_action(BUY, "AAPL", D("1")), 0, ctx2)[0]
    # multi-action proposals consume budget by index
    assert not rules.max_orders_per_day(make_action(BUY, "AAPL", D("1")), 1, ctx2)[0]


def test_symbol_cooldown() -> None:
    policy = make_policy(cooldown_minutes_per_symbol=60)
    recent = {"AAPL": NOW - timedelta(minutes=30)}
    ctx = make_ctx(policy, base_snapshot(), last_order_time_by_symbol=recent)
    assert not rules.symbol_cooldown(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]
    old = {"AAPL": NOW - timedelta(minutes=61)}
    ctx2 = make_ctx(policy, base_snapshot(), last_order_time_by_symbol=old)
    assert rules.symbol_cooldown(make_action(BUY, "AAPL", D("1")), 0, ctx2)[0]


# -- loss limits ---------------------------------------------------------------


def test_max_daily_loss_veto_and_fail_closed() -> None:
    policy = make_policy(max_daily_loss_pct=D("0.02"))
    snapshot = base_snapshot()  # total 12000
    ctx = make_ctx(policy, snapshot, day_start_equity=D("12500"))  # loss 4%
    assert not rules.max_daily_loss(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]
    ctx_ok = make_ctx(policy, snapshot, day_start_equity=D("12100"))  # loss 0.83%
    assert rules.max_daily_loss(make_action(BUY, "AAPL", D("1")), 0, ctx_ok)[0]
    ctx_missing = make_ctx(policy, snapshot, day_start_equity=None)
    assert not rules.max_daily_loss(make_action(BUY, "AAPL", D("1")), 0, ctx_missing)[0]


def test_max_drawdown_veto() -> None:
    policy = make_policy(max_drawdown_pct=D("0.10"))
    snapshot = base_snapshot()  # 12000
    ctx = make_ctx(policy, snapshot, high_water_mark=D("14000"))  # dd ≈ 14.3%
    assert not rules.max_drawdown(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]
    ctx_ok = make_ctx(policy, snapshot, high_water_mark=D("13000"))  # dd ≈ 7.7%
    assert rules.max_drawdown(make_action(BUY, "AAPL", D("1")), 0, ctx_ok)[0]


# -- session / staleness -------------------------------------------------------


def test_trading_hours_veto() -> None:
    ctx = make_ctx(make_policy(), base_snapshot(), market_open=False, market_note="closed")
    assert not rules.trading_hours(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]


def test_stale_quote_veto() -> None:
    stale = make_snapshot(
        D("10000"),
        holdings={"AAPL": (D("10"), D("150"))},
        prices={"AAPL": D("200")},
        quote_as_of=NOW - timedelta(seconds=121),
    )
    ctx = make_ctx(make_policy(stale_quote_max_age_s=120), stale)
    assert not rules.stale_quote(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]
    fresh_ctx = make_ctx(make_policy(stale_quote_max_age_s=120), base_snapshot())
    assert rules.stale_quote(make_action(BUY, "AAPL", D("1")), 0, fresh_ctx)[0]


def test_stale_context_veto() -> None:
    ctx = make_ctx(make_policy(), base_snapshot(), context_missing=("quote:MSFT",))
    assert not rules.stale_context(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]


# -- consistency ---------------------------------------------------------------


def test_policy_changed_veto() -> None:
    ctx = make_ctx(make_policy(), base_snapshot(), active_policy_version=2)
    assert not rules.policy_changed(make_action(BUY, "AAPL", D("1")), 0, ctx)[0]


def test_fractional_veto_when_not_allowed() -> None:
    ctx = make_ctx(make_policy(fractional_shares_allowed=False), base_snapshot())
    assert not rules.fractional_permitted(make_action(BUY, "AAPL", D("1.5")), 0, ctx)[0]
    ctx_ok = make_ctx(make_policy(fractional_shares_allowed=True), base_snapshot())
    assert rules.fractional_permitted(make_action(BUY, "AAPL", D("1.5")), 0, ctx_ok)[0]


def test_earnings_blackout_disabled_passes_enabled_fails_closed() -> None:
    ctx = make_ctx(make_policy(earnings_blackout_days=0), base_snapshot())
    passed, _, limit, _ = rules.earnings_blackout(make_action(BUY, "AAPL", D("1")), 0, ctx)
    assert passed and limit == "disabled"
    ctx_on = make_ctx(make_policy(earnings_blackout_days=3), base_snapshot())
    assert not rules.earnings_blackout(make_action(BUY, "AAPL", D("1")), 0, ctx_on)[0]


def test_concentration_advisory_is_nonblocking_flag() -> None:
    heavy = make_snapshot(
        D("100"),
        holdings={"AAPL": (D("50"), D("100"))},
        prices={"AAPL": D("200")},
    )
    ctx = make_ctx(make_policy(), heavy)
    passed, _observed, _, _ = rules.concentration_advisory(make_action(BUY, "AAPL", D("1")), 0, ctx)
    assert not passed  # flagged...
    advisory = [r for r in rules.DEFAULT_RULES if r.rule_id == "concentration_advisory"]
    assert advisory[0].blocking is False  # ...but never a veto
