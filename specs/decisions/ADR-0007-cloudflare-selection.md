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

---

## Amendment — 2026-08-05: superseded except for genuine multi-party work

**Status: superseded by ADR-0002's placement rule**, except for community
aggregates and live-sharing coordination.

ADR-0002 now reads: *anything a user can run on their own system should happen
on their system*, and moving work off the machine requires it to be impossible
for one user alone — not merely cheaper or more convenient centrally.

Re-reading the primitive table above against that test, almost none of it
survives. Ingestion, normalisation, filings archives, symbol metadata, and
scheduled fetching are all things one machine does perfectly well. The
justification recorded here — amortising one ingestion across a community — is
an argument about aggregate efficiency, which the rule explicitly rejects.

Scheduled ingestion, the strongest remaining case, was answered by `wolf watch`
(T-034) running on any always-on machine. That is strictly better: no account,
no third party, no shared failure domain, and the event log never leaves.

### Free-tier figures above are stale

This ADR asked for re-verification before building. Checked 2026-08-05 against
Cloudflare's docs:

| Recorded here | Actual |
|---|---|
| D1 500 MB free | **5 GB** — off by 10× |
| Cron Triggers 5/account free | **appears to require the paid plan** (~$5/mo) |
| Workers 100k req/day | confirmed; **overage fails closed, it does not bill** |

The Cron Triggers change is the significant one: it was the primitive the whole
tier was most useful for. That it is no longer free, while a homelab does the
same job for nothing, is a second independent reason not to build this.

### What would revive it

Only community aggregates — a sentiment figure across many users' inputs cannot
be computed by one of them. If that ships, it needs its own ADR, because the
privacy question is different in kind: a shared instance learns every querying
user's watchlist, and that has to be designed for up front rather than
retrofitted.

The `cloudflare/` scaffold directories hold no files and are untracked; nothing
in `src/` or `tests/` references any of this.

### Correction — same day: reinstated

The supersession above was based on a misreading of ADR-0002's placement rule
(corrected there). The rule prevents centralising *per-user* work; it does not
reject hosting genuinely shared work, and it says nothing against Cloudflare.

**Status returns to: accepted (design), deferred (build).**

Two arguments survive the corrected rule, and the first is stronger than this
ADR originally credited:

- **Third-party citizenship, not our convenience.** SEC EDGAR enforces fair
  access. Five hundred users each polling it directly is five hundred clients
  that must independently behave — rate limits, User-Agent rules, backoff. One
  cached fetch shared out is better for EDGAR *and* removes a compliance burden
  from every user. The earlier dismissal of this as "aggregate efficiency" was
  wrong: it is about not being a bad neighbour to a public service.
- **Community aggregates**, unchanged — uncomputable by one user by definition.

The hosting target is explicitly **Cloudflare, not a maintainer's homelab**. A
homelab runs its owner's `wolf watch`; it does not serve strangers.

Unchanged: every primitive keeps a documented local fallback, pointing at any
instance stays opt-in, and nothing in the client hard-depends on it. A user who
wants to fetch EDGAR themselves always can.

The stale free-tier figures recorded above still stand as corrections — D1 is
5 GB, and Cron Triggers appear to need the paid plan. The latter matters less
now: scheduled *personal* cycles are `wolf watch` on the user's own machine,
so any Cron use would be for shared ingestion only.
