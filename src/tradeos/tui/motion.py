"""One motion vocabulary, one beat.

Every timing the TUI animates on lives here, so the whole app moves together.
The rule that governs this file: **motion always means something** — alive,
working, arriving, confirmed, or dead. Decorative animation is banned, which is
why each constant below names the system state it represents.

``--calm`` (or a ``prefers-reduced-motion``-style preference) collapses every
duration to zero: animations stop, but no information disappears, because
motion here is always redundant with a glyph or a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# -- the vocabulary -----------------------------------------------------------

#: the runtime is alive — one cursor, always infrared, on every screen
CURSOR_BLINK_S: Final = 1.06

#: a data source is live and fresh; stale sources stop moving and go hollow
FRESHNESS_PULSE_S: Final = 2.4

#: a stage is working — always rendered adjacent to the label it belongs to
SPINNER_FRAME_S: Final = 0.08
SPINNER_FRAMES: Final = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

#: records arriving (boot checks, journal rows, log lines)
RISE_STAGGER_S: Final = 0.07
RISE_DURATION_S: Final = 0.42

#: rules verified one by one — fast enough to feel mechanical, slow enough to count
TICK_STAGGER_S: Final = 0.028

#: model text being generated; never used for system text
TYPE_CHAR_S: Final = 0.018

#: money moved (paper or real)
FLASH_S: Final = 0.38
FLASH_REPEATS: Final = 2

#: ambient "the market is breathing" — dashboard equity strip only
SHIMMER_LOOP_S: Final = 3.4

#: halted; overrides every other motion on screen
KILL_PULSE_S: Final = 1.2

#: a displayed value changed (tabular figures, so no layout shift)
COUNT_UP_S: Final = 0.6

#: how often live screens re-read the runtime
REFRESH_INTERVAL_S: Final = 2.0


@dataclass(frozen=True)
class Motion:
    """Resolved timings for one app instance.

    ``calm=True`` zeroes every duration. Screens must still render their final
    state when a duration is zero — never gate content on an animation finishing.
    """

    calm: bool = False

    def scale(self, seconds: float) -> float:
        """A duration, or 0.0 in calm mode."""
        return 0.0 if self.calm else seconds

    @property
    def cursor_blink(self) -> float:
        return self.scale(CURSOR_BLINK_S)

    @property
    def freshness_pulse(self) -> float:
        return self.scale(FRESHNESS_PULSE_S)

    @property
    def spinner_frame(self) -> float:
        return self.scale(SPINNER_FRAME_S)

    @property
    def rise_stagger(self) -> float:
        return self.scale(RISE_STAGGER_S)

    @property
    def tick_stagger(self) -> float:
        return self.scale(TICK_STAGGER_S)

    @property
    def type_char(self) -> float:
        return self.scale(TYPE_CHAR_S)

    @property
    def flash(self) -> float:
        return self.scale(FLASH_S)

    @property
    def shimmer_loop(self) -> float:
        return self.scale(SHIMMER_LOOP_S)

    @property
    def kill_pulse(self) -> float:
        return self.scale(KILL_PULSE_S)

    @property
    def count_up(self) -> float:
        return self.scale(COUNT_UP_S)


def spinner_frame(tick: int) -> str:
    """Braille spinner frame for a monotonic tick counter."""
    return SPINNER_FRAMES[tick % len(SPINNER_FRAMES)]
