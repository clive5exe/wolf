# Risk Policy Specification — the Deterministic Veto Layer

**Status:** v0.1 · **Implements:** `src/tradeos/risk/` · **Safety class:** CRITICAL (human review + safety tests required for any change)

## 1. Position in the system

The risk engine sits between *proposal* and *anything that can move money or
even simulate moving money*. It is ordinary, fully unit-tested Python. It has
**absolute veto authority**: no agent output, provider response, configuration
of a strategy, or interface action can relax, reorder, skip, or override a
blocking rule. The only inputs it trusts are: the pinned `InvestmentPolicy`
version, broker/portfolio state, quotes with timestamps, the market clock, the
event log (for cooldowns/dedupe/daily loss), and the kill-switch flag.

Design rule: **the engine is a pure function** `validate(proposal, ctx) ->
RiskVerdict | ValidatedOrder`. No network, no LLM, no clock reads inside rules
(the clock is injected via `ctx.now`), so every verdict is replayable.

## 2. Contracts

```python
class RiskCheckResult(BaseModel):
    rule_id: str            # stable identifier, e.g. "max_position_pct"
    passed: bool
    blocking: bool          # False = advisory finding, recorded but not veto
    observed: str           # human-readable observed value ("13.1%")
    limit: str              # the limit applied ("10.0%")
    message: str

class RiskVerdict(BaseModel):
    verdict_id: str         # ULID
    proposal_id: str
    policy_version: int
    evaluated_at: datetime  # = ctx.now, injected
    results: list[RiskCheckResult]   # EVERY configured rule appears, always
    approved: bool          # all(r.passed for r in results if r.blocking)

class ValidatedOrder(BaseModel):
    order_id: str           # ULID
    proposal_id: str
    action: ProposedAction  # side, symbol, quantity, order_type, limit_price
    verdict: RiskVerdict    # must be approved=True (validator re-asserts)
    policy_version: int
    client_order_id: str    # sha256(proposal_id|action_index|symbol|side) — idempotency
    valid_until: datetime   # short TTL; expired orders are dead
```

`ValidatedOrder` is issued **only** by `RiskEngine.validate()`. A model
validator rejects construction with a non-approved verdict; broker adapters
re-assert `verdict.approved and now < valid_until` at their boundary; the
safety suite proves both. (Python cannot make construction physically
impossible — defense is layered: type signature, validator, boundary
re-check, mechanical scan forbidding `ValidatedOrder(` outside `risk/`,
and tests.)

## 3. Evaluation semantics

- Every configured rule runs on every evaluation — no short-circuiting — so
  the audit trail always shows the complete picture.
- Rules are side-effect-free; the engine appends one `risk.evaluated` event
  containing the full verdict.
- Unknown/missing data required by a rule ⇒ that rule **fails closed**
  (`passed=False`, message states what was missing).
- Rule set and limits derive ONLY from the pinned policy version + static
  engine config. Strategies cannot register, disable, or parameterize rules.

## 4. v0.1 rule set

| rule_id | Blocking | Checks | Veto condition |
|---|---|---|---|
| `kill_switch` | ✅ | global kill-switch flag | engaged |
| `mode_permits_orders` | ✅ | policy.mode | mode is `read_only`, or paper order outside paper engine |
| `asset_type_permitted` | ✅ | instrument type ∈ policy.permitted_asset_types | not permitted |
| `symbol_allowed` | ✅ | denylist, allowlist (if set), excluded sectors | denied / not in allowlist / excluded sector |
| `max_order_value` | ✅ | est. notional = qty × quote | > policy.max_order_value_usd |
| `max_position_pct` | ✅ | post-trade position value ÷ post-trade portfolio value | > policy.max_position_pct |
| `max_sector_pct` | ✅ | post-trade sector exposure (needs sector map; missing sector ⇒ fail closed for buys) | > policy.max_sector_pct |
| `min_cash` | ✅ | post-trade cash ÷ portfolio value (buys) | < policy.min_cash_pct |
| `sufficient_holdings` | ✅ | sells: qty ≤ held qty (no shorting in 0.x) | oversell |
| `max_orders_per_day` | ✅ | count of today's submitted orders from event log | ≥ policy.max_orders_per_day |
| `symbol_cooldown` | ✅ | minutes since last order in symbol (event log) | < policy.cooldown_minutes_per_symbol |
| `max_daily_loss` | ✅ | (day-start equity − current equity) ÷ day-start equity | > policy.max_daily_loss_pct |
| `max_drawdown` | ✅ | (HWM − equity) ÷ HWM | > policy.max_drawdown_pct |
| `trading_hours` | ✅ | market clock, regular session (ET) | outside session (paper mode may be configured to simulate-anytime; live never) |
| `stale_quote` | ✅ | quote.as_of vs ctx.now | age > policy.stale_quote_max_age_s |
| `stale_context` | ✅ | context package freshness summary | any REQUIRED item expired (× policy factor) |
| `duplicate_order` | ✅ | client_order_id vs event log | already submitted/filled |
| `policy_changed` | ✅ | active policy version vs pinned | changed since trigger |
| `fractional_permitted` | ✅ | non-integer qty | fractional qty while not allowed |
| `earnings_blackout` | ✅* | earnings calendar | inside blackout window (*inactive when `earnings_blackout_days=0`; still reported as `passed=True, limit="disabled"`) |
| `concentration_advisory` | ❌ | top-3 holdings weight | advisory only: > 50% flagged |

v0.2 additions (specced, not built): correlated-exposure limit, volatility
circuit breaker (halt on abnormal realized vol), max account allocation for
live account, per-strategy budget.

## 5. Kill switch

A single flag in storage + in-memory mirror. Engaged by: user (TUI/CLI
`tradeos kill`), automatic triggers (rule breach in autopilot, stale-data
storm, provider failure loop, inconsistent portfolio reconciliation), or any
uncaught exception in the execution layer. Effects: scheduler pauses, risk
engine vetoes all (`kill_switch` rule), execution layer refuses submission,
notification sent, `killswitch.engaged` event appended. Disengaging is manual
only and emits its own event + notification.

## 6. Failure cases (tested)

- Quote missing → `max_order_value`/`max_position_pct`/`stale_quote` fail closed.
- Sector unknown for a buy → `max_sector_pct` fails closed.
- Event log unreadable → engine raises; execution impossible (fail closed).
- Two rapid identical proposals → second vetoed by `duplicate_order`.
- Policy version bumped between trigger and validation → `policy_changed` veto.
- Clock skew: `ctx.now` is injected by the runtime from a single source.

## 7. Acceptance criteria

1. Each blocking rule has ≥ 2 unit tests (pass, veto) with exact `Decimal`
   arithmetic — no float comparisons.
2. Property: for any proposal, `approved == all(blocking results passed)`.
3. Safety tests: (a) fake broker rejects raw dict / `TradeProposal` /
   unapproved `ValidatedOrder`; (b) constructing `ValidatedOrder` with a
   failed verdict raises; (c) kill switch vetoes everything; (d) grep gate:
   `ValidatedOrder(` constructor appears only under `src/tradeos/risk/` and
   tests.
4. Verdicts serialize into events and replay to identical `approved` values.
