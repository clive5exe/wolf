"""Investment policy: the deterministic source of truth for what the system may want.

Spec: INVESTMENT_POLICY_SPEC.md. Fields marked ⚡ there are read by the risk
engine as hard limits. Models may draft policies. Only user-confirmed
instances become active, and nothing model-generated can widen a limit.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# Autopilot is structurally disabled in all 0.1/0.2 builds. Flipping this
# constant is a v0.3 change gated on the safety review checklist (ADR-0009).
AUTOPILOT_SUPPORTED = False

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class TradingMode(StrEnum):
    READ_ONLY = "read_only"
    PAPER = "paper"
    APPROVAL = "approval"
    RESTRICTED_AUTOPILOT = "autopilot"


# The only legal ladder: no mode may be skipped on the way up.
MODE_LADDER = [
    TradingMode.READ_ONLY,
    TradingMode.PAPER,
    TradingMode.APPROVAL,
    TradingMode.RESTRICTED_AUTOPILOT,
]

# Modes buildable in v0.1 binaries.
SUPPORTED_MODES = {TradingMode.READ_ONLY, TradingMode.PAPER}


class RiskTolerance(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class AssetType(StrEnum):
    EQUITY = "equity"
    ETF = "etf"


class TargetAllocation(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    weight: Decimal

    @field_validator("symbol")
    @classmethod
    def _symbol_format(cls, v: str) -> str:
        if not _SYMBOL_RE.match(v):
            raise ValueError(f"invalid symbol {v!r} (uppercase ticker expected)")
        return v

    @field_validator("weight")
    @classmethod
    def _weight_range(cls, v: Decimal) -> Decimal:
        if not Decimal("0") < v <= Decimal("1"):
            raise ValueError("target weight must be in (0, 1]")
        return v


class TradingHoursSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    session: Literal["regular"] = "regular"


class AutopilotEnvelope(BaseModel):
    """v0.3 envelope. Constructible for schema purposes. Never activatable in 0.1/0.2."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    dedicated_account_id: str
    budget_usd: Decimal
    max_total_loss_usd: Decimal
    allowed_strategy_ids: list[str]
    allowed_symbols: list[str]
    activation_confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def _structurally_disabled(self) -> AutopilotEnvelope:
        if not AUTOPILOT_SUPPORTED:
            raise ValueError(
                "autopilot is not supported in this build, "
                "the envelope cannot exist before the v0.3 safety review (ADR-0009)"
            )
        return self


class InvestmentPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str
    version: int
    created_at: datetime
    status: Literal["draft", "active", "superseded"]
    goals_text: str
    risk_tolerance: RiskTolerance
    time_horizon_years: int
    mode: TradingMode
    permitted_asset_types: frozenset[AssetType]
    fractional_shares_allowed: bool
    preferred_sectors: tuple[str, ...] = ()
    excluded_sectors: tuple[str, ...] = ()
    symbol_allowlist: tuple[str, ...] | None = None
    symbol_denylist: tuple[str, ...] = ()
    target_allocations: tuple[TargetAllocation, ...] = ()
    target_cash_weight: Decimal = Decimal("0.05")
    max_position_pct: Decimal = Decimal("0.10")
    max_sector_pct: Decimal = Decimal("0.30")
    min_cash_pct: Decimal = Decimal("0.02")
    max_order_value_usd: Decimal = Decimal("1000")
    max_orders_per_day: int = 5
    max_daily_loss_pct: Decimal = Decimal("0.02")
    max_drawdown_pct: Decimal = Decimal("0.15")
    cooldown_minutes_per_symbol: int = 240
    trading_hours: TradingHoursSpec = TradingHoursSpec()
    earnings_blackout_days: int = 0
    stale_quote_max_age_s: int = 120
    stale_context_max_age_factor: Decimal = Decimal("1.0")
    account_is_taxable: bool | None = None
    autopilot: AutopilotEnvelope | None = None

    @field_validator("time_horizon_years")
    @classmethod
    def _horizon_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("time_horizon_years must be >= 1")
        return v

    @field_validator("mode")
    @classmethod
    def _mode_supported(cls, v: TradingMode) -> TradingMode:
        if v not in SUPPORTED_MODES:
            raise ValueError(f"mode {v} is not supported in this build (v0.1 ships modes 0-1)")
        return v

    @field_validator("symbol_denylist", "excluded_sectors", "preferred_sectors")
    @classmethod
    def _upper_tuple(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(s.upper() for s in v)

    @model_validator(mode="after")
    def _invariants(self) -> InvestmentPolicy:
        total_weight = sum((t.weight for t in self.target_allocations), Decimal("0"))
        if total_weight + self.target_cash_weight > Decimal("1"):
            raise ValueError(
                f"target weights ({total_weight}) + cash ({self.target_cash_weight}) exceed 1"
            )
        if self.target_allocations:
            heaviest = max(t.weight for t in self.target_allocations)
            if heaviest > self.max_position_pct:
                raise ValueError(
                    f"a target weight ({heaviest}) exceeds max_position_pct "
                    f"({self.max_position_pct}), raise the cap or lower the target"
                )
        if self.symbol_allowlist is not None:
            overlap = set(self.symbol_allowlist) & set(self.symbol_denylist)
            if overlap:
                raise ValueError(f"symbols cannot be in both allow and deny lists: {overlap}")
        for frac_field in (
            "target_cash_weight",
            "max_position_pct",
            "max_sector_pct",
            "min_cash_pct",
            "max_daily_loss_pct",
            "max_drawdown_pct",
        ):
            value: Decimal = getattr(self, frac_field)
            if not Decimal("0") <= value <= Decimal("1"):
                raise ValueError(f"{frac_field} must be a fraction in [0, 1], got {value}")
        return self

    def is_symbol_permitted(self, symbol: str) -> bool:
        """Deterministic symbol gate used by the risk engine (denylist > allowlist)."""
        symbol = symbol.upper()
        if symbol in self.symbol_denylist:
            return False
        if self.symbol_allowlist is not None:
            return symbol in self.symbol_allowlist
        return True
