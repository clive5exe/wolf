# Changelog

All notable changes to WOLF are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow
semver with a `0.x` "everything may change" caveat.

## [Unreleased]

### Changed
- **The product is now WOLF**: *wealth orchestration, local-first* (ADR-0012).
  The command is `wolf`. `tradeos` remains as an alias, and the Python import
  package is unchanged (the PyPI name `wolf` is already taken).

### Added: terminal interface (T-031, T-032, T-033)
- Six screens replacing the plain dashboard: boot check cascade, den
  (dashboard), live decision cycle, verdict, journal, and kill-switch takeover.
- A visual system in `tui/`: palette tokens with enforced colour discipline
  (amber = brand, green/red = money only, cyan = data), motion constants
  expressing one timing vocabulary, and pure glyph renderers. Drift gauge,
  sparkline, freshness dots. Unit-tested without a terminal.
- Drift is rendered spatially and scaled to the strategy's rebalance threshold,
  so reaching the end of the gauge means "at the point of action". Off-scale
  drift is marked, never silently clamped.
- `wolf tui --calm` disables all animation. Every screen still renders complete
  content, because motion is always redundant with a glyph or a number.

### Added: runtime
- `runtime/journal.py`: a pure reducer turning the event log into decision
  records. No-actions and vetoes are first-class records, not absences.
- `runtime/views.py`: read models so every displayed number is computed and
  tested in the runtime rather than in a widget.
- `runtime/progress.py`: a display-only cycle observer. It cannot alter, delay,
  or abort a decision, and its updates are deliberately not recorded as events.
  The log remains the single audit source.
- `runtime/diagnostics.py`: doctor checks moved out of the CLI so the TUI boot
  sequence can reach them through the facade. Startup now doubles as diagnosis.
- Facade queries: `dashboard()`, `journal()`, `cycle_detail()`, `kill_state()`,
  `diagnostics()`, `equity_points()`, `risk_rule_ids()`.
- `thesis.generated` events now carry the bull/bear/why-now/what-changed text,
  so a recorded thesis can be read back in full.

### Fixed
- Cash was displayed as drift against `min_cash_pct`. That is a floor, not a
  target, so healthy compliance rendered as an 8.7% deviation. It now shows the
  floor and whether the floor is met.
- Slippage is reported as a cost on both sides of a trade. Signed, a sell's
  slippage rendered green. As though execution had made money.

### Added
- Initial specifications: product, architecture, threat model, market context,
  investment policy, risk policy, provider, MCP tooling, data sources,
  evaluation, roadmap.
- ADRs 0001, 0011 covering language/TUI, local-first, provider and broker
  interfaces, event sourcing, SQLite storage, Cloudflare selection,
  deterministic risk separation, paper-first execution, secrets handling, and
  model-output validation.
- Agent studio configuration (`.claude/`): orchestrator, builder, reviewer,
  test-safety, and docs agents. Skills. Hooks. Verification scripts.
- v0.1 scaffold: domain models, append-only SQLite event store with replay,
  provider protocol + Claude Code provider, fake broker, paper broker with
  simulated fills, deterministic risk engine, target-allocation rebalance
  strategy, Typer CLI (`tradeos doctor`, `demo`, `events`), Textual TUI shell,
  macOS notifications, unit/safety test suites, CI pipeline.

### Explicitly absent (by design, see ROADMAP.md)
- Real-money execution, options, autopilot, multi-broker, community features.
