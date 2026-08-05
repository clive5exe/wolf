# TradeOS

**A local-first, open-source AI portfolio-management runtime for macOS.**

TradeOS orchestrates AI tools you already have (Claude Code under your
existing subscription first; Codex CLI, Ollama, and API providers later), MCP
services, market context, deterministic risk policies, and notifications to
continuously monitor a portfolio, generate *sourced* decisions, simulate or
execute *bounded* actions, and evaluate its own behavior over time.

> ⚠️ **Experimental software. Not investment advice.** TradeOS is a research
> runtime. It ships with no real-money execution: v0.1 is read-only
> intelligence + paper trading, by design. Nothing here predicts markets, and
> no output should be treated as a recommendation to buy or sell anything.

## Why this exists

Most "AI trading" projects are a prompt around a chatbot. TradeOS takes the
opposite stance:

- **The model proposes; deterministic code disposes.** An LLM may synthesize
  research and draft theses. It cannot touch position limits, loss limits,
  trading hours, symbol permissions, or the kill switch — those are ordinary,
  fully-tested Python with absolute veto power.
- **Every decision is explainable.** Each cycle records its context package
  (source, timestamps, TTL, freshness), the strategy's arithmetic, every risk
  rule's result, fills, and notifications — into an append-only event log
  that replays byte-identically.
- **Stale data is a stop sign.** Nothing enters a decision without an event
  time, ingestion time, TTL, and credibility score. "Insufficient or stale
  data; no action" is a successful outcome, not an error.
- **Bring your own AI.** Subscription-backed local clients via their
  documented interfaces only — no browser scraping, no cookie theft, no
  private endpoints, no mandatory API bill.

## Status: v0.1 scaffold (see [ROADMAP.md](ROADMAP.md))

| Works today | Deliberately absent |
|---|---|
| `tradeos doctor` environment diagnosis with fix hints | Real-money execution (v0.2+, human-approved only) |
| Claude Code provider: detection, auth state, native schema-constrained structured output (verified live) | Autopilot (v0.3, restricted envelope, dedicated account) |
| Deterministic risk engine — 20 rules, fail-closed, absolute veto | Options, multi-broker, consensus, marketplace (see PRODUCT.md §6) |
| Paper trading with slippage model + event-sourced replay | |
| Target-allocation rebalance strategy (explicit Decimal math) | |
| Versioned investment policy with mode ladder + kill switch | |
| Textual TUI dashboard, Typer CLI, macOS notifications | |
| 127 tests incl. safety/contract/replay suites; mypy clean; CI | |

## Quickstart (macOS)

```bash
git clone <repo> tradeos && cd tradeos
./scripts/dev_setup.sh          # venv, editable install, git hooks
source .venv/bin/activate

tradeos doctor                  # check platform, store, Claude Code, policy
tradeos doctor --full           # + one live structured round-trip probe*
tradeos demo --cycles 2         # paper decision cycles with the sample policy
tradeos portfolio               # allocations, drift, concentration
tradeos events                  # the audit trail
tradeos tui                     # dashboard (q quit · r refresh · c cycle · k kill)
```

\* Requires a logged-in Claude Code CLI. Note: headless (`claude -p`) calls
may draw from your plan's *programmatic* usage allowance and report a real
cost per call — TradeOS records it per event and never hides it.

## Architecture (short version)

```
TUI / CLI  ──►  Runtime facade  ──►  decision cycle
                    │   trigger → observe → retrieve → candidates
                    │   → optional AI thesis (schema-validated, citation-checked)
                    │   → deterministic sizing → RISK ENGINE (veto) → mode gate
                    │   → paper execution → events → notify → evaluate
                    ▼
        append-only SQLite event log  ←  replay == release gate
```

- One reusable **headless core**; interfaces only display state and send
  commands (mechanically enforced).
- `ValidatedOrder` — the only object a broker adapter accepts — can only be
  issued by the risk engine, is idempotent by construction, and expires.
- Kill switch is checked at the scheduler, cycle, engine, and execution
  layers; engaging it is one command (`tradeos kill "reason"`).

Full detail: [ARCHITECTURE.md](ARCHITECTURE.md) · [RISK_POLICY_SPEC.md](RISK_POLICY_SPEC.md) ·
[MARKET_CONTEXT_SPEC.md](MARKET_CONTEXT_SPEC.md) · [PROVIDER_SPEC.md](PROVIDER_SPEC.md) ·
[THREAT_MODEL.md](THREAT_MODEL.md) · ADRs in `specs/decisions/`.

## Security model (summary — see [SECURITY.md](SECURITY.md))

- Secrets live in the macOS Keychain only; repo, SQLite, logs, and prompts
  are scanned for credential shapes on every commit and in CI.
- Model output and ingested market content are treated as hostile input:
  schema validation, citation integrity checks, and — decisively — the
  deterministic risk boundary between any text and any order.
- Broker access is read-only in v0.1; the Robinhood integration targets only
  the official Agentic Trading MCP, never private APIs.

## Verification

```bash
./scripts/verify.sh        # ruff format+lint, mypy, full pytest
./scripts/safety_check.sh  # secrets scan, boundary scan, safety suite
```

CI runs both on macOS and Linux (Python 3.12/3.13). The safety suite proves:
no order path bypasses the risk engine, tampered orders are refused at the
broker boundary, duplicates never re-execute, the kill switch halts
everything, and hostile context text cannot change a proposal or verdict.

## Known limitations (honest list)

- Quotes in the demo are static fixtures; live market data lands with the
  Robinhood MCP read-only adapter (T-024, requires an Agentic account).
- The market clock knows regular NYSE hours but not exchange holidays (paper
  mode simulates sessions; live modes in v0.2 require a holiday source).
- Sharpe/Sortino/beta report "unavailable" until a licensed benchmark series
  is configured — they are never approximated silently.
- Paper fills model slippage as a flat bps adjustment: no spread, no partial
  fills, no market impact (documented in every fill event).
- Earnings-blackout rule exists but defaults to disabled: no reliable free
  earnings-calendar source has been verified yet.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Development runs through a
spec-first, agent-assisted workflow (`.claude/`) with hard gates: risk,
execution, broker, and security changes always require human review plus the
safety suite. Task backlog: [specs/tasks/BACKLOG.md](specs/tasks/BACKLOG.md).

## License

MIT — see [LICENSE](LICENSE). Again: **experimental, not investment advice,
no warranty, capital at risk if you ever wire this to a real account.**
