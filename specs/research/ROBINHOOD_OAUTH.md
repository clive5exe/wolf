# Robinhood Agentic MCP: the auth surface

Probed live 2026-08-05. Everything here was read off the wire, not from docs.

## Endpoints

| | |
|---|---|
| MCP | `https://agent.robinhood.com/mcp/trading` |
| Discovery | `https://agent.robinhood.com/.well-known/oauth-authorization-server` |
| Resource metadata | `https://agent.robinhood.com/.well-known/oauth-protected-resource/mcp/trading` |
| Authorization | `https://robinhood.com/oauth` |
| Token | `https://api.robinhood.com/oauth2/token/` |
| Registration | `https://agent.robinhood.com/oauth/trading/register` |

## What it tells us

```
code_challenge_methods_supported      ["S256"]
grant_types_supported                 ["authorization_code", "refresh_token"]
scopes_supported                      ["internal"]
token_endpoint_auth_methods_supported ["none"]
```

Four things follow, and all four are good news:

1. **Public client, no secret.** `auth_methods: ["none"]` means there is no
   client secret to ship, so nothing confidential has to live in a repo that
   users clone. This is the correct shape for a desktop app.
2. **PKCE S256 is mandatory and supported.** The code verifier is what protects
   the exchange in the absence of a secret.
3. **Dynamic client registration works.** A `registration_endpoint` is
   advertised, so WOLF registers itself at first run rather than asking
   Robinhood to issue credentials or asking the user to create an app.
4. **Refresh tokens are issued**, so a user authorises once rather than every
   session.

Unauthenticated requests answer `401` with a correct
`WWW-Authenticate: Bearer resource_metadata="..."` header, so the client can
discover where to authenticate from the failure itself.

## The one scope is `internal`

There is no read-only scope. This was checked when Q2 was answered and it has
not changed: an authorised token can place orders. The allowlist in
`mcp/registry.py` is therefore the *only* thing standing between the model and
an execution tool, which is why it is an S2 surface and why `ensure_callable`
refuses anything not on it rather than filtering after the fact.

## Build order

1. Discovery, with the response cached and re-validated rather than hardcoded.
2. Dynamic registration, storing the issued `client_id` in the OS keystore.
3. Authorization code + PKCE. Opens a browser, listens on a loopback port,
   which is the only redirect a public client can safely use.
4. Token exchange and refresh, tokens in the keystore, never on disk.
5. Streamable HTTP MCP client, honouring `Mcp-Session-Id`.
6. Adapter mapping the allowlisted read tools onto the existing `Broker` and
   `QuoteSource` protocols, so the rest of the app does not learn a new shape.
