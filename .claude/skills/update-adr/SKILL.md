---
name: update-adr
description: Record or amend an architecture decision without rewriting history.
---

# ADR procedure

1. New decision → next number: `specs/decisions/ADR-NNNN-kebab-title.md` with
   sections: Status (proposed/accepted/superseded + date), Context, Decision,
   Consequences, Alternatives rejected. State the *forces* honestly. An ADR
   that only praises its choice is broken.
2. Changing a past decision → do NOT edit the old Decision text. Append an
   "## Amended (date)" section to the old ADR AND/OR create a superseding ADR
   that links both ways ("Supersedes ADR-0003" / "Superseded by ADR-0017").
3. Any diff that crosses a boundary defined in ARCHITECTURE.md §2, adds a
   dependency, adds a cloud primitive, or changes a safety mechanism REQUIRES
   an ADR in the same PR. Reviewers block otherwise.
4. Keep it under a page. Link the spec sections it affects. Update them in
   the same PR so specs never contradict accepted ADRs.
