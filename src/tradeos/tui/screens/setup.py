"""Setup — where a new install becomes a policy.

Three steps: say what this portfolio is for, let a model draft a starting
point, then confirm every enforceable field yourself. The third step is the
product's whole stance in miniature — the model proposes, you decide — so the
screen shows the draft as *suggestions on a form you own*, never as a fait
accompli you dismiss.

Guardrail clamps are displayed rather than applied quietly. If the model
wanted a 90% position cap and was held at 25%, you see that it asked.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Input, Static

from tradeos.runtime.onboarding import PolicyProposal
from tradeos.tui.base import WolfScreen, footer_bar
from tradeos.tui.glyphs import fmt_money, fmt_pct, truncate
from tradeos.tui.theme import ACRONYM, WORDMARK_BLOCK, Ink, key

#: (attribute, label, kind) — the enforceable fields a human must confirm.
FIELDS: tuple[tuple[str, str, str], ...] = (
    ("goals_text", "goals", "text"),
    ("target_allocations", "targets", "alloc"),
    ("target_cash_weight", "cash target", "pct"),
    ("time_horizon_years", "horizon (years)", "int"),
    ("max_position_pct", "max per position", "pct"),
    ("max_sector_pct", "max per sector", "pct"),
    ("min_cash_pct", "min cash floor", "pct"),
    ("max_order_value_usd", "max order value", "money"),
    ("max_orders_per_day", "max orders / day", "int"),
    ("max_daily_loss_pct", "max daily loss", "pct"),
    ("max_drawdown_pct", "max drawdown", "pct"),
)


class SetupScreen(WolfScreen):
    """First-run policy onboarding."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("down", "next_field", "next"),
        Binding("up", "prev_field", "previous"),
        Binding("e", "edit", "edit"),
        Binding("enter", "advance", "continue"),
        Binding("c", "confirm", "confirm"),
        Binding("escape", "cancel_edit", "cancel"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._step = "goals"  # goals -> drafting -> review -> done
        self._proposal: PolicyProposal | None = None
        self._index = 0
        self._editing = False
        self._error = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="setup"):
            yield Static("", id="setup-head")
            yield Static("", id="setup-body")
            yield Input(placeholder="", id="setup-input")
            yield Static("", id="setup-error")
            yield Static("", id="setup-footer")

    def on_mount(self) -> None:
        field = self.query_one("#setup-input", Input)
        field.placeholder = "e.g. steady long-term growth, mostly index funds, nothing risky"
        field.focus()
        self._paint()

    # -- steps -----------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._step == "goals":
            self._start_draft(event.value)
        elif self._editing:
            self._apply_edit(event.value)

    def _start_draft(self, goals: str) -> None:
        if not goals.strip():
            self._error = "say something about what this portfolio is for"
            self._paint()
            return
        self._error = ""
        self._step = "drafting"
        self._paint()
        self.run_worker(lambda: self._draft(goals), thread=True, exclusive=True)

    def _draft(self, goals: str) -> None:
        service = self.runtime.onboarding()
        proposal = service.propose(goals)
        self.app.call_from_thread(self._drafted, proposal)

    def _drafted(self, proposal: PolicyProposal) -> None:
        self._proposal = proposal
        self._step = "review"
        self.query_one("#setup-input", Input).display = False
        self._paint()

    # -- editing ---------------------------------------------------------------

    def _current_field(self) -> tuple[str, str, str]:
        return FIELDS[self._index % len(FIELDS)]

    def action_edit(self) -> None:
        if self._step != "review" or self._editing:
            return
        attr, label, kind = self._current_field()
        field = self.query_one("#setup-input", Input)
        field.display = True
        field.value = self._raw_value(attr, kind)
        field.placeholder = f"{label} — press enter to accept, esc to cancel"
        field.focus()
        self._editing = True
        self._paint()

    def action_cancel_edit(self) -> None:
        if not self._editing:
            return
        self._editing = False
        self.query_one("#setup-input", Input).display = False
        self._error = ""
        self._paint()

    def _raw_value(self, attr: str, kind: str) -> str:
        proposal = self._proposal
        assert proposal is not None
        value = getattr(proposal, attr)
        if kind == "alloc":
            return ", ".join(f"{s} {w * 100:g}" for s, w in sorted(value.items()))
        if kind == "pct":
            return f"{value * 100:g}"
        return str(value)

    def _apply_edit(self, raw: str) -> None:
        proposal = self._proposal
        assert proposal is not None
        attr, label, kind = self._current_field()
        try:
            setattr(proposal, attr, _parse(raw, kind))
        except (ValueError, InvalidOperation, ArithmeticError):
            self._error = f"{label}: could not read {raw!r}"
            self._paint()
            return
        self._error = ""
        self._editing = False
        self.query_one("#setup-input", Input).display = False
        self._paint()

    # -- actions ---------------------------------------------------------------

    def action_next_field(self) -> None:
        if self._step == "review" and not self._editing:
            self._index = (self._index + 1) % len(FIELDS)
            self._paint()

    def action_prev_field(self) -> None:
        if self._step == "review" and not self._editing:
            self._index = (self._index - 1) % len(FIELDS)
            self._paint()

    def action_advance(self) -> None:
        if self._step == "review" and not self._editing:
            self.action_confirm()

    def action_confirm(self) -> None:
        if self._step != "review" or self._editing or self._proposal is None:
            return
        problems = self._proposal.validation_errors()
        if problems:
            self._error = problems[0] if len(problems) == 1 else f"{len(problems)} problems below"
            self._paint()
            return
        self.runtime.onboarding().confirm(self._proposal)
        self._step = "done"
        self._paint()
        self.app.switch_screen("den")

    # -- rendering -------------------------------------------------------------

    def _paint(self) -> None:
        self.query_one("#setup-head", Static).update(self._head())
        self.query_one("#setup-body", Static).update(self._body())
        self.query_one("#setup-error", Static).update(
            f"\n  [{Ink.RED}]{self._error}[/]" if self._error else ""
        )
        self.query_one("#setup-footer", Static).update(self._footer())

    def _head(self) -> str:
        if self._step == "goals":
            block = "\n".join(
                f"    [{Ink.BRIGHT}]{line}[/]" for line in WORDMARK_BLOCK.splitlines()
            )
            return (
                f"\n{block}\n\n    [{Ink.AMBER}]{ACRONYM}[/]\n\n"
                f"    [{Ink.INK}]What is this portfolio for?[/]\n"
                f"    [{Ink.DIM}]Plain words. A model turns it into a draft policy, "
                f"and you confirm every field.[/]\n"
            )
        if self._step == "drafting":
            return f"\n  [{Ink.AMBER}]drafting a policy from your goals…[/]\n"
        return (
            f"\n  [{Ink.BRIGHT}]Review every field before anything activates.[/]\n"
            f"  [{Ink.DIM}]This becomes an enforceable policy — the risk engine reads "
            f"these numbers, not your intent.[/]\n"
        )

    def _body(self) -> str:
        proposal = self._proposal
        if self._step != "review" or proposal is None:
            return ""

        lines: list[str] = [""]
        for index, (attr, label, kind) in enumerate(FIELDS):
            selected = index == self._index
            marker = f"[{Ink.AMBER}]▸[/]" if selected else " "
            tint = Ink.BRIGHT if selected else Ink.INK
            lines.append(f"  {marker} [{Ink.DIM}]{label:<18}[/][{tint}]{self._show(attr, kind)}[/]")

        source = (
            f"[{Ink.CYAN}]drafted from your goals[/]"
            if proposal.drafted_by_model
            else f"[{Ink.FAINT}]conservative defaults — no model was available[/]"
        )
        lines += ["", f"  {source}"]

        if proposal.adjustments:
            lines.append(f"\n  [{Ink.AMBER}]the draft asked for wider limits; held at these:[/]")
            for adjustment in proposal.adjustments:
                lines.append(
                    f"    [{Ink.FAINT}]· {truncate(adjustment.describe(), self.frame - 6)}[/]"
                )

        if proposal.interpretation_notes:
            lines.append(f"\n  [{Ink.DIM}]what it understood:[/]")
            for note in proposal.interpretation_notes:
                lines.append(f"    [{Ink.FAINT}]· {truncate(note, self.frame - 6)}[/]")

        problems = proposal.validation_errors()
        if problems:
            lines.append(f"\n  [{Ink.RED}]fix before confirming:[/]")
            for problem in problems:
                lines.append(f"    [{Ink.RED}]· {truncate(problem, self.frame - 6)}[/]")

        lines.append(
            f"\n  [{Ink.FAINT}]mode is always paper at setup; moving up the ladder "
            f"is a separate, deliberate step[/]"
        )
        return "\n".join(lines)

    def _show(self, attr: str, kind: str) -> str:
        proposal = self._proposal
        assert proposal is not None
        value = getattr(proposal, attr)
        if kind == "alloc":
            if not value:
                return "— none set"
            return " · ".join(f"{s} {fmt_pct(w)}" for s, w in sorted(value.items()))
        if kind == "pct":
            return fmt_pct(value)
        if kind == "money":
            return fmt_money(value)
        if kind == "text":
            text = str(value).strip()
            return (text[:56] + "…") if len(text) > 57 else (text or "—")
        return str(value)

    def _footer(self) -> str:
        if self._step == "goals":
            return footer_bar(f"[{Ink.DIM}]type your goals, then press[/] [{Ink.AMBER}]⏎[/]")
        if self._step == "drafting":
            return footer_bar(f"[{Ink.DIM}]asking the model…[/]")
        if self._editing:
            return footer_bar(f"{key('⏎', ' accept')}  {key('esc', ' cancel')}")
        return footer_bar(
            "  ".join((key("↑↓", " field"), key("e", "dit"), key("c", "onfirm & activate")))
        )


def _parse(raw: str, kind: str) -> object:
    raw = raw.strip()
    if kind == "pct":
        return Decimal(raw.rstrip("%")) / 100
    if kind == "money":
        return Decimal(raw.lstrip("$").replace(",", ""))
    if kind == "int":
        return int(raw)
    if kind == "alloc":
        allocations: dict[str, Decimal] = {}
        for chunk in raw.replace(",", " ").split():
            if chunk.replace(".", "", 1).isdigit() and allocations:
                symbol = next(reversed(allocations))
                allocations[symbol] = Decimal(chunk) / 100
            else:
                allocations[chunk.upper()] = Decimal("0")
        return allocations
    return raw
