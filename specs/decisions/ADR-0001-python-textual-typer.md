# ADR-0001: Python 3.12+, Textual TUI, Typer CLI

**Status:** accepted · 2026-08-05

## Context
v0.1 needs a polished macOS terminal interface fast, a scriptable CLI, and a
headless core reusable by a future desktop app. The team's agent tooling
(Claude Code) and the financial/typing ecosystem (Pydantic, Decimal, pytest)
are strongest in Python. Textual 8.2.8 (MIT, actively released 2026-06) offers
CSS-styled widgets, DataTable, async workers, and headless Pilot testing.
Verified against current docs (RESEARCH_NOTES §3).

## Decision
Python ≥3.12 (dev on 3.14). Textual for the TUI, Typer for the CLI, both as
thin adapters over `runtime/` facade. Rich comes with Textual for CLI output.
Strict typing: Pydantic v2 at boundaries, mypy in CI, Ruff for lint/format.
Async only where an event loop already exists (TUI, future streaming).

## Consequences
- Fast iteration, testable UI (Pilot), zero GUI toolchain for v0.1.
- Python performance is ample: workloads are I/O + small-N portfolio math.
- A future Tauri/native app talks to the same core (ADR-0002 boundary makes
  this real, not aspirational).

## Alternatives rejected
- Swift/SwiftUI native first: slower to iterate, locks out the CLI/agent
  audience, harder for OSS contribution.
- Go + Bubbletea: fine TUI story, but loses Pydantic/typing synergy with
  LLM structured outputs and the strategy/quant ecosystem.
- Electron/web: contradicts local-first terminal-first identity.
