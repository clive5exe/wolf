---
name: risk-boundary-review
description: Adversarial review procedure for any diff touching risk, execution, brokers, security, or providers — enumerate bypass paths and verify fail-closed behavior.
---

# Risk-boundary review (run on every S1/S2 diff)

Answer each with file:line evidence; any "no" is BLOCKING:

1. **Order path integrity.** Enumerate every call path from the diff to any
   broker `submit_order`. Does each pass through `RiskEngine.validate()`
   returning an approved `ValidatedOrder`? Is `client_order_id` derived
   deterministically (no randomness)?
2. **Constructor containment.** `grep -rn "ValidatedOrder(" src/ | grep -v
   "src/tradeos/risk/"` — empty? (tests exempt).
3. **Fail-closed audit.** For each new data dependency in a rule/adapter:
   what happens when it's None/stale/malformed? Show the test proving veto
   or abort — "it won't happen" is not an answer.
4. **Clock discipline.** Any `datetime.now(`/`time.time(` outside
   `runtime/clock.py` and interfaces? (grep; injected `ctx.now` is the rule).
5. **LLM taint.** Does any model-produced value reach: rule parameters,
   sizing arithmetic, mode/kill-switch state, or adapter arguments? Thesis
   fields may inform *which* deterministic candidate is chosen, never *how
   much* or *whether limits apply*.
6. **Secret hygiene.** New subprocess/env/log surfaces: run
   `./scripts/safety_check.sh`; confirm redaction covers new event payloads.
7. **Idempotency.** Replay the new path twice in a test — second run must be
   a no-op (dedupe) not a double effect.
8. **Kill switch.** Does the new path check it (directly or via a layer that
   does)? Show the test.

Output the numbered answers + verdict. S2 diffs end with
"HUMAN REVIEW REQUIRED — S2" no matter the verdict.
