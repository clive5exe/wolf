# Evaluation & Replay Specification

**Status:** v0.1 · **Implements:** `src/tradeos/{evaluation,replay}/`, `tests/replay/`

## 1. Purpose

TradeOS must measure its own decision quality with metrics that are
**independent of raw P&L** (a bad process can get lucky; a good process can
lose a quarter). Evaluation never mutates behavior automatically: it produces
data for humans. The system must never "learn" by silently changing risk
rules — rule changes are policy-version changes made by the user.

## 2. Replay engine

- Input: an event log segment (paper or live-read history) + pinned code
  version.
- Guarantee: replaying events through the derived-state reducers reproduces
  byte-identical derived state (positions, P&L, journal). Verified by hashing
  canonical JSON of derived state; a release gate in `tests/replay/`.
- Decision replay (v0.1): re-run the deterministic half of a recorded cycle
  (strategy + sizing + risk) from the recorded `MarketContextPackage` and
  assert identical proposals and verdicts. Provider calls are NOT re-executed;
  the recorded `StructuredThesis` is replayed as a fixture.
- Historical market replay (v0.2): synthetic clock + recorded quotes to
  exercise strategies over past windows.

## 3. Golden scenarios (`tests/replay/golden/`)

Versioned fixture bundles: `{world state, context package, policy} → expected
{proposal, verdict}`. v0.1 ships at least:
1. drift-above-threshold → rebalance proposal approved (paper)
2. drift present but stale quotes → `no_action`, `stale_quote` veto recorded
3. proposal breaching `max_position_pct` → veto
4. kill switch engaged → veto
5. within-threshold drift → first-class `no_action`
6. oversell attempt → `sufficient_holdings` veto

Golden files change only via explicit human-reviewed diffs.

## 4. Decision-quality metrics

Recorded per decision (event `evaluation.recorded`) and aggregated:

| Metric | Definition | Source |
|---|---|---|
| policy_compliance | 1 − (blocking vetoes that *reached* risk from a strategy ÷ proposals) — strategies should learn limits, engine catches them regardless | verdict events |
| context_freshness | mean freshness ratio (age/ttl) of cited items at decision time | packages |
| citation_quality | cited item ids that exist ÷ claimed; plus fraction of thesis claims with ≥1 citation | thesis validation |
| unsupported_claim_rate | thesis validation failures + reviewer-flagged uncited claims ÷ theses | provider events |
| proposal_fill_gap | |proposed price − simulated/actual fill| in bps | execution events |
| slippage_model_error | paper-assumed vs later-observed slippage (v0.2 live compare) | fills |
| decision_latency | trigger → verdict wall time | event timestamps |
| provider_latency / cost | per query; cost where reported by CLI envelope | provider events |
| turnover / concentration / drawdown / vol | standard portfolio stats (formulas in `portfolio/stats.py` docstrings) | snapshots |
| thesis_outcome_alignment | at +7d/+30d: did invalidation conditions trigger? was directional claim consistent with outcome? graded by the Journal agent, stored as data | journal |

Every metric implementation carries a docstring stating formula, window,
assumptions, and limitations; EVALUATION docs must not present any metric as
performance advice.

## 5. Strategy lifecycle (promotion gates)

`research → simulation → regression → paper → approval-mode → restricted-autopilot`

| Gate | Requirement to advance |
|---|---|
| simulation | golden scenarios written; deterministic outputs stable across 3 runs |
| regression | added to strategy regression suite; no golden diffs |
| paper | ≥ 4 weeks paper history, ≥ 20 decisions, zero blocking-rule breaches *originated by the strategy*, drawdown within policy |
| approval-mode (v0.2) | human review of paper journal; explicit user opt-in per strategy |
| autopilot (v0.3) | extensive paper + approval history, safety review checklist, dedicated account |

Demotion is automatic on: any strategy-originated limit breach, golden
regression failure, or evaluation metrics collapsing below thresholds.
Promotion/demotion are events + notifications.

## 6. Model/provider comparison (v0.2 design)

Same context package + prompt → N providers → compare structured theses on
citation quality, calibration (confidence vs outcome), and latency/cost. No
consensus trading in 0.x; comparison is evaluation data only.

## 7. Acceptance criteria (v0.1)

1. Replay hash-equality test passes on a captured paper session.
2. Six golden scenarios implemented and green.
3. `evaluation.recorded` events written for every completed cycle with at
   least: compliance, freshness, citation, latency fields.
4. Journal view renders per-decision: thesis vs verdict vs outcome-so-far.
