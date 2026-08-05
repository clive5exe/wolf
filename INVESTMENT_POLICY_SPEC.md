# Investment Policy Specification

**Status:** v0.1 · **Implements:** `src/tradeos/domain/policy.py` · **Related:** [RISK_POLICY_SPEC.md](RISK_POLICY_SPEC.md)

## 1. Concept

The **Investment Policy Profile** is the single deterministic source of truth
for what the system is allowed to want. Natural language goes in during
onboarding; an LLM may *draft* the structured policy; the user confirms it
field by field; only the confirmed struct is enforced. Models can never read a
policy field permissively, relax it, or invent one. The policy is versioned:
every change produces a new immutable version and a `policy.updated` event.

Flow: `goals_text --(provider draft)--> DraftPolicy --(human edit+confirm)-->
InvestmentPolicy vN (active)`. If no provider is available, onboarding falls
back to a plain form. The draft step is sugar, not architecture.

## 2. Schema (`InvestmentPolicy`, Pydantic)

All percentages are fractions in `[0, 1]` stored as `Decimal`. All money is
`Decimal` USD. All timestamps UTC. Fields marked ⚡ are read by the risk
engine as hard limits.

```python
class TradingMode(StrEnum):
    READ_ONLY = "read_only"            # mode 0
    PAPER = "paper"                    # mode 1
    APPROVAL = "approval"              # mode 2 (v0.2)
    RESTRICTED_AUTOPILOT = "autopilot" # mode 3 (v0.3)

class RiskTolerance(StrEnum):
    CONSERVATIVE = "conservative"; MODERATE = "moderate"; AGGRESSIVE = "aggressive"
    # informational label; numeric limits below are what is enforced

class AssetType(StrEnum):
    EQUITY = "equity"; ETF = "etf"     # v0.1 universe; options NEVER in 0.x

class TargetAllocation(BaseModel):
    symbol: str                        # uppercase ticker
    weight: Decimal                    # 0..1; sum of weights + cash target <= 1

class AutopilotEnvelope(BaseModel):    # v0.3; must be None before then
    enabled: bool = False
    dedicated_account_id: str
    budget_usd: Decimal                # fixed capital allocation, hard cap
    max_total_loss_usd: Decimal        # breach => automatic shutdown
    allowed_strategy_ids: list[str]
    allowed_symbols: list[str]
    allowed_hours: TradingHours
    activation_confirmed_at: datetime | None   # multi-step activation record

class InvestmentPolicy(BaseModel):
    policy_id: str                     # ULID, stable across versions
    version: int                       # monotonically increasing
    created_at: datetime
    status: Literal["draft", "active", "superseded"]
    goals_text: str                    # user's own words, informational
    risk_tolerance: RiskTolerance
    time_horizon_years: int            # >= 1
    mode: TradingMode                  # ⚡ gates every execution path
    permitted_asset_types: set[AssetType]              # ⚡
    fractional_shares_allowed: bool
    preferred_sectors: list[str]       # advisory (strategy input)
    excluded_sectors: list[str]        # ⚡ hard deny
    symbol_allowlist: list[str] | None # ⚡ if set, ONLY these symbols
    symbol_denylist: list[str]         # ⚡ always deny
    target_allocations: list[TargetAllocation]         # strategy input
    target_cash_weight: Decimal        # strategy input
    max_position_pct: Decimal          # ⚡ per-symbol share of portfolio value
    max_sector_pct: Decimal            # ⚡
    min_cash_pct: Decimal              # ⚡ cash floor after any buy
    max_order_value_usd: Decimal       # ⚡ per order
    max_orders_per_day: int            # ⚡ trading frequency cap
    max_daily_loss_pct: Decimal        # ⚡ realized+unrealized vs day start
    max_drawdown_pct: Decimal          # ⚡ vs high-water mark; breach halts
    cooldown_minutes_per_symbol: int   # ⚡ min gap between orders in a symbol
    trading_hours: Literal["regular"]  # ⚡ v0.1: regular session only (ET)
    earnings_blackout_days: int        # ⚡ 0 disables; needs earnings calendar
    stale_quote_max_age_s: int         # ⚡ quotes older than this veto action
    stale_context_max_age_factor: Decimal  # ⚡ multiplier on per-item TTLs
    account_is_taxable: bool | None    # informational in 0.x; no tax advice
    autopilot: AutopilotEnvelope | None = None  # ⚡ must be None in v0.1/0.2
```

### Validation invariants (Pydantic validators, tested)

- `sum(target weights) + target_cash_weight <= 1`.
- `min_cash_pct <= target_cash_weight` warning (not error).
- `max_position_pct >= max(target weights)` — a target may not exceed the cap.
- allowlist and denylist disjoint; symbols uppercase, `^[A-Z][A-Z0-9.\-]{0,9}$`.
- `mode` transitions only via `PolicyService.change_mode()` which enforces the
  ladder (no skipping to autopilot) and emits events.
- `autopilot` non-None ⇒ `ValidationError` while the feature flag
  `TRADEOS_ENABLE_AUTOPILOT` build constant is False (it is False in all 0.1/0.2
  releases; flipping it requires the v0.3 safety review checklist).

## 3. Onboarding contract

The provider draft step uses `PolicyDraft` — same fields, all optional, plus
`interpretation_notes: list[str]` where the model must state every assumption
it made ("interpreted 'no single position above 5%' as max_position_pct=0.05").
The TUI renders each populated field with its provenance (`user_stated` /
`model_inferred` / `default`) and requires explicit confirmation of every
⚡ field before the policy can become `active`. Unconfirmed drafts cannot be
referenced by a decision cycle.

## 4. Defaults (used when the user accepts "sensible defaults")

| Field | Default | Rationale |
|---|---|---|
| mode | `read_only` | safety ladder start |
| max_position_pct | 0.10 | broad-market norm for retail concentration |
| max_sector_pct | 0.30 | |
| min_cash_pct | 0.02 | |
| max_order_value_usd | 1000 | small until trust is earned |
| max_orders_per_day | 5 | |
| max_daily_loss_pct | 0.02 | |
| max_drawdown_pct | 0.15 | |
| cooldown_minutes_per_symbol | 240 | |
| stale_quote_max_age_s | 120 (paper) / 15 (live, v0.2+) | |
| earnings_blackout_days | 0 (off — no calendar source in v0.1) | honest default |

## 5. Failure cases

- **No active policy** → decision cycles refuse to run; TUI shows onboarding.
- **Draft translation fails validation** → user sees raw errors + form; the
  model is never asked to "fix" limits silently.
- **Policy edited mid-cycle** → cycles pin the policy version at trigger time;
  the risk engine re-checks the *pinned* version and additionally aborts if
  the active version changed since trigger (`policy_changed` veto).

## 6. Acceptance criteria

1. Round-trip: NL example from PRODUCT.md J2 → draft → confirm → stored active
   v1 → event emitted; reload from store is field-identical.
2. All validators above have unit tests (pass + reject cases).
3. A `PolicyDraft` containing `autopilot.enabled=true` is rejected at
   validation with an explicit message, and a safety test asserts no code path
   can activate autopilot in v0.1.
4. Mode change emits `mode.changed` event + notification; ladder enforced.
