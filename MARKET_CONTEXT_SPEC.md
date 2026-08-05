# Market Context Specification — the Time-Aware Intelligence Engine

**Status:** v0.1 · **Implements:** `src/tradeos/{ingestion,context,retrieval,sentiment}/`, models in `domain/context.py`

## 1. Principle

This is not "RAG over finance documents." Every piece of information that can
influence a decision is a **timestamped, sourced, expiring asset**. The system
must always be able to answer: *what did we know, from where, how old was it,
and was it still valid when we acted?* Data with unknown provenance or expired
freshness cannot enter a live decision — the `stale_context` risk rule
enforces this downstream.

## 2. Source classes

| Class | Examples | Typical TTL |
|---|---|---|
| A. Live state | broker account, quotes, spreads, market status, breaking news, econ releases, earnings events, social sentiment, order events | seconds–hours |
| B. Durable knowledge | SEC filings, transcripts, company profiles/sectors, macro series, user strategy docs, journal, prior decisions, historical snapshots | days–quarters |
| C. Derived intelligence | sentiment direction/velocity, source diversity, credibility, price confirmation, relative volume, trend state, concentration, correlation, exposures, vol/drawdown, event risk, completeness, freshness | recomputed per cycle |

## 3. `ContextItem` schema (every item, no exceptions)

```python
class SourceType(StrEnum):
    BROKER="broker"; MARKET_DATA="market_data"; FILING="filing"; NEWS="news"
    SOCIAL="social"; MACRO="macro"; USER="user"; DERIVED="derived"

class Provenance(StrEnum):
    RAW="raw"; NORMALIZED="normalized"; DERIVED="derived"; MODEL_GENERATED="model_generated"

class Freshness(StrEnum):
    FRESH="fresh"        # age <= 0.5 * ttl
    AGING="aging"        # 0.5*ttl < age <= ttl
    STALE="stale"        # ttl < age <= 2*ttl   (usable ONLY for non-decision display)
    EXPIRED="expired"    # age > 2*ttl          (never usable in decisions)

class ContextItem(BaseModel):
    item_id: str                     # ULID
    source_name: str                 # "sec_edgar", "robinhood_mcp", "paper_engine"…
    source_url: str | None           # canonical URL / identifier where applicable
    source_type: SourceType
    entities: list[str]              # tickers / entity ids, resolved + uppercased
    event_time: datetime             # original publication/event timestamp (UTC)
    ingested_at: datetime            # when we received it (UTC)
    ttl_s: int                       # per source-type default, overridable per item
    credibility: Decimal             # 0..1, rubric in §6
    retrieval_reason: str            # why this item was pulled into this package
    provenance: Provenance
    payload: dict[str, Any]          # normalized, schema per source connector
    content_hash: str                # sha256 of normalized payload → dedupe

    def age_s(self, now: datetime) -> int
    def freshness(self, now: datetime) -> Freshness   # pure function of age/ttl
```

Freshness is **computed, never stored** — a stored freshness would itself go
stale. `event_time` vs `ingested_at` are both mandatory; connectors that
cannot supply a real `event_time` must say so explicitly by setting
`event_time = ingested_at` AND `payload["event_time_is_ingestion_proxy"] = true`.

## 4. Default TTLs by source type (constants in `context/ttl.py`)

| Kind | TTL | Note |
|---|---|---|
| quote | 60 s (paper) / 10 s (live modes) | risk rule uses policy.stale_quote_max_age_s |
| market_status | 60 s | |
| broker account/positions | 300 s | must be refreshed at cycle start anyway |
| social sentiment aggregate | 15 min | |
| breaking news item | 6 h | decays through AGING |
| analyst revision | 5 days | |
| earnings result | 1 quarter | |
| SEC filing | durable (ttl = 400 days) | but retrieval must run a "latest-known filing" check |
| company profile / sector | 30 days | |
| macro series point | series-specific | |
| user documents / policy | no TTL (versioned instead) | |

## 5. `MarketContextPackage`

The unit handed to strategies and providers. Assembled per cycle by
`context/assembler.py` from retrieval filters (symbols, sectors, strategy
needs, event type).

```python
class ContextRequirement(BaseModel):
    kind: str                        # "quote", "positions", "market_status"…
    required: bool                   # required + missing/expired ⇒ incomplete

class MarketContextPackage(BaseModel):
    package_id: str; created_at: datetime
    purpose: str                     # "rebalance_check:AAPL,MSFT…"
    requirements: list[ContextRequirement]
    items: list[ContextItem]
    completeness: Decimal            # fraction of required kinds present & non-expired
    missing: list[str]               # required kinds absent or expired
    citations: list[str]             # item_ids — what a thesis may reference
```

Rules:
- A package with `completeness < 1.0` may still be produced (transparency),
  but the decision cycle records `context.incomplete` and the `stale_context`
  risk rule vetoes order-producing paths.
- Providers receive the package rendered with per-item ids, sources, and ages;
  `StructuredThesis.supporting_item_ids` must be a subset of `citations`
  (validated — unknown ids are a validation failure, recorded as an
  unsupported-claim signal for evaluation).
- Model-generated content re-entering context is tagged
  `provenance=MODEL_GENERATED`, `credibility ≤ 0.3`, and is barred from being
  the sole support for any thesis claim.

## 6. Credibility rubric (initial, deterministic)

| Band | Score | Examples |
|---|---|---|
| Official primary | 0.95 | SEC EDGAR, broker account data, exchange status |
| Licensed market data | 0.85 | broker-provided quotes |
| Established outlet (allowlisted) | 0.7 | curated news feeds |
| Aggregated social (min sample met) | 0.4 | sentiment aggregates |
| Single social post | 0.15 | never decision-bearing alone |
| Model-generated | ≤ 0.3 | theses, summaries |

Scores are per-source constants in v0.1; per-item adjustment (author history,
bot likelihood) is v0.2+.

## 7. Sentiment (design; one connector max in v0.1, only if legally viable)

Normalization: post → `{tickers, event_time, sentiment ∈ [-1,1], confidence,
engagement, author_cred?, duplicate_or_bot_likelihood, topic}`. Aggregation is
deterministic over rolling windows (15 m / 1 h / 24 h): direction,
volume-vs-baseline acceleration, engagement-adjusted intensity, source
diversity (distinct authors/venues), disagreement (variance), and price/volume
confirmation flag. Hard floors: `n ≥ 25` posts and `diversity ≥ 10` authors,
else the aggregate is emitted with `below_floor=true` and is non-decision-
bearing. A single post can never form a tradable signal.

## 8. Ingestion pipeline (per connector)

`fetch → raw event (stored verbatim) → normalize → entity/ticker resolution →
dedupe (content_hash) → credibility stamp → TTL stamp → context store`.
Each stage appends events; failures quarantine the item, never silently drop.

## 9. Failure cases

- Connector down → last-known items age out naturally; cycles see `missing`.
- Clock disagreement (event_time > now + 5 min) → item quarantined.
- Unresolvable ticker → item kept with `entities=[]`, excluded from retrieval.
- Duplicate storm → dedupe by content_hash; duplicate count recorded.

## 10. v0.1 acceptance criteria

1. `ContextItem`/`MarketContextPackage` implemented with computed freshness;
   property tests over age/ttl boundaries.
2. Paper/fake quote source + broker positions connector produce packages with
   correct completeness math.
3. An expired required item vetoes an order path (integration test with the
   risk engine).
4. Thesis citing an unknown item id fails validation (test).
