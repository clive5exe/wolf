"""Event type registry. Append here. Never rename a shipped value (events are forever)."""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    # Policy lifecycle
    POLICY_CREATED = "policy.created"
    POLICY_UPDATED = "policy.updated"
    MODE_CHANGED = "mode.changed"

    # Decision cycle
    CYCLE_TRIGGERED = "cycle.triggered"
    CYCLE_ABORTED = "cycle.aborted"
    CYCLE_NO_ACTION = "cycle.no_action"
    CYCLE_COMPLETED = "cycle.completed"
    CONTEXT_ASSEMBLED = "context.assembled"
    PROPOSAL_CREATED = "proposal.created"
    THESIS_GENERATED = "thesis.generated"
    RISK_EVALUATED = "risk.evaluated"

    # Provider traffic
    PROVIDER_QUERY = "provider.query"
    PROVIDER_RESPONSE = "provider.response"
    PROVIDER_ERROR = "provider.error"

    # Execution
    ORDER_VALIDATED = "order.validated"
    ORDER_SUBMITTED = "order.submitted"
    ORDER_FILLED = "order.filled"
    ORDER_REJECTED = "order.rejected"
    ORDER_DUPLICATE = "order.duplicate"

    # Paper engine
    PAPER_INITIALIZED = "paper.initialized"

    # Ingestion
    INGEST_RAW = "ingest.raw"
    INGEST_ERROR = "ingest.error"

    # Safety & ops
    KILLSWITCH_ENGAGED = "killswitch.engaged"
    KILLSWITCH_DISENGAGED = "killswitch.disengaged"
    NOTIFICATION_SENT = "notification.sent"
    EVALUATION_RECORDED = "evaluation.recorded"
    PORTFOLIO_SNAPSHOT = "portfolio.snapshot"
