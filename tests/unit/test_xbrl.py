"""Point-in-time correctness is the whole point of the XBRL layer.

Most of these tests exist to prove one thing: a value filed after the date you
asked about must be invisible, even though the document contains it. That is
the difference between a backtest and a story.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tradeos.ingestion.xbrl import (
    Fact,
    FactSet,
    XbrlError,
    derived_ratios,
    parse_company_facts,
)


def entry(val, end, filed, *, form="10-K", start=None, fy=2024, fp="FY", accn="a-1"):
    body = {"val": val, "end": end, "filed": filed, "form": form, "fy": fy, "fp": fp, "accn": accn}
    if start:
        body["start"] = start
    return body


def payload(**tags):
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {"us-gaap": {tag: {"units": {"USD": rows}} for tag, rows in tags.items()}},
    }


class TestParsing:
    def test_maps_tags_to_concepts(self) -> None:
        facts = parse_company_facts(payload(Revenues=[entry(1000, "2024-09-28", "2024-11-01")]))
        assert facts.cik == "0000320193"
        assert facts.entity_name == "Apple Inc."
        assert [f.concept for f in facts.facts] == ["revenue"]

    def test_values_are_decimal_not_float(self) -> None:
        facts = parse_company_facts(payload(Revenues=[entry(1234.56, "2024-09-28", "2024-11-01")]))
        value = facts.facts[0].value
        assert isinstance(value, Decimal)
        # Via str(), so the reported figure does not gain binary-float digits.
        assert value == Decimal("1234.56")

    def test_unknown_tags_are_skipped_not_guessed(self) -> None:
        facts = parse_company_facts(
            payload(SomeTagNobodyMapped=[entry(1, "2024-01-01", "2024-02-01")])
        )
        assert facts.facts == ()

    @pytest.mark.parametrize(
        "bad",
        [
            {"val": None, "end": "2024-09-28", "filed": "2024-11-01"},
            {"val": 10, "end": None, "filed": "2024-11-01"},
            {"val": 10, "end": "2024-09-28", "filed": None},
            {"val": 10, "end": "not-a-date", "filed": "2024-11-01"},
        ],
    )
    def test_undateable_entries_are_dropped(self, bad: dict) -> None:
        """A fact we cannot date is one we would have to invent a date for."""
        facts = parse_company_facts(payload(Revenues=[bad]))
        assert facts.facts == ()

    def test_rejects_payloads_that_are_not_companyfacts(self) -> None:
        for bad in ({}, {"cik": 1}, {"cik": 1, "facts": []}):
            with pytest.raises(XbrlError):
                parse_company_facts(bad)


class TestPointInTime:
    #: The same fiscal year, reported once and then restated four months later.
    RESTATED = payload(
        Revenues=[
            entry(1000, "2024-09-28", "2024-11-01", accn="original"),
            entry(1100, "2024-09-28", "2025-03-01", accn="restated"),
        ]
    )

    def test_sees_the_original_before_the_restatement_is_filed(self) -> None:
        facts = parse_company_facts(self.RESTATED)
        assert facts.as_of(date(2025, 1, 1))["revenue"].value == Decimal("1000")

    def test_sees_the_restatement_afterwards(self) -> None:
        facts = parse_company_facts(self.RESTATED)
        assert facts.as_of(date(2025, 6, 1))["revenue"].value == Decimal("1100")

    def test_sees_nothing_before_anything_was_filed(self) -> None:
        facts = parse_company_facts(self.RESTATED)
        assert facts.as_of(date(2024, 10, 1)) == {}

    def test_filing_date_boundary_is_inclusive(self) -> None:
        facts = parse_company_facts(self.RESTATED)
        assert facts.as_of(date(2024, 11, 1))["revenue"].value == Decimal("1000")

    def test_a_later_filing_wins_over_a_later_period(self) -> None:
        """Restatement beats recency of period, which is the subtle ordering."""
        facts = parse_company_facts(
            payload(
                Revenues=[
                    entry(200, "2024-09-28", "2024-11-01", fy=2024),
                    # Filed later, but describes an *earlier* period.
                    entry(150, "2023-09-30", "2025-01-15", fy=2023),
                ]
            )
        )
        assert facts.as_of(date(2025, 6, 1))["revenue"].value == Decimal("150")

    def test_quarterly_facts_are_excluded_by_default(self) -> None:
        """Mixing three months into a twelve month column is a silent lie."""
        facts = parse_company_facts(
            payload(
                Revenues=[
                    entry(1000, "2024-09-28", "2024-11-01", form="10-K"),
                    entry(260, "2024-12-28", "2025-02-01", form="10-Q"),
                ]
            )
        )
        assert facts.as_of(date(2025, 6, 1))["revenue"].value == Decimal("1000")
        assert facts.as_of(date(2025, 6, 1), annual_only=False)["revenue"].value == Decimal("260")


class TestHistoryAndRestatements:
    def test_history_shows_one_value_per_period_newest_first(self) -> None:
        facts = parse_company_facts(
            payload(
                Revenues=[
                    entry(900, "2023-09-30", "2023-11-01"),
                    entry(1000, "2024-09-28", "2024-11-01"),
                    entry(1100, "2024-09-28", "2025-03-01"),
                ]
            )
        )
        history = facts.history("revenue")
        assert [f.period_end for f in history] == [date(2024, 9, 28), date(2023, 9, 30)]
        # The restated figure, not the superseded one.
        assert history[0].value == Decimal("1100")

    def test_restatements_are_surfaced_as_pairs(self) -> None:
        facts = parse_company_facts(
            payload(
                Revenues=[
                    entry(1000, "2024-09-28", "2024-11-01"),
                    entry(1100, "2024-09-28", "2025-03-01"),
                ]
            )
        )
        ((original, revised),) = facts.restatements("revenue")
        assert (original.value, revised.value) == (Decimal("1000"), Decimal("1100"))

    def test_refiling_the_same_number_is_not_a_restatement(self) -> None:
        facts = parse_company_facts(
            payload(
                Revenues=[
                    entry(1000, "2024-09-28", "2024-11-01"),
                    entry(1000, "2024-09-28", "2025-03-01"),
                ]
            )
        )
        assert facts.restatements("revenue") == ()

    def test_superseded_values_are_retained_not_discarded(self) -> None:
        """They are what makes an as-of query possible at all."""
        facts = parse_company_facts(
            payload(
                Revenues=[
                    entry(1000, "2024-09-28", "2024-11-01"),
                    entry(1100, "2024-09-28", "2025-03-01"),
                ]
            )
        )
        assert len(facts.facts) == 2


class TestDerivedRatios:
    def _fact(self, concept: str, value: str, end: date, filed: date) -> Fact:
        return Fact(
            concept=concept,
            tag=concept,
            unit="USD",
            value=Decimal(value),
            period_end=end,
            period_start=None,
            filed=filed,
            form="10-K",
            accession="a",
            fiscal_year=2024,
            fiscal_period="FY",
        )

    def test_margins_are_computed_from_the_same_period(self) -> None:
        end, filed = date(2024, 9, 28), date(2024, 11, 1)
        ratios = derived_ratios(
            {
                "revenue": self._fact("revenue", "1000", end, filed),
                "gross_profit": self._fact("gross_profit", "473", end, filed),
            }
        )
        assert ratios["gross_margin"] == Decimal("473") / Decimal("1000")

    def test_mismatched_periods_produce_nothing(self) -> None:
        ratios = derived_ratios(
            {
                "revenue": self._fact("revenue", "1000", date(2024, 9, 28), date(2024, 11, 1)),
                "gross_profit": self._fact(
                    "gross_profit", "473", date(2023, 9, 30), date(2023, 11, 1)
                ),
            }
        )
        assert "gross_margin" not in ratios

    def test_zero_denominator_does_not_raise(self) -> None:
        end, filed = date(2024, 9, 28), date(2024, 11, 1)
        ratios = derived_ratios(
            {
                "revenue": self._fact("revenue", "0", end, filed),
                "gross_profit": self._fact("gross_profit", "473", end, filed),
            }
        )
        assert "gross_margin" not in ratios


def test_empty_factset_as_of_is_empty_not_an_error() -> None:
    assert FactSet(cik="0000000001", entity_name="X", facts=()).as_of(date(2025, 1, 1)) == {}


class TestPeriodShape:
    """Regressions found only by running against Apple's real filings."""

    def test_quarterly_durations_inside_a_10k_are_not_annual(self) -> None:
        """A 10-K carries quarterly and year-to-date figures alongside annual
        ones, all ending on the same day. Judging annual-ness by form alone
        produced 158 phantom revenue restatements against real data."""
        annual = parse_company_facts(
            payload(Revenues=[entry(400, "2024-09-28", "2024-11-01", start="2023-10-01")])
        ).facts[0]
        quarterly = parse_company_facts(
            payload(Revenues=[entry(94, "2024-09-28", "2024-11-01", start="2024-06-30")])
        ).facts[0]
        assert annual.is_annual
        assert not quarterly.is_annual

    def test_balance_sheet_facts_have_no_duration_and_stay_annual(self) -> None:
        instant = parse_company_facts(
            payload(Assets=[entry(365, "2024-09-28", "2024-11-01")])
        ).facts[0]
        assert instant.is_instant
        assert instant.duration_days is None
        assert instant.is_annual

    def test_history_keys_on_the_whole_period_not_just_its_end(self) -> None:
        facts = parse_company_facts(
            payload(
                Revenues=[
                    entry(400, "2024-09-28", "2024-11-01", start="2023-10-01"),
                    entry(94, "2024-09-28", "2024-11-01", start="2024-06-30"),
                ]
            )
        )
        assert [f.value for f in facts.history("revenue")] == [Decimal("400")]
        assert facts.restatements("revenue") == ()

    def test_period_label_ignores_the_misleading_fy_tag(self) -> None:
        """`fy` is the filing's year context, not the period's."""
        fact = parse_company_facts(
            payload(Revenues=[entry(391, "2024-09-28", "2025-10-31", start="2023-10-01", fy=2025)])
        ).facts[0]
        assert fact.fiscal_year == 2025
        assert fact.period_label == "FY2024"
