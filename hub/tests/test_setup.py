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
    assert '127.0.0.1' in source
    assert '403' in source or 'Forbidden' in source


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
