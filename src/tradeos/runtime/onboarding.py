"""Policy onboarding: goals in your words → a draft you confirm → an active policy.

Three properties make this safe to put in front of a new user:

**The model drafts; it cannot decide.** ``PolicyDraft`` has no field for
``mode`` or ``autopilot``, so a draft cannot even express "trade for real" or
"trade unattended". That is enforced by the schema, not by this module.

**A draft can narrow a limit, never widen one.** INVESTMENT_POLICY_SPEC states
that nothing model-generated may widen a limit; :data:`GUARDRAILS` enforces it.
A model suggesting a 90% single-position cap gets clamped to the ceiling and
the clamp is *recorded and shown*, because silently ignoring a suggestion is
its own kind of dishonesty. A human can still type a wider value — they just
have to do it themselves, having seen the default.

**Nothing activates without explicit confirmation of every enforceable field.**
The draft only pre-fills a form. Confirmation is a separate, deliberate act.

Onboarding also works with no provider at all: without one you get the
conservative defaults to edit, rather than a dead end.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from tradeos.domain.clock import Clock
from tradeos.domain.common import new_ulid
from tradeos.domain.policy import (
    AssetType,
    InvestmentPolicy,
    RiskTolerance,
    TargetAllocation,
    TradingMode,
)
from tradeos.domain.thesis import PolicyDraft
from tradeos.providers.base import ModelProvider
from tradeos.runtime.policy_service import PolicyService


class Bound(StrEnum):
    """Which direction a limit becomes *more permissive* in."""

    CEILING = "ceiling"  # larger is riskier — a draft may not exceed this
    FLOOR = "floor"  # smaller is riskier — a draft may not go below this


@dataclass(frozen=True)
class Guardrail:
    bound: Bound
    limit: Decimal
    why: str


#: The most permissive a *drafted* value may be. These are not the policy's
#: limits — a human may deliberately set something wider — they are the limit
#: on what a language model is allowed to talk you into during onboarding.
GUARDRAILS: dict[str, Guardrail] = {
    "max_position_pct": Guardrail(
        Bound.CEILING, Decimal("0.25"), "a quarter of the portfolio in one name is already bold"
    ),
    "max_sector_pct": Guardrail(
        Bound.CEILING, Decimal("0.40"), "sector concentration is the usual way a portfolio blows up"
    ),
    "min_cash_pct": Guardrail(
        Bound.FLOOR, Decimal("0.01"), "some cash must remain to settle and to absorb error"
    ),
    "max_order_value_usd": Guardrail(
        Bound.CEILING, Decimal("5000"), "a first policy should not authorise large single orders"
    ),
}

#: Limits a draft cannot express *at all*, because ``PolicyDraft`` has no field
#: for them. This is stronger than a guardrail: a clamp bounds what a model may
#: suggest, whereas these are beyond its reach entirely. The loss limits, the
#: order rate limits, and the staleness thresholds are set by a human or left
#: at their defaults — a model never participates.
#:
#: Enforced by ``test_onboarding.py``, so widening ``PolicyDraft`` in future
#: cannot quietly hand any of them over.
NOT_DRAFTABLE: frozenset[str] = frozenset(
    {
        "autopilot",
        "mode",
        "max_daily_loss_pct",
        "max_drawdown_pct",
        "max_orders_per_day",
        "cooldown_minutes_per_symbol",
        "earnings_blackout_days",
        "stale_quote_max_age_s",
        "stale_context_max_age_factor",
    }
)


@dataclass(frozen=True)
class Adjustment:
    """A drafted value the guardrails pulled back, and why."""

    field: str
    suggested: Decimal
    applied: Decimal
    why: str

    def describe(self) -> str:
        return (
            f"{self.field}: model suggested {self.suggested}, held at {self.applied} — {self.why}"
        )


@dataclass
class PolicyProposal:
    """A complete, editable policy-in-progress. Nothing here is active yet."""

    goals_text: str
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    time_horizon_years: int = 10
    target_allocations: dict[str, Decimal] = field(default_factory=dict)
    target_cash_weight: Decimal = Decimal("0.10")
    max_position_pct: Decimal = Decimal("0.15")
    max_sector_pct: Decimal = Decimal("0.30")
    min_cash_pct: Decimal = Decimal("0.05")
    max_order_value_usd: Decimal = Decimal("1000")
    max_orders_per_day: int = 5
    max_daily_loss_pct: Decimal = Decimal("0.02")
    max_drawdown_pct: Decimal = Decimal("0.15")
    fractional_shares_allowed: bool = False
    excluded_sectors: tuple[str, ...] = ()
    #: Guardrail interventions, surfaced to the user rather than applied quietly.
    adjustments: tuple[Adjustment, ...] = ()
    #: What the model said it inferred, for the human to sanity-check.
    interpretation_notes: tuple[str, ...] = ()
    #: True when a model contributed; False means these are plain defaults.
    drafted_by_model: bool = False

    #: Mode is deliberately absent as an editable field. Onboarding always
    #: produces PAPER; moving up the ladder is a separate, deliberate act
    #: through PolicyService.change_mode, one step at a time.
    mode: TradingMode = TradingMode.PAPER

    @property
    def allocation_total(self) -> Decimal:
        return sum(self.target_allocations.values(), Decimal("0"))

    def validation_errors(self) -> tuple[str, ...]:
        """Everything wrong with this proposal, in plain language.

        Reported all at once rather than one per attempt: a form that reveals
        problems one at a time turns a two-minute task into ten.
        """
        problems: list[str] = []
        if not self.goals_text.strip():
            problems.append("goals: say something about what this portfolio is for")
        if self.time_horizon_years < 1:
            problems.append("time horizon: must be at least 1 year")
        if not self.target_allocations:
            problems.append("targets: add at least one symbol and weight")

        total = self.allocation_total + self.target_cash_weight
        if total > Decimal("1"):
            problems.append(
                f"targets: weights plus cash come to {total:.0%} — they cannot exceed 100%"
            )
        heaviest = max(self.target_allocations.values(), default=Decimal("0"))
        if heaviest > self.max_position_pct:
            problems.append(
                f"targets: {heaviest:.0%} exceeds the {self.max_position_pct:.0%} position cap — "
                "raise the cap or lower the target"
            )
        if self.min_cash_pct > self.target_cash_weight:
            problems.append(
                f"cash: the {self.min_cash_pct:.0%} floor is above the "
                f"{self.target_cash_weight:.0%} target, so every cycle would breach it"
            )
        for name in ("max_position_pct", "max_sector_pct", "min_cash_pct"):
            value: Decimal = getattr(self, name)
            if not Decimal("0") <= value <= Decimal("1"):
                problems.append(f"{name}: must be between 0% and 100%")
        return tuple(problems)

    def to_policy(self, *, policy_id: str, version: int, created_at: datetime) -> InvestmentPolicy:
        return InvestmentPolicy(
            policy_id=policy_id,
            version=version,
            created_at=created_at,
            status="active",
            goals_text=self.goals_text.strip(),
            risk_tolerance=self.risk_tolerance,
            time_horizon_years=self.time_horizon_years,
            mode=self.mode,
            permitted_asset_types=frozenset({AssetType.EQUITY, AssetType.ETF}),
            fractional_shares_allowed=self.fractional_shares_allowed,
            excluded_sectors=self.excluded_sectors,
            target_allocations=tuple(
                TargetAllocation(symbol=symbol, weight=weight)
                for symbol, weight in sorted(self.target_allocations.items())
            ),
            target_cash_weight=self.target_cash_weight,
            max_position_pct=self.max_position_pct,
            max_sector_pct=self.max_sector_pct,
            min_cash_pct=self.min_cash_pct,
            max_order_value_usd=self.max_order_value_usd,
            max_orders_per_day=self.max_orders_per_day,
            max_daily_loss_pct=self.max_daily_loss_pct,
            max_drawdown_pct=self.max_drawdown_pct,
        )


def apply_guardrails(
    proposal: PolicyProposal, draft: PolicyDraft
) -> tuple[PolicyProposal, list[Adjustment]]:
    """Merge a model draft into a proposal, refusing to widen any limit."""
    adjustments: list[Adjustment] = []

    for name, rail in GUARDRAILS.items():
        suggested = getattr(draft, name, None)
        if suggested is None:
            continue
        suggested = Decimal(str(suggested))
        widens = suggested > rail.limit if rail.bound is Bound.CEILING else suggested < rail.limit
        if widens:
            adjustments.append(Adjustment(name, suggested, rail.limit, rail.why))
            setattr(proposal, name, rail.limit)
        else:
            setattr(proposal, name, suggested)

    if draft.time_horizon_years and draft.time_horizon_years >= 1:
        proposal.time_horizon_years = draft.time_horizon_years
    if draft.risk_tolerance:
        # An unrecognised label is ignored rather than guessed at.
        with contextlib.suppress(ValueError):
            proposal.risk_tolerance = RiskTolerance(draft.risk_tolerance.lower())
    if draft.target_allocations:
        proposal.target_allocations = {
            symbol.upper(): Decimal(str(weight))
            for symbol, weight in draft.target_allocations.items()
        }
    if draft.excluded_sectors:
        proposal.excluded_sectors = tuple(s.upper() for s in draft.excluded_sectors)
    if draft.fractional_shares_allowed is not None:
        proposal.fractional_shares_allowed = bool(draft.fractional_shares_allowed)

    proposal.interpretation_notes = tuple(draft.interpretation_notes)
    proposal.adjustments = tuple(adjustments)
    proposal.drafted_by_model = True
    return proposal, adjustments


ONBOARDING_PROMPT = """You are helping someone set up an investment policy for
WOLF, a portfolio runtime. They will review and confirm every field before
anything takes effect — you are drafting a starting point, not deciding.

Their words:
---
{goals}
---

Fill the schema from what they actually said. Rules:
- Infer only what is supported by their words. Leave a field null rather than
  inventing a preference they did not express.
- target_allocations must be symbol -> weight as a 0..1 decimal, summing with
  cash to no more than 1.
- Prefer broad-market ETFs for a core unless they asked for something else.
- Limits are safety rails, not aspirations: suggest conservative values.
- Record what you inferred, and what you were unsure about, in
  interpretation_notes so they can correct you."""


class OnboardingService:
    """Turns goals into a confirmable proposal, then into an active policy."""

    def __init__(
        self,
        policy_service: PolicyService,
        clock: Clock,
        provider: ModelProvider | None = None,
    ) -> None:
        self._policies = policy_service
        self._clock = clock
        self._provider = provider

    @property
    def can_draft(self) -> bool:
        return self._provider is not None

    def propose(self, goals_text: str) -> PolicyProposal:
        """A proposal for the human to edit. Uses the model when one is
        available, and conservative defaults when it is not — never a dead end."""
        proposal = PolicyProposal(goals_text=goals_text)
        if self._provider is None:
            return proposal

        result = self._provider.query_structured(
            prompt=ONBOARDING_PROMPT.format(goals=goals_text), schema=PolicyDraft
        )
        if not result.ok or result.value is None:
            # A provider failure must not block setup; the adapter already
            # recorded the error, and defaults are a fine starting point.
            return proposal
        merged, _ = apply_guardrails(proposal, result.value)
        return merged

    def confirm(self, proposal: PolicyProposal) -> InvestmentPolicy:
        """Activate a reviewed proposal. Raises if it is not internally valid."""
        problems = proposal.validation_errors()
        if problems:
            raise ValueError("; ".join(problems))
        current = self._policies.active_policy()
        policy = proposal.to_policy(
            policy_id=new_ulid(),
            version=1 if current is None else current.version + 1,
            created_at=self._clock.now(),
        )
        return self._policies.activate(policy)
