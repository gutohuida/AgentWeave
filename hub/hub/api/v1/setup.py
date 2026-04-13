"""Setup endpoints for Hub initialization and CLI discovery."""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from ...db.engine import async_session_factory
from ...db.models import ApiKey

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
    if a == 172 and 16 <= b <= 31:
        return True
    return False


@router.get("/setup/token")
async def get_setup_token(request: Request) -> dict[str, Any]:
    """Return the bootstrap API key - only accessible from localhost.

    This endpoint allows the CLI to automatically discover the Hub's API key
    after starting the Hub container, enabling zero-touch configuration.

    Accepts loopback (127.x.x.x, ::1) and Docker bridge addresses (172.16-31.x.x,
    10.x.x.x) since Docker port-forwarding makes host requests appear to arrive
    from the Docker gateway IP rather than 127.0.0.1.
    """
    # Enforce local-only access
    client_host = request.client.host if request.client else None
    if not _is_local_address(client_host):
        logger.warning(f"Rejected /setup/token request from {client_host}")
        raise HTTPException(status_code=403, detail="Forbidden: localhost only")

    async with async_session_factory() as session:
        # Get the first non-revoked API key
        result = await session.execute(
            select(ApiKey).where(ApiKey.revoked == False).limit(1)
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise HTTPException(status_code=503, detail="No API key configured")

        return {"api_key": api_key.id}
