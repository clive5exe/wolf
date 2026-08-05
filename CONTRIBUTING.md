# Contributing to WOLF

WOLF is developed by a small, tightly controlled agent studio plus human
maintainers. Humans and coding agents follow the same rules. Agents follow
them mechanically via `.claude/` configuration.

## Ground rules

- **Specs are law.** `ARCHITECTURE.md`, the `*_SPEC.md` documents, and ADRs in
  `specs/decisions/` define boundaries. If your change needs to cross a
  boundary, write or amend an ADR first. Do not "just do it".
- **One task, one branch/worktree, one diff.** Tasks come from
  `specs/tasks/`. Keep diffs reviewable (< ~500 lines where possible).
- **Interfaces display. The core decides.** No business logic in `cli/` or
  `tui/`. No broker calls outside `brokers/` + `execution/`. No provider calls
  outside `providers/`.
- **Determinism where money moves.** Risk rules, order construction, and
  execution are ordinary tested code. LLM output is validated data, never
  control flow around a limit.

## Definition of done

A change is done only when all of the following hold:

1. Acceptance criteria of the task packet pass.
2. `scripts/verify.sh` passes: Ruff format + lint, mypy, pytest.
3. `scripts/safety_check.sh` passes (secrets scan, forbidden-pattern scan,
   safety test suite).
4. Documentation matches the implemented behavior. No aspirational docs.
5. Sensitive areas (risk, execution, brokers, security, autopilot, auth) have
   explicit human approval.

## Setup

```bash
./scripts/dev_setup.sh   # creates .venv, installs package + dev tools, git hooks
source .venv/bin/activate
tradeos doctor           # verify your environment
./scripts/verify.sh      # run the full local pipeline
```

## Commit style

- Conventional-ish: `feat(risk): add sector concentration rule`, `fix(paper): …`
- Reference the task ID (e.g. `T-014`) in the body.
- Never commit credentials, `.db` files, or user data. The pre-commit hook and
  CI both scan for this.

## Architecture decisions

Add ADRs as `specs/decisions/ADR-NNNN-title.md` using the existing format
(Context / Decision / Consequences / Alternatives). Superseded ADRs are marked,
never deleted.
