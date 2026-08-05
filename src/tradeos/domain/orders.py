"""Order-related models: strategy proposals through broker results.

A ProposedAction is *intent*; it carries no authority. Authority exists only
as a ValidatedOrder (domain/risk.py), issued by the risk engine.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from tradeos.domain.policy import AssetType


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"  # v0.1 paper engine supports market orders only


class OrderStatus(StrEnum):
    SUBMITTED = "submitted"
    FILLED = "filled"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"  # idempotency: already processed, not re-executed


class ProposedAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    side: OrderSide
    symbol: str
    quantity: Decimal
    asset_type: AssetType
    order_type: OrderType = OrderType.MARKET
    rationale: str = ""

    @field_validator("quantity")
    @classmethod
    def _positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class TradeProposal(BaseModel):
    """Full output of one strategy run within a decision cycle."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str
    correlation_id: str
    created_at: datetime
    strategy_id: str
    strategy_version: str
    actions: tuple[ProposedAction, ...]  # empty tuple == explicit no-action
    rationale: str
    context_package_id: str

    @property
    def is_no_action(self) -> bool:
        return len(self.actions) == 0


class Fill(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: Decimal
    quantity: Decimal
    filled_at: datetime
    slippage_bps: Decimal


class OrderResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    client_order_id: str
    status: OrderStatus
    fill: Fill | None = None
    broker_order_id: str | None = None
    error: str | None = None
