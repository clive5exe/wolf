"""SEC XBRL company facts: parsing and point-in-time selection.

Pure. No I/O and no clock reads, so a fact set is a function of the payload and
nothing else. ``EdgarConnector`` does the fetching.

The whole reason this module exists separately from a dict lookup is
**restatement**. A company reports revenue for Q4 2024, then restates it four
months later. The SEC's ``companyfacts`` document contains *both* values, each
tagged with the date it was filed. Asking "what was Q4 2024 revenue" therefore
has no single answer: it has an answer *as of a date*.

Backtests that ignore this read the restated figure while claiming to stand in
the past, which is look-ahead bias wearing a suit. So the only way to read a
fact here is through :meth:`FactSet.as_of`, which cannot return anything filed
after the date you asked about.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from typing import Any, Final

#: Concepts worth surfacing, mapped to the US-GAAP tags that carry them.
#:
#: Order matters. Companies tag the same economic quantity differently, and the
#: newer revenue tag replaced the older one for most filers around 2018, so both
#: are listed and the first one present wins. A curated map is deliberate: the
#: raw document carries hundreds of tags and showing all of them is a data dump,
#: not a screen.
CONCEPTS: Final[dict[str, tuple[str, ...]]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss",),
    "assets": ("Assets",),
    "liabilities": ("Liabilities",),
    "equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "shares_outstanding": (
        "CommonStockSharesOutstanding",
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    ),
}

#: Annual filings only. Quarterly facts are present too, but mixing periods in
#: one column is how a chart ends up comparing three months against twelve.
ANNUAL_FORMS: Final[frozenset[str]] = frozenset({"10-K", "20-F", "40-F"})

#: A reported year is not exactly 365 days. Fiscal calendars run 52 or 53 weeks,
#: and filers round period boundaries to their own week-end, so the window has
#: to be generous enough to admit a real annual figure and tight enough to
#: exclude a nine month year-to-date one.
ANNUAL_MIN_DAYS: Final[int] = 330
ANNUAL_MAX_DAYS: Final[int] = 400


class XbrlError(ValueError):
    """The payload was not a companyfacts document we can trust."""


@dataclass(frozen=True, slots=True)
class Fact:
    """One reported value, with both dates that matter.

    ``period_end`` is when the fact was *true*. ``filed`` is when it became
    *knowable*. Conflating them is the bug this whole module exists to prevent.
    """

    concept: str
    tag: str
    unit: str
    value: Decimal
    period_end: date
    period_start: date | None
    filed: date
    form: str
    accession: str
    fiscal_year: int | None
    fiscal_period: str | None

    @property
    def duration_days(self) -> int | None:
        """Length of the reported period, or None for a balance-sheet figure."""
        if self.period_start is None:
            return None
        return (self.period_end - self.period_start).days

    @property
    def is_instant(self) -> bool:
        """A stock, not a flow. Assets and cash are measured at an instant."""
        return self.period_start is None

    @property
    def is_annual(self) -> bool:
        """A full-year figure, judged by duration rather than by form.

        The form alone is not enough. A 10-K carries quarterly and year-to-date
        durations alongside the annual ones, all sharing the same ``end`` date.
        Treating those as annual makes a three month figure look like a
        restatement of a twelve month one, which is exactly what it looked like
        against Apple's real filings: 158 phantom revenue restatements, every
        one of them a period-length mismatch.
        """
        if self.form not in ANNUAL_FORMS:
            return False
        if self.is_instant:
            return True
        days = self.duration_days or 0
        return ANNUAL_MIN_DAYS <= days <= ANNUAL_MAX_DAYS

    @property
    def period_label(self) -> str:
        """Label a period by when it ended, never by its ``fy`` tag.

        XBRL's ``fy`` is the fiscal year of the *filing* that carried the fact,
        not of the period it describes. Apple's FY2025 10-K tags its FY2024 and
        FY2023 comparatives ``fy=2025`` as well, so labelling from ``fy`` puts
        three different years under one heading.
        """
        return f"FY{self.period_end.year}"

    @property
    def period(self) -> tuple[date | None, date]:
        """The full period. Two facts are comparable only if these match.

        Keying on ``period_end`` alone conflates a quarter with the year that
        ends on the same day.
        """
        return (self.period_start, self.period_end)


@dataclass(frozen=True, slots=True)
class FactSet:
    """Every reported value for one company, including superseded ones.

    Superseded values are kept rather than discarded. They are what makes an
    as-of query possible, and they are also evidence: a restatement is itself a
    thing worth being able to see.
    """

    cik: str
    entity_name: str
    facts: tuple[Fact, ...]

    def as_of(self, when: date, *, annual_only: bool = True) -> dict[str, Fact]:
        """Latest known value per concept, using only what was filed by ``when``.

        Selection is by ``filed`` first, then ``period_end``. That order is the
        point: a restatement filed later wins over the original even though both
        describe the same period, and nothing filed after ``when`` is visible at
        all.
        """
        best: dict[str, Fact] = {}
        for fact in self.facts:
            if fact.filed > when:
                continue
            if annual_only and not fact.is_annual:
                continue
            current = best.get(fact.concept)
            if current is None or (fact.filed, fact.period_end) > (
                current.filed,
                current.period_end,
            ):
                best[fact.concept] = fact
        return best

    def history(self, concept: str, *, annual_only: bool = True) -> tuple[Fact, ...]:
        """One concept over time, one value per period, newest period first.

        Within a period the most recently filed value wins, so a restated year
        appears once with its corrected figure rather than twice.
        """
        latest: dict[tuple[date | None, date], Fact] = {}
        for fact in self.facts:
            if fact.concept != concept:
                continue
            if annual_only and not fact.is_annual:
                continue
            current = latest.get(fact.period)
            if current is None or fact.filed > current.filed:
                latest[fact.period] = fact
        return tuple(sorted(latest.values(), key=lambda f: f.period_end, reverse=True))

    def restatements(self, concept: str) -> tuple[tuple[Fact, Fact], ...]:
        """Pairs of (original, revised) where a period's value actually changed.

        Only differing values count. Refiling the same number is not a
        restatement, and flagging it as one would cry wolf.
        """
        by_period: dict[tuple[date | None, date], list[Fact]] = {}
        for fact in self.facts:
            if fact.concept == concept:
                by_period.setdefault(fact.period, []).append(fact)
        out: list[tuple[Fact, Fact]] = []
        for versions in by_period.values():
            ordered = sorted(versions, key=lambda f: f.filed)
            for earlier, later in pairwise(ordered):
                if earlier.value != later.value:
                    out.append((earlier, later))
        return tuple(sorted(out, key=lambda pair: pair[1].filed, reverse=True))


def _as_date(raw: Any) -> date | None:
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _as_decimal(raw: Any) -> Decimal | None:
    # str() first: floats arriving from JSON must not become binary floats on
    # the way to Decimal, or a reported figure acquires digits nobody filed.
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def parse_company_facts(payload: Mapping[str, Any]) -> FactSet:
    """Turn a ``companyfacts`` document into a :class:`FactSet`.

    Unrecognised tags are skipped rather than guessed at, and any entry missing
    a value, an end date or a filing date is dropped: a fact we cannot date is a
    fact we cannot use without inventing when it was knowable.
    """
    if not isinstance(payload, Mapping):
        raise XbrlError("companyfacts payload is not an object")
    cik_raw = payload.get("cik")
    if cik_raw is None:
        raise XbrlError("companyfacts payload has no cik")
    facts_by_taxonomy = payload.get("facts")
    if not isinstance(facts_by_taxonomy, Mapping):
        raise XbrlError("companyfacts payload has no facts object")

    tag_to_concept: dict[str, str] = {
        tag: concept for concept, tags in CONCEPTS.items() for tag in tags
    }

    collected: list[Fact] = []
    for taxonomy in facts_by_taxonomy.values():
        if not isinstance(taxonomy, Mapping):
            continue
        for tag, body in taxonomy.items():
            concept = tag_to_concept.get(tag)
            if concept is None or not isinstance(body, Mapping):
                continue
            units = body.get("units")
            if not isinstance(units, Mapping):
                continue
            for unit, entries in units.items():
                if not isinstance(entries, Iterable):
                    continue
                for entry in entries:
                    fact = _entry_to_fact(entry, concept=concept, tag=tag, unit=str(unit))
                    if fact is not None:
                        collected.append(fact)

    return FactSet(
        cik=str(cik_raw).zfill(10),
        entity_name=str(payload.get("entityName") or ""),
        facts=tuple(sorted(collected, key=lambda f: (f.filed, f.period_end))),
    )


def _entry_to_fact(entry: Any, *, concept: str, tag: str, unit: str) -> Fact | None:
    if not isinstance(entry, Mapping):
        return None
    value = _as_decimal(entry.get("val"))
    period_end = _as_date(entry.get("end"))
    filed = _as_date(entry.get("filed"))
    if value is None or period_end is None or filed is None:
        return None
    fiscal_year = entry.get("fy")
    return Fact(
        concept=concept,
        tag=tag,
        unit=unit,
        value=value,
        period_end=period_end,
        period_start=_as_date(entry.get("start")),
        filed=filed,
        form=str(entry.get("form") or ""),
        accession=str(entry.get("accn") or ""),
        fiscal_year=int(fiscal_year) if isinstance(fiscal_year, int) else None,
        fiscal_period=str(entry.get("fp")) if entry.get("fp") else None,
    )


def derived_ratios(facts: Mapping[str, Fact]) -> dict[str, Decimal]:
    """Ratios computable from a single as-of snapshot.

    Deliberately few. Every ratio here divides two figures the company itself
    reported in the same filing, so nothing is estimated, annualised, or blended
    across periods. Anything needing a market price belongs elsewhere: this
    module never sees one.
    """
    out: dict[str, Decimal] = {}

    def ratio(name: str, num: str, den: str) -> None:
        a, b = facts.get(num), facts.get(den)
        if a is None or b is None or b.value == 0:
            return
        if a.period_end != b.period_end:
            # Mixing periods would silently compare a restated year against an
            # older one. Better to show nothing.
            return
        out[name] = a.value / b.value

    ratio("gross_margin", "gross_profit", "revenue")
    ratio("operating_margin", "operating_income", "revenue")
    ratio("net_margin", "net_income", "revenue")
    ratio("return_on_equity", "net_income", "equity")
    ratio("return_on_assets", "net_income", "assets")
    return out
