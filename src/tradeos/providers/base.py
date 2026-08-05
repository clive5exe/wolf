"""The provider protocol: every AI backend implements this and nothing more.

Providers are stateless synthesizers in v0.1: schema in, validated model out.
They hold no execution authority and are never handed tools (PROVIDER_SPEC §1).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ConfigDict

T = TypeVar("T", bound=BaseModel)


class ProviderCapability(StrEnum):
    STRUCTURED_OUTPUT = "structured_output"
    STREAMING = "streaming"
    SESSIONS = "sessions"
    TOOL_USE = "tool_use"  # declared, never granted in v0.1


class ProviderErrorKind(StrEnum):
    NOT_INSTALLED = "not_installed"
    NOT_AUTHENTICATED = "not_authenticated"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    RATE_LIMITED = "rate_limited"
    CRASHED = "crashed"


class ProviderStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    installed: bool
    version: str | None = None
    authenticated: bool | None = None  # None = cannot determine without a probe
    detail: str = ""

    @property
    def ready(self) -> bool:
        return self.installed and self.authenticated is not False


class ProviderResult[T: BaseModel](BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    ok: bool
    value: T | None = None
    error: ProviderErrorKind | None = None
    error_detail: str = ""
    raw_excerpt: str | None = None  # redacted, truncated diagnostics
    duration_ms: int = 0
    cost_usd: Decimal | None = None
    session_id: str | None = None


@runtime_checkable
class ModelProvider(Protocol):
    name: str

    def detect(self) -> ProviderStatus: ...

    def capabilities(self) -> frozenset[ProviderCapability]: ...

    def query_structured(
        self,
        *,
        prompt: str,
        schema: type[T],
        timeout_s: int = 120,
        max_turns: int = 1,
        model: str | None = None,
    ) -> ProviderResult[T]: ...
