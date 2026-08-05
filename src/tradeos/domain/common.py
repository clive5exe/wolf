"""Shared primitives: ULIDs, UTC time, canonical JSON, money formatting.

Money is Decimal end-to-end; floats never touch financial arithmetic.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ulid_lock = threading.Lock()
_last_ts_ms = 0
_last_rand = 0


def utc_now() -> datetime:
    """Current time, always timezone-aware UTC.

    Domain/risk/strategy code must receive time via injection (``ctx.now``);
    this is for runtime edges (event recording, id generation).
    """
    return datetime.now(UTC)


def new_ulid() -> str:
    """Generate a ULID (sortable 26-char id): 48-bit ms timestamp + 80-bit randomness.

    Monotonic within this process: same-millisecond ids increment the random
    component so event ordering by id matches insertion order.
    """
    global _last_ts_ms, _last_rand
    with _ulid_lock:
        ts_ms = time.time_ns() // 1_000_000
        if ts_ms == _last_ts_ms:
            _last_rand += 1
        else:
            _last_ts_ms = ts_ms
            _last_rand = int.from_bytes(os.urandom(10))
        rand = _last_rand
    value = (ts_ms << 80) | (rand & ((1 << 80) - 1))
    chars = []
    for shift in range(125, -5, -5):
        chars.append(_CROCKFORD[(value >> shift) & 0x1F])
    return "".join(chars)


def canonical_json(data: Any) -> str:
    """Deterministic JSON encoding (sorted keys, no whitespace variance).

    Used for content hashes and replay-equality comparison, so the encoding
    must never depend on dict ordering or platform.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_canonical_default)


def _canonical_default(obj: Any) -> str:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"not canonically serializable: {type(obj)!r}")


def format_money(value: Decimal, currency: str = "$") -> str:
    """Render a Decimal as money for interfaces. Display-only — never parse back."""
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    sign = "-" if quantized < 0 else ""
    return f"{sign}{currency}{abs(quantized):,}"


def pct(value: Decimal) -> str:
    """Render a 0..1 fraction as a percentage string for interfaces."""
    return f"{(value * Decimal('100')).quantize(Decimal('0.1'))}%"
