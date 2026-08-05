# ADR-0007: Cloudflare service selection for the optional shared backend

**Status:** accepted (design), deferred (build) · 2026-08-05

## Context
Local-first is the rule (ADR-0002), but shared market intelligence (one
ingestion of EDGAR/news per community rather than per user), community
aggregates, and future sync benefit from a small managed backend. Free-tier
facts verified 2026-08-05 (RESEARCH_NOTES §6.8) — re-verify before building.

## Decision — smallest useful subset, per primitive

| Primitive | Use | Why / free-tier fit | Failure behavior & local fallback |
|---|---|---|---|
| Workers | ingestion + context read APIs, normalization | 100k req/day free covers a small community | client falls back to direct-source connectors (EDGAR local) |
| Cron Triggers | scheduled ingestion (5/account free) | replaces per-user cron | staleness rises; clients see it via freshness metadata, nothing breaks |
| Queues | decouple fetch→normalize→classify (free 10k ops/day, 24 h retention) | bursty filing days | Worker falls back to synchronous inline processing when queue unavailable |
| R2 | raw filings, normalized payload archives, replay datasets (10 GB + zero egress free) | immutable blobs, cheap distribution | clients keep local raw copies regardless |
| D1 | symbols, source refs, event indexes, aggregate sentiment (500 MB/db free) | relational metadata | read-through cache locally; stale-tolerant |
| KV | cached low-consistency config (1k writes/day free — config only, never truth) | | defaults compiled into client |
| Durable Objects | ONLY per-symbol rolling aggregate state / websocket coordination if live sharing ships (SQLite-backend DOs are free) | genuine coordinated state | feature simply absent locally |
| Vectorize | NOT adopted yet — semantic retrieval hasn't shown measurable value over metadata filters; adopt only with an eval demonstrating lift; vectors would carry ticker/source/type/pub-time/ingest-time/expiry metadata for staleness filtering | | n/a |

Budget alerts + explicit resource caps configured from day one. `cloudflare/`
holds wrangler config and migrations; nothing in the client hard-depends on
any of it.

## Consequences
- Community tier can run at ~$0 initially; every primitive has a stated
  failure mode and local fallback.
- We consciously skip Vectorize/DO until evidence demands them — architecture
  stays explainable.
