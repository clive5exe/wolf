"""The event envelope. Payloads are JSON-safe dicts (Decimals as strings,
datetimes as ISO-8601) produced via ``model_dump(mode="json")``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from tradeos.events.types import EventType


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str  # ULID — lexicographic order == creation order
    event_type: EventType
    occurred_at: datetime
    recorded_at: datetime
    schema_version: int = 1
    correlation_id: str | None = None  # decision-cycle id
    causation_id: str | None = None  # event that caused this one
    payload: dict[str, Any]
