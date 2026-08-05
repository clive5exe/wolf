"""Client-side rate limiting for outbound connectors.

Rate limits published by a data source are not suggestions, and exceeding them
is how a project gets its whole user base blocked at once. WOLF therefore
limits itself *below* every documented ceiling rather than up against it — SEC
permits 10 requests/second and this ships at 5.

Time and sleeping are injected so the limiter can be tested at speed. A rate
limiter verified only by a test that actually waits is a rate limiter nobody
runs often enough to trust.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class RateLimiter:
    """Spacing limiter: guarantees a minimum interval between acquisitions.

    Strict spacing rather than a token bucket, deliberately. A bucket permits
    bursts that are invisible in aggregate statistics but very visible to the
    server being burst at, and "we averaged under the limit" is no defence
    once you have been blocked.
    """

    def __init__(
        self,
        max_per_second: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_per_second <= 0:
            raise ValueError("max_per_second must be positive")
        self._interval = 1.0 / max_per_second
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_allowed: float | None = None

    @property
    def interval_s(self) -> float:
        return self._interval

    def acquire(self) -> float:
        """Block until the next request is allowed. Returns seconds waited."""
        with self._lock:
            now = self._monotonic()
            if self._next_allowed is None or now >= self._next_allowed:
                self._next_allowed = now + self._interval
                return 0.0
            wait = self._next_allowed - now
            self._next_allowed += self._interval
        # Sleeping outside the lock so concurrent callers queue rather than
        # serialise on the mutex for the whole wait.
        self._sleep(wait)
        return wait
