# ADR-0003: Provider protocol; Claude Code first via subprocess CLI

**Status:** accepted · 2026-08-05

## Context
"Bring your own AI" requires one stable protocol over heterogeneous clients
(Claude Code, Codex CLI, Ollama, API SDKs) with wildly different capabilities.
Claude Code's headless mode natively supports schema-constrained output
(`--json-schema` → `structured_output` envelope field) and subscription OAuth
(RESEARCH_NOTES §1). The Agent SDK exists but adds a dependency and its
credential path is equivalent for our use.

## Decision
`ModelProvider` protocol (PROVIDER_SPEC §2): `detect / capabilities /
health_check / query_structured`. Providers declare capabilities; the runtime
routes and degrades explicitly. v0.1 implements Claude Code as a subprocess
adapter around documented CLI flags only, no tools granted, max-turns capped,
timeouts enforced with kill. Model output is always schema-validated Pydantic;
one retry with validation feedback; then typed failure.

## Consequences
- Zero additional Python deps for the first provider; auth stays fully in the
  user's existing CLI login (no token handling by us).
- Subprocess spawn latency (~1-3 s) is acceptable for cycle cadence; if it
  becomes a problem, migrating the adapter internals to `claude-agent-sdk`
  is contained within one module.
- Every future provider must publish honest capabilities; no
  lowest-common-denominator faking.

## Alternatives rejected
- Agent SDK first: better streaming/sessions, but another dependency and no
  v0.1 requirement needs it.
- LiteLLM/OpenRouter abstraction: API-key-centric, contradicts
  subscription-first; may appear later as one optional adapter.
