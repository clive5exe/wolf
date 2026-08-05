#!/usr/bin/env python
"""Regenerate the README screenshots in ``docs/screens/``.

These are captures of the real application driven against a live in-memory
runtime. Not mockups. Every figure on screen is one the code actually
produced, which is the only kind of screenshot a project making claims about
honesty has any business publishing.

Run after any UI change:  ./scripts/capture_screens.py
"""

from __future__ import annotations

import asyncio
import math
import pathlib
import sys
from datetime import datetime
from decimal import Decimal

from tradeos.domain.market import Quote
from tradeos.runtime.facade import DEMO_PRICES, RuntimeConfig, TradeOSRuntime
from tradeos.tui.app import WolfApp

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "screens"


class WalkingQuoteSource:
    """Prices that move, for capture only.

    The shipped demo quotes are static, and a static market never drifts past
    the rebalance threshold, so no cycle ever trades and no equity history ever
    accumulates. The dashboard then had nothing to chart and the screenshots
    looked identical no matter how many cycles ran.

    Deterministic: a fixed waveform per symbol rather than a random walk, so a
    capture is reproducible and two runs of this script produce the same image.
    """

    name = "walking"

    def __init__(self, base: dict[str, Decimal]) -> None:
        self._base = {k.upper(): v for k, v in base.items()}
        self._order = list(self._base)
        self._tick = 0

    def advance(self) -> None:
        self._tick += 1

    def get_quote(self, symbol: str, *, now: datetime) -> Quote | None:
        price = self._base.get(symbol.upper())
        if price is None:
            return None
        # Symbols must diverge from each other, not merely move. Drift is a
        # *relative* weight, so a uniform move changes no weights at all and
        # the rebalancer correctly does nothing. Each symbol therefore gets its
        # own phase and amplitude.
        index = self._order.index(symbol.upper())
        phase = index * 1.9
        amplitude = 0.06 + 0.02 * index
        swing = Decimal(str(round(amplitude * math.sin(self._tick / 1.7 + phase), 6)))
        return Quote(
            symbol=symbol.upper(),
            price=price * (1 + swing),
            as_of=now,
            source=self.name,
        )


#: One terminal size for every capture. Uniform output matters downstream: the
#: site presents these in a slideshow, and mixed aspect ratios there mean either
#: letterboxing or the frame resizing between slides. 30 rows is set by the
#: tallest screen (boot's splash plus ten checks). The shorter ones simply have
#: empty terminal below, which is what a real terminal looks like anyway.
SIZE = (100, 34)

SHOTS = (
    # name, screen, cycles, engage_kill
    ("den", "den", 14, False),
    ("boot", "boot", 0, False),
    ("cycle", "cycle", 0, False),
    ("verdict", "verdict", 1, False),
    ("journal", "journal", 14, False),
    ("kill", "kill", 1, True),
)


async def capture(name: str, screen: str, cycles: int, engage_kill: bool) -> None:
    quotes = WalkingQuoteSource(DEMO_PRICES)
    runtime = TradeOSRuntime(RuntimeConfig(in_memory=True, quote_source=quotes))
    runtime.ensure_sample_policy()
    for index in range(cycles):
        runtime.run_cycle(f"demo-{index}")
        quotes.advance()
    if engage_kill:
        runtime.engage_kill_switch("market data storm · engaged by operator")

    app = WolfApp(runtime, calm=True, start_screen=screen)
    async with app.run_test(size=SIZE) as pilot:
        # The cycle screen runs a real decision on a worker. Give it time to finish.
        for _ in range(30 if screen == "cycle" else 2):
            await pilot.pause()
        svg = app.export_screenshot(title=f"wolf · {name}")

    target = OUT / f"{name}.svg"
    target.write_text(svg)
    print(f"  {target.relative_to(OUT.parent.parent)}  ({len(svg) // 1024}KB)")


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"capturing {len(SHOTS)} screens →")
    for shot in SHOTS:
        await capture(*shot)

    # An in-memory runtime should never surface a real path, but the captures
    # are published, so the check is cheap insurance against that changing.
    leaked = [
        path.name
        for path in OUT.glob("*.svg")
        if any(marker in path.read_text() for marker in ("/Users/", "/home/", "C:\\Users"))
    ]
    if leaked:
        print(f"error: filesystem paths present in {leaked}", file=sys.stderr)
        return 1
    print("all captures clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
