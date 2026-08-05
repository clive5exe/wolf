"""Verdict — where the thesis meets the wall.

The page reads in the exact order the system works: thesis on top, the rule
wall below, receipt at the bottom. Nothing is summarised away — every rule is
listed, every time, including the ones that passed and the advisory ones that
did not veto. A veto stops the cascade dead on the red ✗.

In a future approval mode this same screen gains exactly two keys (approve /
reject) and nothing else changes, so the trust built here transfers intact.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Static

from tradeos.runtime.journal import ActionVerdict, CycleRecord
from tradeos.tui.base import WolfScreen, footer_bar
from tradeos.tui.glyphs import fmt_completeness, fmt_money, fmt_qty, truncate
from tradeos.tui.theme import Ink, key

# Three columns wide enough for the longest rule id (concentration_advisory).
# Abbreviating rule names would defeat the point of listing every rule.
_RULES_PER_ROW = 3
_RULE_WIDTH = 25


class VerdictScreen(WolfScreen):
    """Thesis, the full rule grid, and the execution receipt for one decision."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "back", "den"),
        Binding("down", "next_order", "next order"),
        Binding("up", "prev_order", "previous order"),
        Binding("x", "show_context", "context package"),
        Binding("j", "open_journal", "journal"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._record: CycleRecord | None = None
        self._index = 0
        self._revealed_rules = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="verdict"):
            yield Static("", id="verdict-order")
            yield Static("", id="verdict-thesis")
            yield Static("", id="verdict-rules-head")
            yield Static("", id="verdict-rules")
            yield Static("", id="verdict-execution")
            yield Static("", id="verdict-footer")

    def on_mount(self) -> None:
        cycle_id = self.wolf.focused_cycle_id
        self._record = (
            self.runtime.cycle_detail(cycle_id) if cycle_id else self.runtime.latest_cycle()
        )
        self._start_cascade()

    def _start_cascade(self) -> None:
        """Rules land one by one — mechanical, but slow enough to read as checks."""
        verdict = self._current_verdict()
        total = len(verdict.results) if verdict is not None else 0
        if self.motion.calm or total == 0:
            self._revealed_rules = total
            self._paint()
            return
        self._revealed_rules = 0
        self._paint()
        self.set_interval(self.motion.tick_stagger, self._reveal_next_rule)

    def _reveal_next_rule(self) -> None:
        verdict = self._current_verdict()
        if verdict is None or self._revealed_rules >= len(verdict.results):
            return
        self._revealed_rules += 1
        self._render_rules()

    # -- data ------------------------------------------------------------------

    def _current_verdict(self) -> ActionVerdict | None:
        if self._record is None or not self._record.verdicts:
            return None
        self._index = max(0, min(self._index, len(self._record.verdicts) - 1))
        return self._record.verdicts[self._index]

    # -- rendering -------------------------------------------------------------

    def _paint(self) -> None:
        self._render_order()
        self._render_thesis()
        self._render_rules()
        self._render_execution()
        self._render_footer()

    def _render_order(self) -> None:
        record, verdict = self._record, self._current_verdict()
        if record is None:
            self.query_one("#verdict-order", Static).update(
                f"\n  [{Ink.DIM}]no decision recorded yet — run a cycle from the den[/]\n"
            )
            return
        if verdict is None:
            self.query_one("#verdict-order", Static).update(
                f"\n  [{Ink.BRIGHT}]NO ACTION[/]\n"
                f"  [{Ink.DIM}]{truncate(record.reason, 74)}[/]\n"
                f"  [{Ink.FAINT}]a decision not to trade is recorded, cited, "
                f"and replayable like any fill[/]\n"
            )
            return
        total = len(record.verdicts)
        price = next(
            (f.fill_price for f in record.fills if f.symbol == verdict.symbol),
            None,
        )
        # A vetoed order never reached a broker, so it has no price. Printing
        # "@ — ≈ —" would imply a fill that was attempted and came back empty.
        if price is not None and verdict.quantity is not None:
            pricing = f"@ {fmt_money(price)} ≈ {fmt_money(price * verdict.quantity)} · "
        else:
            pricing = "· not executed · "
        self.query_one("#verdict-order", Static).update(
            f"\n  [{Ink.BRIGHT}]{verdict.side.upper()} {fmt_qty(verdict.quantity)} "
            f"{verdict.symbol}[/] [{Ink.DIM}]{pricing}"
            f"{record.strategy} · order {self._index + 1} of {total}[/]\n"
        )

    def _render_thesis(self) -> None:
        record = self._record
        widget = self.query_one("#verdict-thesis", Static)
        if record is None:
            widget.update("")
            return
        thesis = record.thesis
        if thesis is None:
            widget.update(
                f"{self._section('thesis')}\n"
                f"  [{Ink.DIM}]deterministic cycle — no model was called, so there is "
                f"no thesis to show.[/]\n"
                f"  [{Ink.FAINT}]the rebalance rationale below is the whole reasoning.[/]\n"
                f"  [{Ink.INK}]{truncate(record.verdicts[0].rationale, 70)}[/]\n"
                if record.verdicts
                else (
                    f"{self._section('thesis')}\n"
                    f"  [{Ink.DIM}]deterministic cycle — no model call.[/]\n"
                )
            )
            return
        head = self._section(
            f"thesis[/] [{Ink.DIM}]· confidence[/] [{Ink.AMBER}]{thesis.confidence}[/] "
            f"[{Ink.DIM}]· {len(thesis.citations)} citations"
        )
        lines = [head]
        if thesis.bull_case:
            lines.append(f"  [{Ink.GREEN}]bull[/]  [{Ink.INK}]{truncate(thesis.bull_case, 68)}[/]")
        if thesis.bear_case:
            lines.append(f"  [{Ink.RED}]bear[/]  [{Ink.INK}]{truncate(thesis.bear_case, 68)}[/]")
        if thesis.invalidation_conditions:
            conditions = " · ".join(thesis.invalidation_conditions)
            lines.append(
                f"  [{Ink.AMBER}]void if[/]  [{Ink.INK}]{truncate(conditions, 64)}[/] "
                f"[{Ink.DIM}]\\[watching][/]"
            )
        if thesis.data_gaps:
            gaps = " · ".join(thesis.data_gaps)
            lines.append(f"  [{Ink.DIM}]gaps[/]  [{Ink.FAINT}]{truncate(gaps, 68)}[/]")
        lines.append("")
        widget.update("\n".join(lines))

    def _render_rules(self) -> None:
        verdict = self._current_verdict()
        head_widget = self.query_one("#verdict-rules-head", Static)
        body_widget = self.query_one("#verdict-rules", Static)
        if verdict is None:
            head_widget.update("")
            body_widget.update("")
            return

        passed, total = verdict.rules_passed, verdict.rules_total
        tint = Ink.GREEN if verdict.approved else Ink.RED
        label = "PASS" if verdict.approved else "VETO"
        head_widget.update(
            self._section(f"risk verdict ·[/] [{tint} bold]{passed}/{total} {label}[/][{Ink.DIM}]")
        )

        # Every result is shown, including on a veto. The engine evaluated all of
        # them, so hiding the rest would summarise away audit information on the
        # one screen whose entire purpose is to summarise nothing. The veto is
        # made unmissable instead: red ✗, VETO in the header, and a detail line.
        cells: list[str] = []
        for rule in verdict.results[: self._revealed_rules]:
            if rule.is_veto:
                mark, mark_ink, name_ink = "✗", Ink.RED, Ink.RED
            elif rule.is_advisory_flag:
                mark, mark_ink, name_ink = "◇", Ink.AMBER, Ink.DIM
            else:
                mark, mark_ink, name_ink = "✓", Ink.GREEN, Ink.DIM
            name = truncate(rule.rule_id, _RULE_WIDTH - 3)
            cells.append(f"[{mark_ink}]{mark}[/] [{name_ink}]{name:<{_RULE_WIDTH - 2}}[/]")

        rows: list[str] = []
        for start in range(0, len(cells), _RULES_PER_ROW):
            rows.append("  " + "".join(cells[start : start + _RULES_PER_ROW]))

        # Explain the count: the engine's configured rules, plus the idempotency
        # check that only exists once a proposal does. Otherwise "21/21" here and
        # "20 armed" on the den look like a contradiction.
        configured = len(self.runtime.risk_rule_ids())
        extra = max(0, total - configured)
        if extra:
            rows.append(
                f"  [{Ink.FAINT}]{configured} policy rules + {extra} per-proposal "
                f"idempotency check — all run, every time[/]"
            )

        for rule in verdict.results[: self._revealed_rules]:
            if rule.is_veto:
                rows.append(
                    f"  [{Ink.RED}]✗ {rule.rule_id}[/] [{Ink.DIM}]— {rule.message}[/]"
                    f"\n    [{Ink.FAINT}]observed {rule.observed} · limit {rule.limit}[/]"
                )
            elif rule.is_advisory_flag:
                rows.append(
                    f"  [{Ink.FAINT}]◇ advisory, non-blocking: {rule.rule_id} — "
                    f"{rule.message} (recorded, not vetoed)[/]"
                )
        body_widget.update("\n".join(rows) + "\n")

    def _render_execution(self) -> None:
        record = self._record
        widget = self.query_one("#verdict-execution", Static)
        if record is None or not record.fills:
            widget.update("")
            return
        verdict = self._current_verdict()
        symbol = verdict.symbol if verdict else ""
        lines = [self._section("paper execution")]
        for fill in record.fills:
            if symbol and fill.symbol != symbol:
                continue
            if not fill.filled:
                lines.append(
                    f"  [{Ink.RED}]NOT FILLED[/]  [{Ink.DIM}]{fill.symbol} — {fill.note}[/]"
                )
                continue
            # Slippage is always a cost, whichever side we traded: a buy fills
            # above the quote, a sell below it. Signing it would paint half of
            # them green, which reads as a gain.
            drag = fill.slippage_drag
            cost_text = (
                f" [{Ink.DIM}](slippage {fill.slippage_bps}bps · cost {fmt_money(drag)})[/]"
                if drag is not None
                else ""
            )
            lines.append(
                f"  [{Ink.GREEN} bold]FILLED[/]  [{Ink.INK}]{fmt_qty(fill.quantity)} "
                f"{fill.symbol} @ {fmt_money(fill.fill_price)}[/]{cost_text} "
                f"[{Ink.FAINT}]{fill.client_order_id[:10]}[/] [{Ink.GREEN}]✓[/]"
            )
        lines.append("")
        widget.update("\n".join(lines))

    def _render_footer(self) -> None:
        record = self._record
        count = len(record.verdicts) if record else 0
        keys = [key("esc", " den")]
        if count > 1:
            keys.insert(0, key("↑↓", f" orders 1-{count}"))
        keys.append(key("x", " context"))
        keys.append(key("j", "ournal"))
        self.query_one("#verdict-footer", Static).update(
            footer_bar("  ".join(keys), width=self.frame)
        )

    # -- actions ---------------------------------------------------------------

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_next_order(self) -> None:
        if self._record and self._index < len(self._record.verdicts) - 1:
            self._index += 1
            self._start_cascade()

    def action_prev_order(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._start_cascade()

    def action_open_journal(self) -> None:
        self.app.push_screen("journal")

    def action_show_context(self) -> None:
        record = self._record
        if record is None:
            return
        self.notify(
            f"package {record.context_package_id[:10]} · {record.context_items} items · "
            f"completeness {fmt_completeness(record.context_completeness)}",
            title="what we knew",
        )
