# Research Notes — External Dependencies (verified 2026-08-05)

Method: three parallel research passes over primary documentation only.
Every claim carries its source URL. Items that could not be verified against
a primary source are marked **NOT CONFIRMED** and repeated in §6. These notes
back ASSUMPTIONS_AND_OPEN_QUESTIONS.md, PROVIDER_SPEC.md, MCP_TOOL_SPEC.md,
DATA_SOURCES.md, and ADR-0007.

## 1. Claude Code programmatic invocation (provider backbone)

- Headless mode: `claude -p/--print`, `--output-format text|json|stream-json`;
  JSON envelope includes `result`, `session_id`, `total_cost_usd`, and
  `structured_output` when `--json-schema` is used.
  https://code.claude.com/docs/en/headless.md
- **Native structured output:** `--json-schema '<schema>'` with
  `--output-format json`; validated output lands in `structured_output`;
  CLI retries validation failures internally.
  https://code.claude.com/docs/en/headless.md
- Agent SDK (`claude-agent-sdk`, Python) is the recommended richer
  programmatic path; supports `output_format={"type":"json_schema",...}`,
  draft-07 validation, `error_max_structured_output_retries`.
  https://code.claude.com/docs/en/agent-sdk/structured-outputs.md
  → v0.1 decision: subprocess CLI (zero extra deps, subscription auth
  inherited); SDK migration is a contained v0.2 option inside the adapter.
- Sessions: `--continue`, `--resume <session_id>` (project-scoped lookup);
  turns capped via `--max-turns`; model via `--model`.
  https://code.claude.com/docs/en/cli-reference.md
- Permissions in `-p` mode: default auto-approves only reads;
  `--allowedTools`/`--disallowedTools` use permission-rule syntax;
  `--permission-mode` incl. `dontAsk` (auto-deny unapproved). We never use
  `bypassPermissions`. https://code.claude.com/docs/en/permissions.md ,
  https://code.claude.com/docs/en/permission-modes.md
- `--bare` skips hooks/skills/MCP but **does not read OAuth credentials**
  (API-key only) → unusable for subscription-backed operation; we use normal
  mode with explicit tool denial instead.
  https://code.claude.com/docs/en/headless.md
- Auth: browser OAuth login; credentials in encrypted macOS Keychain (item
  name undocumented — we never touch it); `claude auth status` reports login
  state (exit-code semantics **NOT CONFIRMED** — adapter parses output
  defensively); `claude setup-token` can mint a 1-year OAuth token for
  Pro/Max+ (env `CLAUDE_CODE_OAUTH_TOKEN`).
  https://code.claude.com/docs/en/authentication.md
- Exit codes: 0 success / non-zero failure / 143 on SIGTERM; stdin cap 10MB.
  https://code.claude.com/docs/en/headless.md
- **Usage pools:** programmatic use (`claude -p`, Agent SDK, CI) reportedly
  draws from a separate monthly programmatic-credit pool on subscription
  plans (effective mid-2026; Pro $20 / Max 5x $100 / Max 20x $200 monthly
  allowances, billed at API rates, non-rollover). Source found was
  third-party (https://freee-ai.jp/2025/claude-usage-credits) — **NOT
  CONFIRMED against an official Anthropic page; verify before shipping docs
  that promise "no additional model bill."** Product copy must say
  "uses your existing Claude subscription's programmatic allowance."
- Extensibility formats used by our agent studio: hooks events
  (PreToolUse/PostToolUse/Stop/…; exit 0 = ok, exit 2 = blocking, stdout JSON
  contract) https://code.claude.com/docs/en/hooks.md ; subagent frontmatter
  (`name`, `description`, `model`, `tools`, `permissionMode`)
  https://code.claude.com/docs/en/agent-sdk/subagents.md ; skills
  `SKILL.md` https://code.claude.com/docs/en/skills.md ; permission rules in
  settings https://code.claude.com/docs/en/settings.md
- Codex CLI: `codex exec` non-interactive mode with sandbox flags exists but
  official first-party docs were not located (**NOT CONFIRMED**; third-party
  only). Gemini CLI non-interactive mode: **NOT CONFIRMED**. Both stay
  v0.2+ with a research task packet of their own.

## 2. Robinhood — the load-bearing finding

**Official Agentic Trading MCP exists** (launched 2026-05-27):

- Announcement: "Robinhood is Now Open to Agents" — Agentic Trading (beta,
  equities first) + Agentic Credit Card via "Robinhood's AI-native Model
  Context Protocol (MCP) servers"; agent funds isolated to a dedicated
  account. https://robinhood.com/us/en/newsroom/robinhood-is-now-open-to-agents/
- Product page: dedicated brokerage account for agent trading; budget
  controls; per-trade notifications; disconnect anytime; explicit "data
  leaves Robinhood's security environment" warning.
  https://robinhood.com/us/en/agentic-trading/
- **Endpoint:** hosted remote MCP `https://agent.robinhood.com/mcp/trading`;
  browser-based OAuth-style approval through the Robinhood login (agent never
  sees the password); trading confined to the dedicated Agentic account;
  read-only visibility across other accounts.
  https://robinhood.com/us/en/support/articles/agentic-trading-overview/
- Tool surface: account/portfolio/P&L/history/watchlist reads; market data
  (real-time quotes, OHLCV, RSI/MACD/Bollinger/MAs, fundamentals, earnings
  calendar, order books, index data); trade simulation; equity + options
  order placement/cancel.
  https://robinhood.com/us/en/support/articles/trading-with-your-agent/
- **Transport CONFIRMED 2026-08-05** (docs updated since first research):
  streamable **HTTP**. Robinhood documents the Claude Code connect verbatim as
  `claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading`,
  then `/mcp` -> select `robinhood-trading` -> authenticate.
  https://robinhood.com/us/en/support/articles/agentic-trading-overview/#ConnectyourAIagent
- **Account flow is the reverse of what we assumed.** The agentic account is not
  opened first: "Complete the onboarding that auto-opens **after** you connect to
  the Robinhood Trading MCP." Prerequisite is a primary individual investing
  account in good standing. Desktop only — "You can only open an agentic account
  and authenticate your agent on a desktop device."
- Token lifetimes and scopes: still unpublished; probe at integration time.
- Tool names/schemas: still unpublished; must be enumerated from a live
  tool-list call. Treated as a read-only source in v0.1 regardless.
- No official equities REST API for retail exists (crypto REST API only:
  API-key + Ed25519 signing, https://docs.robinhood.com/crypto/trading/).
  Unofficial private-API wrappers (`robin_stocks`, community MCP servers such
  as verygoodplugins/robinhood-mcp) are ToS-risky — **excluded** per product
  rules.
- Alignment note: Robinhood's dedicated-agentic-account + budget + isolation
  model matches TradeOS mode 3's design (dedicated account, fixed budget,
  kill switch) — designed independently, now confirmed viable.

## 3. macOS platform

- Textual 8.2.8 (2026-06-30), MIT, Python ≥3.9; confirms App/Screen/DataTable/
  RichLog/Header/Footer/CSS/BINDINGS/workers and headless testing via
  `run_test()` + Pilot. https://pypi.org/project/textual/ ,
  https://textual.textualize.io/guide/testing/
- Secrets: `keyring` 25.7.0 (macOS Keychain backend; caveat: items created by
  a Python executable are readable by that executable without prompting) —
  https://pypi.org/project/keyring/ ; raw `security add-generic-password -U`
  / `find-generic-password -w` verified from local man page (no stable Apple
  URL — **NOT CONFIRMED online**); data-protection keychain requires app
  bundle + entitlements (not viable for CLI) per TN3137
  https://developer.apple.com/documentation/technotes/tn3137-on-mac-keychains
  → v0.1 decision: `security` CLI wrapper (no dependency, ACL model suits a
  CLI); revisit for the desktop app.
- Notifications: `osascript` `display notification` is the pragmatic zero-dep
  path (attribution goes to the scripting process — cosmetic limitation);
  terminal-notifier optional upgrade (repo alive, releases frozen at 2.0.0);
  UserNotifications needs an app bundle.
  https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/DisplayNotifications.html ,
  https://github.com/julienXX/terminal-notifier
- SQLite: JSON1 + WAL verified empirically on this machine (Python 3.14.3 /
  SQLite 3.51.3); JSON1 built-in since SQLite 3.38.
  https://sqlite.org/json1.html · DuckDB 1.5.5 available when analytics
  justify it. https://pypi.org/project/duckdb/

## 4. SEC EDGAR (free filings path for v0.1)

- No auth/API keys; JSON; near-real-time.
  https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Endpoints: `data.sec.gov/submissions/CIK##########.json`,
  `/api/xbrl/companyfacts/CIK##########.json`, `/api/xbrl/companyconcept/…`,
  `/api/xbrl/frames/…`; nightly bulk zips. (same URL)
- Fair access: **max 10 req/s** + declared User-Agent
  (`Company AdminContact@domain`) + gzip; undeclared bots get blocked
  (403 empirically confirmed during research).
  https://www.sec.gov/os/webmaster-faq#developers
- Full-text search backend `efts.sec.gov/LATEST/search-index?q=…` verified
  live; documented only via the UI FAQ.
  https://www.sec.gov/edgar/search/efts-faq.html

## 5. Market data / news / social candidates (no-budget reality)

| Source | Verdict for v0.1 | Key facts |
|---|---|---|
| Robinhood MCP market-data tools | **primary quote/fundamentals path** once connected | real-time quotes, OHLCV, indicators (§2) |
| SEC EDGAR | **primary filings path** | §4 |
| Bluesky Jetstream firehose | best free social option (v0.1-optional connector) | public websocket, no key: `jetstream2.us-east.bsky.network/subscribe` https://docs.bsky.app/docs/advanced-guides/firehose ; Bluesky-only content — a diversity floor must reflect that |
| Alpha Vantage | daily-close fallback only | free tier 25 req/day https://www.alphavantage.co/premium/ |
| Finnhub | possible, verify terms | free key exists; personal-use restriction on JS-rendered pricing page **NOT CONFIRMED** https://finnhub.io/docs/api/rate-limit |
| Reddit Data API | excluded v0.1 | non-commercial scope, no ML-training on content, paid beyond default limits https://www.redditinc.com/policies/data-api-terms |
| Stocktwits | **dead** — do not build | developer docs 404; legacy endpoint has no ToS/program behind it |
| Stooq | unverified | site behind JS wall; license unconfirmed |

## 6. Consolidated NOT-CONFIRMED register

1. Programmatic-credit pool details for Claude subscriptions (third-party
   source only) — blocks marketing copy, not architecture.
2. `claude auth status` exit codes; Keychain item name (we don't need it).
3. Robinhood MCP transport/token/scope details — probe at integration.
4. Robinhood ToS exact clause text on unofficial API use (PDF font
   obfuscation) — moot: we only use official surfaces.
5. Codex CLI / Gemini CLI official non-interactive docs.
6. Finnhub free-tier terms; Reddit 100 QPM figure; Stooq license.
7. Notification attribution behavior for osascript-from-Terminal (cosmetic).
8. Cloudflare figures below are re-verify-before-build (they change): Workers
   free 100k req/day · Queues free 10k ops/day, 24 h retention · D1 free
   500 MB/db, 5M reads/day, 100k writes/day · R2 free 10 GB + zero egress ·
   Vectorize free tier exists · Durable Objects free = SQLite backend only ·
   KV free 1k writes/day · Cron 5 triggers/account free.
   https://developers.cloudflare.com/workers/platform/limits/ and sibling
   `platform/limits/` pages per product.
