# ADR-0010: Secrets in macOS Keychain via `security` CLI wrapper

**Status:** accepted · 2026-08-05 · **Safety-critical**

## Context
We store: optional data-source API keys (e.g. Alpha Vantage), future
Telegram bot token, Robinhood MCP session material if the client must hold
any. We must NOT touch Claude Code's own credentials (its CLI manages them).
Research (RESEARCH_NOTES §3): file-based keychain ACL model suits CLI tools.
Data-protection keychain needs an app bundle. `keyring` lib works but adds a
dependency and binds ACLs to the Python binary.

## Decision
`security/keychain.py` wraps `security add-generic-password -U` /
`find-generic-password -w` / `delete-generic-password` via subprocess
(list-form argv, never shell), service namespace `tradeos.<purpose>`.
No secret ever appears in: repo files, SQLite, event payloads, logs, prompts,
or process argv where avoidable (`-w` value passed via argv is accepted for
v0.1 local threat model. Documented residual). Redaction filter in telemetry
scrubs known secret names + entropy patterns. CI + pre-commit run secret
scans. Revisit with `keyring`/app-bundle when the desktop app ships.

## Consequences
- Zero dependencies. Secrets survive reinstalls. User can audit items in
  Keychain Access.app.
- Keychain prompts may appear when the Python binary changes (ACL model).
  Documented in troubleshooting.
