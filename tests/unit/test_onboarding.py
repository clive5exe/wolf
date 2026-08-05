"""Policy onboarding.

The safety-critical property: INVESTMENT_POLICY_SPEC says nothing
model-generated may widen a limit. These tests hold the guardrails to that,
including the case that matters most — a model that suggests something reckless
and a user who would click through.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradeos.domain.policy import InvestmentPolicy, RiskTolerance, TradingMode
from tradeos.domain.thesis import PolicyDraft
from tradeos.notifications.base import NullNotifier
from tradeos.runtime.facade import RuntimeConfig, TradeOSRuntime
from tradeos.runtime.onboarding import (
    GUARDRAILS,
    NOT_DRAFTABLE,
    Bound,
    OnboardingService,
    PolicyProposal,
    apply_guardrails,
)


@pytest.fixture
def runtime() -> TradeOSRuntime:
    return TradeOSRuntime(RuntimeConfig(in_memory=True, notifier=NullNotifier()))


@pytest.fixture
def service(runtime: TradeOSRuntime) -> OnboardingService:
    return OnboardingService(runtime.policy_service, runtime.clock, provider=None)


class TestGuardrails:
    def test_a_reckless_position_cap_is_held_at_the_ceiling(self) -> None:
        proposal = PolicyProposal(goals_text="go big")
        draft = PolicyDraft(max_position_pct=Decimal("0.90"))
        merged, adjustments = apply_guardrails(proposal, draft)

        assert merged.max_position_pct == GUARDRAILS["max_position_pct"].limit
        assert len(adjustments) == 1
        assert adjustments[0].suggested == Decimal("0.90")

    def test_a_clamp_is_reported_never_applied_silently(self) -> None:
        """Quietly ignoring a suggestion is its own dishonesty — the user
        should see that the model wanted something wider."""
        proposal, adjustments = apply_guardrails(
            PolicyProposal(goals_text="x"), PolicyDraft(max_sector_pct=Decimal("0.95"))
        )
        assert proposal.adjustments
        described = adjustments[0].describe()
        assert "model suggested" in described
        assert "blows up" in described  # the reason travels with it

    def test_a_conservative_suggestion_is_accepted_unchanged(self) -> None:
        """Guardrails cap risk; they do not force it upward."""
        proposal, adjustments = apply_guardrails(
            PolicyProposal(goals_text="careful"), PolicyDraft(max_position_pct=Decimal("0.05"))
        )
        assert proposal.max_position_pct == Decimal("0.05")
        assert not adjustments

    def test_a_floor_cannot_be_lowered_by_a_draft(self) -> None:
        """min_cash_pct is riskier as it shrinks, so the bound runs the other way."""
        assert GUARDRAILS["min_cash_pct"].bound is Bound.FLOOR
        proposal, adjustments = apply_guardrails(
            PolicyProposal(goals_text="all in"), PolicyDraft(min_cash_pct=Decimal("0"))
        )
        assert proposal.min_cash_pct == GUARDRAILS["min_cash_pct"].limit
        assert adjustments

    @pytest.mark.parametrize("name", sorted(GUARDRAILS))
    def test_every_guarded_field_resists_its_risky_direction(self, name: str) -> None:
        rail = GUARDRAILS[name]
        reckless = rail.limit * 10 if rail.bound is Bound.CEILING else Decimal("0")
        proposal, adjustments = apply_guardrails(
            PolicyProposal(goals_text="x"), PolicyDraft(**{name: reckless})
        )
        assert getattr(proposal, name) == rail.limit
        assert any(a.field == name for a in adjustments)


class TestLimitsBeyondModelReach:
    """Stronger than a clamp: these cannot be suggested at all."""

    def test_the_loss_and_rate_limits_are_not_draftable(self) -> None:
        draftable = set(PolicyDraft.model_fields)
        overlap = draftable & NOT_DRAFTABLE
        assert not overlap, (
            f"PolicyDraft gained {sorted(overlap)} — a model can now influence limits "
            "that were deliberately reserved for the human."
        )

    def test_those_limits_still_exist_on_the_policy(self) -> None:
        """i.e. they are unreachable, not merely absent everywhere."""
        policy_fields = set(InvestmentPolicy.model_fields)
        for name in NOT_DRAFTABLE - {"mode"}:
            assert name in policy_fields


class TestTheDraftCannotDecide:
    def test_a_draft_cannot_express_a_mode_or_autopilot(self) -> None:
        """Enforced by the schema, so no reviewer has to remember it."""
        fields = set(PolicyDraft.model_fields)
        assert "mode" not in fields
        assert "autopilot" not in fields

    def test_onboarding_always_produces_paper(self) -> None:
        assert PolicyProposal(goals_text="x").mode is TradingMode.PAPER

    def test_an_unrecognised_risk_label_is_ignored_not_guessed(self) -> None:
        proposal, _ = apply_guardrails(
            PolicyProposal(goals_text="x"), PolicyDraft(risk_tolerance="YOLO")
        )
        assert proposal.risk_tolerance is RiskTolerance.MODERATE


class TestValidation:
    def test_every_problem_is_reported_at_once(self) -> None:
        """One error per attempt turns a two-minute task into ten."""
        problems = PolicyProposal(goals_text="", time_horizon_years=0).validation_errors()
        assert len(problems) >= 3

    def test_weights_over_one_hundred_percent_are_refused(self) -> None:
        proposal = PolicyProposal(
            goals_text="x",
            target_allocations={"VTI": Decimal("0.8"), "AAPL": Decimal("0.5")},
            target_cash_weight=Decimal("0.1"),
        )
        assert any("cannot exceed 100%" in p for p in proposal.validation_errors())

    def test_a_target_above_the_position_cap_is_refused(self) -> None:
        proposal = PolicyProposal(
            goals_text="x",
            target_allocations={"VTI": Decimal("0.5")},
            max_position_pct=Decimal("0.2"),
        )
        assert any("position cap" in p for p in proposal.validation_errors())

    def test_a_cash_floor_above_the_cash_target_is_refused(self) -> None:
        """Otherwise every cycle would breach the floor immediately."""
        proposal = PolicyProposal(
            goals_text="x",
            target_allocations={"VTI": Decimal("0.5")},
            target_cash_weight=Decimal("0.02"),
            min_cash_pct=Decimal("0.10"),
        )
        assert any("floor is above" in p for p in proposal.validation_errors())

    def test_a_sound_proposal_has_no_complaints(self) -> None:
        proposal = PolicyProposal(
            goals_text="steady growth, broad market core",
            target_allocations={"VTI": Decimal("0.6"), "AAPL": Decimal("0.1")},
            target_cash_weight=Decimal("0.1"),
            max_position_pct=Decimal("0.65"),
            min_cash_pct=Decimal("0.02"),
        )
        assert proposal.validation_errors() == ()


class TestActivation:
    def test_confirming_activates_a_paper_policy(self, service: OnboardingService) -> None:
        proposal = PolicyProposal(
            goals_text="broad market, steady",
            target_allocations={"VTI": Decimal("0.6")},
            target_cash_weight=Decimal("0.1"),
            max_position_pct=Decimal("0.65"),
            min_cash_pct=Decimal("0.02"),
        )
        policy = service.confirm(proposal)
        assert policy.mode is TradingMode.PAPER
        assert policy.status == "active"
        assert policy.version == 1
        assert policy.goals_text.startswith("broad market")

    def test_an_invalid_proposal_never_activates(self, service: OnboardingService) -> None:
        with pytest.raises(ValueError, match="targets"):
            service.confirm(PolicyProposal(goals_text="nothing specified"))

    def test_the_activated_policy_is_the_one_that_was_reviewed(
        self, service: OnboardingService, runtime: TradeOSRuntime
    ) -> None:
        proposal = PolicyProposal(
            goals_text="x",
            target_allocations={"VTI": Decimal("0.5"), "MSFT": Decimal("0.2")},
            target_cash_weight=Decimal("0.1"),
            max_position_pct=Decimal("0.55"),
            min_cash_pct=Decimal("0.02"),
            max_orders_per_day=3,
        )
        service.confirm(proposal)
        active = runtime.active_policy()
        assert active is not None
        assert active.max_orders_per_day == 3
        assert {t.symbol for t in active.target_allocations} == {"VTI", "MSFT"}


class TestWithoutAProvider:
    def test_setup_still_works_with_no_model_available(self, service: OnboardingService) -> None:
        """No provider must mean conservative defaults to edit, not a dead end."""
        assert not service.can_draft
        proposal = service.propose("I want steady growth")
        assert proposal.goals_text == "I want steady growth"
        assert not proposal.drafted_by_model
        assert proposal.max_position_pct <= GUARDRAILS["max_position_pct"].limit

    def test_a_provider_failure_falls_back_rather_than_blocking(
        self, runtime: TradeOSRuntime
    ) -> None:
        class BrokenProvider:
            name = "broken"

            def query_structured(self, **kwargs: object) -> object:
                class Result:
                    ok = False
                    value = None

                return Result()

        service = OnboardingService(
            runtime.policy_service, runtime.clock, provider=BrokenProvider()
        )
        proposal = service.propose("steady growth")
        assert not proposal.drafted_by_model
        assert proposal.validation_errors()  # defaults have no targets yet — user adds them
