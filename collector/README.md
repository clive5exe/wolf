# WOLF collector

A daily Cloudflare Worker that records public SEC filing metadata so the
dataset grows into something nobody can revoke.

## Why

Historical index membership and delisted price history are the two things data
vendors actually charge for. Both are only expensive because you are buying
*the past*. Recorded forward, one day at a time, they cost nothing, and they
are survivorship-free by construction rather than by reconstruction.

SEC EDGAR is the only source evaluated that is free, unlimited,
unauthenticated, **and public domain**. US Government works carry no terms of
service, so this is also the only collected dataset we may legally
redistribute.

## What it is not

**Not a backend WOLF depends on.** The site promises "no service behind it",
and a user's portfolio must never require somebody else's Cloudflare account.
The app fetches from SEC directly and treats this only as a mirror. If this
Worker disappears, nothing in WOLF breaks.

## What it collects

One request per day to the SEC daily form index returns every filing accepted
that day. Measured on 2026-08-04: **1,908 relevant rows from a single 1.3 MB
request**, being 1,896 Form 4 and 12 Form 25-NSE.

| Form | What it is | Why keep it |
|---|---|---|
| `4` | Insider transaction | Filed within 2 business days with exact share counts and prices. The timeliest free informed-trading signal there is. |
| `25-NSE` | Exchange delisting notice | Carries a rule provision separating a merger from a compliance failure, so a backtest need not treat an acquisition like a bankruptcy. |
| `25` | Issuer withdrawal | The voluntary equivalent. |
| `SC 13D` | Activist crossing 5% | A real event with a real announcement effect. |

## Cost

Free tier, comfortably. One cron and about 2,000 row writes a day against D1's
100,000 daily allowance, roughly 2% of budget. A year is about 500,000 rows,
well under the 5 GB ceiling.

## Deploy

```sh
npm install -g wrangler
wrangler login
wrangler d1 create wolf-collector          # paste the id into wrangler.toml
wrangler d1 execute wolf-collector --remote --file=schema.sql
wrangler deploy
```

Backfilling a missed day:

```sh
curl -X POST "https://wolf-collector.<subdomain>.workers.dev/collect?day=2026-08-04"
```

Set a `COLLECT_TOKEN` secret to require a token on that endpoint:

```sh
wrangler secret put COLLECT_TOKEN
```

## Read

```
GET /health                                  last run, so a gap is visible
GET /filings?form=4&cik=0000320193&limit=50  filings, newest first
```

## Test

```sh
node --test test/parse.test.mjs
```

The parser is the fragile part, because the index is a fixed-width format with
no machine-readable schema: the header wraps across two lines, the rule beneath
is one unbroken run of dashes, and both form types and company names contain
spaces. It therefore anchors from the right, where the shapes are unambiguous.
It throws rather than returning nothing if the layout changes, since a silent
empty result looks exactly like a quiet day and could go unnoticed for months.
