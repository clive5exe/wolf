```
██╗    ██╗ ██████╗ ██╗     ███████╗
██║    ██║██╔═══██╗██║     ██╔════╝
██║ █╗ ██║██║   ██║██║     █████╗
██║███╗██║██║   ██║██║     ██╔══╝
╚███╔███╔╝╚██████╔╝███████╗██║
 ╚══╝╚══╝  ╚═════╝ ╚══════╝╚═╝
```

**Watches obsessively, lacks feelings.**
*The model advises · your machine decides*

An open-source AI portfolio-management runtime for macOS and Linux.

WOLF orchestrates AI tools you already have (Claude Code under your
existing subscription first, with Codex CLI, Ollama and API providers later), MCP
services, market context, deterministic risk policies, and notifications to
continuously monitor a portfolio, generate *sourced* decisions, simulate or
execute *bounded* actions, and evaluate its own behavior over time.

![The den, WOLF's dashboard](https://raw.githubusercontent.com/clive5exe/wolf/main/docs/screens/den.svg)

> ⚠️ **Experimental software. Not investment advice.** WOLF is a research
> runtime. It ships with no real-money execution: v0.1 is read-only
> intelligence + paper trading, by design. Nothing here predicts markets, and
> no output should be treated as a recommendation to buy or sell anything.

## Why this exists

Most "AI trading" projects are a prompt around a chatbot. WOLF takes the
opposite stance:

- **The model proposes, deterministic code disposes.** An LLM may synthesize
  research and draft theses. It cannot touch position limits, loss limits,
  trading hours, symbol permissions, or the kill switch. Those are ordinary,
  fully-tested Python with absolute veto power.
- **Every decision is explainable.** Each cycle records its context package
  (source, timestamps, TTL, freshness), the strategy's arithmetic, every risk
  rule's result, fills, and notifications, all into an append-only event log
  that replays byte-identically.
- **Stale data is a stop sign.** Nothing enters a decision without an event
  time, ingestion time, TTL, and credibility score. "Insufficient or stale
  data, no action" is a successful outcome, not an error.
- **Runs where you do.** macOS and Linux are supported and tested in CI. Windows is not claimed. Nothing is known to break there, but nobody has run it, and an untested claim is one you get called on.
- **No service behind it.** There is no account to create with us, no backend, and no telemetry. Your history lives in a SQLite file you own. WOLF *does* talk to the network, reaching your AI provider, your broker and SEC EDGAR, but always through your own credentials, and it sends the model proportions rather than amounts.
- **Bring your own AI.** Subscription-backed local clients via their
  documented interfaces only. No browser scraping, no cookie theft, no
  private endpoints, no mandatory API bill.

## Status: v0.1 scaffold (see [ROADMAP.md](ROADMAP.md))

| Works today | Deliberately absent |
|---|---|
| `wolf doctor` environment diagnosis with fix hints (macOS + Linux) | Real-money execution (v0.2+, human-approved only) |
| Claude Code provider: detection, auth state, native schema-constrained structured output (verified live) | Autopilot (v0.3, restricted envelope, dedicated account) |
| Deterministic risk engine, 21 rules, fail-closed, absolute veto | Options, multi-broker, consensus, marketplace (see PRODUCT.md §6) |
| Paper trading with slippage model + event-sourced replay | |
| Target-allocation rebalance strategy (explicit Decimal math) | |
| Versioned investment policy with mode ladder + kill switch | |
| Six-screen terminal UI: boot diagnosis, den, live cycle, verdict, journal, kill | |
| Scheduled cycles (`wolf watch`) with market-hours gating and kill-switch awareness | |
| SEC EDGAR fundamentals with point-in-time correctness (restatements are visible, not silently applied) | |
| Daily SEC filing collector (Cloudflare Worker, optional mirror, never a dependency) | |
| Policy onboarding (`wolf setup`): your goals drafted into a policy you confirm | |
| Typer CLI (`wolf`), notifications via Notification Center or libnotify | |
| 488 tests incl. safety/contract/replay suites, mypy clean, CI | |

## Quickstart

```bash
curl -fsSL https://wolf.clive5.com/install.sh | sh
wolf setup                      # your goals -> a draft policy -> you confirm every limit
```

Read it first if you'd rather (`| less` instead of `| sh`). It prints what it
will do before doing it, touches two paths, and needs no sudo.

<details><summary>From source instead</summary>

```bash
git clone https://github.com/clive5exe/wolf.git && cd wolf
./scripts/dev_setup.sh          # venv, editable install, git hooks
source .venv/bin/activate

wolf doctor                     # check platform, store, Claude Code, policy
wolf doctor --full              # + one live structured round-trip probe*
wolf demo --cycles 2            # paper decision cycles with the sample policy
wolf portfolio                  # allocations, drift, concentration
wolf events                     # the audit trail
wolf tui                        # enter the den, the full terminal interface
wolf tui --calm                 # same, with animation disabled
wolf watch --interval 15m       # run cycles on a schedule until you stop it
```

</details>

\* Requires a logged-in Claude Code CLI. Note: headless (`claude -p`) calls
may draw from your plan's *programmatic* usage allowance and report a real
cost per call. WOLF records it per event and never hides it.

## The den (terminal UI)

`wolf tui` opens a six-screen interface. The dashboard is home, and every screen is
one keystroke away and one `esc` back. There are no menus.

| Screen | Key | What it is for |
|---|---|---|
| **boot** | none | The doctor checks *are* the startup sequence, so you cannot boot past a broken environment. A failing check halts the cascade with its fix hint. |
| **den** | home | NAV, equity history, and one row per holding: size, drift against plan, unrealised P&L, and quote freshness. |
| **cycle** | `c` | A decision running live. Stages complete left to right, making the architecture visible: the model is one box between deterministic walls. |
| **verdict** | `⏎` | Thesis on top, the rule wall below, receipt at the bottom, the order the system actually works in. Every rule is listed, every time. |
| **journal** | `j` | Decision history. Vetoes and no-actions carry the same weight as fills, because "we did not trade" is a result. |
| **kill** | `k` | Full-screen halt. Reachable from anywhere. Deliberately the ugliest thing in the app. |


### The screens

<table>
<tr>
<td width="50%"><b>Boot.</b> The doctor checks <i>are</i> the startup sequence, so a broken environment can't be booted past.<br><img src="https://raw.githubusercontent.com/clive5exe/wolf/main/docs/screens/boot.svg" alt="Boot check cascade"></td>
<td width="50%"><b>Cycle.</b> A decision running live. The model is provably one box between deterministic walls.<br><img src="https://raw.githubusercontent.com/clive5exe/wolf/main/docs/screens/cycle.svg" alt="Live decision cycle"></td>
</tr>
<tr>
<td><b>Verdict.</b> Thesis, then every rule, then the receipt. Nothing summarised away.<br><img src="https://raw.githubusercontent.com/clive5exe/wolf/main/docs/screens/verdict.svg" alt="Verdict screen"></td>
<td><b>Journal.</b> Vetoes and no-actions carry the same weight as fills.<br><img src="https://raw.githubusercontent.com/clive5exe/wolf/main/docs/screens/journal.svg" alt="Decision journal"></td>
</tr>
<tr>
<td colspan="2"><b>Kill switch.</b> Reachable from anywhere, and deliberately the ugliest thing in the app.<br><img src="https://raw.githubusercontent.com/clive5exe/wolf/main/docs/screens/kill.svg" alt="Kill switch takeover"></td>
</tr>
</table>

Three conventions carry most of the meaning:

- **Colour is rationed.** Amber is the wolf (brand, targets, keys). Green and red
  are money, and only money. Cyan is data and history. Anything coloured means
  something.
- **Drift is spatial.** The `◆┼` gauge places each holding against its target on
  a track scaled to the rebalance threshold, so reaching the end means the strategy
  is at the point of trading. Off-scale drift is marked `◀`/`▶`, never clamped.
- **Freshness is never hidden.** `●` fresh · `◐` aging · `○` stale · `✕` no data.
  Live sources pulse. Stale ones go still, so you notice the *absence* of motion.

Animation always encodes a system state, whether alive, working, arriving,
confirmed or dead, and never carries information on its own. `wolf tui --calm` turns it
all off with nothing lost.

## Architecture (short version)

```
TUI / CLI  ──►  Runtime facade  ──►  decision cycle
                    │   trigger → observe → retrieve → candidates
                    │   → optional AI thesis (schema-validated, citation-checked)
                    │   → deterministic sizing → RISK ENGINE (veto) → mode gate
                    │   → paper execution → events → notify → evaluate
                    ▼
        append-only SQLite event log  ←  replay == release gate
```

- One reusable **headless core**. Interfaces only display state and send
  commands (mechanically enforced).
- `ValidatedOrder`, the only object a broker adapter accepts, can only be
  issued by the risk engine, is idempotent by construction, and expires.
- Kill switch is checked at the scheduler, cycle, engine, and execution
  layers. Engaging it is one command (`wolf kill "reason"`), and disengaging is
  deliberately awkward (`wolf unkill`, or two separate presses in the TUI).

Full detail: [ARCHITECTURE.md](ARCHITECTURE.md) · [RISK_POLICY_SPEC.md](RISK_POLICY_SPEC.md) ·
[MARKET_CONTEXT_SPEC.md](MARKET_CONTEXT_SPEC.md) · [PROVIDER_SPEC.md](PROVIDER_SPEC.md) ·
[THREAT_MODEL.md](THREAT_MODEL.md) · ADRs in `specs/decisions/`.

## Security model (summary, see [SECURITY.md](SECURITY.md))

- Secrets live only in an OS credential store, either macOS Keychain or libsecret
  on Linux. There is deliberately **no file fallback**: if no keystore is
  available WOLF refuses rather than writing credentials to disk, because a
  silent downgrade would leave a machine unprotected with nothing on screen
  to say so. Repo, SQLite, logs, and prompts are scanned for credential
  shapes on every commit and in CI.
- Prompts carry **proportions, never amounts**: the model is told a holding is
  39.9% of the portfolio against a 40% target, never that it is $39,914 or 140
  shares. Enforced by type rather than by a filter, so it cannot rot.
- Model output and ingested market content are treated as hostile input:
  schema validation, citation integrity checks, and decisively the
  deterministic risk boundary between any text and any order.
- Broker access is read-only in v0.1. The Robinhood integration targets only
  the official Agentic Trading MCP, never private APIs.

## Verification

```bash
./scripts/verify.sh        # ruff format+lint, mypy, full pytest
./scripts/safety_check.sh  # secrets scan, boundary scan, safety suite
```

CI runs both on macOS and Linux (Python 3.12/3.13). The safety suite proves:
no order path bypasses the risk engine, tampered orders are refused at the
broker boundary, duplicates never re-execute, the kill switch halts
everything, and hostile context text cannot change a proposal or verdict.

## Known limitations (honest list)

- Quotes in the demo are static fixtures. Live market data lands with the
  Robinhood MCP read-only adapter (T-024, requires an Agentic account).
- The market clock knows regular NYSE hours but not exchange holidays (paper
  mode simulates sessions, and live modes in v0.2 require a holiday source).
- Sharpe/Sortino/beta report "unavailable" until a licensed benchmark series
  is configured. They are never approximated silently.
- Paper fills model slippage as a flat bps adjustment: no spread, no partial
  fills, no market impact (documented in every fill event).
- Earnings-blackout rule exists but defaults to disabled: no reliable free
  earnings-calendar source has been verified yet.
- The dashboard shows no per-symbol price sparkline, because no price history
  is stored yet, because drawing one would be fabricated data. The equity strip fills
  in as cycles record portfolio snapshots.
- Max drawdown is computed from recorded equity snapshots only, so it reflects
  observed history, not intraday extremes the runtime never sampled.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Development runs through a
spec-first, agent-assisted workflow (`.claude/`) with hard gates: risk,
execution, broker, and security changes always require human review plus the
safety suite. Task backlog: [specs/tasks/BACKLOG.md](specs/tasks/BACKLOG.md).

## License

MIT, see [LICENSE](LICENSE). Again: **experimental, not investment advice,
no warranty, capital at risk if you ever wire this to a real account.**
