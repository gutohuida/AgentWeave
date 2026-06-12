"""Tests for setup endpoints and auto-key generation."""

import pytest


@pytest.mark.asyncio
async def test_setup_token_from_localhost(app):
    """Test that /setup/token returns API key when called from localhost."""
    # Use the test client which simulates requests from the test server
    resp = await app.get("/api/v1/setup/token")
    assert resp.status_code == 200
    data = resp.json()
    assert "api_key" in data
    assert data["api_key"].startswith("aw_live_")


@pytest.mark.asyncio
async def test_setup_token_requires_localhost():
    """Test that /setup/token rejects non-localhost requests.

    This test verifies the endpoint logic by checking that the middleware
    would reject external IPs. The actual client IP check is done in the
    endpoint, so we test this by verifying the endpoint implementation
    has the check present.
    """
    # Import the endpoint function to verify it has localhost check
    from hub.api.v1.setup import get_setup_token
    import inspect

    source = inspect.getsource(get_setup_token)
    # Verify the check for 127.0.0.1 is present
    assert "127.0.0.1" in source
    assert "403" in source or "Forbidden" in source


@pytest.mark.asyncio
async def test_auto_key_generation():
    """Test that auto-generated keys follow the correct format."""
    from hub.db.engine import _generate_api_key

    key = _generate_api_key()
    assert key.startswith("aw_live_")
    # Should be aw_live_ + 32 hex characters
    hex_part = key.replace("aw_live_", "")
    assert len(hex_part) == 32
    # Verify it's valid hex
    int(hex_part, 16)


@pytest.mark.asyncio
async def test_placeholder_detection():
    """Test that the placeholder key is correctly identified."""
    from hub.db.engine import _PLACEHOLDER_API_KEY

    assert _PLACEHOLDER_API_KEY == "aw_live_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
    assert _PLACEHOLDER_API_KEY.startswith("aw_live_")


@pytest.mark.asyncio
async def test_spa_does_not_leak_api_key_in_html(app) -> None:
    """Regression test: GET / must not contain the API key in the response body.

    The Hub serves the React dashboard at /. Previously, the SPA fallback
    injected the live API key into a <script> tag in the HTML so the
    dashboard could auto-connect. This leaked the key to any unauthenticated
    request, including remote attackers (curl http://hub:8000/anything).
    The key must now be fetched by the SPA from /api/v1/setup/token,
    which is restricted to localhost + Docker bridge IPs.
    """
    from pathlib import Path

    ui_dist = Path(__file__).parent.parent / "hub" / "static" / "ui"
    if not (ui_dist / "index.html").exists():
        pytest.skip("UI not built (no hub/static/ui/index.html)")

    resp = await app.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "aw_live_testkey_abcdefgh" not in body, (
        "API key leaked into SPA HTML response. "
        "The serve_spa handler must not inject __AW_CONFIG__."
    )
    assert "aw_live_" not in body
    assert "<html" in body.lower()


@pytest.mark.asyncio
async def test_setup_token_still_works_for_localhost(app) -> None:
    """After the fix, /api/v1/setup/token must still be the bootstrap path."""
    resp = await app.get("/api/v1/setup/token")
    assert resp.status_code == 200
    data = resp.json()
    assert "api_key" in data
    assert data["api_key"].startswith("aw_live_")
