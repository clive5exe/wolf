---
name: add-textual-screen
description: Create a Textual TUI screen that renders runtime state without embedding business logic, with Pilot tests.
---

# Adding a Textual screen

1. Screens live in `src/tradeos/tui/screens/<name>.py`; styles in the
   screen's `CSS` or shared `tui/tradeos.tcss`.
2. **Interface discipline (hard rule):** screens import ONLY from
   `tradeos.runtime.facade` and `tradeos.domain`. No brokers, providers,
   risk, storage imports — the facade exposes query/command methods; if one
   is missing, add it to the facade (that's core code with its own tests).
3. Pattern: `compose()` builds widgets (Header/Footer/DataTable/RichLog/
   Static); data loads in `on_mount` via `self.run_worker` for anything
   slower than a dict lookup; refresh via facade subscriptions or a timer
   (`set_interval`), never by polling storage directly.
4. Every displayed money value comes formatted from
   `domain.format_money` (Decimal-aware); timestamps rendered local with UTC
   in tooltip/detail; staleness shown via the freshness glyphs (● fresh
   ◐ aging ○ stale ✕ expired) — never hide freshness.
5. Keys: add `BINDINGS` entries + `action_*` methods; register the screen in
   `tui/app.py` `SCREENS`; update the footer hints.
6. Test with Pilot in `tests/unit/test_tui_<name>.py`: `app.run_test()`,
   `pilot.press(...)`, assert on queried widget state (use the fake broker /
   in-memory store fixtures — TUI tests never touch the real data dir).
