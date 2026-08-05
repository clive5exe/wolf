"""ContextItem freshness boundaries and package completeness (MARKET_CONTEXT_SPEC §10.1)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tests.conftest import NOW, make_package
from tradeos.domain.context import (
    ContextItem,
    ContextRequirement,
    Freshness,
    Provenance,
    SourceType,
)


def item_with_age(age_s: int, ttl_s: int = 100, kind: str = "quote:AAPL") -> ContextItem:
    return ContextItem(
        item_id=f"item-{age_s}",
        source_name="test",
        source_type=SourceType.MARKET_DATA,
        entities=("AAPL",),
        event_time=NOW - timedelta(seconds=age_s),
        ingested_at=NOW,
        ttl_s=ttl_s,
        credibility=Decimal("0.9"),
        retrieval_reason="test",
        provenance=Provenance.NORMALIZED,
        payload={"kind": kind},
    )


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (0, Freshness.FRESH),
        (50, Freshness.FRESH),  # boundary: age*2 == ttl
        (51, Freshness.AGING),
        (100, Freshness.AGING),  # boundary: age == ttl
        (101, Freshness.STALE),
        (200, Freshness.STALE),  # boundary: age == 2*ttl
        (201, Freshness.EXPIRED),
    ],
)
def test_freshness_boundaries(age: int, expected: Freshness) -> None:
    assert item_with_age(age).freshness(NOW) == expected


def test_decision_usability_excludes_stale_and_expired() -> None:
    assert item_with_age(50).usable_for_decision(NOW)
    assert item_with_age(100).usable_for_decision(NOW)
    assert not item_with_age(150).usable_for_decision(NOW)
    assert not item_with_age(500).usable_for_decision(NOW)


def test_policy_ttl_factor_tightens_freshness() -> None:
    # factor 0.5 halves the effective ttl: age 60 of ttl 100 becomes STALE-ish
    item = item_with_age(60)
    assert item.freshness(NOW) == Freshness.AGING
    assert item.freshness(NOW, ttl_factor=Decimal("0.5")) == Freshness.STALE


def test_package_completeness_and_missing() -> None:
    package = make_package(
        items=(item_with_age(10, kind="quote:AAPL"),),
        requirements=(
            ContextRequirement(kind="quote:AAPL"),
            ContextRequirement(kind="positions"),
        ),
    )
    assert package.missing(NOW) == ("positions",)
    assert package.completeness(NOW) == Decimal("0.5")


def test_expired_required_item_counts_as_missing() -> None:
    package = make_package(
        items=(item_with_age(500, kind="quote:AAPL"),),
        requirements=(ContextRequirement(kind="quote:AAPL"),),
    )
    assert package.missing(NOW) == ("quote:AAPL",)


def test_model_generated_credibility_is_capped() -> None:
    with pytest.raises((ValidationError, ValueError), match="capped"):
        ContextItem(
            item_id="x",
            source_name="model",
            source_type=SourceType.DERIVED,
            entities=(),
            event_time=NOW,
            ingested_at=NOW,
            ttl_s=60,
            credibility=Decimal("0.9"),
            retrieval_reason="test",
            provenance=Provenance.MODEL_GENERATED,
            payload={"kind": "summary"},
        )


def test_citations_are_item_ids() -> None:
    a, b = item_with_age(1), item_with_age(2)
    package = make_package(items=(a, b))
    assert package.citations == {a.item_id, b.item_id}
