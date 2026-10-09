"""F568: two context routes had no caller and are retired.

`GET /agents/context?charter=` was superseded by `get_agent_context` (its own hint said so), and
`POST /agents/{name}/context-usage` was never called by the product -- the Hub records usage
itself through `output_recording.record_context_usage`, which stays.
"""

import pytest

from ._routing import iter_api_routes


def _paths_and_methods(app):
    return {(method, path) for path, route in iter_api_routes(app) for method in route.methods}


def test_the_charter_lookup_and_context_usage_post_routes_are_gone():
    from hub.main import app as hub_app

    routes = _paths_and_methods(hub_app)
    assert not any(path.endswith("/agents/context") for _, path in routes)
    assert not any(path.endswith("/context-usage") for _, path in routes)


@pytest.mark.asyncio
async def test_the_retired_routes_answer_no_route(app, auth_headers):
    post = await app.post(
        "/api/v1/projects/proj-test/agents/anyone/context-usage",
        json={"status": "unavailable", "source": "x", "observed_at": 1},
        headers=auth_headers,
    )
    assert post.status_code in (404, 405)
    get = await app.get(
        "/api/v1/projects/proj-test/agents/context?charter=charter-x", headers=auth_headers
    )
    assert get.status_code == 404
    assert "Charter" not in get.text
