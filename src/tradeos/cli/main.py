"""WOLF CLI. Interfaces display state and send commands — nothing else.

The command is ``wolf``; the Python distribution stays ``tradeos`` because
the PyPI name ``wolf`` is already taken (see ADR-0012).
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

import tradeos
from tradeos.runtime.diagnostics import CheckStatus
from tradeos.runtime.facade import RuntimeConfig, TradeOSRuntime

app = typer.Typer(
    name="wolf",
    help="WOLF — wealth orchestration, local-first. Experimental — not investment advice.",
    no_args_is_help=True,
)
console = Console()

_STATUS_GLYPH = {
    CheckStatus.OK: "[green]✓[/]",
    CheckStatus.WARN: "[yellow]![/]",
    CheckStatus.FAIL: "[red]✗[/]",
}


def _runtime(*, notify: bool = False) -> TradeOSRuntime:
    notifier = None
    if notify:
        from tradeos.notifications.macos import MacNotifier  # macOS-only import

        notifier = MacNotifier()
    return TradeOSRuntime(RuntimeConfig(notifier=notifier))


@app.command()
def version() -> None:
    """Print the WOLF version."""
    console.print(
        f"[bold]W[/][#F0B45C]◉[/][bold]LF[/] {tradeos.__version__} — "
        "wealth orchestration, local-first\n"
        "experimental · paper trading · not investment advice"
    )


@app.command()
def doctor(
    full: bool = typer.Option(False, "--full", help="Include a live provider round-trip probe"),
) -> None:
    """Check the environment: platform, store, provider, policy, kill switch."""
    runtime = _runtime()
    checks = runtime.diagnostics(full=full)
    table = Table(title="wolf doctor", show_lines=False)
    table.add_column("")
    table.add_column("Check", style="bold")
    table.add_column("Detail")
    table.add_column("Fix hint", style="dim")
    for check in checks:
        table.add_row(_STATUS_GLYPH[check.status], check.name, check.detail, check.hint)
    console.print(table)
    if any(c.status == CheckStatus.FAIL for c in checks):
        raise typer.Exit(code=1)


@app.command()
def demo(
    cycles: int = typer.Option(1, help="Number of paper decision cycles to run"),
    notify: bool = typer.Option(False, "--notify", help="Send real macOS notifications"),
) -> None:
    """Run paper decision cycle(s) with the sample policy and demo quotes."""
    runtime = _runtime(notify=notify)
    policy = runtime.ensure_sample_policy()
    console.print(
        f"[bold]policy[/] v{policy.version} mode={policy.mode.value} "
        f"targets={len(policy.target_allocations)}"
    )
    for i in range(cycles):
        outcome = runtime.run_cycle(trigger=f"cli-demo-{i + 1}")
        console.print(
            f"[bold]cycle {i + 1}[/] [{outcome.status}] {outcome.reason} — "
            f"approved={outcome.approved_actions} vetoed={outcome.vetoed_actions}"
        )
        for fill in outcome.fills:
            console.print(f"   {fill}")
    _print_portfolio(runtime)


@app.command()
def portfolio() -> None:
    """Show paper portfolio allocations, drift, and concentration."""
    _print_portfolio(_runtime())


@app.command("events")
def events_cmd(limit: int = typer.Option(20, help="How many recent events")) -> None:
    """Tail the audit event log."""
    runtime = _runtime()
    table = Table(title=f"last {limit} events")
    table.add_column("event_id", style="dim")
    table.add_column("type", style="bold")
    table.add_column("occurred_at")
    table.add_column("correlation", style="dim")
    for event in runtime.events_tail(limit):
        table.add_row(
            event.event_id[:10],
            event.event_type.value,
            event.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
            (event.correlation_id or "")[:10],
        )
    console.print(table)


@app.command("policy-show")
def policy_show() -> None:
    """Show the active investment policy (the enforceable struct, not prose)."""
    policy = _runtime().active_policy()
    if policy is None:
        console.print("[yellow]no active policy — run `wolf policy-init-sample`[/]")
        raise typer.Exit(code=1)
    console.print_json(policy.model_dump_json(indent=2))


@app.command("policy-init-sample")
def policy_init_sample() -> None:
    """Create the sample paper-mode policy (refuses if one exists)."""
    runtime = _runtime()
    policy = runtime.policy_service.create_sample_policy()
    console.print(f"[green]created[/] sample policy v{policy.version} (mode={policy.mode.value})")


@app.command()
def kill(reason: str = typer.Argument(..., help="Why you are stopping everything")) -> None:
    """Engage the kill switch: all execution refused until `wolf unkill`."""
    _runtime().engage_kill_switch(reason)
    console.print("[red]kill switch ENGAGED[/] — execution refused everywhere")


@app.command()
def unkill() -> None:
    """Disengage the kill switch (manual, deliberate)."""
    _runtime().disengage_kill_switch()
    console.print("[green]kill switch disengaged[/]")


@app.command()
def tui(
    calm: bool = typer.Option(
        False, "--calm", help="Disable animation (reduced motion); no information is lost"
    ),
    skip_boot: bool = typer.Option(
        False, "--skip-boot", help="Go straight to the den, past the check cascade"
    ),
) -> None:
    """Enter the den — the full terminal interface."""
    from tradeos.tui.app import WolfApp

    WolfApp(
        _runtime(),
        calm=calm,
        start_screen="den" if skip_boot else "boot",
    ).run()


def _print_portfolio(runtime: TradeOSRuntime) -> None:
    stats = runtime.portfolio_stats()
    table = Table(title="paper portfolio")
    table.add_column("symbol", style="bold")
    table.add_column("value", justify="right")
    table.add_column("weight", justify="right")
    table.add_column("target", justify="right")
    table.add_column("drift", justify="right")
    table.add_column("unreal P&L", justify="right")
    for row in stats.rows:
        drift = f"{row.drift:+.2%}" if row.drift is not None else "—"
        target = f"{row.target_weight:.0%}" if row.target_weight is not None else "—"
        pnl = f"{row.unrealized_pnl:,.2f}" if row.unrealized_pnl is not None else "—"
        table.add_row(row.symbol, f"${row.value:,.2f}", f"{row.weight:.2%}", target, drift, pnl)
    console.print(table)
    cash_weight = f"{stats.cash_weight:.2%}" if stats.cash_weight is not None else "n/a"
    total = f"${stats.total_value:,.2f}" if stats.total_value is not None else "unpriced"
    console.print(f"cash ${stats.cash:,.2f} ({cash_weight}) · total {total}")
    if stats.top3_concentration is not None:
        console.print(f"top-3 concentration {stats.top3_concentration:.1%} · HHI {stats.hhi:.3f}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
