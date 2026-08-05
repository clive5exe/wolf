"""Kill switch — the loud screen.

Anti-design, on purpose: no sparklines, no shimmer, no charm. Safety should not
be tasteful. Engaging is one key; disengaging is deliberately annoying — two
separate presses, or the typed `wolf unkill` command — because an accidental
keystroke must never re-arm execution. Both paths are recorded with who and when.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Static

from tradeos.tui.base import WolfScreen, footer_bar
from tradeos.tui.theme import Ink, key

_BANNER_WIDTH = 38


class KillScreen(WolfScreen):
    """Full-screen takeover shown whenever execution is halted."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "back", "back"),
        Binding("k", "engage", "engage"),
        Binding("u", "arm_disengage", "unkill (twice)"),
        Binding("j", "open_journal", "journal"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._pulse_on = True
        self._disengage_armed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="kill"):
            yield Static("", id="kill-banner")
            yield Static("", id="kill-detail")
            yield Static("", id="kill-footer")

    def on_mount(self) -> None:
        self._paint()
        if not self.motion.calm:
            self.set_interval(self.motion.kill_pulse / 2, self._pulse)

    def _pulse(self) -> None:
        self._pulse_on = not self._pulse_on
        self._paint()

    # -- rendering -------------------------------------------------------------

    def _paint(self) -> None:
        engaged = self.runtime.kill_switch.is_engaged()
        self.query_one("#kill-banner", Static).update(self._banner(engaged))
        self.query_one("#kill-detail", Static).update(self._detail(engaged))
        self.query_one("#kill-footer", Static).update(self._footer(engaged))

    def _banner(self, engaged: bool) -> str:
        if not engaged:
            return (
                f"\n       [{Ink.GREEN}]● execution armed[/]\n"
                f"       [{Ink.DIM}]the kill switch is clear — trading can proceed[/]\n"
            )
        tint = Ink.RED if (self._pulse_on or self.motion.calm) else Ink.ON_RED
        bar = "█" * _BANNER_WIDTH
        label = "TRADING  HALTED".center(_BANNER_WIDTH - 4)
        return (
            f"\n       [{tint} bold]{bar}[/]\n"
            f"       [{tint} bold]██{' ' * (_BANNER_WIDTH - 4)}██[/]\n"
            f"       [{tint} bold]██[/][{Ink.BRIGHT} bold]{label}[/][{tint} bold]██[/]\n"
            f"       [{tint} bold]██{' ' * (_BANNER_WIDTH - 4)}██[/]\n"
            f"       [{tint} bold]{bar}[/]\n"
        )

    def _detail(self, engaged: bool) -> str:
        if not engaged:
            return (
                f"\n       [{Ink.DIM}]press[/] [{Ink.AMBER}]k[/] "
                f"[{Ink.DIM}]to halt everything immediately.[/]\n"
                f"       [{Ink.FAINT}]execution is refused at four layers — "
                f"scheduler · cycle · engine · broker.[/]\n"
            )
        state = self.runtime.kill_state()
        when = state.since.strftime("%H:%M:%SZ") if state.since else "—"
        reason = state.reason or "—"
        who = state.source or "unknown"
        armed = (
            f"\n       [{Ink.AMBER}]press[/] [{Ink.AMBER} bold]u[/] "
            f"[{Ink.AMBER}]again to confirm — this re-arms execution[/]"
            if self._disengage_armed
            else (
                f"\n       [{Ink.DIM}]nothing trades until a human types:[/]\n"
                f"       [{Ink.AMBER} bold]wolf unkill[/] [{Ink.DIM}]— or —[/] "
                f"[{Ink.AMBER}]u[/] [{Ink.DIM}]here, twice, deliberately[/]"
            )
        )
        return (
            f"\n       [{Ink.RED}]●[/] [{Ink.DIM}]kill switch engaged ·[/] "
            f"[{Ink.BRIGHT}]{when}[/] [{Ink.DIM}]· by[/] [{Ink.BRIGHT}]{who}[/]\n"
            f"       [{Ink.DIM}]reason:[/] [{Ink.INK}]{reason}[/]\n\n"
            f"       [{Ink.DIM}]execution refused at[/] [{Ink.BRIGHT}]4 layers[/] "
            f"[{Ink.DIM}]— scheduler · cycle · engine · broker[/]\n"
            f"{armed}\n"
        )

    def _footer(self, engaged: bool) -> str:
        keys = [key("esc", " back"), key("j", "ournal")]
        if engaged:
            keys.append(key("u", "nkill (twice)"))
        else:
            keys.append(key("k", "ill"))
        return footer_bar("  ".join(keys))

    # -- actions ---------------------------------------------------------------

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_engage(self) -> None:
        if self.runtime.kill_switch.is_engaged():
            return
        self.runtime.engage_kill_switch("engaged from the TUI")
        self._disengage_armed = False
        self._paint()

    def action_arm_disengage(self) -> None:
        """First press arms, second press disengages — never one accidental key."""
        if not self.runtime.kill_switch.is_engaged():
            return
        if not self._disengage_armed:
            self._disengage_armed = True
            self._paint()
            return
        self.runtime.disengage_kill_switch()
        self._disengage_armed = False
        self._paint()
        self.notify("kill switch disengaged — execution re-armed", severity="warning")

    def action_open_journal(self) -> None:
        self.app.push_screen("journal")
