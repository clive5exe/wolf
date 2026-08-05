# Live Provider Smoke Log (T-029)

Manual structured round-trips against the real, subscription-authenticated
Claude Code CLI. No CI. Logged-in machines only.

| Date | CLI version | Result | Duration | Reported cost | Notes |
|---|---|---|---|---|---|
| 2026-08-05 | 2.1.222 | ✅ PASS (`tradeos doctor --full`) | 10.1 s | $0.6702 (envelope `total_cost_usd`) | `--json-schema` + `structured_output` path worked first try. HealthProbe echo nonce verified. **Cost observation:** a single probe reported ~$0.67. Scheduled AI-synthesis cycles must be budgeted deliberately (ASSUMPTIONS Q1). Deterministic-only cycles cost $0. |
