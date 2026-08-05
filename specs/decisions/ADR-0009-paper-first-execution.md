# ADR-0009: Paper-first execution ladder

**Status:** accepted · 2026-08-05

## Context
Trust in an autonomous financial system is earned with evidence, not
disclaimers. The brief's mode ladder (read-only → paper → approval →
restricted autopilot) needs teeth: code structure, not configuration vibes.

## Decision
v0.1 ships modes 0, 1 only. The paper engine exercises the *identical*
proposal → risk → ValidatedOrder → adapter path as live will, with simulated
fills (quote ± slippage bps) and full event trails, so evidence accumulates
against the real pipeline. Mode transitions are policy-version changes with
events + notifications. Live execution code paths do not exist in v0.1
binaries (`RobinhoodMCPBroker.submit_order` raises. Trade tools never
allowlisted). V0.2 adds them behind per-order human approval. V0.3 adds the
bounded autopilot envelope only inside Robinhood's dedicated Agentic account.
Promotion between modes gates on EVALUATION_SPEC §5 evidence.

## Consequences
- Paper metrics (incl. slippage assumptions) become directly comparable to
  live fills in v0.2. The paper engine is calibration, not a toy.
- Users cannot skip the ladder even intentionally in v0.1. That friction is a
  feature and is documented.
