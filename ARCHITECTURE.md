# TradeOS — Architecture

**Status:** v0.1 · **Related ADRs:** specs/decisions/ADR-0001…0011

## 1. Shape

One reusable **headless core** (`src/tradeos/`) with thin interfaces on top.
Interfaces render state and send commands; they contain zero business logic
(enforced by review + import-linting in `scripts/safety_check.sh`).

```
┌────────────────────────────────────────────────────────────────────┐
│ Interface Layer          TUI (Textual) · CLI (Typer) · future GUI  │
└──────────────┬─────────────────────────────────────────────────────┘
               │ commands / state queries (runtime facade)
┌──────────────▼─────────────────────────────────────────────────────┐
│ Runtime & Orchestration  registry · workflow engine · scheduler ·  │
│                          permissions/approvals · kill switch       │
├────────────┬──────────────┬──────────────┬─────────────────────────┤
│ AI Provider│ Market Intel │ Portfolio &  │ Deterministic Risk &    │
│ Layer      │ & Context    │ Strategy     │ Policy Engine (VETO)    │
├────────────┴──────┬───────┴──────┬───────┴─────────────────────────┤
│ Broker Layer      │ Execution    │ Communication (notifications)   │
│ fake/paper/RH-MCP │ (idempotent) │                                 │
├───────────────────┴──────────────┴─────────────────────────────────┤
│ Storage & Events (append-only SQLite) · Evaluation & Replay ·      │
│ Telemetry · Security (Keychain)                                    │
└────────────────────────────────────────────────────────────────────┘
```

## 2. Package map and dependency rules

| Package | Responsibility | May import from |
|---|---|---|
| `domain/` | Pydantic models shared everywhere (policy, portfolio, orders, context, thesis, risk) | stdlib only |
| `events/` | Event model, event types, store protocol | domain |
| `storage/` | SQLite append-only store, migrations, snapshots | events, domain |
| `providers/` | `ModelProvider` protocol + adapters (claude_code first) | domain |
| `brokers/` | `BrokerAdapter` protocol + fake / paper / robinhood | domain, events |
| `market_data/` | Quote sources, market clock | domain |
| `ingestion/`, `context/`, `retrieval/`, `sentiment/` | Market Intelligence engine (connectors → normalize → score → assemble) | domain, events, storage |
| `portfolio/` | Portfolio state, statistics, drift | domain, market_data |
| `strategies/` | Strategy plugin protocol + built-ins | domain, portfolio |
| `risk/` | Deterministic rule engine, `ValidatedOrder` issuance | domain, events |
| `execution/` | Sole caller of `broker.submit_order`; idempotency | domain, brokers, events |
| `runtime/` | Facade, decision cycle, scheduler, registries, kill switch | everything above |
| `notifications/` | Notifier protocol + macOS adapter | domain |
| `evaluation/`, `replay/` | Metrics, golden scenarios, replay engine | events, storage, domain |
| `telemetry/` | Logging with redaction; OTel later | stdlib |
| `security/` | Keychain access, secret redaction helpers | stdlib |
| `cli/`, `tui/` | Interfaces | runtime facade ONLY |

Forbidden edges (checked mechanically): `cli|tui → brokers|providers|risk`
directly; `providers → brokers`; `strategies → brokers`; anything → `tui`.
Only `execution/` may call `submit_order`.

## 3. The decision cycle (runtime/cycle.py)

```
trigger ──► observe ──► retrieve ──► candidates ──► AI synthesis (optional)
                │            │             │                │
                ▼            ▼             ▼                ▼
          [stale? ABORT] [citations] [no-action ok]  [validated StructuredThesis]
                                                          │
        deterministic sizing ◄────────────────────────────┘
                │
                ▼
        risk engine (every rule, every result stored) ──► VETO ⇒ record+notify
                │ approved
                ▼
        mode gate: display / paper-fill / await-approval / (v0.3 autopilot)
                │
                ▼
        events + notification + journal ──► later: evaluation vs outcome
```

Each cycle gets a `correlation_id`; every event in the cycle carries it. A
cycle that stops early (stale data, missing context, veto) is a *successful*
cycle with outcome `no_action` and a recorded reason.

## 4. Contracts (canonical Pydantic models, `domain/`)

- `InvestmentPolicy` — versioned, deterministic; see INVESTMENT_POLICY_SPEC.md.
- `ContextItem` / `MarketContextPackage` — sourced, timestamped, TTL'd; see
  MARKET_CONTEXT_SPEC.md.
- `ProposedAction` / `TradeProposal` — strategy output; quantities as
  `Decimal`; includes `strategy_id@version`, `context_package_id`, rationale.
- `StructuredThesis` — the ONLY accepted LLM synthesis shape: bull case, bear
  case, why-now, what-changed, invalidation conditions, data gaps, confidence,
  supporting `ContextItem` ids. Schema-validated; failures are retried once
  then recorded as provider errors — never "best-effort parsed".
- `RiskVerdict` — list of `RiskCheckResult` (rule_id, passed, blocking,
  observed, limit, message); `approved` iff all blocking rules pass.
- `ValidatedOrder` — constructible only via `risk.engine.validate()`; carries
  the verdict, policy version, `client_order_id` (deterministic idempotency
  key), and `valid_until`. Broker adapters type-require it and re-assert
  `verdict.approved` at the boundary.
- `Event` — append-only envelope: `event_id` (ULID), `event_type`,
  `occurred_at`/`recorded_at` (UTC), `correlation_id`, `causation_id`,
  `schema_version`, JSON payload.

## 5. Storage

SQLite (WAL) at `~/Library/Application Support/TradeOS/tradeos.db`
(override: `TRADEOS_DATA_DIR`). `events` table is append-only — UPDATE/DELETE
blocked by triggers. Derived state (paper positions, journal views, stats
caches) is rebuildable from events; replay equality is a release gate.
Migrations are numbered SQL files applied by `storage/migrations.py`.
Secrets never touch SQLite — macOS Keychain only (`security/keychain.py`).
DuckDB is a later, justified addition for analytics (ADR-0006).

## 6. Failure behavior (design, not aspiration)

| Failure | Behavior |
|---|---|
| Provider missing/unauthenticated | Doctor reports fix; cycles run without AI synthesis (deterministic-only) or skip, per config |
| Provider timeout / invalid output | One retry with error feedback → recorded `provider.error` event → cycle continues without thesis or aborts (config), never fabricates |
| Stale quote/context | Blocking risk rule `stale_data` vetoes; cycle outcome `no_action` |
| Broker read failure | Cycle aborts pre-proposal; alert raised |
| Duplicate submission | `client_order_id` dedupe in execution layer + broker adapter |
| Crash mid-cycle | Events already appended are truth; restart reconciles derived state from log |
| Kill switch | Flag checked by scheduler, cycle entry, risk engine, and execution; engages → all execution paths refuse, notification sent |

## 7. Concurrency model

Sync core, async only at the edges that need it: the Textual TUI (its own
event loop), the scheduler, and future streaming ingestion. Broker/provider
adapters expose sync methods in v0.1 (subprocess + HTTP timeouts); an async
provider session API is a v0.2 concern. No threads sharing mutable domain
state; the event store serializes writes.

## 8. Cloud (optional, later)

Local operation never requires the network beyond chosen data sources. The
Cloudflare component (ADR-0007, `cloudflare/`) is for shared ingestion and
community aggregates only, with local fallback. Nothing in v0.1 depends on it.

## 9. Observability

`telemetry/logging.py`: structured stdlib logging, redaction filter for
account ids/secrets, per-cycle correlation ids. OTel tracing is scaffolded as
a no-op interface and wired in v0.2 (spans: provider call, retrieval, rule
evaluation, broker op, notification).
