"""A provider prompt is the only thing that leaves the machine (ASSUMPTIONS Q3).

Level A: relative quantities only — no dollar amounts, no share counts, no
account identifiers. These tests build real prompts from real state and assert
the rule holds, so a future change to the assembler, a strategy's phrasing, or
the prompt template cannot quietly widen what is sent.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tradeos.context.assembler import ContextAssembler
from tradeos.context.project import project_context
from tradeos.context.projection import CandidateLine, HoldingLine
from tradeos.domain.portfolio import PortfolioSnapshot
from tradeos.notifications.base import NullNotifier
from tradeos.providers.prompts import build_thesis_prompt
from tradeos.runtime.facade import RuntimeConfig, TradeOSRuntime
from tradeos.strategies.rebalance import TargetAllocationRebalance

#: Anything that is not a percentage and not a 0..1 ratio is an absolute.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?\s*%?")
_CURRENCY = re.compile(r"[$£€¥]|\b(?:usd|dollars?|cents?)\b", re.IGNORECASE)
#: ULIDs and ISO timestamps are opaque identifiers, not quantities.
_OPAQUE = re.compile(r"\b[0-9A-HJKMNP-TV-Z]{26}\b|\d{4}-\d{2}-\d{2}T[\d:.+\-]+")
#: Bracketed integers are structural markers in our own template — candidate
#: indices the model selects by, and the literal "confidence in [0,1]".
_TEMPLATE_MARKERS = re.compile(r"\[[\d,]+\]")


def absolutes_in(prompt: str) -> list[str]:
    """Every numeric token in a prompt that is not a ratio or a percentage."""
    stripped = _TEMPLATE_MARKERS.sub(" ", _OPAQUE.sub(" ", prompt))
    found = []
    for match in _NUMBER.finditer(stripped):
        token = match.group().strip()
        if token.endswith("%"):
            continue
        try:
            if abs(float(token.replace(",", ""))) < 1:
                continue
        except ValueError:
            continue
        found.append(token)
    return found


def build_real_prompt(runtime: TradeOSRuntime) -> str:
    policy = runtime.ensure_sample_policy()
    now = runtime._clock.now()
    account = runtime.broker.get_account()
    targets = {t.symbol: t.weight for t in policy.target_allocations}
    quotes = {s: q for s in targets if (q := runtime.broker.get_quote(s)) is not None}
    package = ContextAssembler().assemble(
        purpose="safety",
        account=account,
        quotes=quotes,
        required_symbols=tuple(targets),
        market_note="regular session",
        now=now,
        source_name=runtime.broker.name,
    )
    snapshot = PortfolioSnapshot(account=account, quotes=quotes, as_of=now)
    proposal = TargetAllocationRebalance().generate(
        snapshot=snapshot, policy=policy, package=package, now=now, correlation_id="safety"
    )
    context = project_context(
        package,
        snapshot=snapshot,
        targets=targets,
        candidates=proposal.actions,
        policy_summary="mode=paper",
        now=now,
    )
    return build_thesis_prompt(context)


@pytest.fixture
def runtime() -> TradeOSRuntime:
    return TradeOSRuntime(RuntimeConfig(in_memory=True, notifier=NullNotifier()))


class TestNoAbsolutesLeaveTheMachine:
    def test_a_fresh_portfolio_prompt_carries_no_absolutes(self, runtime: TradeOSRuntime) -> None:
        prompt = build_real_prompt(runtime)
        assert not absolutes_in(prompt), f"absolute values in prompt: {absolutes_in(prompt)}"
        assert not _CURRENCY.search(prompt)

    def test_a_funded_portfolio_prompt_carries_no_absolutes(self, runtime: TradeOSRuntime) -> None:
        """After trading, cash and share counts are large and varied — the case
        the old assembler leaked ($10,694.50 cash, 140 shares of VTI)."""
        runtime.ensure_sample_policy()
        runtime.run_cycle(trigger="fund-it")
        prompt = build_real_prompt(runtime)
        assert not absolutes_in(prompt), f"absolute values in prompt: {absolutes_in(prompt)}"
        assert not _CURRENCY.search(prompt)

    def test_net_worth_cannot_be_reconstructed(self, runtime: TradeOSRuntime) -> None:
        """Weights plus prices would multiply back to the portfolio value."""
        runtime.ensure_sample_policy()
        runtime.run_cycle(trigger="fund-it")
        prompt = build_real_prompt(runtime)
        for price in ("285.10", "232.50", "418.20", "161.35", "118.90"):
            assert price not in prompt
        assert "99,955" not in prompt and "99955" not in prompt


class TestProjectionRefusesAbsolutes:
    """The types are the enforcement; the scrubber is only the first line."""

    def test_a_share_count_in_prose_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="absolute quantity"):
            CandidateLine(index=0, side="buy", symbol="VTI", rationale="buy 140 shares")

    def test_a_currency_marker_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="currency marker"):
            CandidateLine(index=0, side="buy", symbol="VTI", rationale="worth $39,914.00")

    def test_percentages_and_ratios_are_allowed(self) -> None:
        line = CandidateLine(
            index=0, side="buy", symbol="VTI", rationale="drift -0.4% vs target 0.40"
        )
        assert "0.4%" in line.rationale

    def test_a_weight_outside_zero_to_one_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="ratio"):
            HoldingLine(symbol="VTI", weight=Decimal("140"))

    def test_item_ids_survive_because_citations_depend_on_them(
        self, runtime: TradeOSRuntime
    ) -> None:
        policy = runtime.ensure_sample_policy()
        now = runtime._clock.now()
        account = runtime.broker.get_account()
        targets = {t.symbol: t.weight for t in policy.target_allocations}
        quotes = {s: q for s in targets if (q := runtime.broker.get_quote(s)) is not None}
        package = ContextAssembler().assemble(
            purpose="safety",
            account=account,
            quotes=quotes,
            required_symbols=tuple(targets),
            market_note="regular session",
            now=now,
            source_name=runtime.broker.name,
        )
        snapshot = PortfolioSnapshot(account=account, quotes=quotes, as_of=now)
        context = project_context(package, snapshot=snapshot, targets=targets, now=now)
        assert context.citations == package.citations


class TestLabelsAreNotMistakenForAmounts:
    """Regression: the ratio rule once rejected its own trigger labels.

    `schedule/15m` and `cli-demo-1` contain digits that are part of a *name*,
    not a measurement. Scanning them as quantities raised on every scheduled
    AI cycle — the guard taking down the thing it was guarding.
    """

    @pytest.mark.parametrize(
        "purpose",
        ["schedule/15m:VTI,AAPL", "schedule/1h:VTI", "cli-demo-1:VTI", "tui:VTI"],
    )
    def test_trigger_labels_survive_the_projection(self, purpose: str) -> None:
        from decimal import Decimal as D

        from tradeos.context.projection import PromptContext

        context = PromptContext(
            package_id="p1",
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            purpose=purpose,
            completeness=D("1"),
        )
        assert context.purpose == purpose

    def test_a_ticker_containing_digits_is_allowed(self) -> None:
        from decimal import Decimal as D

        from tradeos.context.projection import HoldingLine

        assert HoldingLine(symbol="BRK.B", weight=D("0.1")).symbol == "BRK.B"

    def test_but_prose_amounts_are_still_refused(self) -> None:
        from tradeos.context.projection import CandidateLine

        with pytest.raises(ValidationError, match="absolute quantity"):
            CandidateLine(index=0, side="buy", symbol="VTI", rationale="buy 140 shares")
