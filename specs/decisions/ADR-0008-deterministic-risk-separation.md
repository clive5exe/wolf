# ADR-0008: Deterministic risk engine with absolute veto, separated from AI

**Status:** accepted · 2026-08-05 · **Safety-critical**

## Context
LLMs synthesize well and enforce nothing. Every catastrophic scenario in the
threat model (T1, T2, T8) is cut off by one property: limits are enforced by
ordinary code that model output cannot reach.

## Decision
The risk engine (RISK_POLICY_SPEC) is a pure function over pinned policy +
observed state, injected clock, and event history. Every rule runs on every
evaluation; missing data fails closed; the full verdict is an event.
`ValidatedOrder` is issued only by the engine; broker adapters re-assert
approval at their boundary. Strategies and providers cannot register,
parameterize, or skip rules. The kill switch is checked at scheduler, cycle,
engine, and execution layers.

## Consequences
- The blast radius of any AI failure is a wasted thesis, never a breached
  limit.
- Some flexibility is deliberately lost: a strategy cannot "explain its way"
  past a rule even when arguably right — the user changes policy versions
  instead, leaving an audit trail.
- The engine's purity makes verdicts replayable and property-testable.
