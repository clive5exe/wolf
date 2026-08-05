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
