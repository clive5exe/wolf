"""The outbound projection: what a model is allowed to be told.

Everything else in WOLF is local. A provider prompt is the one thing that
leaves the machine, so this module defines, as *types*, not as a filter, the
only shape portfolio information may take on the way out.

The rule is level A (ASSUMPTIONS Q3): **relative quantities only**. No dollar
amounts, no share counts, no account identifiers. That is not primarily a
privacy setting. It is the same boundary that stops the model sizing orders.
Every use of an absolute figure is arithmetic, and arithmetic belongs to the
deterministic strategy and risk engine. A component that supplies judgement
rather than calculation has no need of the units.

Enforcement is deliberately structural. A redaction filter applied on the way
out is opt-in by memory: someone adds a field next year, forgets the filter,
and nothing complains. Here the fields capable of carrying an absolute simply
do not exist, and the free-text fields that remain are validated against
money-shaped content on construction.

``item_id`` is carried through unchanged: the cycle checks a thesis's
``supporting_item_ids`` against the package's citations, so a projection that
renumbered items would silently break citation integrity.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from tradeos.domain.context import Freshness, SourceType

#: Currency markers are the obvious tell.
_MONEY_MARKERS = re.compile(r"[$£€¥]|\b(?:usd|dollars?|cents?)\b", re.IGNORECASE)
#: Any number, so each one can be judged against the ratio rule below.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?\s*%?")


class ProjectionLeak(ValueError):
    """Raised when an absolute value reaches the outbound projection."""


def _is_ratio(token: str) -> bool:
    """Level A permits exactly two numeric shapes: a percentage, or a 0..1 ratio.

    Anything else. 140 shares, 10694.50 of cash. Is an absolute, and the whole
    point of this projection is that absolutes do not leave the machine.
    """
    token = token.strip()
    if token.endswith("%"):
        return True
    try:
        return abs(float(token.replace(",", ""))) < 1
    except ValueError:
        return False


def _assert_no_absolutes(field: str, value: str) -> str:
    if _MONEY_MARKERS.search(value):
        raise ProjectionLeak(
            f"{field!r} contains a currency marker. The outbound projection carries "
            f"relative quantities only (ASSUMPTIONS Q3, level A): {value!r}"
        )
    for match in _NUMBER.finditer(value):
        if not _is_ratio(match.group()):
            raise ProjectionLeak(
                f"{field!r} contains {match.group()!r}, which is neither a percentage "
                f"nor a 0..1 ratio, so it is an absolute quantity: {value!r}"
            )
    return value


class _NoAbsolutes(BaseModel):
    """Base that rejects money-shaped content in any of its string fields.

    Opaque identifiers are exempt: a ULID is a long digit-and-letter run that
    trips the numeric heuristic while carrying no financial information, and
    ``item_id`` in particular must survive verbatim for citation integrity.
    """

    model_config = ConfigDict(frozen=True)

    #: Fields holding identifiers and labels rather than quantities. Digits in
    #: these are part of a name, not a measurement: a ULID, a trigger label like
    #: ``schedule/15m``, a ticker that legitimately contains numerals. Scanning
    #: them for "absolute amounts" rejects ordinary text and takes the whole
    #: prompt down with it. Which is exactly what happened to the scheduler.
    #: The scan still applies by default to every field not listed here, so a
    #: newly added prose field is protected without anyone remembering to opt in.
    OPAQUE_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "item_id",
            "package_id",
            "purpose",  # "<trigger>:<symbols>", e.g. "schedule/15m:VTI,AAPL"
            "kind",  # "quote:VTI"
            "missing_kinds",
            "symbol",  # tickers may contain digits
            "side",
            "source_name",
        }
    )

    #: Fields carrying third-party content. A news headline, a filing extract.
    #: These are exempt from the ratio rule, and the exemption is safe for a
    #: specific reason: the rule exists so *the user's financial position* does
    #: not leave the machine. A headline reading "Q3 profit up $2.1B" is public
    #: information about someone else and reveals nothing about this portfolio.
    #: Applying the ratio rule here would reject legitimate market context and
    #: fail closed on exactly the data the model is meant to reason about.
    EXTERNAL_TEXT_FIELDS: ClassVar[frozenset[str]] = frozenset({"text"})

    @model_validator(mode="after")
    def _scan_strings(self) -> Any:
        for name, value in self:
            if name in self.OPAQUE_FIELDS or name in self.EXTERNAL_TEXT_FIELDS:
                continue
            if isinstance(value, str):
                _assert_no_absolutes(name, value)
            elif isinstance(value, tuple):
                for element in value:
                    if isinstance(element, str):
                        _assert_no_absolutes(name, element)
        return self


class HoldingLine(_NoAbsolutes):
    """One position, in proportions. There is no field for a share count."""

    symbol: str
    weight: Decimal  # 0..1 of portfolio value
    target_weight: Decimal | None = None
    drift: Decimal | None = None  # weight − target
    #: Position size as a fraction of the symbol's average daily volume. The
    #: figure that actually governs whether liquidity constrains a trade, and a
    #: strictly better scale signal than a dollar amount. Requires a volume
    #: source: ``None`` until the Robinhood market-data tools land (T-024).
    pct_adv: Decimal | None = None

    @field_validator("weight")
    @classmethod
    def _weight_is_a_ratio(cls, v: Decimal) -> Decimal:
        if not Decimal("0") <= v <= Decimal("1"):
            raise ProjectionLeak(f"weight must be a 0..1 ratio, got {v}")
        return v


class CandidateLine(_NoAbsolutes):
    """A proposed action, sized as a proportion rather than in shares."""

    index: int
    side: str
    symbol: str
    #: Order value as a fraction of portfolio value.
    size_of_portfolio: Decimal | None = None
    #: Expected execution drag, in basis points. A ratio, not a cash figure.
    est_slippage_bps: Decimal | None = None
    rationale: str = ""


class PromptContextItem(_NoAbsolutes):
    """A context item as the model sees it.

    Structured payloads are projected into typed ratio fields. ``note`` remains
    free text for genuinely non-numeric context (market session, etc.) and is
    validated on construction.
    """

    item_id: str  # unchanged. Citation integrity depends on it
    source_name: str
    source_type: SourceType
    event_time: datetime
    credibility: Decimal
    freshness: Freshness
    kind: str
    holdings: tuple[HoldingLine, ...] = ()
    cash_weight: Decimal | None = None
    note: str | None = None
    #: Verbatim third-party content (headline, filing extract, post). Carried
    #: unmodified so the injection frame's promise holds. The model is told
    #: this block is untrusted data, and the risk engine is the real defense.
    text: str | None = None
    #: Price movement relative to a reference, as a ratio. Absolute prices are
    #: public information, but sending them alongside weights would let the
    #: portfolio value be reconstructed by division.
    change: Decimal | None = None


class PromptContext(_NoAbsolutes):
    """The complete outbound view for one thesis request."""

    package_id: str
    created_at: datetime
    purpose: str
    completeness: Decimal
    missing_kinds: tuple[str, ...] = ()
    items: tuple[PromptContextItem, ...] = ()
    candidates: tuple[CandidateLine, ...] = ()
    top3_concentration: Decimal | None = None
    hhi: Decimal | None = None
    policy_summary: str = ""

    @property
    def citations(self) -> frozenset[str]:
        return frozenset(i.item_id for i in self.items)
