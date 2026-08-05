"""TradeOS dashboard TUI (Textual).

Interface discipline: everything on screen comes from the TradeOSRuntime
facade; keys send commands back through it. Freshness/mode are always visible.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, RichLog, Static

from tradeos.runtime.facade import RuntimeConfig, TradeOSRuntime


class TradeOSApp(App[None]):
    TITLE = "TradeOS"
    SUB_TITLE = "paper portfolio runtime — experimental, not investment advice"

    CSS = """
    #mode-banner {
        dock: top;
        height: 1;
        background: $primary-darken-2;
        color: $text;
        text-align: center;
        text-style: bold;
    }
    #positions { height: 1fr; }
    #activity {
        height: 12;
        border-top: solid $primary;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("c", "run_cycle", "Run paper cycle"),
        Binding("k", "kill", "Kill switch"),
    ]

    def __init__(self, runtime: TradeOSRuntime | None = None) -> None:
        super().__init__()
        self._runtime = runtime or TradeOSRuntime(RuntimeConfig())

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="mode-banner")
        with Vertical():
            yield DataTable(id="positions")
            yield RichLog(id="activity", markup=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#positions", DataTable)
        table.add_columns("symbol", "value", "weight", "target", "drift", "unreal P&L")
        self._refresh_all()

    # -- actions ---------------------------------------------------------------

    def action_refresh(self) -> None:
        self._refresh_all()

    def action_run_cycle(self) -> None:
        self.run_worker(self._run_cycle_worker, thread=True, exclusive=True)

    def action_kill(self) -> None:
        if self._runtime.kill_switch.is_engaged():
            self._runtime.disengage_kill_switch()
        else:
            self._runtime.engage_kill_switch("engaged from TUI")
        self._refresh_all()

    # -- workers / internals ---------------------------------------------------

    def _run_cycle_worker(self) -> None:
        outcome = self._runtime.run_cycle(trigger="tui")
        self.call_from_thread(self._after_cycle, outcome.status, outcome.reason)

    def _after_cycle(self, status: str, reason: str) -> None:
        self.query_one("#activity", RichLog).write(f"cycle finished: [{status}] {reason}")
        self._refresh_all()

    def _refresh_all(self) -> None:
        self._refresh_banner()
        self._refresh_positions()
        self._refresh_activity()

    def _refresh_banner(self) -> None:
        policy = self._runtime.active_policy()
        mode = policy.mode.value.upper() if policy else "NO POLICY — onboarding required"
        kill = "  ·  KILL SWITCH ENGAGED" if self._runtime.kill_switch.is_engaged() else ""
        self.query_one("#mode-banner", Static).update(f"mode: {mode}{kill}")

    def _refresh_positions(self) -> None:
        stats = self._runtime.portfolio_stats()
        table = self.query_one("#positions", DataTable)
        table.clear()
        for row in stats.rows:
            table.add_row(
                row.symbol,
                f"${row.value:,.2f}",
                f"{row.weight:.2%}",
                f"{row.target_weight:.0%}" if row.target_weight is not None else "—",
                f"{row.drift:+.2%}" if row.drift is not None else "—",
                f"{row.unrealized_pnl:,.2f}" if row.unrealized_pnl is not None else "—",
            )
        cash_weight = f"{stats.cash_weight:.2%}" if stats.cash_weight is not None else "n/a"
        table.add_row("CASH", f"${stats.cash:,.2f}", cash_weight, "—", "—", "—")

    def _refresh_activity(self) -> None:
        log = self.query_one("#activity", RichLog)
        log.clear()
        for event in self._runtime.events_tail(12):
            log.write(
                f"{event.occurred_at.strftime('%H:%M:%S')}  {event.event_type.value}"
                + (f"  [{event.correlation_id[:8]}]" if event.correlation_id else "")
            )


if __name__ == "__main__":
    TradeOSApp().run()
