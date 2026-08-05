"""EDGAR connector — fixtures only, never the network.

The properties that matter here are about honesty of provenance rather than
parsing convenience: a filing must carry its own acceptance time, and a payload
we do not fully understand must be quarantined rather than half-read.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradeos.events.store import InMemoryEventStore
from tradeos.events.types import EventType
from tradeos.ingestion.edgar import (
    SUBMISSIONS_URL,
    TICKERS_URL,
    EdgarConfig,
    EdgarConnector,
    EdgarError,
    normalize_cik,
    parse_acceptance,
)
from tradeos.ingestion.ratelimit import RateLimiter

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "edgar"


class FakeTransport:
    """Serves fixtures and records every request, including its headers."""

    def __init__(self, routes: dict[str, tuple[int, bytes]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, *, headers: dict[str, str], timeout_s: float) -> tuple[int, bytes]:
        self.calls.append((url, headers))
        if url not in self.routes:
            return 404, b"not found"
        return self.routes[url]


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport(
        {
            TICKERS_URL: (200, fixture("company_tickers.json")),
            SUBMISSIONS_URL.format(cik="0000320193"): (200, fixture("submissions_aapl.json")),
        }
    )


@pytest.fixture
def connector(transport: FakeTransport) -> EdgarConnector:
    return EdgarConnector(
        transport,
        InMemoryEventStore(),
        EdgarConfig(enabled=True),
        # No real waiting: the limiter's behaviour is tested separately.
        limiter=RateLimiter(1000, sleep=lambda _s: None),
    )


class TestCikNormalisation:
    @pytest.mark.parametrize("raw", [320193, "320193", "0000320193", "CIK0000320193", " 320193 "])
    def test_all_spellings_of_apple_resolve_to_one_cik(self, raw: str | int) -> None:
        assert normalize_cik(raw) == "0000320193"

    @pytest.mark.parametrize("raw", ["", "AAPL", "12345678901", "CIK"])
    def test_nonsense_is_refused(self, raw: str) -> None:
        with pytest.raises(EdgarError):
            normalize_cik(raw)


class TestAcceptanceTimes:
    def test_the_shapes_edgar_actually_sends(self) -> None:
        expected = datetime(2024, 11, 1, 6, 1, 36, tzinfo=UTC)
        assert parse_acceptance("2024-11-01T06:01:36.000Z") == expected
        assert parse_acceptance("2024-11-01 06:01:36") == expected

    def test_a_naive_timestamp_is_treated_as_utc(self) -> None:
        parsed = parse_acceptance("2024-11-01T06:01:36")
        assert parsed is not None and parsed.tzinfo is not None

    @pytest.mark.parametrize("raw", ["", "   ", "not a date"])
    def test_unparseable_returns_none_rather_than_guessing(self, raw: str) -> None:
        assert parse_acceptance(raw) is None


class TestFetching:
    def test_the_user_agent_is_on_every_request(
        self, connector: EdgarConnector, transport: FakeTransport
    ) -> None:
        """SEC refuses unidentified clients; a request without this is how the
        whole project gets blocked at once."""
        connector.recent_filings("AAPL")
        assert transport.calls
        for _url, headers in transport.calls:
            assert headers["User-Agent"].startswith("WOLF/")

    def test_a_blank_user_agent_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="User-Agent"):
            EdgarConfig(user_agent="   ")

    def test_ticker_resolves_through_secs_own_mapping(self, connector: EdgarConnector) -> None:
        assert connector.resolve_cik("aapl") == "0000320193"
        assert connector.resolve_cik("MSFT") == "0000789019"
        assert connector.resolve_cik("NOSUCH") is None

    def test_the_mapping_is_fetched_once_not_per_ticker(
        self, connector: EdgarConnector, transport: FakeTransport
    ) -> None:
        connector.resolve_cik("AAPL")
        connector.resolve_cik("MSFT")
        assert sum(1 for url, _ in transport.calls if url == TICKERS_URL) == 1

    def test_only_forms_of_interest_are_kept(self, connector: EdgarConnector) -> None:
        filings = connector.recent_filings("AAPL")
        forms = {f.form for f in filings}
        assert forms == {"10-K", "10-Q"}
        assert "4" not in forms  # insider form, noise for v0.1

    def test_a_disabled_connector_fetches_nothing(self, transport: FakeTransport) -> None:
        connector = EdgarConnector(transport, InMemoryEventStore(), EdgarConfig(enabled=False))
        assert connector.recent_filings("AAPL") == []
        assert transport.calls == []

    def test_the_newest_filing_is_identified(self, connector: EdgarConnector) -> None:
        latest = connector.latest_known_filing("AAPL")
        assert latest is not None
        assert latest.form == "10-K"
        assert latest.accepted_at == datetime(2024, 11, 1, 6, 1, 36, tzinfo=UTC)

    def test_a_filing_url_is_reconstructed_correctly(self, connector: EdgarConnector) -> None:
        latest = connector.latest_known_filing("AAPL")
        assert latest is not None
        assert latest.url == (
            "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm"
        )


class TestProvenance:
    def test_event_time_is_the_filings_own_acceptance_time(self, connector: EdgarConnector) -> None:
        """Stamping ingestion time would make an old filing look fresh to every
        staleness rule downstream — THREAT_MODEL T5, introduced by the source."""
        filings = connector.recent_filings("AAPL")
        items = connector.to_context_items(filings, now=datetime(2026, 8, 5, tzinfo=UTC))

        newest = max(items, key=lambda i: i.event_time)
        assert newest.event_time == datetime(2024, 11, 1, 6, 1, 36, tzinfo=UTC)
        assert newest.ingested_at == datetime(2026, 8, 5, tzinfo=UTC)
        assert newest.event_time != newest.ingested_at

    def test_a_two_year_old_filing_is_not_decision_fresh(self, connector: EdgarConnector) -> None:
        items = connector.to_context_items(connector.recent_filings("AAPL"))
        far_future = datetime(2030, 1, 1, tzinfo=UTC)
        assert not any(item.usable_for_decision(far_future) for item in items)

    def test_items_carry_source_type_and_credibility(self, connector: EdgarConnector) -> None:
        items = connector.to_context_items(connector.recent_filings("AAPL"))
        assert items
        for item in items:
            assert item.source_type.value == "filing"
            assert item.credibility == Decimal("0.95")
            assert item.source_url and item.source_url.startswith("https://www.sec.gov/")


class TestFailuresAreQuarantined:
    def _events(self, connector: EdgarConnector) -> InMemoryEventStore:
        return connector._events  # type: ignore[attr-defined]

    def test_raw_payloads_are_recorded_before_normalisation(
        self, connector: EdgarConnector
    ) -> None:
        """So a parsing change can be replayed against what was received."""
        connector.recent_filings("AAPL")
        raw = [e for e in self._events(connector).iter_events(event_types=(EventType.INGEST_RAW,))]
        assert len(raw) == 2  # ticker map + submissions
        assert all(e.payload["bytes"] > 0 for e in raw)

    def test_malformed_json_is_quarantined_not_parsed_leniently(self) -> None:
        transport = FakeTransport({TICKERS_URL: (200, b"{ not json at all")})
        store = InMemoryEventStore()
        connector = EdgarConnector(
            transport,
            store,
            EdgarConfig(enabled=True),
            limiter=RateLimiter(1000, sleep=lambda _s: None),
        )
        with pytest.raises(EdgarError):
            connector.resolve_cik("AAPL")
        errors = list(store.iter_events(event_types=(EventType.INGEST_ERROR,)))
        assert errors and "malformed JSON" in errors[0].payload["reason"]

    def test_an_http_error_is_recorded_and_raised(self) -> None:
        transport = FakeTransport({TICKERS_URL: (503, b"upstream unavailable")})
        store = InMemoryEventStore()
        connector = EdgarConnector(
            transport,
            store,
            EdgarConfig(enabled=True),
            limiter=RateLimiter(1000, sleep=lambda _s: None),
        )
        with pytest.raises(EdgarError, match="503"):
            connector.resolve_cik("AAPL")
        assert list(store.iter_events(event_types=(EventType.INGEST_ERROR,)))

    def test_mismatched_parallel_arrays_abort_rather_than_mispair(self) -> None:
        """EDGAR returns columns as parallel arrays; unequal lengths would pair
        a form with another filing's timestamp."""
        broken = json.loads(fixture("submissions_aapl.json"))
        broken["filings"]["recent"]["form"] = ["10-K"]  # now shorter than the rest
        transport = FakeTransport(
            {
                TICKERS_URL: (200, fixture("company_tickers.json")),
                SUBMISSIONS_URL.format(cik="0000320193"): (200, json.dumps(broken).encode()),
            }
        )
        store = InMemoryEventStore()
        connector = EdgarConnector(
            transport,
            store,
            EdgarConfig(enabled=True),
            limiter=RateLimiter(1000, sleep=lambda _s: None),
        )
        assert connector.recent_filings("AAPL") == []
        errors = list(store.iter_events(event_types=(EventType.INGEST_ERROR,)))
        assert any("disagree in length" in e.payload["reason"] for e in errors)

    def test_a_filing_without_an_acceptance_time_is_dropped(self) -> None:
        broken = json.loads(fixture("submissions_aapl.json"))
        broken["filings"]["recent"]["acceptanceDateTime"][0] = ""
        transport = FakeTransport(
            {
                TICKERS_URL: (200, fixture("company_tickers.json")),
                SUBMISSIONS_URL.format(cik="0000320193"): (200, json.dumps(broken).encode()),
            }
        )
        store = InMemoryEventStore()
        connector = EdgarConnector(
            transport,
            store,
            EdgarConfig(enabled=True),
            limiter=RateLimiter(1000, sleep=lambda _s: None),
        )
        filings = connector.recent_filings("AAPL")
        assert all(f.form != "10-K" for f in filings), "undateable filing must be dropped"
        assert list(store.iter_events(event_types=(EventType.INGEST_ERROR,)))

    def test_an_unknown_ticker_is_recorded_rather_than_silently_empty(self) -> None:
        transport = FakeTransport({TICKERS_URL: (200, fixture("company_tickers.json"))})
        store = InMemoryEventStore()
        connector = EdgarConnector(
            transport,
            store,
            EdgarConfig(enabled=True),
            limiter=RateLimiter(1000, sleep=lambda _s: None),
        )
        assert connector.recent_filings("NOSUCH") == []
        assert list(store.iter_events(event_types=(EventType.INGEST_ERROR,)))
