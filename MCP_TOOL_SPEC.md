# MCP & Tool Integration Specification

**Status:** v0.1 · **Implements:** `src/tradeos/{mcp,tools}/`

## 1. Role of MCP in TradeOS

MCP servers are **capability endpoints** (broker access, market data), not
decision makers. TradeOS is an MCP *client*. Two very different consumers:

1. **The runtime core** calls MCP tools directly (deterministic code paths,
   e.g. `robinhood.get_positions`). This is the primary path.
2. **AI providers** may be given a *restricted, read-only* tool subset for
   research tasks (v0.2+; v0.1 providers get NO tools — context is assembled
   by the core and handed to them as data).

## 2. Registry and configuration

`ToolRegistry` loads from `~/.tradeos/mcp.toml` (validated Pydantic config):

```toml
[servers.robinhood]
transport = "http"                  # official hosted server (stdio supported for local servers)
url = "https://agent.robinhood.com/mcp/trading"   # official endpoint, RESEARCH_NOTES §2
allowed_tools = ["get_account", "get_positions", "get_quote", "get_orders"]  # explicit allowlist; names re-probed at startup
tool_class = "broker_read"          # broker_read | broker_trade | market_data | research
timeout_s = 20
```

Rules:
- **Allowlist-only.** A tool not listed is not callable, period.
- `broker_trade` class tools cannot be listed while the active policy mode is
  read_only/paper (config validation cross-checks policy; also re-checked at
  call time).
- Servers are spawned as subprocesses with clean env (no ambient secrets);
  credentials are injected per-server from Keychain by name, never inherited.
- Every tool call and response → `tool.call`/`tool.result` events (payloads
  redacted per telemetry rules).

## 3. Call contract

```python
class ToolCall(BaseModel):
    server: str; tool: str; args: dict[str, Any]
    correlation_id: str; timeout_s: int

class ToolResult(BaseModel):
    ok: bool; value: Any | None; error: str | None
    duration_ms: int; called_at: datetime
```

Responses feeding domain logic are validated into domain models at the
adapter (`brokers/robinhood.py` maps MCP payloads → `AccountState`,
`Position`, `Quote`); raw payloads are stored as raw ingestion events for
audit. Schema drift from a server ⇒ adapter raises, cycle aborts, alert
raised — never best-effort parsing of account data.

## 4. Failure behavior

| Failure | Handling |
|---|---|
| Server won't spawn / handshake timeout | registry marks DOWN, doctor shows fix hint, dependent cycles abort pre-proposal |
| Tool timeout | one retry for idempotent reads; never retry writes; record event |
| Malformed response | adapter ValidationError → abort + alert (fail closed) |
| Unlisted tool requested | `ToolPermissionError`, recorded — this is a bug or an attack |
| Server version/tool-list drift | tool list re-probed at startup; diff logged + surfaced |

## 5. Robinhood MCP adapter (v0.1: read-only)

Targets the **official Agentic Trading MCP** (hosted at
`agent.robinhood.com/mcp/trading`, OAuth-style in-app approval; see
RESEARCH_NOTES §2). The adapter implements `BrokerAdapter`'s read methods
only (`get_account`, `get_positions`, `get_quote(s)`, `get_orders`); its
`submit_order` raises `BrokerCapabilityError` in v0.1 regardless of
configuration, and the server's trading tools are never allowlisted in 0.1.
Exact tool names/schemas are unpublished → the adapter probes the tool list
at connect time, maps by documented capability, validates every payload, and
fails closed on drift. Unofficial community Robinhood servers are excluded
(DATA_SOURCES §3).

## 6. Acceptance criteria

1. Registry refuses unlisted tools and `broker_trade` tools in v0.1 modes
   (unit tests).
2. Contract tests: fake MCP server exercises timeout, malformed payload,
   drift, and allowlist paths.
3. All tool traffic visible as events with redaction applied.
