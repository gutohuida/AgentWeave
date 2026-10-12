"""F582: a path that no route matches answers 404 whatever the method.

The dashboard's SPA fallback is `GET /{full_path:path}`. Starlette scores it a partial match for
every path under any other method, so `POST /api/v1/no/such/route` was told `405 Method Not
Allowed` - it was told to change the method when the path is what does not exist. A path that does
exist under another method must keep its 405.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from hub.main import create_app


@pytest.fixture
def spa_app():
    from hub.main import UI_DIST

    if not UI_DIST.exists():
        pytest.skip("needs the committed UI bundle: the SPA fallback is only mounted with it")
    return create_app()


async def _call(app, method: str, path: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://hub") as client:
        return await client.request(method, path)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_unknown_api_path_is_404_not_405(spa_app, method):
    resp = await _call(spa_app, method, "/api/v1/projects/proj-x/vault/no-such-route")
    assert resp.status_code == 404, resp.text
    assert resp.json() == {"detail": "Not Found"}


@pytest.mark.asyncio
async def test_unknown_non_api_path_is_404_not_405_for_post(spa_app):
    resp = await _call(spa_app, "POST", "/no/such/page")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_known_path_under_the_wrong_method_stays_405(spa_app):
    # /health is registered for GET only.
    resp = await _call(spa_app, "POST", "/health")
    assert resp.status_code == 405, resp.text


@pytest.mark.asyncio
async def test_known_api_path_under_the_wrong_method_stays_405(spa_app):
    resp = await _call(spa_app, "DELETE", "/api/v1/projects")
    assert resp.status_code == 405, resp.text
    assert "allow" in resp.headers
