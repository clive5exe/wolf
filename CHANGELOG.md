# Changelog

All notable changes to TradeOS are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
semver with a `0.x` "everything may change" caveat.

## [Unreleased]

### Added
- Initial specifications: product, architecture, threat model, market context,
  investment policy, risk policy, provider, MCP tooling, data sources,
  evaluation, roadmap.
- ADRs 0001–0011 covering language/TUI, local-first, provider and broker
  interfaces, event sourcing, SQLite storage, Cloudflare selection,
  deterministic risk separation, paper-first execution, secrets handling, and
  model-output validation.
- Agent studio configuration (`.claude/`): orchestrator, builder, reviewer,
  test-safety, and docs agents; skills; hooks; verification scripts.
- v0.1 scaffold: domain models, append-only SQLite event store with replay,
  provider protocol + Claude Code provider, fake broker, paper broker with
  simulated fills, deterministic risk engine, target-allocation rebalance
  strategy, Typer CLI (`tradeos doctor`, `demo`, `events`), Textual TUI shell,
  macOS notifications, unit/safety test suites, CI pipeline.

### Explicitly absent (by design, see ROADMAP.md)
- Real-money execution, options, autopilot, multi-broker, community features.
