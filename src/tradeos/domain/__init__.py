"""Shared domain models. Depends on stdlib + pydantic only (ARCHITECTURE §2)."""

from tradeos.domain.common import canonical_json, format_money, new_ulid, utc_now
from tradeos.domain.context import (
    ContextItem,
    ContextRequirement,
    Freshness,
    MarketContextPackage,
    Provenance,
    SourceType,
)
from tradeos.domain.market import MarketStatus, Quote
from tradeos.domain.orders import (
    Fill,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    ProposedAction,
    TradeProposal,
)
from tradeos.domain.policy import (
    AssetType,
    AutopilotEnvelope,
    InvestmentPolicy,
    RiskTolerance,
    TargetAllocation,
    TradingMode,
)
from tradeos.domain.portfolio import AccountState, PortfolioSnapshot, Position
from tradeos.domain.risk import RiskCheckResult, RiskVerdict, ValidatedOrder
from tradeos.domain.thesis import HealthProbe, PolicyDraft, StructuredThesis

__all__ = [
    "AccountState",
    "AssetType",
    "AutopilotEnvelope",
    "ContextItem",
    "ContextRequirement",
    "Fill",
    "Freshness",
    "HealthProbe",
    "InvestmentPolicy",
    "MarketContextPackage",
    "MarketStatus",
    "OrderResult",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PolicyDraft",
    "PortfolioSnapshot",
    "Position",
    "ProposedAction",
    "Provenance",
    "Quote",
    "RiskCheckResult",
    "RiskTolerance",
    "RiskVerdict",
    "SourceType",
    "StructuredThesis",
    "TargetAllocation",
    "TradeProposal",
    "TradingMode",
    "ValidatedOrder",
    "canonical_json",
    "format_money",
    "new_ulid",
    "utc_now",
]
