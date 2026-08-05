"""Build the outbound :mod:`projection` from real (absolute) local state.

This is the only place absolutes are converted into ratios for a prompt. It
reads the full context package — which keeps real cash and share counts for the
strategy, risk engine, event log, and replay — and emits the relative view.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from tradeos.context.projection import (
    CandidateLine,
    HoldingLine,
    PromptContext,
    PromptContextItem,
    _is_ratio,
)
from tradeos.domain.context import MarketContextPackage
from tradeos.domain.orders import ProposedAction
from tradeos.domain.portfolio import PortfolioSnapshot
from tradeos.portfolio.stats import compute_stats

_ZERO = Decimal("0")


def project_context(
    package: MarketContextPackage,
    *,
    snapshot: PortfolioSnapshot,
    targets: dict[str, Decimal],
    candidates: tuple[ProposedAction, ...] = (),
    policy_summary: str = "",
    now: datetime,
    est_slippage_bps: Decimal | None = None,
) -> PromptContext:
    """Project local state into the relative-only view a model may receive.

    Absolute quantities are converted here and nowhere else. Item ids are
    preserved so the cycle's citation-integrity check still works.
    """
    stats = compute_stats(snapshot, targets)
    total = snapshot.total_value

    items: list[PromptContextItem] = []
    for item in package.items:
        kind = str(item.payload.get("kind", ""))
        common = {
            "item_id": item.item_id,
            "source_name": item.source_name,
            "source_type": item.source_type,
            "event_time": item.event_time,
            "credibility": item.credibility,
            "freshness": item.freshness(now),
            "kind": kind,
        }
        if kind == "positions":
            items.append(
                PromptContextItem(
                    **common,
                    holdings=tuple(
                        HoldingLine(
                            symbol=row.symbol,
                            weight=row.weight,
                            target_weight=row.target_weight,
                            drift=row.drift,
                            # pct_adv needs a volume source; lands with T-024.
                            pct_adv=None,
                        )
                        for row in stats.rows
                    ),
                    cash_weight=stats.cash_weight,
                )
            )
        elif kind.startswith("quote:"):
            # The price itself is public, but paired with a weight it would
            # reconstruct the portfolio's absolute value — so quotes contribute
            # freshness and identity only.
            items.append(PromptContextItem(**common, note="priced"))
        else:
            # Ingested third-party content (news, filings, sentiment) keeps its
            # text verbatim. Dropping unknown payload keys would silently erase
            # exactly the context T-023/T-025 exist to supply.
            note = item.payload.get("note")
            items.append(
                PromptContextItem(
                    **common,
                    note=str(note) if note else None,
                    text=_external_text(item.payload),
                )
            )

    projected_candidates: list[CandidateLine] = []
    for index, action in enumerate(candidates):
        quote = snapshot.quotes.get(action.symbol)
        size: Decimal | None = None
        if quote is not None and total not in (None, _ZERO):
            size = (quote.price * action.quantity) / total
        projected_candidates.append(
            CandidateLine(
                index=index,
                side=action.side.value,
                symbol=action.symbol,
                size_of_portfolio=size,
                est_slippage_bps=est_slippage_bps,
                rationale=_scrub(action.rationale),
            )
        )

    return PromptContext(
        package_id=package.package_id,
        created_at=package.created_at,
        purpose=package.purpose,
        completeness=package.completeness(now),
        missing_kinds=package.missing(now),
        items=tuple(items),
        candidates=tuple(projected_candidates),
        top3_concentration=stats.top3_concentration,
        hhi=stats.hhi,
        policy_summary=_scrub(policy_summary),
    )


#: Payload keys holding third-party narrative content, in preference order.
_TEXT_KEYS = ("headline", "title", "summary", "text", "body", "excerpt")


def _external_text(payload: dict[str, object]) -> str | None:
    for key in _TEXT_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


_MONEY = re.compile(r"[$£€¥]\s?[\d,]*(?:\.\d+)?")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?\s*%?")


def _scrub(text: str) -> str:
    """Strip absolute figures out of strategy-authored prose.

    Rationales come from our own strategies and legitimately mention sizing
    ("buy 140 @ ~$285.10"). Rather than trusting every present and future
    strategy to phrase itself carefully, absolutes are removed at this boundary
    — which is the boundary's job. The projection's validators are the backstop:
    anything this misses raises rather than being sent.
    """
    text = _MONEY.sub("[amount]", text)

    def replace(match: re.Match[str]) -> str:
        token = match.group()
        return token if _is_ratio(token) else "[quantity]"

    return _NUMBER.sub(replace, text)
