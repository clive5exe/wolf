# Assumptions & Open Questions

**Status:** living document, v0.1 · **Basis:** product brief + specs/research/RESEARCH_NOTES.md
Per the brief: questions answerable from official docs or by a reversible
technical choice were resolved, not asked. What remains is either a genuine
product decision, a legal question, or an external unknown.

## 1. Resolved assumptions (decided, reversible, documented)

| # | Assumption | Basis / where recorded |
|---|---|---|
| A1 | Python 3.12+ / Textual TUI / Typer CLI | ADR-0001. Textual 8.2.8 verified |
| A2 | Claude Code provider via subprocess `claude -p --output-format json --json-schema` (not Agent SDK) for v0.1 | ADR-0003, PROVIDER_SPEC. Native structured output confirmed |
| A3 | Robinhood integration targets the **official Agentic Trading MCP** (`agent.robinhood.com/mcp/trading`), read-only in v0.1. All unofficial private-API wrappers excluded | RESEARCH_NOTES §2, MCP_TOOL_SPEC |
| A4 | SEC EDGAR is the v0.1 filings connector (free, official, 10 req/s + declared UA) | DATA_SOURCES, RESEARCH_NOTES §4 |
| A5 | Social sentiment in v0.1: interface + deterministic aggregation shipped. The single connector slot targets Bluesky Jetstream (public, keyless) as an **optional** connector. Low diversity of that venue is encoded in credibility/diversity floors | MARKET_CONTEXT_SPEC §7, DATA_SOURCES |
| A6 | Secrets via macOS Keychain using the `security` CLI wrapper (no keyring dep in v0.1) | ADR-0010 |
| A7 | Notifications via `osascript display notification`. Terminal-notifier optional | RESEARCH_NOTES §3 |
| A8 | SQLite (WAL, append-only events via triggers) at `~/Library/Application Support/TradeOS/`. DuckDB deferred | ADR-0005/0006 |
| A9 | Money/percentages as `Decimal`. All timestamps UTC. Market hours computed in America/New_York | domain models |
| A10 | Paper fills = quote price ± configurable slippage bps, market orders only in v0.1 | paper broker docstrings |
| A11 | v0.1 strategy = target-allocation rebalancing (deterministic). Quality-growth screening deferred | strategies/rebalance.py |
| A12 | Cloudflare backend entirely optional and deferred beyond scaffolding/design. Nothing in v0.1 requires it | ADR-0007 |
| A13 | Benchmark for beta/Sharpe deferred until a licensed benchmark series exists. Stats that need it ship "unavailable" rather than approximated | portfolio/stats.py |
| A14 | MIT license | LICENSE |

## 2. Open questions. ANSWERED 2026-08-05 (by the project owner)

| # | Question | Decision |
|---|---|---|
| Q1 | Claude plan tier (programmatic-credit budget)? | **Max.** Measured ~$0.67/structured call → budget allows scheduled AI-synthesis cycles, but cost stays recorded per event and surfaced in doctor/status. |
| Q2 | Open a Robinhood Agentic account? | **Yes.** T-024 unblocked for fixture-driven development now. Live connect happens once the owner completes Robinhood's desktop onboarding. |
| Q3 | Prompt redaction level for holdings? | **Pending** (owner requested a plainer explanation). Safe default stands: percentages only, no dollar amounts, no account identifiers in any prompt. |
| Q4 | Telegram as v0.2 comms channel? | **Yes.** Bot token in Keychain. Adapter task lands in v0.2. |
| Q5 | Public repo timing? | **After v0.1 hardening.** Additionally: no AI-authorship attribution in repo history or docs (commit trailers removed. Policy recorded below). The Claude Code *provider integration* is product functionality and stays. |

Repo policy from Q5: commits in this repository carry no AI co-authorship
trailers. References to Claude/Anthropic remain only where they are factual
product content (the provider adapter, provider docs, research citations).

## 3. Open questions. External/technical unknowns (tracked, non-blocking)

| # | Unknown | Tracking |
|---|---|---|
| U1 | Robinhood MCP transport details (streamable-HTTP vs SSE), token lifetime, tool schemas | Probe task T-018. Adapter written against MCP standard client with allowlist |
| U2 | `claude auth status` exit-code semantics | Adapter parses output defensively. Upstream docs watched |
| U3 | Official confirmation of programmatic-credit pool mechanics | Recheck before any release notes mention costs |
| U4 | Codex CLI / Gemini CLI official non-interactive docs | v0.2 research packets |
| U5 | Finnhub/other market-data fallback license terms | Only needed if Robinhood MCP path unavailable |

## 4. Requirements flagged per the brief

- **Technically unsupported (v0.1):** true real-time streaming quotes without
  the Robinhood MCP connection. Earnings-calendar blackout enforcement (no
  free reliable calendar source verified): rule ships but defaults disabled
  and honest (`limit="disabled"`).
- **Legally questionable → excluded:** unofficial Robinhood private-API access
  (`robin_stocks` et al.). Reddit content for our purposes under current Data
  API terms. Scraping any source behind auth walls or bot checks (Stooq until
  verified). Also: no earnings-transcript scraping. Transcripts only if a
  permitted source is found (none verified yet).
- **Dependent on undocumented behavior → mitigated:** none load-bearing.
  Robinhood MCP tool schemas are unpublished → adapter validates and fails
  closed (MCP_TOOL_SPEC §3). Claude auth detection has an undocumented edge →
  probe fallback (PROVIDER_SPEC §3).
