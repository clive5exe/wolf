"""The decision cycle, watchable as it happens.

Transparency as theatre. The pipeline tracker makes the architecture visible:
stages complete left to right, and the model is provably *one box* with
deterministic walls on either side. A deterministic cycle skips the THESIS
stage outright and costs nothing — which the screen says, in those words.

The cycle runs on a worker thread and reports through the facade's progress
observer, which cannot alter what the cycle decides.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Static

from tradeos.runtime.cycle import CycleOutcome
from tradeos.runtime.progress import STAGE_ORDER, CycleStage, ProgressUpdate, StageState
from tradeos.tui.base import WolfScreen, footer_bar
from tradeos.tui.motion import spinner_frame
from tradeos.tui.theme import Ink, key

_STATE_INK = {
    StageState.PENDING: Ink.FAINT,
    StageState.RUNNING: Ink.AMBER,
    StageState.DONE: Ink.GREEN,
    StageState.SKIPPED: Ink.DIM,
    StageState.FAILED: Ink.RED,
}
_STATE_MARK = {
    StageState.PENDING: "·",
    StageState.DONE: "✓",
    StageState.SKIPPED: "–",
    StageState.FAILED: "✗",
}


class CycleScreen(WolfScreen):
    """Live pipeline view for one decision cycle."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "back", "den"),
        Binding("enter", "open_verdict", "verdict"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._states: dict[CycleStage, StageState] = dict.fromkeys(STAGE_ORDER, StageState.PENDING)
        self._log_lines: list[str] = []
        self._tick = 0
        self._correlation_id = ""
        self._outcome: CycleOutcome | None = None
        self._cycle_running = True

    def compose(self) -> ComposeResult:
        with Vertical(id="cycle"):
            yield Static("", id="cycle-title")
            yield Static("", id="cycle-pipeline")
            yield Static("", id="cycle-log")
            yield Static("", id="cycle-outcome")
            yield Static("", id="cycle-footer")

    def on_mount(self) -> None:
        self._paint()
        if not self.motion.calm:
            self.set_interval(self.motion.spinner_frame, self._spin)
        # Deferred to after the first refresh: the worker calls back onto the
        # UI thread, which is not yet pumping messages during on_mount.
        self.call_after_refresh(self._start_worker)

    def _start_worker(self) -> None:
        self.run_worker(self._run_cycle, thread=True, exclusive=True)

    # -- worker ----------------------------------------------------------------

    def _run_cycle(self) -> None:
        """Runs off the UI thread; every update marshals back via call_from_thread."""
        outcome = self.runtime.run_cycle(trigger="tui", progress=self._on_progress)
        self.app.call_from_thread(self._finish, outcome)

    def _on_progress(self, update: ProgressUpdate) -> None:
        self.app.call_from_thread(self._apply, update)

    def _apply(self, update: ProgressUpdate) -> None:
        self._correlation_id = update.correlation_id
        self._states[update.stage] = update.state
        if update.state != StageState.RUNNING:
            mark = _STATE_MARK.get(update.state, "·")
            tint = _STATE_INK[update.state]
            stamp = update.at.strftime("%H:%M:%S.%f")[:-3]
            self._log_lines.append(
                f"  [{Ink.FAINT}]{stamp}[/]  [{tint}]{mark}[/] "
                f"[{Ink.DIM}]{update.stage.value:<9}[/] [{Ink.INK}]{update.detail}[/]"
            )
        self._paint()

    def _finish(self, outcome: CycleOutcome) -> None:
        self._outcome = outcome
        self._cycle_running = False
        self.wolf.focused_cycle_id = outcome.correlation_id
        self._paint()

    def _spin(self) -> None:
        if not self._cycle_running:
            return
        self._tick += 1
        self._render_pipeline()

    # -- rendering -------------------------------------------------------------

    def _paint(self) -> None:
        cid = self._correlation_id[:8] or "…"
        self.query_one("#cycle-title", Static).update(
            f"\n  [{Ink.DIM}]CYCLE[/] [{Ink.BRIGHT}]{cid}[/] "
            f"[{Ink.DIM}]· trigger tui · policy pinned at dispatch[/]\n"
        )
        self._render_pipeline()
        self.query_one("#cycle-log", Static).update("\n".join(self._log_lines))
        self.query_one("#cycle-outcome", Static).update(self._outcome_block())
        note = key("⏎", " verdict") if self._outcome is not None else ""
        self.query_one("#cycle-footer", Static).update(
            footer_bar(f"{key('esc', ' den')}  {note}".strip(), width=self.frame)
        )

    def _render_pipeline(self) -> None:
        labels: list[str] = []
        marks: list[str] = []
        for stage in STAGE_ORDER:
            state = self._states[stage]
            tint = _STATE_INK[state]
            name = stage.value.upper()
            labels.append(f"[{tint}]{name:^9}[/]")
            if state == StageState.RUNNING:
                glyph = spinner_frame(self._tick) if not self.motion.calm else "▸"
                marks.append(f"[{Ink.AMBER}]{glyph:^9}[/]")
            else:
                marks.append(f"[{tint}]{_STATE_MARK.get(state, '·'):^9}[/]")
        joiner = f"[{Ink.FAINT}]──[/]"
        self.query_one("#cycle-pipeline", Static).update(
            f"  {joiner.join(labels)}\n  {'   '.join(marks)}\n"
        )

    def _outcome_block(self) -> str:
        if self._outcome is None:
            return (
                f"\n  [{Ink.DIM}]cost so far[/] [{Ink.BRIGHT}]$0.00[/] "
                f"[{Ink.DIM}]· deterministic stages are free; only THESIS calls a model[/]"
            )
        outcome = self._outcome
        tint = Ink.GREEN if outcome.status == "completed" else Ink.AMBER
        if outcome.status == "aborted":
            tint = Ink.RED
        lines = [
            "",
            f"  [{tint}]{outcome.status.replace('_', ' ')}[/] [{Ink.DIM}]— {outcome.reason}[/]",
            f"  [{Ink.DIM}]approved[/] [{Ink.BRIGHT}]{outcome.approved_actions}[/] "
            f"[{Ink.DIM}]· vetoed[/] [{Ink.BRIGHT}]{outcome.vetoed_actions}[/]",
        ]
        for fill in outcome.fills:
            lines.append(f"  [{Ink.GREEN}]▸[/] [{Ink.INK}]{fill}[/]")
        return "\n".join(lines)

    # -- actions ---------------------------------------------------------------

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_open_verdict(self) -> None:
        if self._outcome is None:
            self.notify("cycle still running", severity="information")
            return
        self.app.push_screen("verdict")
