"""Policy lifecycle: versioning, activation, mode ladder (INVESTMENT_POLICY_SPEC).

Policies are event-sourced: the active policy is the payload of the latest
policy event, revalidated through the InvestmentPolicy schema on read (so a
tampered event fails loudly rather than loading permissively).
"""

from __future__ import annotations

from decimal import Decimal

from tradeos.domain.clock import Clock
from tradeos.domain.common import new_ulid
from tradeos.domain.policy import (
    MODE_LADDER,
    SUPPORTED_MODES,
    AssetType,
    InvestmentPolicy,
    RiskTolerance,
    TargetAllocation,
    TradingMode,
)
from tradeos.events.store import EventStore
from tradeos.events.types import EventType


class PolicyError(RuntimeError):
    pass


class PolicyService:
    def __init__(self, event_store: EventStore, clock: Clock) -> None:
        self._events = event_store
        self._clock = clock

    def active_policy(self) -> InvestmentPolicy | None:
        newest = None
        for event in self._events.iter_events(
            event_types=(EventType.POLICY_CREATED, EventType.POLICY_UPDATED)
        ):
            newest = event
        if newest is None:
            return None
        return InvestmentPolicy.model_validate(newest.payload["policy"])

    def activate(self, policy: InvestmentPolicy) -> InvestmentPolicy:
        current = self.active_policy()
        expected_version = 1 if current is None else current.version + 1
        if policy.version != expected_version:
            raise PolicyError(f"policy version must be {expected_version}, got {policy.version}")
        event_type = EventType.POLICY_CREATED if current is None else EventType.POLICY_UPDATED
        self._events.append(
            event_type,
            {"policy": policy.model_dump(mode="json"), "policy_id": policy.policy_id},
        )
        return policy

    def change_mode(self, new_mode: TradingMode) -> InvestmentPolicy:
        """Mode ladder: one step up at a time. Any number of steps down."""
        current = self.active_policy()
        if current is None:
            raise PolicyError("no active policy")
        if new_mode not in SUPPORTED_MODES:
            raise PolicyError(f"mode {new_mode.value} is not supported in this build")
        old_idx = MODE_LADDER.index(current.mode)
        new_idx = MODE_LADDER.index(new_mode)
        if new_idx > old_idx + 1:
            raise PolicyError(
                f"cannot skip modes: {current.mode.value} -> {new_mode.value} "
                "(the safety ladder moves one step up at a time)"
            )
        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "mode": new_mode,
                "created_at": self._clock.now(),
            }
        )
        self._events.append(
            EventType.POLICY_UPDATED,
            {"policy": updated.model_dump(mode="json"), "policy_id": updated.policy_id},
        )
        self._events.append(
            EventType.MODE_CHANGED,
            {"from": current.mode.value, "to": new_mode.value, "policy_version": updated.version},
        )
        return updated

    def create_sample_policy(self, *, mode: TradingMode = TradingMode.PAPER) -> InvestmentPolicy:
        """Demo/dogfood policy: diversified ETF-tilted targets, conservative caps."""
        if self.active_policy() is not None:
            raise PolicyError("a policy already exists, edit it instead of re-sampling")
        policy = InvestmentPolicy(
            policy_id=new_ulid(),
            version=1,
            created_at=self._clock.now(),
            status="active",
            goals_text=(
                "Sample: steady growth with a broad-market core, modest tech tilt, "
                "no position above 15%, keep some cash."
            ),
            risk_tolerance=RiskTolerance.MODERATE,
            time_horizon_years=10,
            mode=mode,
            permitted_asset_types=frozenset({AssetType.EQUITY, AssetType.ETF}),
            fractional_shares_allowed=False,
            target_allocations=(
                TargetAllocation(symbol="VTI", weight=Decimal("0.40")),
                TargetAllocation(symbol="AAPL", weight=Decimal("0.15")),
                TargetAllocation(symbol="MSFT", weight=Decimal("0.15")),
                TargetAllocation(symbol="JNJ", weight=Decimal("0.10")),
                TargetAllocation(symbol="XOM", weight=Decimal("0.10")),
            ),
            target_cash_weight=Decimal("0.10"),
            max_position_pct=Decimal("0.45"),
            max_sector_pct=Decimal("0.60"),
            min_cash_pct=Decimal("0.02"),
            max_order_value_usd=Decimal("50000"),
            max_orders_per_day=10,
            max_daily_loss_pct=Decimal("0.05"),
            max_drawdown_pct=Decimal("0.20"),
            cooldown_minutes_per_symbol=0,
            stale_quote_max_age_s=300,
        )
        return self.activate(policy)
