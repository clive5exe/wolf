# ADR-0011: All model output is schema-validated data

**Status:** accepted · 2026-08-05 · **Safety-critical**

## Context
Free-text model output cannot be audited, cited, compared, or safely acted
on. Claude Code supports native schema-constrained output; other providers
will vary (PROVIDER_SPEC §4).

## Decision
Every provider call declares a Pydantic schema (`StructuredThesis`,
`PolicyDraft`, `HealthProbe`, …). Native constrained output is used where the
client supports it; otherwise instruct-and-validate. Validation failures get
exactly one retry with the errors quoted back; a second failure is a typed
`invalid_output` provider error — recorded as an evaluation signal, never
"best-effort parsed." Cross-field semantic checks live in the schema too:
thesis citations must reference known context-item ids; confidence bounds;
invalidation conditions non-empty for actionable recommendations. Prompt
templates are versioned (`prompt_version` recorded in events) so output-
quality shifts are attributable.

## Consequences
- Hallucination surfaces as measurable validation/citation failures instead
  of confident prose.
- Providers without structured support pay a retry tax — honest capability
  reporting, not hidden flakiness.
- Schema evolution is versioned with the events that carry instances.
