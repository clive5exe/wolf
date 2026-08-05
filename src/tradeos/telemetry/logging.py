"""Structured logging with mandatory redaction (THREAT_MODEL T3, ARCHITECTURE §9).

Ordinary logs must never contain: credentials, account identifiers, or
secret-shaped strings. The redaction filter is attached to every tradeos
logger; ``redact()`` is also called directly on strings destined for event
payload excerpts.
"""

from __future__ import annotations

import logging
import re

_PATTERNS = [
    re.compile(r"(AKIA[0-9A-Z]{16})"),
    re.compile(r"(rh-api-[A-Za-z0-9-]{4,})"),
    re.compile(r"(sk-[A-Za-z0-9]{16,})"),
    re.compile(r"(xox[baprs]-[0-9A-Za-z-]{8,})"),
    re.compile(r"(-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----)"),
    re.compile(
        r"((?:api[_-]?key|token|secret|password)[\"']?\s*[:=]\s*[\"'])([^\"']{6,})([\"'])", re.I
    ),
    # brokerage account-number shapes (8+ consecutive digits in account context)
    re.compile(r"((?:account|acct)[^0-9]{0,12})(\d{8,})", re.I),
]


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(r"\1[REDACTED]\3", text)
        elif pattern.groups == 2:
            text = pattern.sub(r"\1[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


class _RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(redact(str(a)) for a in record.args)
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"tradeos.{name}")
    if not any(isinstance(f, _RedactionFilter) for f in logger.filters):
        logger.addFilter(_RedactionFilter())
    return logger
