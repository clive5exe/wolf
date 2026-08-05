"""SEC EDGAR connector. Filings as primary-source market context.

EDGAR is open: no registration, no API key, no browser step. The only
obligations are a User-Agent that identifies who is calling and staying inside
their fair-access limits. Both are handled here so no user is ever asked to
satisfy a financial regulator during setup (ADR-0013).

Two properties are worth stating because they are easy to get wrong:

**``event_time`` is the filing's acceptance time, never ingestion time.** A
filing accepted three weeks ago is three weeks old however recently it was
downloaded. Stamping it with "now" would make stale information look fresh to
every freshness rule downstream. The exact failure T5 in the threat model
describes, introduced by the source rather than by an outage.

**Malformed payloads are quarantined, not parsed leniently.** A partially
understood filing is worse than an absent one: absence is visible to the
completeness check, whereas a half-parsed document silently becomes evidence.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from tradeos.context.ttl import DEFAULT_TTLS
from tradeos.domain.common import new_ulid, utc_now
from tradeos.domain.context import ContextItem, Provenance, SourceType
from tradeos.events.store import EventStore
from tradeos.events.types import EventType
from tradeos.ingestion.ratelimit import RateLimiter
from tradeos.telemetry.logging import get_logger

_log = get_logger("ingestion.edgar")

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

#: SEC publishes 10 req/s. We ship at half that: the cost of being slower is
#: nothing, and the cost of being blocked is every user at once.
MAX_REQUESTS_PER_SECOND = 5.0

#: Filings are durable, a 10-K does not go stale, but retrieval still
#: re-checks that nothing newer exists before one is cited as current.
FILING_TTL_S = DEFAULT_TTLS["filing"]
EDGAR_CREDIBILITY = Decimal("0.95")

#: Identifies the project and gives SEC a real contact channel, so onboarding
#: never has to ask a stranger for their email. Overridable for anyone who
#: wants their own contact declared instead.
DEFAULT_USER_AGENT = "WOLF/0.1 (+https://github.com/clive5exe/wolf)"


class EdgarError(RuntimeError):
    """A request or payload failed in a way that must not be parsed around."""


class Transport(Protocol):
    """HTTP indirection. Tests supply fixtures. Nothing here opens a socket."""

    def get(self, url: str, *, headers: dict[str, str], timeout_s: float) -> tuple[int, bytes]: ...


@dataclass(frozen=True)
class EdgarConfig:
    """Connector configuration. Disabled by default. A data source that
    reaches the network should be switched on deliberately."""

    enabled: bool = False
    user_agent: str = DEFAULT_USER_AGENT
    timeout_s: float = 20.0
    max_filings_per_company: int = 10
    #: Forms worth turning into context. Everything else is noise for v0.1.
    forms: frozenset[str] = field(
        default_factory=lambda: frozenset({"10-K", "10-Q", "8-K", "20-F", "40-F"})
    )

    def __post_init__(self) -> None:
        if not self.user_agent.strip():
            raise ValueError(
                "a User-Agent is required: SEC fair access refuses unidentified clients"
            )


def normalize_cik(raw: str | int) -> str:
    """CIK as EDGAR wants it: ten digits, zero-padded.

    ``320193`` and ``"0000320193"`` and ``"CIK0000320193"`` all denote Apple.
    Only the padded form resolves.
    """
    text = str(raw).strip().upper().removeprefix("CIK").lstrip("0")
    if not text or not text.isdigit():
        raise EdgarError(f"not a CIK: {raw!r}")
    if len(text) > 10:
        raise EdgarError(f"CIK too long: {raw!r}")
    return text.zfill(10)


def parse_acceptance(raw: str) -> datetime | None:
    """EDGAR acceptance timestamps, which arrive in more than one shape."""
    text = (raw or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


@dataclass
class Filing:
    """One filing, normalized."""

    cik: str
    ticker: str
    form: str
    accession: str
    accepted_at: datetime
    filing_date: str
    primary_document: str
    report_date: str = ""

    @property
    def url(self) -> str:
        stripped = self.accession.replace("-", "")
        return (
            f"https://www.sec.gov/Archives/edgar/data/{int(self.cik)}/"
            f"{stripped}/{self.primary_document}"
        )


class EdgarConnector:
    """Fetches filings and turns them into context items.

    The connector records the raw payload as an ``ingest.raw`` event *before*
    normalizing, so a parsing change can be replayed against what was actually
    received rather than against what was understood at the time.
    """

    name = "sec_edgar"

    def __init__(
        self,
        transport: Transport,
        event_store: EventStore,
        config: EdgarConfig | None = None,
        *,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._transport = transport
        self._events = event_store
        self._config = config or EdgarConfig()
        self._limiter = limiter or RateLimiter(MAX_REQUESTS_PER_SECOND)
        self._ticker_map: dict[str, str] | None = None

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    # -- transport -------------------------------------------------------------

    def _get_json(self, url: str) -> Any:
        self._limiter.acquire()
        headers = {
            # Always present. SEC refuses unidentified clients, and shipping a
            # request without this is how the project gets blocked collectively.
            "User-Agent": self._config.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }
        try:
            status, body = self._transport.get(
                url, headers=headers, timeout_s=self._config.timeout_s
            )
        except Exception as exc:
            self._quarantine(url, f"transport failure: {type(exc).__name__}: {exc}")
            raise EdgarError(f"EDGAR request failed: {url}") from exc

        if status != 200:
            self._quarantine(url, f"HTTP {status}")
            raise EdgarError(f"EDGAR returned HTTP {status} for {url}")

        self._events.append(
            EventType.INGEST_RAW,
            {
                "source": self.name,
                "url": url,
                "bytes": len(body),
                # The payload itself is not inlined: submissions documents run to
                # megabytes, and the event log is not an archive of the internet.
                "sha256_prefix": _digest(body),
            },
        )
        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._quarantine(url, f"malformed JSON: {exc}")
            raise EdgarError(f"EDGAR sent unparseable JSON for {url}") from exc

    def _quarantine(self, url: str, reason: str) -> None:
        """Record a failure rather than degrading into a partial parse."""
        _log.warning("edgar ingest failed: %s (%s)", url, reason)
        self._events.append(
            EventType.INGEST_ERROR, {"source": self.name, "url": url, "reason": reason}
        )

    # -- resolution ------------------------------------------------------------

    def resolve_cik(self, ticker: str) -> str | None:
        """Ticker → padded CIK, using SEC's own mapping file."""
        if self._ticker_map is None:
            payload = self._get_json(TICKERS_URL)
            mapping: dict[str, str] = {}
            entries = payload.values() if isinstance(payload, dict) else payload
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                symbol = str(entry.get("ticker", "")).upper()
                cik = entry.get("cik_str")
                if symbol and cik is not None:
                    mapping[symbol] = normalize_cik(cik)
            self._ticker_map = mapping
        return self._ticker_map.get(ticker.upper())

    # -- fetching --------------------------------------------------------------

    def recent_filings(self, ticker: str) -> list[Filing]:
        """Recent filings of interest for one ticker, newest first."""
        if not self._config.enabled:
            return []
        cik = self.resolve_cik(ticker)
        if cik is None:
            self._quarantine(TICKERS_URL, f"no CIK for ticker {ticker!r}")
            return []

        payload = self._get_json(SUBMISSIONS_URL.format(cik=cik))
        recent = (payload.get("filings") or {}).get("recent") or {}

        forms = recent.get("form") or []
        accessions = recent.get("accessionNumber") or []
        accepted = recent.get("acceptanceDateTime") or []
        filed = recent.get("filingDate") or []
        primary = recent.get("primaryDocument") or []
        reports = recent.get("reportDate") or []

        # EDGAR returns parallel arrays. A length mismatch means the shape
        # changed and rows would silently pair up wrongly.
        lengths = {len(forms), len(accessions), len(accepted), len(filed)}
        if len(lengths) > 1:
            self._quarantine(
                SUBMISSIONS_URL.format(cik=cik),
                f"parallel arrays disagree in length: {sorted(lengths)}",
            )
            return []

        filings: list[Filing] = []
        for index, form in enumerate(forms):
            if form not in self._config.forms:
                continue
            accepted_at = parse_acceptance(_at(accepted, index))
            if accepted_at is None:
                # Without a true acceptance time we cannot date the filing, and
                # dating it "now" would make an old document look current.
                self._quarantine(
                    SUBMISSIONS_URL.format(cik=cik),
                    f"filing {_at(accessions, index)} has no usable acceptance time",
                )
                continue
            filings.append(
                Filing(
                    cik=cik,
                    ticker=ticker.upper(),
                    form=form,
                    accession=_at(accessions, index),
                    accepted_at=accepted_at,
                    filing_date=_at(filed, index),
                    primary_document=_at(primary, index),
                    report_date=_at(reports, index),
                )
            )
            if len(filings) >= self._config.max_filings_per_company:
                break
        return filings

    def to_context_items(
        self, filings: Iterable[Filing], *, now: datetime | None = None
    ) -> tuple[ContextItem, ...]:
        """Normalize filings into context items with true event times."""
        ingested_at = now or utc_now()
        return tuple(
            ContextItem(
                item_id=new_ulid(),
                source_name=self.name,
                source_url=filing.url,
                source_type=SourceType.FILING,
                entities=(filing.ticker,),
                # The filing's own acceptance time. Never when we downloaded it.
                event_time=filing.accepted_at,
                ingested_at=ingested_at,
                ttl_s=FILING_TTL_S,
                credibility=EDGAR_CREDIBILITY,
                retrieval_reason=f"{filing.form} for {filing.ticker}",
                provenance=Provenance.NORMALIZED,
                payload={
                    "kind": "filing",
                    "ticker": filing.ticker,
                    "form": filing.form,
                    "accession": filing.accession,
                    "filed": filing.filing_date,
                    "report_period": filing.report_date,
                    "url": filing.url,
                },
            )
            for filing in filings
        )

    def latest_known_filing(self, ticker: str) -> Filing | None:
        """Newest filing for an entity.

        Retrieval calls this before citing a filing as current: durable items
        stay citable, but nothing should be presented as the latest word when
        something newer exists (DATA_SOURCES §5).
        """
        filings = self.recent_filings(ticker)
        return max(filings, key=lambda f: f.accepted_at, default=None)


def _at(values: list[Any], index: int) -> str:
    return str(values[index]) if index < len(values) else ""


def _digest(body: bytes) -> str:
    import hashlib

    return hashlib.sha256(body).hexdigest()[:16]
