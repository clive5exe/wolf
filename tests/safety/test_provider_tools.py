"""The allowlist is the only thing between the model and an execution tool.

Robinhood's MCP server issues one scope, `internal`, and there is no read-only
variant. An authorised token can place orders. So the guarantee cannot come
from the credential and has to come from here: the provider passes an
intersection with its own allowlist, never the caller's list.

These are safety tests. A failure here means a prompt could reach a tool nobody
granted it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from tradeos.providers.claude_code import ClaudeCodeProvider


class Answer(BaseModel):
    text: str


READ_TOOL = "mcp__robinhood-trading__get_equity_quotes"
TRADE_TOOL = "mcp__robinhood-trading__place_equity_order"


class Recorder(ClaudeCodeProvider):
    """Captures the argv the provider would have run, without running it."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.argv: list[str] = []
        self.cwd: Path | None = None

    def _find_executable(self) -> str | None:
        return "claude"

    def _invoke(self, exe, prompt, schema_json, *, timeout_s, max_turns, model, tools=()):  # type: ignore[no-untyped-def]
        self.argv = [exe, "--max-turns", str(max_turns)]
        if tools:
            self.argv += ["--allowedTools", ",".join(tools)]
        self.cwd = self._tool_dir if tools else None
        return {"text": "ok"}

    def granted(self) -> set[str]:
        if "--allowedTools" not in self.argv:
            return set()
        return set(self.argv[self.argv.index("--allowedTools") + 1].split(","))


def provider(allowed: tuple[str, ...] = (READ_TOOL,)) -> Recorder:
    return Recorder(allowed_tools=allowed, tool_dir=Path("/tmp/mcp"))


def ask(p: Recorder, tools: tuple[str, ...]) -> None:
    p.query_structured(prompt="hello", schema=Answer, tools=tools)


class TestTheAllowlistHolds:
    def test_an_allowlisted_tool_is_granted(self) -> None:
        p = provider()
        ask(p, (READ_TOOL,))
        assert p.granted() == {READ_TOOL}

    def test_a_trade_tool_is_refused_even_when_asked_for_by_name(self) -> None:
        p = provider()
        ask(p, (TRADE_TOOL,))
        assert TRADE_TOOL not in p.granted()

    def test_a_trade_tool_smuggled_beside_a_read_tool_is_stripped(self) -> None:
        """The dangerous case: a mostly-legitimate request with one extra."""
        p = provider()
        ask(p, (READ_TOOL, TRADE_TOOL))
        assert p.granted() == {READ_TOOL}

    def test_an_empty_allowlist_grants_nothing(self) -> None:
        p = provider(allowed=())
        ask(p, (READ_TOOL,))
        assert p.granted() == set()

    @pytest.mark.parametrize(
        "sneaky",
        [
            "mcp__robinhood-trading__get_equity_quotes ",
            " mcp__robinhood-trading__get_equity_quotes",
            "MCP__ROBINHOOD-TRADING__GET_EQUITY_QUOTES",
            "mcp__robinhood-trading__get_equity_quotes,mcp__robinhood-trading__place_equity_order",
        ],
    )
    def test_near_misses_do_not_match(self, sneaky: str) -> None:
        """Membership is exact. Whitespace, case, and a comma-joined pair are
        all different strings from the one that was allowed."""
        p = provider()
        ask(p, (sneaky,))
        assert p.granted() == set()


class TestNoToolsIsTheDefault:
    def test_no_tools_are_passed_unless_asked_for(self) -> None:
        p = provider()
        p.query_structured(prompt="hello", schema=Answer)
        assert "--allowedTools" not in p.argv

    def test_the_tool_directory_is_not_entered_without_tools(self) -> None:
        """A toolless synthesis must not inherit an MCP connection it was never
        meant to reach, which is what running in that directory would give it."""
        p = provider()
        p.query_structured(prompt="hello", schema=Answer)
        assert p.cwd is None

    def test_the_tool_directory_is_used_when_tools_are_granted(self) -> None:
        p = provider()
        ask(p, (READ_TOOL,))
        assert p.cwd == Path("/tmp/mcp")


def test_refusals_are_recorded_not_silent() -> None:
    """A dropped tool must leave a trace. Silently narrowing a request makes a
    verdict impossible to interpret later."""
    events: list[tuple[object, dict]] = []

    class Store:
        def append(self, kind: object, payload: dict) -> None:
            events.append((kind, payload))

    p = Recorder(allowed_tools=(READ_TOOL,), tool_dir=Path("/tmp/mcp"), event_store=Store())
    ask(p, (READ_TOOL, TRADE_TOOL))
    refused = [e for _, e in events if e.get("refused")]
    assert refused, "a tool refusal must be recorded"
    assert TRADE_TOOL in refused[0]["refused"]
