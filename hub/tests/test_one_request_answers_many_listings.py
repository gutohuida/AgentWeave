"""Perf slice 4: one request answers what the app read once per project, or once per agent.

`GET /api/v1/conversations?project_id=..` carries several projects' rail listings and
`GET /projects/{id}/queue-status?agent=..` several agents' queue statuses. Each body inside is the
one the per-project or per-agent route answers, compared here byte for byte, so the two cannot drift;
a name the single route would 404 is listed as missing rather than failing the whole request.
"""

import pytest

from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Project
from hub.inbound_queue import new_entry

pytestmark = pytest.mark.asyncio

P = "/api/v1/projects/proj-test"


async def _seed() -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-other", name="Other"))
        session.add(Agent(id="agt-a", project_id="proj-test", name="alpha"))
        session.add(Agent(id="agt-b", project_id="proj-test", name="beta"))
        session.add(Agent(id="agt-c", project_id="proj-other", name="gamma"))
        await session.flush()
        for project_id, agent in [
            ("proj-test", "alpha"),
            ("proj-test", "beta"),
            ("proj-other", "gamma"),
        ]:
            session.add(new_conversation(project_id=project_id, agent=agent, origin="operator"))
        archived = new_conversation(project_id="proj-test", agent="alpha", origin="operator")
        archived.lifecycle = "archived"
        session.add(archived)
        session.add(
            new_entry(
                project_id="proj-test",
                agent="beta",
                content="hello",
                origin_type="operator",
                hop_depth=0,
            )
        )
        await session.commit()


@pytest.mark.parametrize("lifecycle", ["open", "archived"])
async def test_the_sidebar_listing_is_each_projects_own_listing(app, auth_headers, lifecycle):
    await _seed()
    many = await app.get(
        "/api/v1/conversations",
        params=[
            ("project_id", "proj-test"),
            ("project_id", "proj-other"),
            ("lifecycle", lifecycle),
        ],
        headers=auth_headers,
    )
    assert many.status_code == 200, many.text
    body = many.json()
    assert body["missing"] == []
    assert list(body["projects"]) == ["proj-test", "proj-other"]
    for project_id in ("proj-test", "proj-other"):
        one = await app.get(
            f"/api/v1/projects/{project_id}/conversations?lifecycle={lifecycle}",
            headers=auth_headers,
        )
        assert one.status_code == 200
        assert body["projects"][project_id] == one.json()
    assert body["projects"]["proj-test"]["conversations"]  # not vacuous: rows were compared


async def test_an_unknown_project_is_missing_not_a_failure(app, auth_headers):
    await _seed()
    r = await app.get(
        "/api/v1/conversations",
        params=[
            ("project_id", "proj-test"),
            ("project_id", "proj-nowhere"),
            ("project_id", "proj-test"),
        ],
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert list(r.json()["projects"]) == ["proj-test"]
    assert r.json()["missing"] == ["proj-nowhere"]


async def test_the_sidebar_listing_requires_the_operator(app, auth_headers):
    await _seed()
    assert (await app.get("/api/v1/conversations?project_id=proj-test")).status_code == 401
    assert (await app.get("/api/v1/conversations", headers=auth_headers)).status_code == 422


async def test_queue_statuses_are_each_agents_own_status(app, auth_headers):
    await _seed()
    many = await app.get(
        f"{P}/queue-status",
        params=[("agent", "alpha"), ("agent", "beta"), ("agent", "ghost"), ("agent", "gamma")],
        headers=auth_headers,
    )
    assert many.status_code == 200, many.text
    body = many.json()
    # gamma is another project's agent: this project's single route answers it 404 too.
    assert body["missing"] == ["ghost", "gamma"]
    assert list(body["statuses"]) == ["alpha", "beta"]
    for agent in ("alpha", "beta"):
        one = await app.get(f"{P}/queue/{agent}/status", headers=auth_headers)
        assert one.status_code == 200
        assert body["statuses"][agent] == one.json()
    assert body["statuses"]["beta"]["waiting_count"] == 1  # not vacuous: a waiting entry compared
    assert (await app.get(f"{P}/queue/ghost/status", headers=auth_headers)).status_code == 404
