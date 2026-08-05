"""InvestmentPolicy validator tests (INVESTMENT_POLICY_SPEC acceptance §6.2/6.3)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from tests.conftest import make_policy
from tradeos.domain.policy import (
    AutopilotEnvelope,
    TargetAllocation,
    TradingMode,
)


def test_valid_policy_roundtrip() -> None:
    policy = make_policy()
    reloaded = type(policy).model_validate(policy.model_dump(mode="json"))
    assert reloaded == policy


def test_target_weights_plus_cash_must_not_exceed_one() -> None:
    with pytest.raises(ValidationError, match="exceed 1"):
        make_policy(
            target_allocations=(
                TargetAllocation(symbol="AAPL", weight=Decimal("0.35")),
                TargetAllocation(symbol="MSFT", weight=Decimal("0.35")),
                TargetAllocation(symbol="VTI", weight=Decimal("0.25")),
            ),
            target_cash_weight=Decimal("0.10"),
            max_position_pct=Decimal("0.40"),
        )


def test_target_weight_may_not_exceed_position_cap() -> None:
    with pytest.raises(ValidationError, match="max_position_pct"):
        make_policy(
            target_allocations=(TargetAllocation(symbol="AAPL", weight=Decimal("0.50")),),
            max_position_pct=Decimal("0.10"),
        )


def test_allowlist_denylist_disjoint() -> None:
    with pytest.raises(ValidationError, match="both allow and deny"):
        make_policy(symbol_allowlist=("AAPL",), symbol_denylist=("AAPL",))


def test_unsupported_modes_rejected_in_this_build() -> None:
    for mode in (TradingMode.APPROVAL, TradingMode.RESTRICTED_AUTOPILOT):
        with pytest.raises(ValidationError, match="not supported"):
            make_policy(mode=mode)


def test_autopilot_envelope_structurally_impossible() -> None:
    with pytest.raises(ValidationError, match="autopilot"):
        AutopilotEnvelope(
            dedicated_account_id="x",
            budget_usd=Decimal("100"),
            max_total_loss_usd=Decimal("10"),
            allowed_strategy_ids=[],
            allowed_symbols=[],
        )


def test_invalid_symbol_rejected() -> None:
    with pytest.raises(ValidationError):
        TargetAllocation(symbol="lower", weight=Decimal("0.1"))


def test_symbol_permission_gate() -> None:
    denied = make_policy(symbol_denylist=("TSLA",))
    assert denied.is_symbol_permitted("AAPL")
    assert not denied.is_symbol_permitted("TSLA")
    allowlisted = make_policy(symbol_allowlist=("AAPL", "MSFT"))
    assert allowlisted.is_symbol_permitted("AAPL")
    assert not allowlisted.is_symbol_permitted("JNJ")


def test_fraction_fields_bounded() -> None:
    with pytest.raises(ValidationError, match="fraction"):
        make_policy(min_cash_pct=Decimal("1.5"))
