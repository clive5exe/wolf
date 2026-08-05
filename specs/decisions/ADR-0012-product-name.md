# ADR-0012. Product name: WOLF (command `wolf`, distribution `tradeos`)

- **Status:** accepted
- **Date:** 2026-08-05
- **Supersedes:** nothing. Amends the working title used in ADR-0001…0011.

## Context

The project shipped its founding scaffold under the working title *TradeOS*.
The terminal UI design direction proposed renaming to **WOLF**: *Wealth
Orchestration, Local-First*. On three grounds:

1. The acronym is honest: local-first is the actual architecture, not marketing.
2. It supplies a brand mark for free. The amber eye in `W◉LF`.
3. It gives the binary a verb-like feel (`wolf tui`, `wolf unkill`) and the
   product a voice ("wolf is watching", "enter the den").

The design direction flagged one open risk: *the word is common. Check
crates/PyPI/Homebrew collisions before committing.*

## Collision check (2026-08-05)

| Registry | `wolf` | Result |
|---|---|---|
| PyPI | HTTP 200 | **taken** |
| PyPI `wolf-cli` | HTTP 200 | **taken** |
| PyPI `wolfos` | HTTP 404 | free |
| Homebrew core formula | HTTP 404 | **free** |
| npm | HTTP 200 | taken (different ecosystem) |
| crates.io | HTTP 200 | taken (different ecosystem) |
| local `$PATH` | not found | **free** |

The command name is clear. The Python distribution name is not.

## Decision

Split the two identities, because they answer to different registries:

- **Product and interface name: WOLF.** Wordmark `W◉LF`, tagline "wealth
  orchestration, local-first". All user-facing surfaces. TUI, CLI help,
  `--version`, notifications. Say WOLF.
- **Command: `wolf`.** Free on Homebrew and on PATH, so the name a human types
  is the name the product uses. `tradeos` is retained as an alias entry point so
  existing muscle memory and scripts keep working.
- **Python distribution and import package: `tradeos`.** Unchanged. `wolf` is
  unavailable on PyPI, and renaming the import path would touch every module,
  spec, and ADR in the repo for no user-visible benefit.

## Consequences

- Screens can truthfully instruct `wolf unkill`, because that command exists.
- `import tradeos` remains valid. No spec, ADR, or test needed rewriting.
- Two console scripts point at one `main()`. There is no second code path.
- If the PyPI name is ever acquired or a distinct one chosen (`wolfos` is free),
  the distribution rename is a separate, mechanical change. This ADR does not
  block it.
- The mismatch between product name and package name is documented here so
  future readers do not "fix" it by accident.

## Open

The owner has accepted the WOLF direction but is not settled on the `◉` eye
mark specifically (recorded 2026-08-05: *"the only thing I'm not in love with is
the Wolf logo, but just go for now"*). The wordmark lives in exactly one place.
`tradeos/tui/theme.py::WORDMARK`: so revisiting it is a one-line change.

---

## Amendment. 2026-08-05: the expansion and the tagline

Two changes after owner review. The decision to use WOLF stands. What it *says*
has changed.

### "Wealth Orchestration, Local-First" is withdrawn

That expansion was a backronym. Invented to justify a name already chosen, and
presented above as though the acronym were a reason to pick it. It was not.
Recording that plainly, because a reader comparing the original text against
this amendment deserves to know which parts were reasoning and which were
decoration.

### The expansion is now "Watches Obsessively, Lacks Feelings"

Chosen deliberately as a joke, on the grounds that a self-deprecating expansion
is harder to resent than an earnest one. And this one happens to be the most
accurate four-word summary of the architecture available. It monitors
continuously, and the component holding veto power is deterministic code that
cannot be reasoned with, flattered, or talked around. The joke and the spec
agree.

### "Local-first" is withdrawn as a public tagline

Raised by the owner: the phrase oversells, and the project would be called out
for it. That objection is correct. Over a normal cycle WOLF contacts an AI
provider, a broker's hosted MCP server, and (with T-023/T-025) EDGAR and a
social firehose. A newcomer reads "local-first" as "nothing leaves my machine",
and that is false.

**ADR-0002 keeps the term**: as an architectural statement about where state
lives and who owns it, it remains accurate: the event log, policy, risk
decisions and secrets are all local, and there is no service of ours in the
path. The problem is only in using an architecture term as a marketing claim.

The public tagline is now **"the model advises · your machine decides"**, which
states ADR-0008 and is checkable against the code by anyone who doubts it.

This matters beyond wording. A project whose interface refuses to show a
sparkline it lacks data for, and reports "no action" as a result rather than
hiding it, cannot afford a tagline that overclaims. The honesty has to be the
same all the way out.
