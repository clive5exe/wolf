# v0.1 Backlog — Milestones & Task Index

**Status:** live · Task packets in [V0.1_TASK_PACKETS.md](V0.1_TASK_PACKETS.md) · Safety classes: `S0` routine · `S1` money/data adjacent (test+reviewer gates) · `S2` safety-critical (human review mandatory)

State legend: ☐ ready · ◐ in progress · ☑ done (this scaffold session) · ▷ blocked-by noted

## M1 — Foundation (repo runs, verifies, stores events)
| ID | Task | Class | State |
|---|---|---|---|
| T-001 | Package scaffold, pyproject, tooling config (Ruff/mypy/pytest) | S0 | ☑ |
| T-002 | Domain models: policy, portfolio, orders, context, thesis, risk | S1 | ☑ |
| T-003 | ULID + clock + Decimal/JSON canonicalization utilities | S0 | ☑ |
| T-004 | Append-only SQLite event store + migrations + triggers + replay reducers | S1 | ☑ |
| T-005 | Telemetry: structured logging with redaction filter | S1 | ☑ |
| T-006 | Verification scripts (verify.sh, safety_check.sh, dev_setup.sh) + CI | S0 | ☑ |

## M2 — Providers & brokers
| ID | Task | Class | State |
|---|---|---|---|
| T-007 | Provider protocol + result/error types | S1 | ☑ |
| T-008 | Claude Code adapter: detect, auth status, health, structured query (fake-CLI tests) | S1 | ☑ |
| T-009 | Fake broker (scripted) + broker contract test suite | S1 | ☑ |
| T-010 | Paper broker: fills, slippage, cash/position accounting via events | S1 | ☑ |
| T-011 | Keychain wrapper (`security` CLI) with mocked tests | S2 | ☑ |

## M3 — Decisions (policy → strategy → risk → paper execution)
| ID | Task | Class | State |
|---|---|---|---|
| T-012 | Policy service: versioning, mode ladder, events; sample policy fixture | S1 | ☑ |
| T-013 | Context: ContextItem/Package, TTL table, assembler over broker+quotes | S1 | ☑ |
| T-014 | Risk engine + full v0.1 rule set + ValidatedOrder issuance | **S2** | ☑ |
| T-015 | Rebalance strategy (drift threshold, fractional handling, no-action) | S1 | ☑ |
| T-016 | Execution layer: idempotent submit, event trail, kill-switch check | **S2** | ☑ |
| T-017 | Decision cycle orchestrator (trigger→…→notify) + runtime facade | S1 | ☑ |

## M4 — Interfaces & experience
| ID | Task | Class | State |
|---|---|---|---|
| T-018 | `tradeos doctor` with fix hints (provider states, store, notifier) | S0 | ☑ |
| T-019 | CLI: `demo`, `events list`, `policy show/init-sample`, `kill` | S0 | ☑ |
| T-020 | TUI shell: dashboard (positions, drift, activity feed, mode badge) | S0 | ☑ |
| T-021 | macOS notifier (osascript) with message contract | S0 | ☑ |
| T-022 | Onboarding flow: NL goals → PolicyDraft (provider) → confirm form → active policy | S1 | ☐ |

## M5 — Intelligence & evaluation
| ID | Task | Class | State |
|---|---|---|---|
| T-023 | SEC EDGAR connector: submissions+companyfacts, rate limiter, raw events | S1 | ☐ |
| T-024 | Robinhood Agentic MCP read-only adapter + tool-probe + allowlist registry | **S2** | ☐ unblocked (Q2 answered yes 2026-08-05); fixture-driven dev now, live connect after owner completes RH onboarding |
| T-025 | Sentiment interface + deterministic aggregation (+ optional Bluesky connector, flag-off) | S1 | ☐ |
| T-026 | Portfolio statistics module with documented formulas | S1 | ◐ (core stats done; Sharpe/Sortino/beta pending benchmark decision A13) |
| T-027 | Golden scenarios (6) + replay hash-equality gate | S1 | ◐ (replay equality done; goldens 5/6) |
| T-028 | Journal + evaluation.recorded metrics per cycle | S1 | ☐ |
| T-029 | Provider structured-output live smoke doc (manual, logged-in machine) | S0 | ☐ |
| T-030 | Threat-model regression suite completion (T1–T7 rows each mapped to a test) | **S2** | ◐ |

Next five (priority order): **T-022, T-023, T-026 finish, T-027 finish, T-028.**
T-024 stays blocked on the human answering ASSUMPTIONS Q2.

## Milestone acceptance
- M-gates are the PRODUCT.md §7 criteria mapped: M1→cr.5,7 · M2→cr.2 · M3→cr.3,4 · M4→cr.1,8 · M5→cr.3,5,6.
- No task is "done" without the CONTRIBUTING.md definition-of-done evidence
  attached to its PR/commit.
