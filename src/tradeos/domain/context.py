"""Market context models: sourced, timestamped, expiring information assets.

Spec: MARKET_CONTEXT_SPEC.md. Freshness is always computed from (age, ttl) —
never stored — so a persisted item can never lie about being fresh.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from tradeos.domain.common import canonical_json


class SourceType(StrEnum):
    BROKER = "broker"
    MARKET_DATA = "market_data"
    FILING = "filing"
    NEWS = "news"
    SOCIAL = "social"
    MACRO = "macro"
    USER = "user"
    DERIVED = "derived"


class Provenance(StrEnum):
    RAW = "raw"
    NORMALIZED = "normalized"
    DERIVED = "derived"
    MODEL_GENERATED = "model_generated"


class Freshness(StrEnum):
    FRESH = "fresh"  # age <= 0.5 * ttl
    AGING = "aging"  # 0.5*ttl < age <= ttl
    STALE = "stale"  # ttl < age <= 2*ttl — display only, never decision-bearing
    EXPIRED = "expired"  # age > 2*ttl


# Model-generated content may never carry high credibility (THREAT_MODEL B5).
MAX_MODEL_GENERATED_CREDIBILITY = Decimal("0.3")


class ContextItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_id: str
    source_name: str
    source_url: str | None = None
    source_type: SourceType
    entities: tuple[str, ...] = ()
    event_time: datetime
    ingested_at: datetime
    ttl_s: int
    credibility: Decimal
    retrieval_reason: str
    provenance: Provenance
    payload: dict[str, Any]

    @field_validator("credibility")
    @classmethod
    def _credibility_range(cls, v: Decimal) -> Decimal:
        if not Decimal("0") <= v <= Decimal("1"):
            raise ValueError("credibility must be in [0, 1]")
        return v

    @field_validator("ttl_s")
    @classmethod
    def _ttl_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ttl_s must be positive")
        return v

    def model_post_init(self, __context: Any) -> None:
        if (
            self.provenance == Provenance.MODEL_GENERATED
            and self.credibility > MAX_MODEL_GENERATED_CREDIBILITY
        ):
            raise ValueError(
                f"model-generated content is capped at credibility "
                f"{MAX_MODEL_GENERATED_CREDIBILITY} (got {self.credibility})"
            )

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.payload).encode()).hexdigest()

    def age_s(self, now: datetime) -> int:
        return max(0, int((now - self.event_time).total_seconds()))

    def freshness(self, now: datetime, ttl_factor: Decimal = Decimal("1.0")) -> Freshness:
        """Pure function of age vs (ttl * policy factor)."""
        ttl = int(self.ttl_s * ttl_factor)
        if ttl <= 0:
            return Freshness.EXPIRED
        age = self.age_s(now)
        if age * 2 <= ttl:
            return Freshness.FRESH
        if age <= ttl:
            return Freshness.AGING
        if age <= ttl * 2:
            return Freshness.STALE
        return Freshness.EXPIRED

    def usable_for_decision(self, now: datetime, ttl_factor: Decimal = Decimal("1.0")) -> bool:
        return self.freshness(now, ttl_factor) in (Freshness.FRESH, Freshness.AGING)


class ContextRequirement(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str  # matches ContextItem.payload["kind"]
    required: bool = True


class MarketContextPackage(BaseModel):
    model_config = ConfigDict(frozen=True)

    package_id: str
    created_at: datetime
    purpose: str
    requirements: tuple[ContextRequirement, ...]
    items: tuple[ContextItem, ...]

    def items_of_kind(self, kind: str) -> tuple[ContextItem, ...]:
        return tuple(i for i in self.items if i.payload.get("kind") == kind)

    def missing(self, now: datetime) -> tuple[str, ...]:
        """Required kinds that are absent or unusable (stale/expired)."""
        gone = []
        for req in self.requirements:
            if not req.required:
                continue
            usable = [i for i in self.items_of_kind(req.kind) if i.usable_for_decision(now)]
            if not usable:
                gone.append(req.kind)
        return tuple(gone)

    def completeness(self, now: datetime) -> Decimal:
        required = [r for r in self.requirements if r.required]
        if not required:
            return Decimal("1")
        present = len(required) - len(self.missing(now))
        return Decimal(present) / Decimal(len(required))

    @property
    def citations(self) -> frozenset[str]:
        """Item ids a thesis is allowed to reference."""
        return frozenset(i.item_id for i in self.items)
