"""Who may open, attach to or end a shell (FR-1, FR-2, FR-3).

A shell runs any command as the operator, so every route that starts, drives or ends one asks, in
this order, and the first refusal is the answer:

1. **Docker mode** -- a containerised Hub offers no terminal at all.
2. **Loopback only.** The peer must be a loopback address. Docker bridge addresses are *not*
   local here, unlike `/setup/token` (`api/v1/setup.py::_is_local_address`). A request carrying
   any forwarding header (`X-Forwarded-For`, `X-Real-IP`, `Forwarded`) is refused whatever it
   claims: uvicorn trusts forwarded headers from 127.0.0.1, so a proxy on this computer would
   otherwise make anyone it forwards look local, and a request that came through a proxy did not
   come from the app on this computer.
3. **A loopback Host**, so a DNS-rebound name pointing at 127.0.0.1 is not the app.
4. **The app's own page.** Browsers let any website open a WebSocket to localhost, and send a
   cross-site POST without asking; the Origin header is the one thing that says which page asked.
   It must be present (for whatever changes something) and name exactly the Host the request was
   sent to. A GET may omit it -- a same-origin `fetch` GET carries none -- but a foreign one is
   refused there too.

The operator's sign-in is checked by the caller: `get_project` for the HTTP routes, and
`api/v1/terminal.py::_websocket_refusal` for the WebSocket ones, which browsers cannot give a
header.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

from starlette.requests import HTTPConnection

REMOTE_MESSAGE = "The terminal opens only on the computer AgentWeave runs on."
DOCKER_MESSAGE = "The terminal is not available in Docker mode."
FOREIGN_MESSAGE = "A shell can be opened only from AgentWeave's own page."
FORWARDING_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded")


@dataclass(frozen=True)
class Refusal:
    #: "docker" | "remote" | "origin"
    reason: str
    detail: str
    status: int = 403

    def body(self) -> dict:
        return {"detail": self.detail, "reason": self.reason}


def docker_mode() -> bool:
    # The one rule `/health` reports (`main._runtime_kind`), read at the request so a test can set it.
    from ..main import _runtime_kind

    return _runtime_kind() == "docker"


def is_loopback(host: Optional[str]) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback


def _hostname(host_header: str) -> str:
    host_header = host_header.strip()
    if host_header.startswith("["):
        end = host_header.find("]")
        return host_header[1:end] if end != -1 else host_header
    return host_header.rsplit(":", 1)[0] if host_header.count(":") == 1 else host_header


def where_refusal(conn: HTTPConnection) -> Optional[Refusal]:
    """Docker mode, or a request not from this computer: the reason the tab shows as well."""
    if docker_mode():
        return Refusal("docker", DOCKER_MESSAGE)
    peer = conn.client.host if conn.client else None
    if not is_loopback(peer):
        return Refusal("remote", REMOTE_MESSAGE)
    if any(conn.headers.get(name) for name in FORWARDING_HEADERS):
        return Refusal("remote", REMOTE_MESSAGE)
    if not is_loopback(_hostname(conn.headers.get("host") or "")):
        return Refusal("remote", REMOTE_MESSAGE)
    return None


def origin_refusal(conn: HTTPConnection, *, required: bool) -> Optional[Refusal]:
    origin = conn.headers.get("origin")
    if not origin:
        return Refusal("origin", FOREIGN_MESSAGE) if required else None
    parsed = urlsplit(origin)
    host = (conn.headers.get("host") or "").lower()
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return Refusal("origin", FOREIGN_MESSAGE)
    if parsed.netloc.lower() != host:
        return Refusal("origin", FOREIGN_MESSAGE)
    return None


def refusal(conn: HTTPConnection, *, changes_something: bool) -> Optional[Refusal]:
    """The first rule *conn* breaks, or None when it may reach a shell."""
    return where_refusal(conn) or origin_refusal(conn, required=changes_something)
