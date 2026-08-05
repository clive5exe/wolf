"""The one place WOLF opens an outbound HTTP connection.

Standard library only. Adding ``requests`` or ``httpx`` would buy connection
pooling we do not need at five requests a second, and cost a dependency on an
installer that must work on macOS and Linux without sudo.

Deliberate behaviours, each of which exists because the alternative hides a
failure the caller needs to see:

* **Non-2xx is returned, not raised.** Connectors record an ``ingest.error``
  event carrying the status. An exception would lose the status.
* **Responses are decompressed here.** SEC honours ``Accept-Encoding`` and
  ``urllib`` does not decode the result, so a caller that forgets is handed
  gzip bytes and blames its JSON parser.
* **Bodies are size-capped.** A redirect to something enormous should fail
  loudly rather than exhaust memory on a machine that is also holding a
  portfolio.
* **Only http(s) is followed.** ``urllib`` will happily open ``file://``.
"""

from __future__ import annotations

import gzip
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from typing import Final

#: 64 MB. SEC's largest companyfacts documents run to tens of megabytes, so this
#: has to clear them comfortably while still refusing anything absurd.
MAX_BODY_BYTES: Final[int] = 64 * 1024 * 1024

ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})


class TransportError(RuntimeError):
    """The request could not be completed at all, as opposed to answering badly."""


def _decompress(body: bytes, encoding: str) -> bytes:
    enc = encoding.lower().strip()
    if enc == "gzip":
        return gzip.decompress(body)
    if enc == "deflate":
        try:
            return zlib.decompress(body)
        except zlib.error:
            # Some servers send raw deflate without the zlib header.
            return zlib.decompress(body, -zlib.MAX_WBITS)
    return body


@dataclass(frozen=True, slots=True)
class HttpTransport:
    """A minimal GET client satisfying the connectors' ``Transport`` protocol."""

    #: Kept small on purpose. A connector that needs redirects chased across
    #: hosts is a connector pointed at the wrong URL.
    max_redirects: int = 3

    def get(self, url: str, *, headers: dict[str, str], timeout_s: float) -> tuple[int, bytes]:
        scheme = url.split(":", 1)[0].lower()
        if scheme not in ALLOWED_SCHEMES:
            raise TransportError(f"refusing non-http(s) URL scheme: {scheme!r}")

        request = urllib.request.Request(url, headers=headers, method="GET")
        opener = urllib.request.build_opener(
            urllib.request.HTTPRedirectHandler(),
        )
        try:
            with opener.open(request, timeout=timeout_s) as response:
                raw = response.read(MAX_BODY_BYTES + 1)
                if len(raw) > MAX_BODY_BYTES:
                    raise TransportError(f"response exceeded {MAX_BODY_BYTES} bytes: {url}")
                encoding = response.headers.get("Content-Encoding", "")
                return int(response.status), _decompress(raw, encoding)
        except urllib.error.HTTPError as exc:
            # A status is an answer. Read the body so the caller can log why.
            body = b""
            try:
                body = exc.read(MAX_BODY_BYTES)
                body = _decompress(body, exc.headers.get("Content-Encoding", ""))
            except Exception:
                body = b""
            return int(exc.code), body
        except urllib.error.URLError as exc:
            raise TransportError(f"could not reach {url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise TransportError(f"timed out after {timeout_s}s: {url}") from exc
