"""Boot sequence — startup doubles as diagnosis.

The doctor checks *are* the boot sequence, so you cannot boot past a broken
environment: a failing check halts the cascade in place, shows its fix hint,
and refuses to open the den until you press a key to continue anyway.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Static

from tradeos.runtime.diagnostics import CheckStatus, DoctorCheck
from tradeos.tui.base import WolfScreen
from tradeos.tui.theme import ACRONYM, DISCLAIMER, TAGLINE, WORDMARK_BLOCK, Ink

_GLYPH = {
    CheckStatus.OK: f"[{Ink.GREEN}]✓[/]",
    CheckStatus.WARN: f"[{Ink.AMBER}]![/]",
    CheckStatus.FAIL: f"[{Ink.RED}]✗[/]",
}
_LEADER_WIDTH = 22


class BootScreen(WolfScreen):
    """The check cascade. Lines land one by one; a failure stops the cascade."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "enter_den", "enter the den"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._checks: list[DoctorCheck] = []
        self._revealed = 0
        self._blocked = False
        self._cursor_on = True

    def compose(self) -> ComposeResult:
        with Vertical(id="boot"):
            yield Static(self._splash(), id="boot-brand")
            yield Static("", id="boot-checks")
            yield Static("", id="boot-status")
            yield Static(f"  [{Ink.FAINT}]{DISCLAIMER}[/]", id="boot-disclaimer")

    def on_mount(self) -> None:
        self._checks = self.runtime.diagnostics()
        if self.motion.calm:
            self._revealed = self._reveal_limit()
            self._blocked = self._has_failure_within(self._revealed)
            self._paint()
            return
        self.set_interval(self.motion.rise_stagger, self._advance)
        self.set_interval(self.motion.cursor_blink, self._blink)
        self._paint()

    @staticmethod
    def _splash() -> str:
        """The one brand moment, above the checks — never gating them.

        A splash is ornament in an app whose rule is that decoration must mean
        something, so it earns its place by staying out of the way: it renders
        instantly, delays nothing, and the diagnosis begins underneath it.
        """
        block = "\n".join(f"    [{Ink.BRIGHT}]{line}[/]" for line in WORDMARK_BLOCK.splitlines())
        return f"\n{block}\n\n    [{Ink.AMBER}]{ACRONYM}[/]\n    [{Ink.DIM}]{TAGLINE}[/]\n"

    # -- cascade ---------------------------------------------------------------

    def _reveal_limit(self) -> int:
        """Reveal up to and including the first failure, then stop."""
        for index, check in enumerate(self._checks):
            if check.status == CheckStatus.FAIL:
                return index + 1
        return len(self._checks)

    def _has_failure_within(self, count: int) -> bool:
        return any(c.status == CheckStatus.FAIL for c in self._checks[:count])

    def _advance(self) -> None:
        limit = self._reveal_limit()
        if self._revealed >= limit:
            self._blocked = self._has_failure_within(limit)
            self._paint()
            return
        self._revealed += 1
        self._paint()

    def _blink(self) -> None:
        self._cursor_on = not self._cursor_on
        self._render_status()

    # -- rendering -------------------------------------------------------------

    def _paint(self) -> None:
        lines: list[str] = [""]
        for check in self._checks[: self._revealed]:
            leader = "." * max(3, _LEADER_WIDTH - len(check.name))
            line = (
                f"  [{Ink.AMBER}]▸[/] [{Ink.INK}]{check.name}[/] "
                f"[{Ink.FAINT}]{leader}[/] {_GLYPH[check.status]} "
                f"[{Ink.DIM}]{check.detail}[/]"
            )
            lines.append(line)
            if check.status != CheckStatus.OK and check.hint:
                tint = Ink.RED if check.status == CheckStatus.FAIL else Ink.AMBER
                lines.append(f"      [{tint}]↳ {check.hint}[/]")
        self.query_one("#boot-checks", Static).update("\n".join(lines))
        self._render_status()

    def _render_status(self) -> None:
        done = self._revealed >= self._reveal_limit()
        if not done:
            self.query_one("#boot-status", Static).update("")
            return
        cursor = f"[{Ink.AMBER}]█[/]" if self._cursor_on else " "
        if self._blocked:
            body = (
                f"\n  [{Ink.RED}]environment check failed[/] "
                f"[{Ink.DIM}]— fix the line above, or press[/] "
                f"[{Ink.BRIGHT}]⏎[/] [{Ink.DIM}]to continue anyway[/] {cursor}"
            )
        else:
            warned = sum(1 for c in self._checks if c.status == CheckStatus.WARN)
            note = (
                f" [{Ink.DIM}]({warned} warning{'s' if warned != 1 else ''})[/]" if warned else ""
            )
            body = (
                f"\n  [{Ink.GREEN}]all systems nominal[/]{note} [{Ink.DIM}]—[/] "
                f"[{Ink.DIM}]press[/] [{Ink.BRIGHT}]⏎[/] [{Ink.DIM}]to enter the den[/] {cursor}"
            )
        self.query_one("#boot-status", Static).update(body)

    # -- actions ---------------------------------------------------------------

    def action_enter_den(self) -> None:
        if self._revealed < self._reveal_limit():  # let an impatient human skip ahead
            self._revealed = self._reveal_limit()
            self._blocked = self._has_failure_within(self._revealed)
            self._paint()
            return
        self.app.switch_screen("den")
