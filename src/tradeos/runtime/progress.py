"""Cycle progress notifications for live interfaces.

Strictly an observer: the decision cycle *tells* a listener what stage it
reached, and nothing a listener does can change what the cycle decides.
``emit`` swallows every listener exception for that reason — a TUI bug must
never alter, delay past its own frame, or abort a decision. Progress is
therefore display-only and is deliberately **not** recorded as events; the
event log remains the single audit source (ARCHITECTURE §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class CycleStage(StrEnum):
    OBSERVE = "observe"
    RETRIEVE = "retrieve"
    PROPOSE = "propose"
    THESIS = "thesis"
    RISK = "risk"
    EXECUTE = "execute"


#: Render order for the pipeline tracker; the model occupies exactly one box.
STAGE_ORDER: tuple[CycleStage, ...] = (
    CycleStage.OBSERVE,
    CycleStage.RETRIEVE,
    CycleStage.PROPOSE,
    CycleStage.THESIS,
    CycleStage.RISK,
    CycleStage.EXECUTE,
)


class StageState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"  # e.g. THESIS on a deterministic (no-provider) cycle
    FAILED = "failed"


@dataclass(frozen=True)
class ProgressUpdate:
    correlation_id: str
    stage: CycleStage
    state: StageState
    detail: str
    at: datetime


class CycleProgress(Protocol):
    """Anything that wants to watch a cycle run."""

    def __call__(self, update: ProgressUpdate) -> None: ...


def emit(
    listener: CycleProgress | None,
    *,
    correlation_id: str,
    stage: CycleStage,
    state: StageState,
    detail: str,
    at: datetime,
) -> None:
    """Notify a listener, absorbing any failure it raises."""
    if listener is None:
        return
    try:
        listener(
            ProgressUpdate(
                correlation_id=correlation_id,
                stage=stage,
                state=state,
                detail=detail,
                at=at,
            )
        )
    except Exception:  # an observer must never break a decision
        return
