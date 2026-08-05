"""WOLF — the terminal application.

Interface discipline: everything on screen comes from the ``TradeOSRuntime``
facade, and keys send commands back through it. The dashboard is home; every
screen is one keystroke away and one ``esc`` back. There are no menus.

``k`` reaches the kill switch from anywhere, on every screen, always.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from textual.app import App
from textual.binding import Binding, BindingType
from textual.screen import Screen

from tradeos.runtime.facade import RuntimeConfig, TradeOSRuntime
from tradeos.tui.motion import Motion
from tradeos.tui.screens.boot import BootScreen
from tradeos.tui.screens.cycle import CycleScreen
from tradeos.tui.screens.den import DenScreen
from tradeos.tui.screens.journal import JournalScreen
from tradeos.tui.screens.kill import KillScreen
from tradeos.tui.screens.verdict import VerdictScreen
from tradeos.tui.theme import DISCLAIMER, Ink


class WolfApp(App[None]):
    TITLE = "W◉LF"
    SUB_TITLE = DISCLAIMER

    CSS = f"""
    Screen {{
        background: {Ink.BG};
        color: {Ink.INK};
    }}
    Vertical {{
        padding: 0 1;
    }}
    Static {{
        background: {Ink.BG};
    }}
    """

    SCREENS: ClassVar[dict[str, Callable[[], Screen[None]]]] = {
        "boot": BootScreen,
        "den": DenScreen,
        "cycle": CycleScreen,
        "verdict": VerdictScreen,
        "journal": JournalScreen,
        "kill": KillScreen,
    }

    #: The kill switch is reachable from every screen without exception.
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("k", "kill_switch", "kill switch", priority=True),
    ]

    def __init__(
        self,
        runtime: TradeOSRuntime | None = None,
        *,
        calm: bool = False,
        start_screen: str = "boot",
    ) -> None:
        super().__init__()
        self.runtime = runtime or TradeOSRuntime(RuntimeConfig())
        self.motion = Motion(calm=calm)
        #: Which decision the verdict screen should open; set by den/journal/cycle.
        self.focused_cycle_id: str = ""
        self._start_screen = start_screen

    def on_mount(self) -> None:
        self.push_screen(self._start_screen)

    def action_kill_switch(self) -> None:
        """``k`` from anywhere. Never a toggle — engaging and disengaging differ.

        This binding is ``priority``, so it would otherwise shadow the kill
        screen's own ``k``; there we hand the key back to the screen instead of
        swallowing it.
        """
        if isinstance(self.screen, KillScreen):
            self.screen.action_engage()
            return
        self.push_screen("kill")


#: Kept so `from tradeos.tui.app import TradeOSApp` still resolves post-rename.
TradeOSApp = WolfApp


def run(calm: bool = False) -> None:
    WolfApp(calm=calm).run()


if __name__ == "__main__":
    run()
