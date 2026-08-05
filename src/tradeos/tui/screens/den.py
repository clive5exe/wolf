"""The den — home. Every other screen is one keystroke away and one esc back.

One row answers five questions per holding: how much, how far from plan (the
◆┼ gauge shows drift *spatially*, scaled so the end of the track is the point
at which the strategy trades), what it is costing, how fresh the price is, and
what it is worth. Freshness dots pulse while data is live and go hollow and
motionless when it is not — you notice the *absence* of movement.
"""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Static

from tradeos.runtime.views import DashboardView, HoldingView
from tradeos.tui.base import WolfScreen, footer_bar, header_bar
from tradeos.tui.glyphs import (
    fmt_age,
    fmt_money,
    fmt_pct,
    fmt_qty,
    fmt_signed,
    fmt_signed_pct,
    freshness_glyph,
    freshness_ink,
    paint_gauge,
    sparkline,
)
from tradeos.tui.motion import REFRESH_INTERVAL_S
from tradeos.tui.theme import Ink, badge, key, money_ink

_COLUMNS = (
    f"  [{Ink.DIM}]{'SYM':<6}{'QTY':>6}{'VALUE':>13}{'WEIGHT':>9}"
    f"  {'vs TARGET':<11}{'DRIFT':>7}{'uP&L':>11}  SRC[/]"
)


class DenScreen(WolfScreen):
    """The dashboard. Reads only ``runtime.dashboard()``."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("c", "run_cycle", "cycle"),
        Binding("enter", "open_verdict", "verdict"),
        Binding("j", "open_journal", "journal"),
        Binding("p", "open_policy", "policy"),
        Binding("k", "open_kill", "kill"),
        Binding("r", "refresh", "refresh"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._view: DashboardView | None = None
        self._pulse_on = True

    def compose(self) -> ComposeResult:
        with Vertical(id="den"):
            yield Static("", id="den-header")
            yield Static("", id="den-stats")
            yield Static("", id="den-equity")
            yield Static(_COLUMNS, id="den-columns")
            yield Static("", id="den-rows")
            yield Static("", id="den-concentration")
            yield Static("", id="den-last-cycle")
            yield Static("", id="den-footer")

    def on_mount(self) -> None:
        self.refresh_view()
        self.set_interval(REFRESH_INTERVAL_S, self.refresh_view)
        if not self.motion.calm:
            self.set_interval(self.motion.freshness_pulse / 2, self._pulse)

    # -- data ------------------------------------------------------------------

    def refresh_view(self) -> None:
        self._view = self.runtime.dashboard()
        self._paint()

    def _pulse(self) -> None:
        self._pulse_on = not self._pulse_on
        self._paint()

    # -- rendering -------------------------------------------------------------

    def _dot(self, *, live: bool) -> str:
        """A live source breathes; a stale one is hollow and still."""
        if not live:
            return f"[{Ink.RED}]○[/]"
        if self.motion.calm or self._pulse_on:
            return f"[{Ink.GREEN}]●[/]"
        return f"[{Ink.FAINT}]●[/]"

    def _paint(self) -> None:
        view = self._view
        if view is None:
            return

        mode = badge(view.mode, danger=view.mode not in {"PAPER", "READ_ONLY"})
        risk = (
            f"[{Ink.RED}]HALTED[/]"
            if view.kill_engaged
            else f"[{Ink.GREEN}]risk armed[/] [{Ink.DIM}]({view.rules_armed})[/]"
        )
        status = (
            f"{mode} [{Ink.DIM}]·[/] {risk} [{Ink.DIM}]·[/] {self._dot(live=not view.any_stale)} "
            f"[{Ink.DIM}]{view.as_of.strftime('%H:%MZ')}[/]"
        )
        self.query_one("#den-header", Static).update(header_bar(status))

        self.query_one("#den-stats", Static).update(self._stats_line(view))
        self.query_one("#den-equity", Static).update(self._equity_line(view))
        self.query_one("#den-rows", Static).update(self._rows(view))
        self.query_one("#den-concentration", Static).update(self._concentration(view))
        self.query_one("#den-last-cycle", Static).update(self._last_cycle(view))
        self.query_one("#den-footer", Static).update(
            footer_bar(
                "  ".join(
                    (
                        key("c", "ycle"),
                        key("⏎", "verdict"),
                        key("j", "ournal"),
                        key("p", "olicy"),
                        key("k", "ill"),
                    )
                ),
                f"[{Ink.DIM}]wolf is watching[/] {self._dot(live=True)}",
            )
        )

    def _stats_line(self, view: DashboardView) -> str:
        day = view.day_change
        if day is None:
            day_part = f"[{Ink.DIM}]day[/] [{Ink.FAINT}]— no session history[/]"
        else:
            arrow = "▲" if day > 0 else "▼" if day < 0 else "—"
            day_part = f"[{Ink.DIM}]day[/] [{money_ink(day)}]{arrow} {fmt_signed_pct(day)}[/]"
        dd = view.max_drawdown
        dd_part = (
            f"[{Ink.DIM}]max dd[/] [{Ink.INK}]{fmt_pct(dd)}[/]"
            if dd is not None
            else f"[{Ink.DIM}]max dd[/] [{Ink.FAINT}]—[/]"
        )
        cash_part = f"[{Ink.DIM}]cash[/] [{Ink.AMBER}]{fmt_pct(view.cash_weight)}[/]"
        nav = fmt_money(view.nav) if view.nav is not None else "unpriced"
        return (
            f"\n  [{Ink.DIM}]NAV[/] [{Ink.BRIGHT}]{nav}[/]    "
            f"{day_part}    {dd_part}    {cash_part}\n"
        )

    def _equity_line(self, view: DashboardView) -> str:
        points = [p.equity for p in view.equity]
        if len(points) < 2:
            return (
                f"  [{Ink.FAINT}]{'▁' * 24}[/]  "
                f"[{Ink.FAINT}]equity history builds as cycles run[/]\n"
            )
        spark = sparkline(points)
        return f"  [{Ink.CYAN}]{spark}[/]  [{Ink.FAINT}]{len(points)} equity snapshots[/]\n"

    def _rows(self, view: DashboardView) -> str:
        lines: list[str] = []
        for holding in view.holdings:
            lines.append(self._holding_row(holding, view.drift_threshold))
        lines.append(self._cash_row(view))
        return "\n".join(lines)

    def _holding_row(self, holding: HoldingView, threshold: Decimal) -> str:
        pnl = holding.unrealized_pnl
        pnl_text = fmt_signed(pnl) if pnl is not None else "—"
        dot = self._dot(live=not holding.is_stale)
        if holding.is_stale:
            dot = f"[{freshness_ink(holding.quote_age_s, holding.quote_ttl_s)}]"
            dot += f"{freshness_glyph(holding.quote_age_s, holding.quote_ttl_s)}[/]"
        drift_tint = Ink.AMBER if _is_notable(holding.drift, threshold) else Ink.DIM
        return (
            f"  [{Ink.BRIGHT}]{holding.symbol:<6}[/]"
            f"[{Ink.INK}]{fmt_qty(holding.quantity):>6}[/]"
            f"[{Ink.INK}]{fmt_money(holding.value):>13}[/]"
            f"[{Ink.INK}]{fmt_pct(holding.weight):>9}[/]"
            f"  {paint_gauge(holding.drift, full_scale=threshold)}   "
            f"[{drift_tint}]{fmt_signed_pct(holding.drift):>7}[/]"
            f"[{money_ink(pnl)}]{pnl_text:>11}[/]  {dot}"
        )

    def _cash_row(self, view: DashboardView) -> str:
        """Cash carries a floor, not a target — so it gets a floor readout, not a gauge.

        Rendering ``min_cash_pct`` as drift would report healthy compliance as a
        deviation, which is precisely backwards.
        """
        above = view.cash_above_floor
        if view.cash_floor is None:
            status = f"[{Ink.FAINT}]{'no floor':<12}[/]"
        elif above:
            status = f"[{Ink.GREEN}]{'above floor':<12}[/]"
        else:
            status = f"[{Ink.RED}]{'BELOW FLOOR':<12}[/]"
        floor_text = f"min {fmt_pct(view.cash_floor)}" if view.cash_floor is not None else "—"
        return (
            f"  [{Ink.DIM}]{'CASH':<6}{'':>6}[/]"
            f"[{Ink.INK}]{fmt_money(view.cash):>13}[/]"
            f"[{Ink.INK}]{fmt_pct(view.cash_weight):>9}[/]"
            f"  {status}[{Ink.DIM}]{floor_text:>7}[/]"
            f"[{Ink.FAINT}]{'—':>11}[/]"
        )

    def _concentration(self, view: DashboardView) -> str:
        hhi = f"{view.hhi:.3f}" if view.hhi is not None else "—"
        age = fmt_age(view.oldest_quote_age_s)
        return (
            f"\n  [{Ink.FAINT}]◆ current · ┼ target · track ends at the "
            f"{fmt_pct(view.drift_threshold)} rebalance band[/]\n"
            f"  [{Ink.DIM}]top-3[/] [{Ink.AMBER}]{fmt_pct(view.top3_concentration)}[/] "
            f"[{Ink.DIM}]· hhi {hhi} · oldest quote {age}[/]"
        )

    def _last_cycle(self, view: DashboardView) -> str:
        record = view.last_cycle
        if record is None:
            return (
                f"\n  [{Ink.DIM}]no decisions yet — press[/] "
                f"[{Ink.AMBER}]c[/] [{Ink.DIM}]to run a paper cycle[/]\n"
            )
        tint = Ink.RED if record.veto_reasons else Ink.GREEN
        rules = (
            f"[{Ink.DIM}]verdict[/] [{tint}]{record.rules_passed}/{record.rules_total}[/]"
            if record.rules_total
            else f"[{Ink.DIM}]no verdict[/]"
        )
        thesis = (
            f" [{Ink.DIM}]·[/] [{Ink.CYAN}]thesis {record.thesis.confidence}[/]"
            if record.thesis and record.thesis.confidence is not None
            else ""
        )
        return (
            f"\n  [{Ink.DIM}]last cycle {record.occurred_at.strftime('%H:%M:%S')} —[/] "
            f"[{tint}]{record.headline}[/][{Ink.DIM}],[/] {rules}{thesis}\n"
        )

    # -- actions ---------------------------------------------------------------

    def action_refresh(self) -> None:
        self.refresh_view()

    def action_run_cycle(self) -> None:
        self.app.push_screen("cycle")

    def action_open_verdict(self) -> None:
        if self._view is not None and self._view.last_cycle is not None:
            self.wolf.focused_cycle_id = self._view.last_cycle.correlation_id
            self.app.push_screen("verdict")
        else:
            self.notify("no decision to inspect yet — run a cycle first", severity="warning")

    def action_open_journal(self) -> None:
        self.app.push_screen("journal")

    def action_open_kill(self) -> None:
        self.app.push_screen("kill")

    def action_open_policy(self) -> None:
        policy = self.runtime.active_policy()
        if policy is None:
            self.notify("no active policy — run `wolf policy-init-sample`", severity="warning")
            return
        targets = ", ".join(f"{t.symbol} {fmt_pct(t.weight)}" for t in policy.target_allocations)
        self.notify(
            f"policy v{policy.version} · mode {policy.mode.value} · {targets}",
            title="investment policy",
        )


def _is_notable(drift: Decimal | None, threshold: Decimal) -> bool:
    """Highlight drift once it is at least halfway to the action band."""
    if drift is None or threshold <= 0:
        return False
    return abs(drift) >= threshold / 2
