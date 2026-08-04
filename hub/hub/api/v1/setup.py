"""Setup endpoints for Hub initialization and CLI discovery."""

import logging
from typing import Any, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from ...db.engine import async_session_factory
from ...db.models import OperatorCredential

logger = logging.getLogger(__name__)

router = APIRouter(tags=["setup"])


def _is_local_address(host: Optional[str]) -> bool:
    """Return True if the host is a local/Docker-internal address.

    Accepts:
    - 127.x.x.x  — loopback range
    - ::1         — IPv6 loopback
    - 172.16-31.x.x — Docker bridge networks (RFC1918, Docker default pool)
    - 10.x.x.x   — Docker custom bridge / internal networks
    """
    if not host:
        return False
    if host == "::1":
        return True
    parts = host.split(".")
    if len(parts) != 4:
        return False
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    if a == 127:
        return True
    if a == 10:
        return True
    return a == 172 and 16 <= b <= 31


def _hostname_from_host_header(host_header: str) -> str:
    """Strip the optional port (and IPv6 brackets) from a Host header value."""
    host_header = host_header.strip()
    if host_header.startswith("["):
        end = host_header.find("]")
        return host_header[1:end] if end != -1 else host_header
    return host_header.split(":")[0]


def _is_allowed_host(host_header: Optional[str]) -> bool:
    """Return True if the Host header itself names a loopback/Docker-internal address.

    Checking the client's socket address alone is not enough: a DNS-rebinding
    attack serves a page from a public hostname that later resolves to
    127.0.0.1, so the socket-level check passes while the browser's Host
    header still names the attacker's domain. Requiring Host to independently
    resolve to a loopback allowlist entry defeats that.
    """
    if not host_header:
        return False
    hostname = _hostname_from_host_header(host_header).lower()
    if hostname == "localhost":
        return True
    return _is_local_address(hostname)


def _origin_is_same_or_absent(origin_header: Optional[str], host_header: Optional[str]) -> bool:
    """Return True if Origin is absent, or matches Host — rejects cross-origin browser calls.

    A plain top-level navigation or non-browser client (curl, the CLI) sends
    no Origin header at all, which is fine. A cross-site page fetching this
    endpoint via JS sends an Origin that will not match Host; CORS does not
    block that by itself since this endpoint sets no ACAO header, so the
    comparison has to be done explicitly.
    """
    if not origin_header:
        return True
    if not host_header:
        return False
    parsed = urlsplit(origin_header)
    if not parsed.netloc:
        return False
    return parsed.netloc.lower() == host_header.lower()


@router.get("/setup/token")
async def get_setup_token(request: Request) -> dict[str, Any]:
    """Return the bootstrap API key - only accessible from localhost.

    This endpoint allows the CLI to automatically discover the Hub's API key
    after starting the Hub container, enabling zero-touch configuration.

    Accepts loopback (127.x.x.x, ::1) and Docker bridge addresses (172.16-31.x.x,
    10.x.x.x) since Docker port-forwarding makes host requests appear to arrive
    from the Docker gateway IP rather than 127.0.0.1.

    Also validates the Host and Origin headers: the socket-level check alone
    is vulnerable to DNS rebinding (a public hostname that resolves to
    127.0.0.1), and CORS alone does not block a rebound Host from a browser.
    """
    # Enforce local-only access
    client_host = request.client.host if request.client else None
    if not _is_local_address(client_host):
        logger.warning(f"Rejected /setup/token request from {client_host}")
        raise HTTPException(status_code=403, detail="Forbidden: localhost only")

    host_header = request.headers.get("host")
    if not _is_allowed_host(host_header):
        logger.warning(f"Rejected /setup/token request with Host: {host_header}")
        raise HTTPException(status_code=403, detail="Forbidden: invalid Host header")

    origin_header = request.headers.get("origin")
    if not _origin_is_same_or_absent(origin_header, host_header):
        logger.warning(f"Rejected /setup/token request with Origin: {origin_header}")
        raise HTTPException(status_code=403, detail="Forbidden: cross-origin request")

    async with async_session_factory() as session:
        # Return the instance credential; it deliberately carries no project selection.
        result = await session.execute(
            select(OperatorCredential).where(OperatorCredential.revoked.is_(False)).limit(1)
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise HTTPException(status_code=503, detail="No API key configured")

        return {"api_key": api_key.id}
