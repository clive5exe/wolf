"""Shared fixtures: fixed clock, policy/snapshot/context builders, fake claude CLI."""

from __future__ import annotations

import os
import stat
import textwrap
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradeos.domain.clock import FixedClock
from tradeos.domain.common import new_ulid
from tradeos.domain.context import ContextRequirement, MarketContextPackage
from tradeos.domain.market import Quote
from tradeos.domain.orders import OrderSide, ProposedAction, TradeProposal
from tradeos.domain.policy import (
    AssetType,
    InvestmentPolicy,
    RiskTolerance,
    TargetAllocation,
    TradingMode,
)
from tradeos.domain.portfolio import AccountState, PortfolioSnapshot, Position
from tradeos.risk.context import RiskContext

# Tuesday 2026-08-04 15:00 UTC == 11:00 ET → inside the regular session.
NOW = datetime(2026, 8, 4, 15, 0, tzinfo=UTC)

SECTORS = {
    "AAPL": "TECHNOLOGY",
    "MSFT": "TECHNOLOGY",
    "VTI": "BROAD_MARKET",
    "JNJ": "HEALTHCARE",
    "XOM": "ENERGY",
    "TSLA": "TECHNOLOGY",
}


@pytest.fixture()
def clock() -> FixedClock:
    return FixedClock(NOW)


def make_policy(**overrides: object) -> InvestmentPolicy:
    defaults: dict[str, object] = dict(
        policy_id="policy-test",
        version=1,
        created_at=NOW,
        status="active",
        goals_text="test policy",
        risk_tolerance=RiskTolerance.MODERATE,
        time_horizon_years=10,
        mode=TradingMode.PAPER,
        permitted_asset_types=frozenset({AssetType.EQUITY, AssetType.ETF}),
        fractional_shares_allowed=False,
        target_allocations=(
            TargetAllocation(symbol="AAPL", weight=Decimal("0.30")),
            TargetAllocation(symbol="MSFT", weight=Decimal("0.20")),
        ),
        target_cash_weight=Decimal("0.10"),
        max_position_pct=Decimal("0.35"),
        max_sector_pct=Decimal("0.60"),
        min_cash_pct=Decimal("0.02"),
        max_order_value_usd=Decimal("100000"),
        max_orders_per_day=10,
        max_daily_loss_pct=Decimal("0.05"),
        max_drawdown_pct=Decimal("0.20"),
        cooldown_minutes_per_symbol=0,
        stale_quote_max_age_s=120,
    )
    defaults.update(overrides)
    return InvestmentPolicy.model_validate(defaults)


def make_snapshot(
    cash: Decimal,
    holdings: dict[str, tuple[Decimal, Decimal]] | None = None,  # symbol -> (qty, avg_cost)
    prices: dict[str, Decimal] | None = None,
    *,
    quote_as_of: datetime = NOW,
) -> PortfolioSnapshot:
    holdings = holdings or {}
    prices = prices or {}
    positions = tuple(
        Position(
            symbol=symbol,
            quantity=qty,
            asset_type=AssetType.EQUITY,
            avg_cost=cost,
            sector=SECTORS.get(symbol),
        )
        for symbol, (qty, cost) in holdings.items()
    )
    quotes = {
        symbol: Quote(symbol=symbol, price=price, as_of=quote_as_of, source="test")
        for symbol, price in prices.items()
    }
    account = AccountState(account_id="acct-test", cash=cash, positions=positions, as_of=NOW)
    return PortfolioSnapshot(account=account, quotes=quotes, as_of=NOW)


def make_ctx(
    policy: InvestmentPolicy, snapshot: PortfolioSnapshot, **overrides: object
) -> RiskContext:
    total = snapshot.total_value
    defaults: dict[str, object] = dict(
        policy=policy,
        active_policy_version=policy.version,
        snapshot=snapshot,
        now=NOW,
        market_open=True,
        market_note="regular session",
        orders_today=0,
        last_order_time_by_symbol={},
        day_start_equity=total,
        high_water_mark=total,
        kill_switch_engaged=False,
        submitted_client_order_ids=frozenset(),
        context_missing=(),
        sector_map=dict(SECTORS),
    )
    defaults.update(overrides)
    return RiskContext(**defaults)  # type: ignore[arg-type]


def make_action(
    side: OrderSide, symbol: str, quantity: Decimal, asset_type: AssetType = AssetType.EQUITY
) -> ProposedAction:
    return ProposedAction(
        side=side,
        symbol=symbol,
        quantity=quantity,
        asset_type=asset_type,
        rationale="test action",
    )


def make_proposal(actions: tuple[ProposedAction, ...]) -> TradeProposal:
    return TradeProposal(
        proposal_id=new_ulid(),
        correlation_id="corr-test",
        created_at=NOW,
        strategy_id="test_strategy",
        strategy_version="0.0.1",
        actions=actions,
        rationale="test proposal",
        context_package_id="pkg-test",
    )


def make_package(items: tuple = (), requirements: tuple = ()) -> MarketContextPackage:
    return MarketContextPackage(
        package_id=new_ulid(),
        created_at=NOW,
        purpose="test",
        requirements=tuple(requirements) or (ContextRequirement(kind="positions"),),
        items=tuple(items),
    )


_FAKE_CLAUDE = textwrap.dedent(
    '''
    #!/usr/bin/env python3
    """Fake claude CLI for provider tests. Behavior via FAKE_CLAUDE_* env vars."""
    import json, os, re, sys, time

    args = sys.argv[1:]
    if "--version" in args:
        print("2.0.0 (fake-claude)")
        sys.exit(0)
    if args[:2] == ["auth", "status"]:
        if os.environ.get("FAKE_CLAUDE_AUTH") == "out":
            print("Not logged in")
            sys.exit(1)
        print("Logged in: test@example.com (fake)")
        sys.exit(0)

    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    if mode == "hang":
        time.sleep(300)
    if mode == "rate_limited":
        sys.stderr.write("Rate limit exceeded for this billing window\\n")
        sys.exit(1)

    prompt = args[args.index("-p") + 1]
    if mode == "invalid_then_valid":
        state = os.environ["FAKE_CLAUDE_STATE"]
        if not os.path.exists(state):
            with open(state, "w") as fh:
                fh.write("attempt1")
            print(json.dumps({"result": "this is not json", "session_id": "s1"}))
            sys.exit(0)
        mode = "ok"
    if mode == "always_invalid":
        print(json.dumps({"structured_output": {"wrong_field": True}, "session_id": "s1"}))
        sys.exit(0)

    structured_env = os.environ.get("FAKE_CLAUDE_STRUCTURED")
    if structured_env:
        out = json.loads(structured_env)
    else:
        match = re.search(r'echo to exactly "([^"]+)"', prompt)
        out = {"status": "ok", "echo": match.group(1) if match else ""}
    print(json.dumps({
        "structured_output": out,
        "result": json.dumps(out),
        "session_id": "fake-session-1",
        "total_cost_usd": 0.0123,
        "is_error": False,
    }))
    '''
).strip()


@pytest.fixture()
def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    script = tmp_path / "claude"
    script.write_text(_FAKE_CLAUDE + "\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FAKE_CLAUDE_STATE", str(tmp_path / "fake_state"))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_AUTH", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_STRUCTURED", raising=False)
    return str(script)


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may touch the real user data dir."""
    monkeypatch.setenv("TRADEOS_DATA_DIR", str(tmp_path / "data"))
    # and no test may accidentally inherit fake-claude state from the host
    assert os.environ.get("TRADEOS_DATA_DIR", "").startswith(str(tmp_path))
