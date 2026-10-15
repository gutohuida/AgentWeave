"""F644: a capability created from the app lands under `spec/capabilities/<name>/`.

`POST /project/documents {"kind": "capability"}` with no path minted the change placeholder
`spec/changes/<random>/spec.json`, so the corpus convention was reachable only by naming a path.
A capability is named from its title; a change keeps its placeholder name.
"""

import pytest

BASE = "/api/v1/projects/proj-test/project"


async def _create(app, headers, **body):
    resp = await app.post(f"{BASE}/documents", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["path"]


@pytest.mark.asyncio
async def test_a_capability_is_named_from_its_title_under_capabilities(app, auth_headers):
    path = await _create(app, auth_headers, title="Temperature conversion", kind="capability")
    assert path == "spec/capabilities/temperature-conversion/spec.json"


@pytest.mark.asyncio
async def test_a_second_capability_with_the_same_title_gets_a_free_name(app, auth_headers):
    await _create(app, auth_headers, title="Rounding", kind="capability")
    second = await _create(app, auth_headers, title="Rounding", kind="capability")
    assert second == "spec/capabilities/rounding-2/spec.json"


@pytest.mark.asyncio
async def test_a_capability_with_no_usable_title_still_lands_under_capabilities(app, auth_headers):
    path = await _create(app, auth_headers, title="???", kind="capability")
    assert path.startswith("spec/capabilities/") and path.endswith("/spec.json")


@pytest.mark.asyncio
async def test_a_change_keeps_its_placeholder_name(app, auth_headers):
    path = await _create(app, auth_headers, title="Temperature conversion")
    assert path.startswith("spec/changes/")
    assert "temperature" not in path
