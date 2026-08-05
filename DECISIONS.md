# Settled

Questions that are closed. Reopening one without the owner asking is a defect,
not diligence.

This file exists because the same questions were answered, unanswered, and
answered again inside a single session, which cost more than getting any of
them wrong would have.

**Read this before proposing, researching, or recommending anything.**

| # | Question | Settled | Where |
|---|---|---|---|
| 1 | What is WOLF? | The model trades, the app hands it instruments, deterministic code holds the veto | `THESIS.md` |
| 2 | Are we hunting for an edge? | **Yes.** It is for retail investors and the point is to make money | `THESIS.md` |
| 3 | Where does the edge come from? | Processing public information at a scale retail does not, never prediction | `THESIS.md` |
| 4 | Do we backtest? | **Yes, required.** It costs a model call per decision and tests judgment, not a rule | `THESIS.md` |
| 5 | Broker and market data? | **Robinhood.** Same venue for data and execution | ADR-0004, below |
| 6 | Alpaca? | **No.** Every user would need a second account they never trade at | below |
| 7 | Does the user have Robinhood connected? | **Yes, already.** MCP registered at `~/Dev/rh-probe`, authenticated, returning live quotes | below |
| 8 | Real-money execution? | Not in v0.1. `SUPPORTED_MODES = {READ_ONLY, PAPER}` | ADR-0009 |
| 9 | Congressional trading? | **Excluded.** Statutory commercial-use ban, Senate needs scraping, no edge | below |
| 10 | Copy-trading platforms? | **Excluded.** Terms forbid the database needed to test them | below |
| 11 | Charts? | Character cells. Not braille, not terminal image protocols | `tui/chart.py` |
| 12 | Prompt redaction? | Percentages only, enforced by type | ADR-0011, `context/projection.py` |
| 13 | Em dashes and prose semicolons? | Zero, repo-wide and in replies | below |

## The ones that were flip-flopped, and why they are closed

**Robinhood, not Alpaca.** Alpaca was recommended because it was faster *for me
to build*, which is not a reason. Robinhood is the venue the user actually
trades at, so its prices are the prices they get, and every user already has
that account. Alpaca would mean asking every user to open a second brokerage
account purely for data. Settled.

**The Robinhood MCP is already set up.** Registered at `~/Dev/rh-probe`, scoped
to that directory, which is why it does not appear in `claude mcp list` run
from anywhere else. It is authenticated and returned a live AAPL quote on
2026-08-05. **Check every scope before concluding a thing does not exist.**

It stays scoped to `rh-probe` deliberately. It exposes `place_equity_order`, so
it must never be registered to the WOLF directory where an unguarded call could
reach it. The allowlist in `mcp/registry.py` is the gate.

**Backtesting is required.** Told the framing was wrong, the correction
inverted it entirely and disowned backtesting, which the owner then had to
correct again. Adjust, do not invert.

**Congressional trading and copy trading are excluded**, with reasons on file.
Do not re-research them.

## The rule

Before proposing work, check it against the standing rule in `THESIS.md`: does
this make the model a better trader, or its decisions safer to act on?

Before researching anything, check this table and the ADRs. Half of one session
was spent re-answering questions already recorded here.
