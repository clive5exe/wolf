# Data Sources

**Status:** v0.1 · **Verified:** specs/research/RESEARCH_NOTES.md (2026-08-05) · **Schemas:** MARKET_CONTEXT_SPEC.md

Policy: every source enters through a connector in `src/tradeos/ingestion/`,
carries the license/ToS assessment recorded here, and stamps every item with
source, event time, ingestion time, TTL, and credibility. **No source ships
without this row.** "Legally questionable" means excluded, not risk-accepted.

## 1. v0.1 sources (build now)

| Source | Class | Connector | Access & limits | License/ToS position | Credibility |
|---|---|---|---|---|---|
| Paper engine / fake broker | A: broker state | `brokers/paper.py`, `fake.py` | local | n/a | 0.95 |
| Robinhood Agentic Trading MCP (read-only) | A: broker + market data | `brokers/robinhood.py` via `mcp/` | hosted MCP `agent.robinhood.com/mcp/trading`; OAuth-style in-app approval; beta | **Official product**; read-only tool allowlist in v0.1; user must accept RH's data-sharing warning during onboarding | 0.85–0.95 |
| SEC EDGAR | B: filings | `ingestion/edgar.py` | `data.sec.gov` submissions + companyfacts JSON; ≤10 req/s; declared `User-Agent: TradeOS <user-contact>`; gzip | **Official, free, no key**; fair-access policy honored by a client-side rate limiter (hard-coded ≤5 req/s) | 0.95 |
| User documents (policy, journal, strategy notes) | B | `ingestion/user_docs.py` | local | user-owned | 1.0 (as *user intent*, not market truth) |
| Derived intelligence | C | `context/derive.py` | computed | n/a | inherits min of inputs |

## 2. v0.1 optional (ship behind config flag, off by default)

| Source | Class | Notes |
|---|---|---|
| Bluesky Jetstream firehose | A: social | Public keyless websocket (`jetstream2.us-east.bsky.network/subscribe`, filter `app.bsky.feed.post`). Free and ToS-clean, but single-venue: sentiment aggregates from it can never satisfy the source-diversity floor alone (MARKET_CONTEXT_SPEC §7) and are marked `below_floor` unless corroborated. Cashtag/ticker extraction is noisy → conservative entity resolution, `duplicate_or_bot_likelihood` heuristics. |
| Alpha Vantage | A: quotes fallback | 25 req/day free — usable only for daily-close snapshots of a small watchlist when no Robinhood MCP connection exists. Requires user's own free key (Keychain-stored). |

## 3. Evaluated and EXCLUDED (do not build)

| Source | Reason |
|---|---|
| Unofficial Robinhood private API (`robin_stocks`, community MCP wrappers) | ToS-violating access pattern; account-suspension and credential-handling risk; violates our "official interfaces only" rule |
| Stocktwits API | Developer program dead (docs 404); legacy endpoint has no terms behind it |
| Reddit Data API | Non-commercial scope + no-AI-training clause + paid tiers make it unsuitable for an open-source agent product |
| Stooq | License unverifiable behind bot wall |
| Earnings-call transcripts (scraped) | No permitted free source verified; revisit only with a licensed source |
| Any scraped news site | Robots/ToS risk; news enters only via licensed/permitted feeds (none in v0.1 — "news" requirement is satisfied by EDGAR filing events, which are news-grade primary sources) |

## 4. Per-source connector requirements (all sources)

1. Rate limiter honoring documented limits (EDGAR ≤5 req/s self-imposed cap).
2. Raw payload persisted as `ingest.raw` event before normalization.
3. Normalizer producing `ContextItem` with true `event_time` (filing accepted
   time, post `createdAt`, quote `as_of`) — proxy timestamps flagged.
4. Failure quarantine + `ingest.error` events; connector health surfaced in
   doctor and provider/data health panel.
5. ToS assessment row in this file, reviewed in PR.

## 5. Freshness defaults

TTLs per source type live in `context/ttl.py` and are specified in
MARKET_CONTEXT_SPEC §4. EDGAR adds a "latest-known filing" check at retrieval
time: durable items remain citable but retrieval re-verifies nothing newer
exists for the entity before a decision cites a filing as current.
