"""Risk verdicts and the ValidatedOrder. The only object with execution authority.

Spec: RISK_POLICY_SPEC.md §2. Containment is layered (ADR-0008):
1. This module's validators reject inconsistent/unapproved construction.
2. Only ``tradeos.risk.engine`` constructs ValidatedOrder (mechanically
   enforced by scripts/safety_check.sh and tests/safety/).
3. Broker adapters re-assert approval at their boundary.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from tradeos.domain.orders import ProposedAction


class RiskCheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    passed: bool
    blocking: bool
    observed: str
    limit: str
    message: str


class RiskVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict_id: str
    proposal_id: str
    action_index: int
    policy_version: int
    evaluated_at: datetime
    results: tuple[RiskCheckResult, ...]
    approved: bool

    @model_validator(mode="after")
    def _approved_consistent(self) -> RiskVerdict:
        derived = all(r.passed for r in self.results if r.blocking)
        if self.approved != derived:
            raise ValueError(
                "verdict.approved is inconsistent with its rule results, "
                "verdicts cannot be hand-assembled"
            )
        if self.approved and not self.results:
            raise ValueError("an approval requires recorded rule results")
        return self


def client_order_id_for(proposal_id: str, action_index: int, action: ProposedAction) -> str:
    """Deterministic idempotency key: same proposal+action always maps to the
    same id, so retries and replays dedupe instead of double-executing."""
    raw = f"{proposal_id}|{action_index}|{action.symbol}|{action.side}|{action.quantity}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class ValidatedOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    proposal_id: str
    action: ProposedAction
    verdict: RiskVerdict
    policy_version: int
    client_order_id: str
    valid_until: datetime

    @model_validator(mode="after")
    def _must_be_approved(self) -> ValidatedOrder:
        if not self.verdict.approved:
            raise ValueError("a ValidatedOrder cannot exist for an unapproved verdict")
        failed_blocking = [r.rule_id for r in self.verdict.results if r.blocking and not r.passed]
        if failed_blocking:
            raise ValueError(f"blocking rules failed: {failed_blocking}")
        if self.policy_version != self.verdict.policy_version:
            raise ValueError("order/verdict policy version mismatch")
        expected = client_order_id_for(self.proposal_id, self.verdict.action_index, self.action)
        if self.client_order_id != expected:
            raise ValueError("client_order_id does not match its deterministic derivation")
        return self

    def is_valid_at(self, now: datetime) -> bool:
        return now < self.valid_until
