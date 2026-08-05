"""Schemas for model output. Everything an LLM returns is validated into one
of these (ADR-0011); free text never flows into decisions."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class HealthProbe(BaseModel):
    """Minimal structured round-trip used by provider health checks."""

    model_config = ConfigDict(frozen=True)

    status: str  # provider must answer exactly "ok"
    echo: str  # must echo the nonce we sent

    @field_validator("status")
    @classmethod
    def _ok(cls, v: str) -> str:
        if v != "ok":
            raise ValueError("health probe status must be 'ok'")
        return v


class StructuredThesis(BaseModel):
    """The only accepted shape for AI synthesis of a trade decision.

    ``supporting_item_ids`` must be validated against the context package's
    citations by the caller (engine-level check) — the schema enforces shape,
    the cycle enforces referential integrity.
    """

    model_config = ConfigDict(frozen=True)

    recommended_action_index: int | None  # index into candidate list; None = no action
    bull_case: str
    bear_case: str
    why_now: str
    what_changed: str
    invalidation_conditions: tuple[str, ...]
    data_gaps: tuple[str, ...]
    confidence: Decimal
    supporting_item_ids: tuple[str, ...]

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, v: Decimal) -> Decimal:
        if not Decimal("0") <= v <= Decimal("1"):
            raise ValueError("confidence must be in [0, 1]")
        return v

    @model_validator(mode="after")
    def _actionable_needs_invalidation(self) -> StructuredThesis:
        if self.recommended_action_index is not None and not self.invalidation_conditions:
            raise ValueError("an actionable recommendation must state invalidation conditions")
        return self


class PolicyDraft(BaseModel):
    """Model-drafted policy fields for onboarding. All optional; the human
    confirms every enforceable field before a real InvestmentPolicy exists.

    Deliberately excludes ``autopilot`` and ``mode`` above PAPER: a draft
    cannot even express them (INVESTMENT_POLICY_SPEC §3).
    """

    model_config = ConfigDict(frozen=True)

    risk_tolerance: str | None = None
    time_horizon_years: int | None = None
    preferred_sectors: tuple[str, ...] = ()
    excluded_sectors: tuple[str, ...] = ()
    target_allocations: dict[str, Decimal] = {}
    max_position_pct: Decimal | None = None
    max_sector_pct: Decimal | None = None
    min_cash_pct: Decimal | None = None
    max_order_value_usd: Decimal | None = None
    fractional_shares_allowed: bool | None = None
    interpretation_notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _no_forbidden_fields(self) -> PolicyDraft:
        # Defense in depth: schema has no autopilot/mode fields, and extra
        # fields are ignored by pydantic default; this validator documents the
        # invariant for future editors.
        return self
