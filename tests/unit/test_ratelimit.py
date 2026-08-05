"""Rate limiter.

Driven by a fake clock rather than real waiting. A limiter whose test suite
takes ten seconds is a limiter people stop running, and this is the component
that decides whether a public data source blocks every WOLF user at once.
"""

from __future__ import annotations

import itertools

import pytest

from tradeos.ingestion.ratelimit import RateLimiter


class FakeClock:
    """Monotonic time that only advances when something sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def limiter(clock: FakeClock, rate: float = 5.0) -> RateLimiter:
    return RateLimiter(rate, monotonic=clock.monotonic, sleep=clock.sleep)


class TestSpacing:
    def test_the_first_request_is_immediate(self, clock: FakeClock) -> None:
        assert limiter(clock).acquire() == 0.0
        assert clock.sleeps == []

    def test_a_burst_is_spaced_out(self, clock: FakeClock) -> None:
        """Bursting is what gets you blocked, even when the average is fine."""
        rl = limiter(clock, rate=5.0)
        for _ in range(5):
            rl.acquire()
        assert clock.now == pytest.approx(0.8)  # 4 gaps of 200ms

    def test_a_caller_that_waits_is_never_delayed(self, clock: FakeClock) -> None:
        rl = limiter(clock, rate=5.0)
        rl.acquire()
        clock.now += 10.0
        assert rl.acquire() == 0.0

    @pytest.mark.parametrize("rate", [1.0, 2.0, 5.0, 10.0])
    def test_consecutive_requests_are_never_closer_than_the_interval(
        self, clock: FakeClock, rate: float
    ) -> None:
        """The property a server actually measures: the gap between one request
        and the next. Dividing count by elapsed time counts both endpoints and
        so always reads fractionally high. It is the wrong metric, not a
        violation."""
        rl = limiter(clock, rate=rate)
        stamps: list[float] = []
        for _ in range(25):
            rl.acquire()
            stamps.append(clock.now)

        gaps = [b - a for a, b in itertools.pairwise(stamps)]
        assert min(gaps) >= rl.interval_s - 1e-9, (
            f"requests {min(gaps):.4f}s apart, below the {rl.interval_s:.4f}s minimum"
        )

    @pytest.mark.parametrize("rate", [1.0, 5.0, 10.0])
    def test_no_one_second_window_holds_more_than_the_ceiling(
        self, clock: FakeClock, rate: float
    ) -> None:
        """Stated the way a rate limit is usually written."""
        rl = limiter(clock, rate=rate)
        stamps: list[float] = []
        for _ in range(30):
            rl.acquire()
            stamps.append(clock.now)

        # A hair under a full second, so accumulated float error at the window
        # boundary cannot pull in an extra request and fail a correct limiter.
        window = 1.0 - 1e-9
        for start in stamps:
            in_window = sum(1 for t in stamps if start <= t < start + window)
            assert in_window <= rate, f"{in_window} requests in one second at {rate}/s"

    def test_interval_is_the_reciprocal_of_the_rate(self, clock: FakeClock) -> None:
        assert limiter(clock, rate=4.0).interval_s == pytest.approx(0.25)


class TestConfiguration:
    @pytest.mark.parametrize("rate", [0, -1, -0.5])
    def test_a_nonsense_rate_is_refused(self, rate: float) -> None:
        with pytest.raises(ValueError, match="positive"):
            RateLimiter(rate)

    def test_edgar_ships_below_secs_published_ceiling(self) -> None:
        """SEC permits 10/s. Shipping at the limit leaves no headroom for
        clock skew, retries, or a second process on the same machine."""
        from tradeos.ingestion.edgar import MAX_REQUESTS_PER_SECOND

        assert MAX_REQUESTS_PER_SECOND <= 5.0
