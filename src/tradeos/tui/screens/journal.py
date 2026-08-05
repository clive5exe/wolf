"""Journal — the memory.

Vetoes and no-actions sit in this list at the same visual weight as fills,
because "we did not trade" is a result, not an absence. Each row carries what
the system knew at the time, so a decision can be judged on its inputs rather
than its outcome.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Static

from tradeos.runtime.journal import CycleRecord
from tradeos.tui.base import WolfScreen, footer_bar
from tradeos.tui.glyphs import fmt_completeness, truncate
from tradeos.tui.theme import Ink, key


class JournalScreen(WolfScreen):
    """Decision history, newest first, with the selected row expanded."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "back", "den"),
        Binding("down", "next_row", "next"),
        Binding("up", "prev_row", "previous"),
        Binding("enter", "open_verdict", "open"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._records: tuple[CycleRecord, ...] = ()
        self._index = 0
        self._revealed = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="journal"):
            yield Static("", id="journal-title")
            yield Static("", id="journal-rows")
            yield Static("", id="journal-legend")
            yield Static("", id="journal-footer")

    def on_mount(self) -> None:
        self._records = self.runtime.journal(40)
        if self.motion.calm:
            self._revealed = len(self._records)
        else:
            self.set_interval(self.motion.rise_stagger, self._reveal_next)
        self._paint()

    def _reveal_next(self) -> None:
        if self._revealed >= len(self._records):
            return
        self._revealed += 1
        self._paint()

    # -- rendering -------------------------------------------------------------

    def _paint(self) -> None:
        count = len(self._records)
        self.query_one("#journal-title", Static).update(
            f"\n  [{Ink.DIM}]JOURNAL · {count} decision{'s' if count != 1 else ''} ·[/] "
            f"[{Ink.GREEN}]replay verified[/]\n"
        )
        self.query_one("#journal-rows", Static).update(self._rows())
        self.query_one("#journal-legend", Static).update(
            f"\n  [{Ink.DIM}]outcome key:[/] [{Ink.GREEN}]●[/] [{Ink.DIM}]traded[/] · "
            f"[{Ink.AMBER}]◐[/] [{Ink.DIM}]held position[/] · "
            f"[{Ink.RED}]✕[/] [{Ink.DIM}]blocked by risk[/]"
        )
        self.query_one("#journal-footer", Static).update(
            footer_bar("  ".join((key("⏎", " open"), key("↑↓", " move"), key("esc", " den"))))
        )

    def _rows(self) -> str:
        if not self._records:
            return (
                f"  [{Ink.DIM}]nothing decided yet.[/]\n"
                f"  [{Ink.FAINT}]run a cycle from the den — no-actions get recorded too.[/]"
            )
        lines: list[str] = []
        for position, record in enumerate(self._records[: self._revealed]):
            selected = position == self._index
            lines.append(self._row(record, selected=selected))
            if selected:
                lines.extend(self._expansion(record))
        return "\n".join(lines)

    def _row(self, record: CycleRecord, *, selected: bool) -> str:
        if record.veto_reasons:
            glyph, tint = "✕", Ink.RED
        elif record.filled_count:
            glyph, tint = "●", Ink.GREEN
        else:
            glyph, tint = "◐", Ink.AMBER

        rules = f"{record.rules_passed}/{record.rules_total}" if record.rules_total else "—"
        rules_ink = Ink.RED if record.veto_reasons else Ink.DIM
        thesis = (
            f"[{Ink.CYAN}]thesis {record.thesis.confidence}[/]"
            if record.thesis and record.thesis.confidence is not None
            else f"[{Ink.FAINT}]deterministic[/]"
        )
        marker = f"[{Ink.AMBER}]▸[/]" if selected else " "
        strategy = _strategy_label(record.strategy)
        return (
            f"  {marker} [{Ink.FAINT}]{record.occurred_at.strftime('%m-%d %H:%M')}[/]  "
            f"[{Ink.DIM}]{strategy:<12}[/]"
            f"[{tint}]{record.headline:<11}[/]"
            f"[{rules_ink}]{rules:>7}[/]   {thesis}  [{tint}]{glyph}[/]"
        )

    def _expansion(self, record: CycleRecord) -> list[str]:
        lines = [
            f"      [{Ink.FAINT}]└ what we knew:[/] [{Ink.DIM}]package "
            f"{record.context_package_id[:10] or '—'} · {record.context_items} items · "
            f"completeness {fmt_completeness(record.context_completeness)}[/]"
        ]
        if record.veto_reasons:
            lines.append(
                f"      [{Ink.FAINT}]└ blocked by:[/] "
                f"[{Ink.RED}]{', '.join(record.veto_reasons)}[/]"
            )
        elif not record.filled_count:
            lines.append(
                f"      [{Ink.FAINT}]└ no-action is a decision:[/] "
                f"[{Ink.DIM}]{truncate(record.reason, 44)}[/]"
            )
        else:
            symbols = ", ".join(f"{f.side} {f.symbol}" for f in record.fills if f.filled)
            lines.append(f"      [{Ink.FAINT}]└ filled:[/] [{Ink.DIM}]{truncate(symbols, 58)}[/]")
        return lines

    # -- actions ---------------------------------------------------------------

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_next_row(self) -> None:
        if self._index < min(self._revealed, len(self._records)) - 1:
            self._index += 1
            self._paint()

    def action_prev_row(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._paint()

    def action_open_verdict(self) -> None:
        if not self._records:
            return
        self.wolf.focused_cycle_id = self._records[self._index].correlation_id
        self.app.push_screen("verdict")


def _strategy_label(strategy: str) -> str:
    """``target_allocation_rebalance@1.0.0`` → ``rebalance``.

    The journal is a list of decisions, not of module names; the distinguishing
    word is the last one, and truncation would otherwise cut mid-prefix.
    """
    name = strategy.split("@")[0]
    if not name:
        return "—"
    return truncate(name.rsplit("_", 1)[-1], 11)
