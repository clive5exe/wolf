"""OAuth 2.1 for the Robinhood Agentic MCP server.

Verified against the live endpoints on 2026-08-05. See
``specs/research/ROBINHOOD_OAUTH.md`` for the probe results.

The server is a **public client**: ``token_endpoint_auth_methods_supported`` is
``["none"]``, so there is no client secret. That is the right shape for
software users clone, because there is no confidential value to leak, and it is
why PKCE is not optional here. Without a secret, the code verifier is the only
thing binding the authorization code to the client that asked for it.

It also advertises a ``registration_endpoint``, so WOLF registers itself on
first run. The user never creates an app, never visits a developer portal, and
never pastes a key. They approve in a browser once.

Only loopback redirects are used. A public client cannot safely accept a
redirect to a URI it does not control, and ``127.0.0.1`` is the one address
that is provably local.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import socket
import threading
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Final

from tradeos.ingestion.http import HttpTransport, TransportError

DISCOVERY_URL: Final = "https://agent.robinhood.com/.well-known/oauth-authorization-server"
RESOURCE: Final = "https://agent.robinhood.com/mcp/trading"

CLIENT_NAME: Final = "WOLF"
CLIENT_URI: Final = "https://wolf.clive5.com"

#: Keystore entries. Renaming one orphans a live credential.
CLIENT_ID_KEY: Final = "robinhood_client_id"
ACCESS_TOKEN_KEY: Final = "robinhood_access_token"
REFRESH_TOKEN_KEY: Final = "robinhood_refresh_token"


class OAuthError(RuntimeError):
    """Authorisation failed in a way worth showing the user."""


@dataclass(frozen=True, slots=True)
class ServerMetadata:
    """The discovery document, reduced to what the flow actually uses."""

    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str
    scopes: tuple[str, ...]

    @classmethod
    def parse(cls, payload: dict[str, Any]) -> ServerMetadata:
        missing = [
            k
            for k in ("authorization_endpoint", "token_endpoint", "registration_endpoint")
            if not payload.get(k)
        ]
        if missing:
            # Without registration there is no way to obtain a client_id, and
            # the whole no-paste flow collapses. Fail loudly rather than
            # silently degrading to "ask the user for credentials".
            raise OAuthError(f"discovery document is missing {', '.join(missing)}")
        methods = payload.get("code_challenge_methods_supported") or []
        if "S256" not in methods:
            raise OAuthError(
                "server does not advertise PKCE S256. A public client without "
                "PKCE has nothing binding the code to it, so WOLF will not proceed"
            )
        return cls(
            authorization_endpoint=str(payload["authorization_endpoint"]),
            token_endpoint=str(payload["token_endpoint"]),
            registration_endpoint=str(payload["registration_endpoint"]),
            scopes=tuple(payload.get("scopes_supported") or ("internal",)),
        )


@dataclass(frozen=True, slots=True)
class Pkce:
    """A code verifier and its challenge."""

    verifier: str
    challenge: str

    @classmethod
    def create(cls) -> Pkce:
        # 96 bytes of entropy, well above RFC 7636's 32-octet floor, and the
        # base64url alphabet is exactly what the spec permits unencoded.
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(96)).decode().rstrip("=")
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return cls(verifier, base64.urlsafe_b64encode(digest).decode().rstrip("="))


def discover(transport: HttpTransport | None = None) -> ServerMetadata:
    """Read the authorization server metadata. Never hardcode these."""
    transport = transport or HttpTransport()
    try:
        status, body = transport.get(
            DISCOVERY_URL, headers={"Accept": "application/json"}, timeout_s=20
        )
    except TransportError as exc:
        raise OAuthError(f"could not reach Robinhood: {exc}") from exc
    if status != 200:
        raise OAuthError(f"discovery returned HTTP {status}")
    return ServerMetadata.parse(json.loads(body))


def _post_json(url: str, payload: dict[str, Any] | str, *, form: bool = False) -> dict[str, Any]:
    """POST and decode JSON. Kept local so the module has no new dependency."""
    import urllib.error
    import urllib.request

    if form:
        data = urllib.parse.urlencode(payload).encode()  # type: ignore[arg-type]
        content_type = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(payload).encode()
        content_type = "application/json"
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": content_type, "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return dict(json.loads(response.read()))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise OAuthError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise OAuthError(f"could not reach {url}: {exc.reason}") from exc


def register(metadata: ServerMetadata, redirect_uri: str) -> str:
    """Register WOLF and return the issued ``client_id``.

    Done once per install. The id is not secret, but it is stored in the
    keystore beside the tokens so a single ``wolf connect --forget`` removes
    everything about the connection rather than leaving a stale registration.
    """
    payload = _post_json(
        metadata.registration_endpoint,
        {
            "client_name": CLIENT_NAME,
            "client_uri": CLIENT_URI,
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": " ".join(metadata.scopes),
        },
    )
    client_id = payload.get("client_id")
    if not client_id:
        raise OAuthError("registration succeeded but returned no client_id")
    return str(client_id)


def authorization_url(
    metadata: ServerMetadata, client_id: str, redirect_uri: str, pkce: Pkce, state: str
) -> str:
    return (
        metadata.authorization_endpoint
        + "?"
        + urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": " ".join(metadata.scopes),
                "state": state,
                "code_challenge": pkce.challenge,
                "code_challenge_method": "S256",
                # RFC 8707. Binds the token to this MCP server rather than issuing
                # something replayable against another Robinhood surface.
                "resource": RESOURCE,
            }
        )
    )


def exchange_code(
    metadata: ServerMetadata, client_id: str, code: str, redirect_uri: str, pkce: Pkce
) -> dict[str, Any]:
    return _post_json(
        metadata.token_endpoint,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": pkce.verifier,
            "resource": RESOURCE,
        },
        form=True,
    )


def refresh(metadata: ServerMetadata, client_id: str, refresh_token: str) -> dict[str, Any]:
    return _post_json(
        metadata.token_endpoint,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "resource": RESOURCE,
        },
        form=True,
    )


# -- loopback listener --------------------------------------------------------


@dataclass
class _Callback:
    code: str | None = None
    state: str | None = None
    error: str | None = None
    received: threading.Event = field(default_factory=threading.Event)


class LoopbackReceiver:
    """Catches the redirect on 127.0.0.1.

    Binds port 0 and reports what the OS assigned, because a fixed port
    collides with whatever else the user is running, and a collision here
    surfaces as a browser error page with no explanation.
    """

    def __init__(self) -> None:
        self._result = _Callback()
        self._server = http.server.HTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/callback"

    def _handler(self) -> type[http.server.BaseHTTPRequestHandler]:
        result = self._result

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                result.code = (query.get("code") or [None])[0]
                result.state = (query.get("state") or [None])[0]
                result.error = (query.get("error") or [None])[0]
                body = (
                    b"<body style='background:#000;color:#F5F5F5;font-family:monospace;"
                    b"display:flex;align-items:center;justify-content:center;height:100vh'>"
                    b"<div style='text-align:center'>"
                    b"<div style='color:#FF2247;font-size:22px'>WOLF connected</div>"
                    b"<div style='color:#8A8A8A;margin-top:10px'>You can close this tab.</div>"
                    b"</div></body>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                result.received.set()

            def log_message(self, *_: Any) -> None:
                """Silence. The console belongs to the CLI during this flow."""

        return Handler

    def __enter__(self) -> LoopbackReceiver:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    def wait(self, expected_state: str, timeout_s: float = 300) -> str:
        """Block for the redirect and return the authorization code."""
        if not self._result.received.wait(timeout_s):
            raise OAuthError(
                f"no response after {int(timeout_s)}s. If the browser never "
                "opened, use the link printed above"
            )
        if self._result.error:
            raise OAuthError(f"Robinhood refused authorisation: {self._result.error}")
        if self._result.state != expected_state:
            # A mismatch means the redirect did not originate from the request
            # this process started, which is what state exists to detect.
            raise OAuthError("state mismatch, discarding the response")
        if not self._result.code:
            raise OAuthError("no authorization code in the redirect")
        return self._result.code


def free_port() -> int:
    """An available loopback port, for callers that need one in advance."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
