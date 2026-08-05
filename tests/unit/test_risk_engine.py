"""Engine-level behavior: verdict aggregation, cumulative simulation,
ValidatedOrder issuance, duplicate detection (RISK_POLICY_SPEC §7.2/7.4)."""

from __future__ import annotations

from decimal import Decimal

from tests.conftest import make_action, make_ctx, make_policy, make_proposal, make_snapshot
from tradeos.domain.orders import OrderSide
from tradeos.domain.risk import RiskVerdict, client_order_id_for
from tradeos.risk.engine import RiskEngine

D = Decimal


def test_approved_action_yields_validated_order() -> None:
    ctx = make_ctx(
        make_policy(), make_snapshot(D("10000"), prices={"AAPL": D("200"), "MSFT": D("400")})
    )
    proposal = make_proposal((make_action(OrderSide.BUY, "AAPL", D("5")),))
    validation = RiskEngine().validate_proposal(proposal, ctx)
    assert validation.fully_approved
    assert len(validation.validated_orders) == 1
    order = validation.validated_orders[0]
    assert order.client_order_id == client_order_id_for(
        proposal.proposal_id, 0, proposal.actions[0]
    )
    assert order.verdict.approved
    # every configured rule appears in the verdict. No short-circuiting
    rule_ids = {r.rule_id for r in order.verdict.results}
    assert {"kill_switch", "max_position_pct", "stale_quote", "duplicate_order"} <= rule_ids


def test_vetoed_action_yields_no_order_and_full_results() -> None:
    ctx = make_ctx(
        make_policy(symbol_denylist=("AAPL",)),
        make_snapshot(D("10000"), prices={"AAPL": D("200")}),
    )
    proposal = make_proposal((make_action(OrderSide.BUY, "AAPL", D("5")),))
    validation = RiskEngine().validate_proposal(proposal, ctx)
    assert not validation.fully_approved
    assert validation.validated_orders == ()
    verdict = validation.verdicts[0]
    failed = [r.rule_id for r in verdict.results if r.blocking and not r.passed]
    assert failed == ["symbol_allowed"]
    assert len(verdict.results) >= 20  # all rules ran anyway


def test_cumulative_simulation_sell_funds_buy() -> None:
    # cash 100. Sell 10 AAPL @200 frees 2000 → buy 5 MSFT @400 = 2000 fits only
    # if the sell was applied to working state first.
    snapshot = make_snapshot(
        D("100"),
        holdings={"AAPL": (D("10"), D("150"))},
        prices={"AAPL": D("200"), "MSFT": D("400")},
    )
    policy = make_policy(max_position_pct=D("0.98"), max_sector_pct=D("1"), min_cash_pct=D("0"))
    ctx = make_ctx(policy, snapshot)
    proposal = make_proposal(
        (
            make_action(OrderSide.SELL, "AAPL", D("10")),
            make_action(OrderSide.BUY, "MSFT", D("5")),
        )
    )
    validation = RiskEngine().validate_proposal(proposal, ctx)
    assert validation.fully_approved, [
        (v.action_index, [r.rule_id for r in v.results if r.blocking and not r.passed])
        for v in validation.verdicts
    ]


def test_vetoed_sell_does_not_fund_later_buy() -> None:
    # Same shape, but the sell is vetoed (denylist): the buy must then fail min_cash.
    snapshot = make_snapshot(
        D("100"),
        holdings={"AAPL": (D("10"), D("150"))},
        prices={"AAPL": D("200"), "MSFT": D("400")},
    )
    policy = make_policy(
        symbol_denylist=("AAPL",),
        max_position_pct=D("0.98"),
        max_sector_pct=D("1"),
        min_cash_pct=D("0"),
    )
    ctx = make_ctx(policy, snapshot)
    proposal = make_proposal(
        (
            make_action(OrderSide.SELL, "AAPL", D("10")),
            make_action(OrderSide.BUY, "MSFT", D("5")),
        )
    )
    validation = RiskEngine().validate_proposal(proposal, ctx)
    assert [v.approved for v in validation.verdicts] == [False, False]


def test_duplicate_client_order_id_vetoed() -> None:
    proposal = make_proposal((make_action(OrderSide.BUY, "AAPL", D("5")),))
    dup_id = client_order_id_for(proposal.proposal_id, 0, proposal.actions[0])
    ctx = make_ctx(
        make_policy(),
        make_snapshot(D("10000"), prices={"AAPL": D("200")}),
        submitted_client_order_ids=frozenset({dup_id}),
    )
    validation = RiskEngine().validate_proposal(proposal, ctx)
    failed = [r.rule_id for r in validation.verdicts[0].results if r.blocking and not r.passed]
    assert failed == ["duplicate_order"]


def test_verdict_consistency_cannot_be_hand_assembled() -> None:
    import pytest
    from pydantic import ValidationError

    from tradeos.domain.risk import RiskCheckResult

    failed_result = RiskCheckResult(
        rule_id="max_position_pct",
        passed=False,
        blocking=True,
        observed="50%",
        limit="10%",
        message="veto",
    )
    with pytest.raises(ValidationError, match="inconsistent"):
        RiskVerdict(
            verdict_id="v1",
            proposal_id="p1",
            action_index=0,
            policy_version=1,
            evaluated_at=make_snapshot(D("1")).as_of,
            results=(failed_result,),
            approved=True,  # lying about the results
        )
