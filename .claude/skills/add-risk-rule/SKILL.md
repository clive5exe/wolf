---
name: add-risk-rule
description: Add or modify a deterministic risk rule. Safety-critical (S2) procedure — enforces spec-first flow, fail-closed semantics, and mandatory pass/veto tests.
---

# Adding a risk rule (S2 — human review mandatory)

1. **Spec first.** Add the rule row to RISK_POLICY_SPEC.md §4 (rule_id,
   blocking, checks, veto condition). If it needs a new policy field, update
   INVESTMENT_POLICY_SPEC.md §2 with the ⚡ marker and a default in §4.
2. **Implement** in `src/tradeos/risk/rules.py`:
   - Subclass pattern: implement `check(action, ctx) -> RiskCheckResult`.
   - Pure function of `(action, ctx)` only. No I/O, no `datetime.now()` —
     use `ctx.now`. No imports from providers/brokers/strategies.
   - **Fail closed:** any missing/None input the rule needs ⇒
     `passed=False` with a message naming the missing datum.
   - `observed` and `limit` are human-readable strings with units.
3. **Register** in `DEFAULT_RULES` (order irrelevant — all rules always run).
4. **Tests** in `tests/unit/test_risk_rules.py` — minimum four:
   pass case, veto case, missing-data fail-closed case, boundary-exact case
   (limit == observed uses `<=`/`>=` per spec; test the equality).
   Use exact `Decimal` literals, never floats.
5. **Safety suite:** extend `tests/safety/test_no_bypass.py` if the rule
   guards a new resource class.
6. Run `./scripts/verify.sh && ./scripts/safety_check.sh`.
7. PR must carry: spec diff + code + tests + "HUMAN REVIEW REQUIRED — S2".

Never: make a blocking rule advisory, add config that disables a rule outside
policy versioning, or let a rule read anything an LLM produced.
