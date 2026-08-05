# ADR-0002: Local-first architecture with optional cloud

**Status:** accepted · 2026-08-05

## Context
Users hand this system read access to their brokerage and their AI
subscription. Trust demands: data stays on the machine, the system works
offline-ish (degrades explicitly), and no mandatory account with us.

## Decision
All state (events, policies, portfolio, journal) lives in local SQLite under
`~/Library/Application Support/TradeOS/`. Secrets live in the macOS Keychain.
The Cloudflare backend (ADR-0007) is an optional enrichment tier — shared
ingestion and community aggregates — never required for core operation; every
cloud-fed feature has a local fallback or explicit absence.

## Consequences
- Privacy and auditability by construction; replay works offline.
- Multi-device sync is deliberately out of scope until a threat-model review.
- Community features must be designed opt-in + aggregate-only later.
- We accept the cost: each user runs their own ingestion for personal sources.

---

## Amendment — 2026-08-05: state the rule as a default, not a preference

Owner's articulation: **"Anything a user can run on their own system should
happen on their system."**

This is sharper than "local-first" and replaces it as the operative rule. It is
a statement about *where computation is placed*, which can be checked against
any proposed feature, rather than a claim about data movement — which is what
made "local-first" an overclaim when used publicly (see ADR-0012).

### The rule

Placement is not an optimisation decision. The default is the user's machine,
and moving work off it requires a reason that survives this question:

> Is there something about this work that makes it *impossible* for a single
> user to do alone — not merely slower, cheaper, or more convenient elsewhere?

"It would reduce load on a third party", "it would save the user CPU", and "it
would be easier to operate centrally" are all rejected by this test. They are
arguments about our convenience, not about capability.

### What passes

Only genuine multi-party work:

- **Community aggregates** — a sentiment figure across many users' inputs
  cannot, by definition, be computed by one of them.
- **Coordination between users**, if live sharing ever ships.

### What this settles

- **ADR-0007's shared backend is superseded for everything except the above.**
  Ingestion, normalisation, filings archives, symbol metadata, and scheduled
  fetching all run fine on one machine, so under this rule they run there.
  EDGAR (T-023) and sentiment sources (T-025) are local connectors, not client
  calls to a service we operate.
- **Scheduling is local.** `wolf watch` on an always-on machine — a homelab, a
  Raspberry Pi, a laptop that stays open — replaces Cloud Cron entirely.
- **The installer never phones home.** Onboarding happens on the machine being
  installed to, not on a server.
- **No hosted instance is on the roadmap.** If one is ever run, it serves
  public market data only, and pointing at it stays opt-in.

### The one standing exception, and why it is temporary

The AI provider. A user cannot run Claude on their own hardware, so the
provider call leaves the machine — which is precisely why the outbound
projection carries proportions rather than amounts (Q3, ADR-0012), and why
PROVIDER_SPEC plans an Ollama adapter. Local inference is this rule applied to
the last component that currently violates it.
