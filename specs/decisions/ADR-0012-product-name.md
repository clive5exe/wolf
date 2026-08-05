# ADR-0012 — Product name: WOLF (command `wolf`, distribution `tradeos`)

- **Status:** accepted
- **Date:** 2026-08-05
- **Supersedes:** nothing. Amends the working title used in ADR-0001…0011.

## Context

The project shipped its founding scaffold under the working title *TradeOS*.
The terminal UI design direction proposed renaming to **WOLF** — *Wealth
Orchestration, Local-First* — on three grounds:

1. The acronym is honest: local-first is the actual architecture, not marketing.
2. It supplies a brand mark for free — the amber eye in `W◉LF`.
3. It gives the binary a verb-like feel (`wolf tui`, `wolf unkill`) and the
   product a voice ("wolf is watching", "enter the den").

The design direction flagged one open risk: *the word is common — check
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

The command name is clear; the Python distribution name is not.

## Decision

Split the two identities, because they answer to different registries:

- **Product and interface name: WOLF.** Wordmark `W◉LF`, tagline "wealth
  orchestration, local-first". All user-facing surfaces — TUI, CLI help,
  `--version`, notifications — say WOLF.
- **Command: `wolf`.** Free on Homebrew and on PATH, so the name a human types
  is the name the product uses. `tradeos` is retained as an alias entry point so
  existing muscle memory and scripts keep working.
- **Python distribution and import package: `tradeos`.** Unchanged. `wolf` is
  unavailable on PyPI, and renaming the import path would touch every module,
  spec, and ADR in the repo for no user-visible benefit.

## Consequences

- Screens can truthfully instruct `wolf unkill`, because that command exists.
- `import tradeos` remains valid; no spec, ADR, or test needed rewriting.
- Two console scripts point at one `main()`; there is no second code path.
- If the PyPI name is ever acquired or a distinct one chosen (`wolfos` is free),
  the distribution rename is a separate, mechanical change — this ADR does not
  block it.
- The mismatch between product name and package name is documented here so
  future readers do not "fix" it by accident.

## Open

The owner has accepted the WOLF direction but is not settled on the `◉` eye
mark specifically (recorded 2026-08-05: *"the only thing I'm not in love with is
the Wolf logo, but just go for now"*). The wordmark lives in exactly one place —
`tradeos/tui/theme.py::WORDMARK` — so revisiting it is a one-line change.
