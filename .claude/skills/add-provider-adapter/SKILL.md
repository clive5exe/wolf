---
name: add-provider-adapter
description: Implement a new AI provider adapter against the ModelProvider protocol with honest capability declaration and fake-executable tests.
---

# Adding a provider adapter

1. Read PROVIDER_SPEC.md fully. Confirm the provider row in §4's capability
   matrix (add it if missing, citing official docs in RESEARCH_NOTES.md.
   Undocumented behavior is a blocker, not a workaround).
2. Create `src/tradeos/providers/<name>.py` implementing `ModelProvider`:
   `detect()` (which/version/auth. Never guess `authenticated`. Return
   `None` when unknowable), `capabilities()` (declare ONLY what the official
   docs support), `health_check()` (cheapest possible structured round-trip),
   `query_structured()` (timeout with SIGTERM→SIGKILL escalation, max one
   retry on invalid_output with validation errors quoted back).
3. Rules: subprocess argv lists only (`shell=False`), no credential handling
   (the client's own login is the auth), redact before storing any raw
   excerpt, map every failure to a typed `ProviderError`.
4. Tests in `tests/unit/test_provider_<name>.py` using a **fake executable
   fixture** (see `tests/fixtures/fake_claude.py` pattern): not-installed,
   installed-not-authed, healthy, invalid-output-retry-fail, timeout-kill.
5. Register in `runtime/registry.py`. Add a doctor check row with a fix hint.
6. Update PROVIDER_SPEC §4 status column and CHANGELOG.
