"""F642: a task's assignee is an open agent of the project, on create and on PATCH.

`PATCH /tasks/{id} {"assignee": "ghost"}` answered 200 and stored the name. The roster no longer
lists a task's assignee as an agent (F618), so a task held by a name with no row would be held by
nobody any surface shows.
"""

import pytest

BASE = "/api/v1/projects/proj-test"


@pytest.mark.asyncio
async def test_create_refuses_an_assignee_that_is_not_an_agent(app, auth_headers):
    resp = await app.post(
        f"{BASE}/tasks", json={"title": "t", "assignee": "ghost"}, headers=auth_headers
    )
    assert resp.status_code == 422, resp.text
    assert "'ghost' is not an agent in this project" in resp.json()["detail"]
    listed = await app.get(f"{BASE}/tasks", headers=auth_headers)
    assert all(t["title"] != "t" for t in listed.json()["tasks"])


@pytest.mark.asyncio
async def test_patch_refuses_an_assignee_that_is_not_an_agent(app, auth_headers, add_agent):
    await add_agent("solo")
    created = await app.post(
        f"{BASE}/tasks", json={"title": "t", "assignee": "solo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    resp = await app.patch(
        f"{BASE}/tasks/{task_id}", json={"assignee": "ghost"}, headers=auth_headers
    )
    assert resp.status_code == 422, resp.text
    assert "'ghost' is not an agent in this project" in resp.json()["detail"]
    again = await app.get(f"{BASE}/tasks/{task_id}", headers=auth_headers)
    assert again.json()["assignee"] == "solo"


@pytest.mark.asyncio
async def test_an_archived_agent_cannot_be_handed_a_task(app, auth_headers, add_agent):
    await add_agent("gone", lifecycle="archived")
    resp = await app.post(
        f"{BASE}/tasks", json={"title": "t", "assignee": "gone"}, headers=auth_headers
    )
    assert resp.status_code == 422, resp.text
    assert "'gone' is archived" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_an_open_agent_and_nobody_are_both_accepted(app, auth_headers, add_agent):
    await add_agent("solo")
    resp = await app.post(
        f"{BASE}/tasks", json={"title": "t", "assignee": "solo"}, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    task_id = resp.json()["id"]
    cleared = await app.patch(
        f"{BASE}/tasks/{task_id}", json={"assignee": None}, headers=auth_headers
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["assignee"] is None
