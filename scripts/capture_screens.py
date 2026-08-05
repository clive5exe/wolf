#!/usr/bin/env python
"""Regenerate the README screenshots in ``docs/screens/``.

These are captures of the real application driven against a live in-memory
runtime — not mockups. Every figure on screen is one the code actually
produced, which is the only kind of screenshot a project making claims about
honesty has any business publishing.

Run after any UI change:  ./scripts/capture_screens.py
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

from tradeos.runtime.facade import RuntimeConfig, TradeOSRuntime
from tradeos.tui.app import WolfApp

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "screens"

#: Terminal size per screen. Height is set so nothing clips — the boot splash
#: plus ten checks needs considerably more room than the journal does.
SHOTS = (
    # name, screen, cycles, size, engage_kill
    ("den", "den", 1, (100, 24), False),
    ("boot", "boot", 0, (100, 30), False),
    ("cycle", "cycle", 0, (100, 26), False),
    ("verdict", "verdict", 1, (100, 30), False),
    ("journal", "journal", 3, (100, 18), False),
    ("kill", "kill", 1, (100, 24), True),
)


async def capture(
    name: str,
    screen: str,
    cycles: int,
    size: tuple[int, int],
    engage_kill: bool,
) -> None:
    runtime = TradeOSRuntime(RuntimeConfig(in_memory=True))
    runtime.ensure_sample_policy()
    for index in range(cycles):
        runtime.run_cycle(f"demo-{index}")
    if engage_kill:
        runtime.engage_kill_switch("market data storm — engaged by operator")

    app = WolfApp(runtime, calm=True, start_screen=screen)
    async with app.run_test(size=size) as pilot:
        # The cycle screen runs a real decision on a worker; give it time to finish.
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
