# WOLF Roadmap

Versions gate on **maturity criteria, not dates**. Nothing advances to a mode
with more autonomy until the previous mode's evidence bar is met.

## v0.1 Read-only intelligence + paper trading (current)

Everything in PRODUCT.md §7. Highlights: BYO-AI (Claude Code), policy
onboarding, deterministic risk engine, rebalance strategy, paper engine,
event sourcing + replay, TUI/CLI, doctor, macOS notifications, full test
pipeline. **No real-money execution of any kind.**

## v0.2 Human-approved execution (mode 2)

Preconditions: v0.1 read path + paper engine + risk rules + audit log +
replay tests mature (≥ 4 weeks of dogfooding paper history. Zero unexplained
replay divergences).

- Robinhood MCP write path behind approval-mode UX (per-order explicit
  confirm, showing thesis + full verdict).
- Live account allocation cap (`max_account_allocation` rule) + correlated
  exposure + volatility circuit breaker.
- Codex CLI provider. Ollama provider. Provider comparison evaluation.
- OTel tracing wired. Telegram notifier. DuckDB analytics if justified.
- Paper-vs-live slippage tracking.

## v0.3 Restricted autopilot (mode 3)

Preconditions: extensive approval-mode history, explicit safety review
(THREAT_MODEL T8 checklist), dedicated Robinhood account.

- One approved strategy, tiny fixed budget, hard loss cap, market-hours only.
- Multi-step activation ceremony, active-state indicator, kill switch drills,
  automatic shutdown conditions exercised in tests.

## v0.4+ Breadth (each item separately justified)

- Additional brokers behind `BrokerAdapter`. Desktop (Tauri/native) interface
  on the same headless core. Cloudflare shared ingestion + community
  aggregates (opt-in, k-anonymous). More strategy families. Gemini CLI +
  API-key providers. Email/SMS adapters.

## Never (product stance, not backlog)

Unbounded autonomy. Options in 0.x. Strategy marketplace before evaluation
infrastructure proves itself. Performance-claim marketing. Dark patterns
around risk acknowledgment.
