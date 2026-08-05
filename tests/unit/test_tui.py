"""TUI smoke tests via Textual Pilot (headless)."""

from __future__ import annotations

import pytest
from textual.widgets import DataTable

from tradeos.notifications.base import NullNotifier
from tradeos.runtime.facade import RuntimeConfig, TradeOSRuntime
from tradeos.tui.app import TradeOSApp


@pytest.mark.asyncio
async def test_dashboard_boots_and_refreshes() -> None:
    runtime = TradeOSRuntime(RuntimeConfig(in_memory=True, notifier=NullNotifier()))
    app = TradeOSApp(runtime)
    async with app.run_test() as pilot:
        table = app.query_one("#positions", DataTable)
        assert table.row_count >= 1  # at least the CASH row
        await pilot.press("r")  # refresh must not crash


@pytest.mark.asyncio
async def test_dashboard_shows_positions_after_cycle() -> None:
    runtime = TradeOSRuntime(RuntimeConfig(in_memory=True, notifier=NullNotifier()))
    runtime.ensure_sample_policy()
    runtime.run_cycle(trigger="tui-test")
    app = TradeOSApp(runtime)
    async with app.run_test():
        table = app.query_one("#positions", DataTable)
        assert table.row_count >= 6  # 5 positions + CASH row
