"""Screen tests via Textual Pilot (headless).

Screens run in ``calm`` mode here: animation is disabled, and every screen must
still show its complete final state. That is the contract — motion is always
redundant with a glyph or a number, never the only carrier of information.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

import pytest
from textual.screen import Screen
from textual.widgets import Static

from tradeos.notifications.base import NullNotifier
from tradeos.runtime.facade import RuntimeConfig, TradeOSRuntime
from tradeos.tui.app import WolfApp
from tradeos.tui.base import MAX_FRAME_WIDTH
from tradeos.tui.markup import plain
from tradeos.tui.screens.boot import BootScreen
from tradeos.tui.screens.cycle import CycleScreen
from tradeos.tui.screens.den import DenScreen
from tradeos.tui.screens.journal import JournalScreen
from tradeos.tui.screens.kill import KillScreen
from tradeos.tui.screens.verdict import VerdictScreen

SCREEN_CLASSES = (
    BootScreen,
    DenScreen,
    CycleScreen,
    VerdictScreen,
    JournalScreen,
    KillScreen,
)


@pytest.fixture
def runtime() -> Iterator[TradeOSRuntime]:
    rt = TradeOSRuntime(RuntimeConfig(in_memory=True, notifier=NullNotifier()))
    rt.ensure_sample_policy()
    yield rt


def screen_text(app: WolfApp) -> str:
    """All rendered text on the current screen, styles resolved away."""
    return "\n".join(plain(str(w.content)) for w in app.screen.query(Static))


class TestBootScreen:
    @pytest.mark.asyncio
    async def test_shows_every_check(self, runtime: TradeOSRuntime) -> None:
        app = WolfApp(runtime, calm=True, start_screen="boot")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            text = screen_text(app)
            for check in runtime.diagnostics():
                assert check.name in text

    @pytest.mark.asyncio
    async def test_enter_opens_the_den(self, runtime: TradeOSRuntime) -> None:
        app = WolfApp(runtime, calm=True, start_screen="boot")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, DenScreen)

    @pytest.mark.asyncio
    async def test_states_whether_the_environment_is_sound(self, runtime: TradeOSRuntime) -> None:
        app = WolfApp(runtime, calm=True, start_screen="boot")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            text = screen_text(app)
            assert "all systems nominal" in text or "environment check failed" in text


class TestDenScreen:
    @pytest.mark.asyncio
    async def test_shows_holdings_mode_and_nav(self, runtime: TradeOSRuntime) -> None:
        runtime.run_cycle(trigger="test")
        app = WolfApp(runtime, calm=True, start_screen="den")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            text = screen_text(app)
            assert "PAPER" in text
            for symbol in ("VTI", "AAPL", "MSFT", "JNJ", "XOM"):
                assert symbol in text
            assert "CASH" in text
            assert "$99,955.45" in text  # NAV, formatted

    @pytest.mark.asyncio
    async def test_cash_shows_a_floor_not_a_drift(self, runtime: TradeOSRuntime) -> None:
        """min_cash_pct is a floor; rendering it as drift would invert its meaning."""
        runtime.run_cycle(trigger="test")
        app = WolfApp(runtime, calm=True, start_screen="den")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            assert "above floor" in screen_text(app)

    @pytest.mark.asyncio
    async def test_empty_portfolio_invites_a_cycle_instead_of_lying(
        self, runtime: TradeOSRuntime
    ) -> None:
        app = WolfApp(runtime, calm=True, start_screen="den")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            assert "no decisions yet" in screen_text(app)

    @pytest.mark.asyncio
    async def test_j_opens_the_journal(self, runtime: TradeOSRuntime) -> None:
        app = WolfApp(runtime, calm=True, start_screen="den")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            assert isinstance(app.screen, JournalScreen)


class TestVerdictScreen:
    @pytest.mark.asyncio
    async def test_lists_every_rule_not_a_summary(self, runtime: TradeOSRuntime) -> None:
        runtime.run_cycle(trigger="test")
        app = WolfApp(runtime, calm=True, start_screen="verdict")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            text = screen_text(app)
            for rule_id in runtime.risk_rule_ids():
                assert rule_id in text, f"verdict screen hid rule {rule_id}"

    @pytest.mark.asyncio
    async def test_shows_the_execution_receipt(self, runtime: TradeOSRuntime) -> None:
        runtime.run_cycle(trigger="test")
        app = WolfApp(runtime, calm=True, start_screen="verdict")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            text = screen_text(app)
            assert "FILLED" in text
            assert "PASS" in text

    @pytest.mark.asyncio
    async def test_a_veto_still_lists_every_rule(self, runtime: TradeOSRuntime) -> None:
        """A veto must not truncate the audit trail — the engine ran all of them."""
        runtime.engage_kill_switch("testing the veto path")
        runtime.run_cycle(trigger="vetoed")
        app = WolfApp(runtime, calm=True, start_screen="verdict")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            text = screen_text(app)
            assert "VETO" in text
            assert "kill switch is engaged" in text
            for rule_id in runtime.risk_rule_ids():
                assert rule_id in text, f"veto view hid rule {rule_id}"

    @pytest.mark.asyncio
    async def test_a_vetoed_order_is_not_shown_as_priced(self, runtime: TradeOSRuntime) -> None:
        """It never reached a broker; a price would imply an attempted fill."""
        runtime.engage_kill_switch("testing")
        runtime.run_cycle(trigger="vetoed")
        app = WolfApp(runtime, calm=True, start_screen="verdict")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            text = screen_text(app)
            assert "not executed" in text
            assert "FILLED" not in text

    @pytest.mark.asyncio
    async def test_a_no_action_cycle_says_so_plainly(self, runtime: TradeOSRuntime) -> None:
        runtime.run_cycle(trigger="first")
        runtime.run_cycle(trigger="second")  # no-action
        app = WolfApp(runtime, calm=True, start_screen="verdict")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            assert "NO ACTION" in screen_text(app)

    @pytest.mark.asyncio
    async def test_arrow_keys_walk_the_orders(self, runtime: TradeOSRuntime) -> None:
        runtime.run_cycle(trigger="test")
        app = WolfApp(runtime, calm=True, start_screen="verdict")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            first = screen_text(app)
            await pilot.press("down")
            await pilot.pause()
            assert screen_text(app) != first


class TestJournalScreen:
    @pytest.mark.asyncio
    async def test_vetoes_and_no_actions_appear_beside_fills(self, runtime: TradeOSRuntime) -> None:
        runtime.run_cycle(trigger="first")  # fills
        runtime.run_cycle(trigger="second")  # no-action
        app = WolfApp(runtime, calm=True, start_screen="journal")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            text = screen_text(app)
            assert "5 fills" in text
            assert "no action" in text
            assert "2 decisions" in text

    @pytest.mark.asyncio
    async def test_empty_journal_explains_itself(self, runtime: TradeOSRuntime) -> None:
        app = WolfApp(runtime, calm=True, start_screen="journal")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            assert "nothing decided yet" in screen_text(app)

    @pytest.mark.asyncio
    async def test_enter_opens_that_decision(self, runtime: TradeOSRuntime) -> None:
        runtime.run_cycle(trigger="test")
        app = WolfApp(runtime, calm=True, start_screen="journal")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, VerdictScreen)


class TestKillScreen:
    @pytest.mark.asyncio
    async def test_k_reaches_the_kill_switch_from_the_den(self, runtime: TradeOSRuntime) -> None:
        app = WolfApp(runtime, calm=True, start_screen="den")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            await pilot.press("k")
            await pilot.pause()
            assert isinstance(app.screen, KillScreen)

    @pytest.mark.asyncio
    async def test_engaging_halts_execution(self, runtime: TradeOSRuntime) -> None:
        app = WolfApp(runtime, calm=True, start_screen="kill")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            assert not runtime.kill_switch.is_engaged()
            await pilot.press("k")
            await pilot.pause()
            assert runtime.kill_switch.is_engaged()
            assert "TRADING  HALTED" in screen_text(app)

    @pytest.mark.asyncio
    async def test_disengaging_takes_two_deliberate_presses(self, runtime: TradeOSRuntime) -> None:
        """One stray keystroke must never re-arm execution."""
        runtime.engage_kill_switch("test")
        app = WolfApp(runtime, calm=True, start_screen="kill")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            await pilot.press("u")
            await pilot.pause()
            assert runtime.kill_switch.is_engaged(), "one press must not disengage"
            await pilot.press("u")
            await pilot.pause()
            assert not runtime.kill_switch.is_engaged()

    @pytest.mark.asyncio
    async def test_names_who_engaged_it_and_why(self, runtime: TradeOSRuntime) -> None:
        runtime.engage_kill_switch("market data storm")
        app = WolfApp(runtime, calm=True, start_screen="kill")
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            text = screen_text(app)
            assert "market data storm" in text
            assert "wolf unkill" in text


class TestCycleScreen:
    @pytest.mark.asyncio
    async def test_runs_a_cycle_and_shows_every_stage(self, runtime: TradeOSRuntime) -> None:
        app = WolfApp(runtime, calm=True, start_screen="cycle")
        async with app.run_test(size=(96, 40)) as pilot:
            for _ in range(30):
                await pilot.pause()
            text = screen_text(app)
            for stage in ("OBSERVE", "RETRIEVE", "PROPOSE", "THESIS", "RISK", "EXECUTE"):
                assert stage in text
            assert "completed" in text

    @pytest.mark.asyncio
    async def test_a_deterministic_cycle_declares_it_cost_nothing(
        self, runtime: TradeOSRuntime
    ) -> None:
        app = WolfApp(runtime, calm=True, start_screen="cycle")
        async with app.run_test(size=(96, 40)) as pilot:
            for _ in range(30):
                await pilot.pause()
            assert "deterministic cycle" in screen_text(app)


class TestScreensDoNotShadowTextualInternals:
    """Regression guard for a bug class that silently breaks rendering.

    Defining ``_render`` stopped every screen painting; assigning
    ``self._running`` stopped them mounting at all. Neither raised, so only a
    structural check catches them.
    """

    #: Deliberate overrides of Textual's own extension points.
    ALLOWED: ClassVar[set[str]] = {
        "compose",
        "on_mount",
        "BINDINGS",
        "CSS",
        "DEFAULT_CSS",
        "TITLE",
        "SUB_TITLE",
        "AUTO_FOCUS",
    }

    @staticmethod
    def _metaclass_injected() -> set[str]:
        """Names Textual's metaclass adds to every subclass — not our doing."""

        class _Control(Screen[None]):
            pass

        return set(vars(_Control))

    @pytest.mark.parametrize("screen_cls", SCREEN_CLASSES, ids=lambda c: c.__name__)
    def test_methods_do_not_shadow_screen_attributes(self, screen_cls: type) -> None:
        injected = self._metaclass_injected()
        for name in vars(screen_cls):
            if name.startswith("__") or name in self.ALLOWED or name in injected:
                continue
            if name.startswith(("action_", "on_", "key_")):
                continue
            assert not hasattr(Screen, name), (
                f"{screen_cls.__name__}.{name} shadows Textual's Screen.{name} — "
                "rename it (this breaks rendering silently)"
            )

    @pytest.mark.parametrize("screen_cls", SCREEN_CLASSES, ids=lambda c: c.__name__)
    def test_init_does_not_assign_over_textual_state(self, screen_cls: type) -> None:
        init = screen_cls.__dict__.get("__init__")
        if init is None:
            return
        tree = ast.parse(textwrap.dedent(inspect.getsource(init)))
        baseline = set(vars(Screen()))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or not isinstance(node.ctx, ast.Store):
                continue
            if not (isinstance(node.value, ast.Name) and node.value.id == "self"):
                continue
            assert node.attr not in baseline, (
                f"{screen_cls.__name__}.__init__ assigns self.{node.attr}, which is "
                "Textual internal state — rename the attribute"
            )


class TestCalmMode:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("screen", ["boot", "den", "journal", "kill"])
    async def test_calm_mode_still_renders_complete_content(
        self, runtime: TradeOSRuntime, screen: str
    ) -> None:
        """Reduced motion must cost animation, never information."""
        runtime.run_cycle(trigger="test")
        app = WolfApp(runtime, calm=True, start_screen=screen)
        async with app.run_test(size=(96, 40)) as pilot:
            await pilot.pause()
            assert screen_text(app).strip()


class TestInterfaceDiscipline:
    def test_screens_import_only_the_facade_and_domain(self) -> None:
        """ARCHITECTURE §2: no TUI module may reach past the runtime facade."""
        forbidden = ("tradeos.brokers", "tradeos.providers", "tradeos.storage", "tradeos.risk")
        tui_dir = Path(__file__).resolve().parents[2] / "src" / "tradeos" / "tui"
        offenders: list[str] = []
        for path in tui_dir.rglob("*.py"):
            text = path.read_text()
            for module in forbidden:
                if f"import {module}" in text or f"from {module}" in text:
                    offenders.append(f"{path.name} imports {module}")
        assert not offenders, offenders


class TestResponsiveLayout:
    """Chrome is drawn into fixed-width strings, so width bugs show up as
    wrapped rows rather than exceptions — only a measured test catches them."""

    WIDTHS: ClassVar[list[int]] = [66, 72, 80, 96, 120, 160]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("width", WIDTHS)
    async def test_no_line_exceeds_the_terminal(self, runtime: TradeOSRuntime, width: int) -> None:
        runtime.run_cycle(trigger="test")
        app = WolfApp(runtime, calm=True, start_screen="den")
        async with app.run_test(size=(width, 30)) as pilot:
            await pilot.pause()
            for widget in app.screen.query(Static):
                for line in plain(str(widget.content)).splitlines():
                    assert len(line) <= width, (
                        f"line of {len(line)} cols overflows a {width}-col terminal: {line!r}"
                    )

    @pytest.mark.asyncio
    async def test_the_gauge_grows_with_the_terminal(self, runtime: TradeOSRuntime) -> None:
        """Spare width goes to drift resolution, not to whitespace."""
        runtime.run_cycle(trigger="test")

        async def gauge_len(width: int) -> int:
            app = WolfApp(runtime, calm=True, start_screen="den")
            async with app.run_test(size=(width, 30)) as pilot:
                await pilot.pause()
                rows = plain(str(app.screen.query_one("#den-rows", Static).content))
                vti = next(ln for ln in rows.splitlines() if ln.strip().startswith("VTI"))
                return sum(ch in "─◆┼◀▶" for ch in vti)

        assert await gauge_len(120) > await gauge_len(70)

    @pytest.mark.asyncio
    async def test_chrome_is_clamped_on_an_ultrawide_terminal(
        self, runtime: TradeOSRuntime
    ) -> None:
        """Past the clamp a seven-column table stops reading as a table."""
        app = WolfApp(runtime, calm=True, start_screen="den")
        async with app.run_test(size=(400, 30)) as pilot:
            await pilot.pause()
            header = plain(str(app.screen.query_one("#den-header", Static).content))
            assert len(header.rstrip()) <= MAX_FRAME_WIDTH

    @pytest.mark.asyncio
    async def test_resize_repaints_at_the_new_width(self, runtime: TradeOSRuntime) -> None:
        runtime.run_cycle(trigger="test")
        app = WolfApp(runtime, calm=True, start_screen="den")
        async with app.run_test(size=(70, 30)) as pilot:
            await pilot.pause()
            narrow = plain(str(app.screen.query_one("#den-header", Static).content))
            await pilot.resize_terminal(120, 30)
            await pilot.pause()
            wide = plain(str(app.screen.query_one("#den-header", Static).content))
            assert len(wide.rstrip()) > len(narrow.rstrip())
