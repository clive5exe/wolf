"""The v0.1 rule set (RISK_POLICY_SPEC §4). Every rule:

- is a pure function of (action, action_index, ctx);
- FAILS CLOSED when data it needs is missing;
- reports observed value and applied limit as human-readable strings;
- runs on every evaluation (the engine never short-circuits).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from tradeos.domain.common import pct
from tradeos.domain.orders import OrderSide, ProposedAction
from tradeos.domain.policy import TradingMode
from tradeos.domain.risk import RiskCheckResult, client_order_id_for
from tradeos.risk.context import RiskContext


class RuleFn(Protocol):
    def __call__(
        self, action: ProposedAction, action_index: int, ctx: RiskContext
    ) -> tuple[bool, str, str, str]:
        """Returns (passed, observed, limit, message)."""
        ...


@dataclass(frozen=True)
class RiskRule:
    rule_id: str
    blocking: bool
    fn: RuleFn

    def check(self, action: ProposedAction, action_index: int, ctx: RiskContext) -> RiskCheckResult:
        passed, observed, limit, message = self.fn(action, action_index, ctx)
        return RiskCheckResult(
            rule_id=self.rule_id,
            passed=passed,
            blocking=self.blocking,
            observed=observed,
            limit=limit,
            message=message,
        )


_Check = tuple[bool, str, str, str]


def _fail_closed(what: str, limit: str) -> _Check:
    return False, f"missing: {what}", limit, f"fail closed — {what} unavailable"


def kill_switch(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    if ctx.kill_switch_engaged:
        return False, "engaged", "disengaged", "kill switch is engaged — all orders vetoed"
    return True, "disengaged", "disengaged", "kill switch clear"


def mode_permits_orders(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    mode = ctx.policy.mode
    if mode == TradingMode.PAPER:
        return True, mode.value, "paper+", "paper mode permits simulated orders"
    return False, mode.value, "paper+", f"mode {mode.value} does not permit order preparation"


def asset_type_permitted(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    permitted = action.asset_type in ctx.policy.permitted_asset_types
    allowed = ",".join(sorted(t.value for t in ctx.policy.permitted_asset_types))
    return (
        permitted,
        action.asset_type.value,
        allowed,
        "asset type permitted"
        if permitted
        else f"asset type {action.asset_type.value} not permitted",
    )


def symbol_allowed(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    symbol = action.symbol
    if not ctx.policy.is_symbol_permitted(symbol):
        return False, symbol, "allow/deny lists", f"{symbol} blocked by symbol lists"
    if ctx.policy.excluded_sectors:
        sector = ctx.sector_map.get(symbol)
        if sector is None:
            if action.side == OrderSide.BUY:
                return _fail_closed(f"sector for {symbol}", "excluded sectors configured")
        elif sector.upper() in ctx.policy.excluded_sectors:
            return False, sector, "excluded sectors", f"{symbol} is in excluded sector {sector}"
    return True, symbol, "allow/deny lists", "symbol permitted"


def max_order_value(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    quote = ctx.snapshot.quotes.get(action.symbol)
    limit = f"${ctx.policy.max_order_value_usd}"
    if quote is None:
        return _fail_closed(f"quote for {action.symbol}", limit)
    notional = quote.price * action.quantity
    ok = notional <= ctx.policy.max_order_value_usd
    return (
        ok,
        f"${notional.quantize(Decimal('0.01'))}",
        limit,
        ("order value within limit" if ok else "order value exceeds per-order limit"),
    )


def max_position_pct(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    limit = pct(ctx.policy.max_position_pct)
    quote = ctx.snapshot.quotes.get(action.symbol)
    total = ctx.snapshot.total_value
    if quote is None or total is None or total == 0:
        return _fail_closed(f"pricing for {action.symbol} / portfolio", limit)
    held = ctx.snapshot.account.position_for(action.symbol)
    held_qty = held.quantity if held else Decimal("0")
    post_qty = (
        held_qty + action.quantity if action.side == OrderSide.BUY else held_qty - action.quantity
    )
    post_qty = max(post_qty, Decimal("0"))
    post_weight = (post_qty * quote.price) / total  # cash<->stock swap keeps total constant
    ok = post_weight <= ctx.policy.max_position_pct
    return (
        ok,
        pct(post_weight),
        limit,
        (
            "post-trade position within cap"
            if ok
            else "post-trade position exceeds max_position_pct"
        ),
    )


def max_sector_pct(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    limit = pct(ctx.policy.max_sector_pct)
    if action.side == OrderSide.SELL:
        return True, "n/a (sell)", limit, "sells cannot increase sector exposure"
    sector = ctx.sector_map.get(action.symbol)
    if sector is None:
        return _fail_closed(f"sector for {action.symbol}", limit)
    quote = ctx.snapshot.quotes.get(action.symbol)
    total = ctx.snapshot.total_value
    current = ctx.snapshot.sector_weight(sector)
    if quote is None or total is None or total == 0 or current is None:
        return _fail_closed(f"sector pricing for {sector}", limit)
    post = current + (action.quantity * quote.price) / total
    ok = post <= ctx.policy.max_sector_pct
    return (
        ok,
        pct(post),
        limit,
        (
            f"post-trade {sector} exposure within cap"
            if ok
            else f"post-trade {sector} exposure exceeds max_sector_pct"
        ),
    )


def min_cash(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    limit = pct(ctx.policy.min_cash_pct)
    if action.side == OrderSide.SELL:
        return True, "n/a (sell)", limit, "sells increase cash"
    quote = ctx.snapshot.quotes.get(action.symbol)
    total = ctx.snapshot.total_value
    if quote is None or total is None or total == 0:
        return _fail_closed("pricing for cash projection", limit)
    post_cash = ctx.snapshot.account.cash - quote.price * action.quantity
    if post_cash < 0:
        return False, f"${post_cash.quantize(Decimal('0.01'))}", limit, "buy exceeds available cash"
    post_weight = post_cash / total
    ok = post_weight >= ctx.policy.min_cash_pct
    return (
        ok,
        pct(post_weight),
        limit,
        ("post-trade cash above floor" if ok else "post-trade cash below min_cash_pct"),
    )


def sufficient_holdings(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    if action.side == OrderSide.BUY:
        return True, "n/a (buy)", "held quantity", "buys need cash, not holdings"
    held = ctx.snapshot.account.position_for(action.symbol)
    held_qty = held.quantity if held else Decimal("0")
    ok = action.quantity <= held_qty
    return (
        ok,
        f"sell {action.quantity} vs held {held_qty}",
        "held quantity",
        ("holdings sufficient" if ok else "oversell — shorting is not supported"),
    )


def max_orders_per_day(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    limit = str(ctx.policy.max_orders_per_day)
    ok = ctx.orders_today + action_index < ctx.policy.max_orders_per_day
    return (
        ok,
        str(ctx.orders_today + action_index),
        limit,
        ("daily order budget available" if ok else "max orders per day reached"),
    )


def symbol_cooldown(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    limit = f"{ctx.policy.cooldown_minutes_per_symbol} min"
    last = ctx.last_order_time_by_symbol.get(action.symbol)
    if last is None:
        return True, "no prior order", limit, "no cooldown applicable"
    elapsed_min = (ctx.now - last).total_seconds() / 60
    ok = elapsed_min >= ctx.policy.cooldown_minutes_per_symbol
    return (
        ok,
        f"{elapsed_min:.0f} min since last order",
        limit,
        ("cooldown satisfied" if ok else f"cooldown active for {action.symbol}"),
    )


def max_daily_loss(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    limit = pct(ctx.policy.max_daily_loss_pct)
    total = ctx.snapshot.total_value
    if ctx.day_start_equity is None or total is None or ctx.day_start_equity == 0:
        return _fail_closed("day-start equity baseline", limit)
    loss = (ctx.day_start_equity - total) / ctx.day_start_equity
    ok = loss <= ctx.policy.max_daily_loss_pct
    return (
        ok,
        pct(max(loss, Decimal("0"))),
        limit,
        ("daily loss within limit" if ok else "daily loss limit breached — trading halted"),
    )


def max_drawdown(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    limit = pct(ctx.policy.max_drawdown_pct)
    total = ctx.snapshot.total_value
    if ctx.high_water_mark is None or total is None or ctx.high_water_mark == 0:
        return _fail_closed("high-water mark", limit)
    drawdown = (ctx.high_water_mark - total) / ctx.high_water_mark
    ok = drawdown <= ctx.policy.max_drawdown_pct
    return (
        ok,
        pct(max(drawdown, Decimal("0"))),
        limit,
        ("drawdown within limit" if ok else "max drawdown breached — trading halted"),
    )


def trading_hours(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    ok = ctx.market_open
    return (
        ok,
        ctx.market_note,
        "regular session (or simulated paper session)",
        ("session permits orders" if ok else "outside permitted trading hours"),
    )


def stale_quote(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    limit = f"{ctx.policy.stale_quote_max_age_s}s"
    quote = ctx.snapshot.quotes.get(action.symbol)
    if quote is None:
        return _fail_closed(f"quote for {action.symbol}", limit)
    age = quote.age_s(ctx.now)
    ok = age <= ctx.policy.stale_quote_max_age_s
    return (
        ok,
        f"{age}s old",
        limit,
        ("quote fresh enough" if ok else f"quote for {action.symbol} is stale"),
    )


def stale_context(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    if ctx.context_missing:
        return (
            False,
            f"missing/expired: {', '.join(ctx.context_missing)}",
            "all required context fresh",
            "required context is missing or expired",
        )
    return True, "complete", "all required context fresh", "context package complete"


def duplicate_order(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    # proposal_id lives on the verdict; the engine passes it via closure — see
    # RiskEngine._duplicate_rule. This module-level variant checks the shared set.
    return True, "n/a", "unique client_order_id", "checked by engine-bound rule"


def policy_changed(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    ok = ctx.active_policy_version == ctx.policy.version
    return (
        ok,
        f"pinned v{ctx.policy.version}, active v{ctx.active_policy_version}",
        ("pinned == active"),
        ("policy stable since trigger" if ok else "policy changed mid-cycle — re-trigger required"),
    )


def fractional_permitted(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    is_fractional = action.quantity != action.quantity.to_integral_value()
    if is_fractional and not ctx.policy.fractional_shares_allowed:
        return (
            False,
            str(action.quantity),
            "whole shares only",
            "fractional quantity while fractional shares are not allowed",
        )
    return (
        True,
        str(action.quantity),
        ("fractional allowed" if ctx.policy.fractional_shares_allowed else "whole shares only"),
        "quantity form permitted",
    )


def earnings_blackout(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    days = ctx.policy.earnings_blackout_days
    if days == 0:
        return True, "n/a", "disabled", "earnings blackout disabled in policy"
    # Honest fail-closed: the rule is configured but v0.1 has no calendar source.
    return _fail_closed("earnings calendar source", f"{days} day blackout")


def concentration_advisory(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
    total = ctx.snapshot.total_value
    if total is None or total == 0:
        return True, "unpriced", "top-3 <= 50% (advisory)", "cannot assess concentration"
    weights = sorted(
        (
            (p.quantity * ctx.snapshot.quotes[p.symbol].price) / total
            for p in ctx.snapshot.account.positions
            if p.symbol in ctx.snapshot.quotes
        ),
        reverse=True,
    )
    top3 = sum(weights[:3], Decimal("0"))
    ok = top3 <= Decimal("0.5")
    return (
        ok,
        pct(top3),
        "top-3 <= 50% (advisory)",
        ("concentration acceptable" if ok else "top-3 holdings exceed 50% of portfolio (advisory)"),
    )


def make_duplicate_rule(proposal_id: str) -> RiskRule:
    """Engine-bound duplicate check: derives the deterministic client id for
    this (proposal, action) and vetoes if it was ever submitted."""

    def _dup(action: ProposedAction, action_index: int, ctx: RiskContext) -> _Check:
        client_id = client_order_id_for(proposal_id, action_index, action)
        if client_id in ctx.submitted_client_order_ids:
            return (
                False,
                f"client_order_id {client_id[:12]}… seen",
                "unique",
                ("duplicate order — already submitted"),
            )
        return True, f"client_order_id {client_id[:12]}… new", "unique", "no duplicate found"

    return RiskRule(rule_id="duplicate_order", blocking=True, fn=_dup)


DEFAULT_RULES: tuple[RiskRule, ...] = (
    RiskRule("kill_switch", True, kill_switch),
    RiskRule("mode_permits_orders", True, mode_permits_orders),
    RiskRule("asset_type_permitted", True, asset_type_permitted),
    RiskRule("symbol_allowed", True, symbol_allowed),
    RiskRule("max_order_value", True, max_order_value),
    RiskRule("max_position_pct", True, max_position_pct),
    RiskRule("max_sector_pct", True, max_sector_pct),
    RiskRule("min_cash", True, min_cash),
    RiskRule("sufficient_holdings", True, sufficient_holdings),
    RiskRule("max_orders_per_day", True, max_orders_per_day),
    RiskRule("symbol_cooldown", True, symbol_cooldown),
    RiskRule("max_daily_loss", True, max_daily_loss),
    RiskRule("max_drawdown", True, max_drawdown),
    RiskRule("trading_hours", True, trading_hours),
    RiskRule("stale_quote", True, stale_quote),
    RiskRule("stale_context", True, stale_context),
    RiskRule("policy_changed", True, policy_changed),
    RiskRule("fractional_permitted", True, fractional_permitted),
    RiskRule("earnings_blackout", True, earnings_blackout),
    RiskRule("concentration_advisory", False, concentration_advisory),
)
