# ADR-0013 — Data acquisition: what runs where, and who pays

- **Status:** accepted · 2026-08-05
- **Refines:** ADR-0002 (placement rule), ADR-0007 (Cloudflare selection)
- **Supersedes:** the three conflicting readings of "should we use Cloudflare"
  recorded across ADR-0002 and ADR-0007 amendments on the same day.

## Context

"Should WOLF have a backend?" was asked and answered three different ways in a
single session, because it is the wrong question. It treats *data* as one thing
when the answer differs entirely by what the data is and whom it belongs to.

This ADR replaces that question with a classification, so the placement of any
future data source is determined rather than debated.

## The classification

| Class | Example | Personal? | Where it is fetched |
|---|---|---|---|
| **A — Account** | positions, cash, orders | inherently, per user | the user's machine |
| **B — Market** | quotes, prices | arrives *with* the account connection | the user's machine |
| **C — Public reference** | SEC filings, sentiment, fundamentals | identical for every user on earth | shared, or the user's machine |

Class A has no alternative: only the user can authenticate to their own broker.
Class B rides along with it — Robinhood's MCP serves quotes beside account
data, so there is no separate fetch to place. **Only class C is a real
decision**, and every previous disagreement was about class C alone.

## Decision

### 1. Classes A and B run on the user's machine, always

No caching tier, ever. A shared service that fetched a user's positions would
need the user's credentials, and a shared service that fetched *their* symbols
would learn their portfolio by inference. Neither is acceptable.

### 2. Class C is fetched once, centrally, and served as a cache

Three reasons, in order of weight:

1. **It removes a regulator-identity question from every user's setup.** SEC
   EDGAR requires a User-Agent declaring a name and contact address. If every
   install fetches directly, onboarding must ask a stranger for their email to
   satisfy a financial regulator — friction that most people answer with
   garbage, which is worse for everyone sharing that address block.
2. **It is good citizenship.** EDGAR enforces fair access. Five hundred clients
   each independently obeying rate limits is five hundred chances to get the
   project blocked.
3. Efficiency. Deliberately listed last: it is the weakest argument and the one
   that repeatedly led to the wrong conclusion.

**The cache never holds user data.** It holds public documents that are the
same for everyone. Pointing at it is always optional, and every source keeps a
direct local fallback, so no user depends on it existing.

### 3. The homelab ingests; Cloudflare stores and serves

```
 homelab                        Cloudflare                  users
 ───────                        ──────────                  ─────
 EDGAR poller     ──push──▶     R2 (documents)   ──read──▶  wolf clients
 Bluesky firehose ──push──▶     D1 (metadata)               (or direct)
 normalisation                  small Worker
```

- **Only outbound connections leave the homelab.** It pushes to R2's API;
  nothing dials in. No open ports, no exposed residential IP, no ISP-terms
  problem, and one household router is never everyone's point of failure.
- **The heavy work is free and belongs at home.** Bluesky's Jetstream is a
  persistent websocket, which Workers handle poorly and a long-running host
  handles trivially. CPU-bound normalisation likewise: Workers cap at 10 ms of
  CPU on the free plan.
- **Cloudflare does what it is uniquely good at**: serving cached bytes to
  strangers, globally, absorbing abuse at the edge.

### 4. The SEC User-Agent needs no user action

No registration, no API key, no account, no browser step — EDGAR is open JSON
over HTTPS. The requirement is a header. WOLF ships a default identifying the
project and linking the repository as its contact channel, with an optional
override for anyone wanting their own contact declared.

The header matters less than the behaviour behind it: a shared default means a
single misbehaving install could get the *project* throttled, so client-side
rate limiting stays well under SEC's published ceiling. Verify their current
wording at implementation time — the docs refuse unidentified fetches, which is
itself the point being made.

## Cost

Verified 2026-08-05; re-verify before building (ADR-0007 recorded figures that
were a full order of magnitude stale within months).

| Resource | Free | Beyond |
|---|---|---|
| R2 storage | 10 GB-month | $0.015/GB-month |
| R2 writes (Class A ops) | 1M/month | $4.50/M |
| R2 reads (Class B ops) | 10M/month | $0.36/M |
| **R2 egress** | **free** | **free** |
| Workers requests | 100k/day | $5/mo → 10M/month |
| D1 storage | 5 GB | paid plan |

**Free egress is the load-bearing number.** Serving documents to any number of
users costs nothing in bandwidth — the charge that would make this expensive
elsewhere.

Expected bill: **$0/month for a long time.** Because ingestion runs on the
homelab, Cron Triggers — the main thing pushing toward the $5 plan — are not
needed; a systemd timer is the scheduler. Workers only serve reads. The paid
plan becomes worthwhile past ~100k requests/day, or if Workers ever need real
CPU, and not before.

## Consequences

- The placement of a new source is now decided by asking which class it is,
  rather than by re-arguing the architecture.
- Nothing about a user's portfolio can reach the cache, because the cache has
  no per-user request shape to leak through. Class C queries are for documents
  by identifier, not "everything about my holdings".
- The homelab is a private ingestion worker, never a public server.
- Every class C source must ship its direct fetch path first. The cache is an
  optimisation of a working connector, never a prerequisite for one — which
  also means the connector is what gets built first, and the offload decision
  is made with evidence about which one is actually heavy.

## Sequencing

1. **T-024 Robinhood** — classes A and B, per-user by necessity, no
   User-Agent question. This is what replaces the static demo prices, and is
   the largest real gap in the product.
2. **T-023 EDGAR** — class C, built as a direct local connector first.
3. **T-025 sentiment** — class C, direct first.
4. **The cache** — only once a connector exists to move, and evidence says it
   is worth moving.
