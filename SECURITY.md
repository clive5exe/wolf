# Security Policy

WOLF handles brokerage credentials, portfolio data, and (in later versions)
order execution. Security failures here are financial failures. Read
[THREAT_MODEL.md](THREAT_MODEL.md) for the full analysis. This file states the
operational policy.

## Hard rules (enforced in code review and CI)

1. **Secrets live in the macOS Keychain only.** No tokens, API keys, cookies,
   or session material in files, environment checked into git, SQLite, logs,
   or model prompts. `scripts/safety_check.sh` scans for violations on every
   commit.
2. **No credential scraping.** WOLF never reads browser sessions, lifts
   cookies, or calls private/undocumented broker endpoints. Subscription AI
   providers are used only through their officially installed clients and
   documented interfaces.
3. **The deterministic risk engine cannot be bypassed.** Broker `submit_order`
   accepts only a `ValidatedOrder` produced by the risk engine. Model output is
   data, never authority. Changes to `src/tradeos/risk/`, `src/tradeos/execution/`,
   `src/tradeos/brokers/`, and `src/tradeos/security/` require human review and
   the safety test suite (`tests/safety/`).
4. **Logs are redacted.** No account numbers, credentials, or personal
   brokerage identifiers in ordinary logs or telemetry.
5. **Autopilot is off by default**, gated behind multi-step activation, a kill
   switch, and automatic shutdown conditions. There is no configuration that
   produces unbounded autonomous trading.

## Reporting a vulnerability

Open a private security advisory on the repository (GitHub → Security →
Advisories) or email the maintainers. Do not open public issues for
exploitable problems. We aim to acknowledge within 72 hours.

Please include: affected module, reproduction steps, impact assessment, and
whether real brokerage credentials or funds could be affected.

## Scope notes

- Paper trading and the fake broker involve no real credentials or funds.
- The Robinhood integration is read-only in v0.1. Execution paths ship disabled.
- WOLF is experimental software and **not investment advice**. See README.
