# WOLF Product Specification

**Status:** v0.1 draft · **Owner:** core team · **Related:** [ARCHITECTURE.md](ARCHITECTURE.md), [ROADMAP.md](ROADMAP.md), [RISK_POLICY_SPEC.md](RISK_POLICY_SPEC.md)

## 1. What WOLF is

A local-first, open-source **AI portfolio-management runtime for macOS**. It
orchestrates AI tools the user already has (Claude Code under a Pro/Max
subscription first. Codex CLI, Gemini CLI, Ollama, and API providers later),
MCP services, market context, deterministic risk policies, and notification
channels to continuously monitor a portfolio, generate **sourced** decisions,
simulate or execute **bounded** actions, and evaluate its own behavior over
time.

It is explicitly **not**: a chatbot with a stock ticker, a signal-selling
service, an unrestricted trading bot, or investment advice.

## 2. Who it is for

| Persona | Need | v0.1 serves them with |
|---|---|---|
| Technical retail investor | Continuous, explainable portfolio intelligence without another SaaS bill | TUI + CLI, BYO-AI provider, paper trading, journal |
| Quant-curious tinkerer | A safe harness to test strategy ideas | Strategy plugin API, replay, evaluation metrics |
| Cautious allocator | Drift monitoring and disciplined rebalancing | Policy onboarding, rebalance strategy, approval-mode proposals |

## 3. Make-or-break experience: Bring Your Own AI

- Detect installed providers, test authentication, probe capabilities, let the
  user pick one. Minutes, not hours.
- Subscription-backed providers are used **only** through officially installed
  local clients and their documented programmatic interfaces. No browser
  scraping, cookie theft, hidden tokens, or private endpoints. Ever.
- API-key providers are optional adapters, never a mandatory bill.
- Every provider publishes a capability set (structured output, streaming,
  sessions, tool use, context size). The runtime routes work accordingly and
  degrades explicitly when a capability is missing.

## 4. Product modes (the safety ladder)

| Mode | Name | May read broker | May prepare orders | May submit orders | Default |
|---|---|---|---|---|---|
| 0 | Read-only intelligence | ✅ | ❌ | ❌ | ✅ (initial) |
| 1 | Paper trading | ✅ | ✅ (simulated) | ✅ paper engine only | |
| 2 | Approval required | ✅ | ✅ (validated) | only after explicit human approval | |
| 3 | Restricted autopilot | ✅ | ✅ | only inside a dedicated, capped account, approved strategies/symbols/hours/budgets | disabled, multi-step activation |

Mode invariants:

- Mode is stored policy state. Every mode change is an audit event and a
  notification.
- Mode 3 requires: dedicated account allocation, per-strategy approval,
  visible active-state indicator, kill switch, and automatic shutdown on rule
  violation, stale data, provider failure, inconsistent portfolio state,
  excessive latency, abnormal volatility, or missing market information.
- There is **no mode 4**. Unbounded autonomy is not a roadmap item.
- v0.1 ships modes 0 and 1 only. Mode 2 arrives in v0.2, mode 3 in v0.3
  (see ROADMAP.md), each gated on maturity criteria, not calendar.

## 5. Core user journeys (v0.1)

### J1 Setup (target: under 10 minutes)
`git clone` → `./scripts/dev_setup.sh` → `tradeos doctor` reports: macOS ok,
Python ok, Claude Code found + authenticated + structured-output round-trip
passed, data dir writable, event store initialized. Failures come with a fix
hint, not a stack trace.

### J2 Policy onboarding
User states goals in natural language. The provider translates them into a
draft `InvestmentPolicy` (see INVESTMENT_POLICY_SPEC.md). The TUI shows the
draft as explicit structured fields. The user edits and confirms. The stored
policy is versioned, deterministic data. The model's interpretation is a
convenience. The confirmed struct is the only thing the runtime enforces.

### J3 Portfolio intelligence (mode 0)
Connect read-only broker source (Robinhood MCP if available, else manual/CSV
positions), display portfolio, allocations, drift vs targets, concentration,
and statistics with documented formulas. Assemble a Market Context Package for
tracked symbols with per-item source, timestamps, TTL, and freshness.

### J4 Paper decision cycle (mode 1)
Trigger (schedule or `tradeos demo`) → observe → retrieve context → run the
rebalance strategy → optional AI thesis with citations → deterministic sizing
→ risk engine verdict (every rule result stored) → paper execution with
slippage model → event trail → macOS notification → journal entry. "No action:
insufficient/stale data" is a successful, first-class outcome.

### J5 Replay & review
`tradeos events list` / replay a captured day of paper events. Every decision
shows its context package, thesis, rule results, and fills. Nothing is
unexplainable.

## 6. Non-goals for v0.1

Options. Unrestricted autonomous execution. Multi-broker. Community holdings.
Strategy marketplace. Multi-model consensus. Massive financial RAG. Knowledge
graph. WhatsApp/iMessage. Mobile. Tax optimization. Any claim of
market-beating performance.

## 7. Acceptance criteria for the v0.1 release

1. Fresh macOS machine reaches a passing `tradeos doctor` in ≤ 10 minutes with
   only documented steps.
2. Claude Code provider detection: correctly distinguishes not-installed /
   installed-not-authenticated / ready, and completes a schema-validated
   structured query.
3. A full paper decision cycle runs end-to-end and emits ≥ 1 event per stage
   (trigger, context, proposal, risk, execution/skip, notification).
4. Every risk rule in RISK_POLICY_SPEC.md §4 (v0.1 set) has passing unit tests
   for both pass and veto cases. A failed blocking rule prevents any order
   object from reaching a broker adapter in all code paths (safety tests).
5. Replay of a captured event log reproduces identical derived portfolio
   state (hash-compared).
6. No secrets in the repo, logs, or event payloads (automated scan).
7. `scripts/verify.sh` (format, lint, types, tests) passes in CI on macOS.
8. README carries the experimental / not-investment-advice statement and the
   security model summary.

## 8. Key product principles

- **Explain or don't act.** Every action carries sources, timestamps, rule
  results, and a rationale identifier.
- **Stale data is a stop sign**, not a fallback.
- **The model proposes. Code disposes.** No LLM output can change a limit.
- **Silence is expensive.** Failures, skips, and shutdowns notify the user.
- **Local by default.** The cloud component is optional enrichment, never a
  requirement for core operation.
