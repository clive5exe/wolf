"""Track. One symbol, in full.

The verdict is on top, the chart is the evidence, the reasoning is underneath.
That order is the point: the previous version of this screen opened with forty
numbers and no conclusion, which is a data dump rather than a screen.

The header names the *subject* rather than the product. You know which app you
are in, and the symbol is the thing that changes as you move around.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Static

from tradeos.tui.base import WolfScreen, footer_bar, header_bar, section
from tradeos.tui.chart import Bar, candles, price_axis
from tradeos.tui.glyphs import fmt_money, fmt_signed_pct
from tradeos.tui.theme import Ink, key


@dataclass(frozen=True, slots=True)
class RiskHeadroom:
    """One rule and how close it is to blocking, not whether it did.

    The verdict screen answers "did anything stop this". This answers "what
    will stop it next", which is the question you have while still deciding.
    """

    rule: str
    detail: str
    used: Decimal | None = None  # 0..1 of the limit consumed, None if not a cap
    clear: bool = True


@dataclass(frozen=True, slots=True)
class TrackView:
    """Everything the screen renders. Assembled by the caller, never fetched
    here, so the screen stays a pure function of state like every other one."""

    symbol: str
    name: str
    exchange: str
    bars: tuple[Bar, ...]
    source: str = "robinhood"
    sessions_label: str = ""
    held_qty: Decimal | None = None
    verdict: str = ""
    momentum: str = ""
    rank: str = ""
    risk: tuple[RiskHeadroom, ...] = field(default_factory=tuple)
    thesis: str = ""
    invalidated_if: str = ""
    thesis_meta: str = ""

    @property
    def last(self) -> Bar | None:
        return self.bars[-1] if self.bars else None

    @property
    def change(self) -> Decimal | None:
        """Move over the whole window, which is what the chart shows."""
        if len(self.bars) < 2 or self.bars[0].close == 0:
            return None
        return (self.bars[-1].close - self.bars[0].close) / self.bars[0].close


class TrackScreen(WolfScreen):
    """Any symbol, in full."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "back", "den"),
        Binding("j", "journal", "journal"),
        Binding("k", "kill", "kill"),
        Binding("q", "quit", "quit"),
    ]

    #: Tall enough that a three month window has shape, short enough to leave
    #: room for the reasoning below it. The chart is evidence, not the screen.
    CHART_ROWS = 16

    def __init__(self, view: TrackView) -> None:
        super().__init__()
        self._view = view

    def compose(self) -> ComposeResult:
        with Vertical(id="track"):
            yield Static("", id="track-header")
            yield Static("", id="track-headline")
            yield Static("", id="track-chart")
            yield Static("", id="track-why")
            yield Static("", id="track-risk")
            yield Static("", id="track-thesis")
            yield Static("", id="track-footer")

    def on_mount(self) -> None:
        self._paint()

    # -- rendering -------------------------------------------------------------

    def _paint(self) -> None:
        view = self._view
        q = self.query_one
        q("#track-header", Static).update(
            header_bar(f"[{Ink.DIM}]{view.exchange} · {view.source}[/]", width=self.frame)
        )
        q("#track-headline", Static).update(self._headline())
        q("#track-chart", Static).update(self._chart())
        q("#track-why", Static).update(self._why())
        q("#track-risk", Static).update(self._risk())
        q("#track-thesis", Static).update(self._thesis())
        q("#track-footer", Static).update(
            footer_bar(
                "  ".join((key("/", "search"), key("j", "ournal"), key("esc", " den"))),
                width=self.frame,
            )
        )

    def _headline(self) -> str:
        view, last = self._view, self._view.last
        if last is None:
            return f"\n  [{Ink.BRIGHT}]{view.symbol}[/]  [{Ink.DIM}]no price data[/]\n"

        change = view.change
        tint = Ink.GREEN if (change or 0) > 0 else Ink.RED if (change or 0) < 0 else Ink.DIM
        bits = [
            f"  [{Ink.BRIGHT}]{view.symbol}[/]  [{Ink.INK}]{view.name}[/]",
            f"[{Ink.BRIGHT}]{fmt_money(last.close)}[/]",
            f"[{tint}]{fmt_signed_pct(change, arrow=True)}[/]",
        ]
        if view.rank:
            bits.append(f"[{Ink.DIM}]rank[/] [{Ink.BRIGHT}]{view.rank}[/]")
        if view.held_qty is not None:
            bits.append(f"[{Ink.DIM}]held[/] [{Ink.BRIGHT}]{view.held_qty:,g}[/]")

        head = "\n" + "     ".join(bits) + "\n"
        if self._view.verdict:
            head += f"  [{Ink.INFRARED}]{self._view.verdict}[/]\n"
        return head

    def _chart(self) -> str:
        view = self._view
        if len(view.bars) < 2:
            return f"\n  [{Ink.FAINT}]not enough sessions to draw a chart[/]\n"

        # Only as many sessions as there are columns, newest kept. Squeezing a
        # year into eighty columns loses the detail the chart exists to show.
        width = max(24, self.frame - 14)
        bars = view.bars[-width:]
        rows = candles(bars, rows=self.CHART_ROWS)
        low = min(b.low for b in bars)
        high = max(b.high for b in bars)
        axis = price_axis(low, high, self.CHART_ROWS)

        lines = ["\n"]
        for row, label in zip(rows, axis, strict=True):
            tick = "├" if label else "│"
            line = f"  [{Ink.FAINT}]{tick}[/]{row}"
            if label:
                line += f"  [{Ink.FAINT}]─[/] [{Ink.DIM}]{label}[/]"
            lines.append(line)
        lines.append(f"  [{Ink.FAINT}]└{'─' * len(bars)}[/]")
        legend = f"[{Ink.GREEN}]┃[/][{Ink.FAINT}] up[/]   [{Ink.RED}]┃[/][{Ink.FAINT}] down[/]"
        label = view.sessions_label or f"{len(bars)} sessions"
        lines.append(f"   [{Ink.FAINT}]{label}[/]        {legend}\n")
        return "\n".join(lines)

    def _why(self) -> str:
        if not self._view.momentum:
            return ""
        return f"{section('why it ranks', width=self.frame)}\n  {self._view.momentum}\n"

    def _risk(self) -> str:
        rules = self._view.risk
        if not rules:
            return ""
        lines = [section("what would stop a trade", width=self.frame)]
        for rule in rules:
            meter = ""
            if rule.used is not None:
                filled = max(0, min(10, int(rule.used * 10)))
                meter = (
                    f"  [{Ink.INFRARED}]{'▰' * filled}[/]"
                    f"[{Ink.FAINT}]{'▱' * (10 - filled)}[/]"
                    f"  [{Ink.INFRARED}]{rule.used:.0%}[/]"
                )
            state = f"[{Ink.GREEN}]clear[/]" if rule.clear else f"[{Ink.RED}]blocking[/]"
            lines.append(
                f"  [{Ink.DIM}]{rule.rule:<18}[/][{Ink.INK}]{rule.detail:<26}[/]{meter}  {state}"
            )
        return "\n".join(lines) + "\n"

    def _thesis(self) -> str:
        if not self._view.thesis:
            return ""
        out = [section(f"thesis · {self._view.thesis_meta}", width=self.frame)]
        out.append(f"  [{Ink.INK}]{self._view.thesis}[/]")
        if self._view.invalidated_if:
            out.append(f"  [{Ink.DIM}]invalidated if[/] [{Ink.INK}]{self._view.invalidated_if}[/]")
        return "\n".join(out) + "\n"

    # -- actions ---------------------------------------------------------------

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_journal(self) -> None:
        self.app.push_screen("journal")

    def action_kill(self) -> None:
        self.app.push_screen("kill")
