# ADR-0004: BrokerAdapter interface; fake and paper brokers are first-class

**Status:** accepted · 2026-08-05

## Context
Broker access must be pluggable (Robinhood today, others later), testable
without network, and safe by type design. The official Robinhood Agentic
Trading MCP (RESEARCH_NOTES §2) is the real integration; deterministic tests
and paper trading must not depend on it.

## Decision
`BrokerAdapter` protocol in `brokers/base.py`: read methods (`get_account`,
`get_positions`, `get_quote`, `get_orders`) + `submit_order(order:
ValidatedOrder) -> OrderResult` + `capabilities()` (READ / PAPER / TRADE).
Three v0.1 implementations: `FakeBroker` (scripted, deterministic, for
tests), `PaperBroker` (simulation engine with slippage model, persistent via
events), `RobinhoodMCPBroker` (read-only; `submit_order` raises in v0.1).
Provider logic and broker logic never mix; only `execution/` calls
`submit_order`.

## Consequences
- The whole pipeline is testable offline; contract tests run against all
  adapters uniformly.
- Paper and live share the exact same order path up to the adapter boundary,
  so v0.2 approval-mode is an adapter swap plus UX, not a rewrite.
- MCP payload-schema drift is contained in one adapter that fails closed.
