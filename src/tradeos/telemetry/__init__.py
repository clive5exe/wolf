"""Observability: structured logging with redaction. OTel arrives in v0.2."""

from tradeos.telemetry.logging import get_logger, redact

__all__ = ["get_logger", "redact"]
