"""F248: a name a caller chooses must not be a word a route registered earlier answers for.

`GET /queue/settings` is registered before `GET /queue/{agent}`, so an agent named `settings` has a
queue panel that shows the settings. The words are refused at creation only, in the Hub-only
`hub.route_words` (design D1), at every door that adds an agent row and at the one task-id check
both task doors share. The route walk is what finds the next collision (`route-table-checked`).
Spec: `a-name-a-caller-chooses-reaches-its-own-resource`, spdoc-4e1fa307cd4e.
"""

import re

import pytest
from fastapi.routing import APIRoute

from hub import route_words
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.model_catalog import get_provider

BASE = "/api/v1/projects/proj-test"
CLAUDE_MODEL = get_provider("claude").models[0].id

# Parameters the Hub mints itself; a caller never chooses their value (design D5).
HUB_MINTED = {"runner_id", "full_path"}

_PARAM = re.compile(r"^\{(\w+)(?::\w+)?\}$")


def _param(segment):
    match = _PARAM.match(segment)
    return match.group(1) if match else None


def _collisions(routes):
    """(earlier path, later path, word, parameter) for every fixed segment, registered earlier, that
    a later route's parameter would also match over the whole path: shared method, equal depth, every
    segment equal or literal-against-parameter in either direction (design D5)."""
    found = []
    for i, early in enumerate(routes):
        for late in routes[i + 1 :]:
            if not set(early.methods) & set(late.methods):
                continue
            a, b = early.path.split("/"), late.path.split("/")
            if len(a) != len(b):
                continue
            words = []
            for sa, sb in zip(a, b, strict=True):
                pa, pb = _param(sa), _param(sb)
                if pa is None and pb is None:
                    if sa != sb:
                        break
                elif pa is None and pb is not None:
                    words.append((sa, pb))
            else:
                found.extend((early.path, late.path, word, param) for word, param in words)
    return found


def _api_routes():
    from hub.main import app as hub_app

    return [r for r in hub_app.routes if isinstance(r, APIRoute)]


def _refused_for(param, word):
    if param in HUB_MINTED:
        return True
    words = {"agent": route_words.AGENT_WORDS, "task_id": route_words.TASK_WORDS}.get(param, {})
    return word.lower() in words


def test_the_route_table_has_no_unrefused_collision():
    bad = [c for c in _collisions(_api_routes()) if not _refused_for(c[3], c[2])]

    assert bad == [], "\n".join(
        f"{early} is registered before {late}: '{word}' reaches the first, not a "
        f"{{{param}}} named '{word}'"
        for early, late, word, param in bad
    )


def test_the_walk_names_a_literal_route_put_before_a_parameter_route():
    class Fake:
        def __init__(self, path):
            self.path, self.methods = path, {"GET"}

    routes = [Fake("/queue/peek"), Fake("/queue/{agent}")]

    assert _collisions(routes) == [("/queue/peek", "/queue/{agent}", "peek", "agent")]
    assert not _refused_for("agent", "peek")
    # The other order is the ordinary one: the parameter route is last and answers the rest.
    assert _collisions(list(reversed(routes))) == []


def test_the_words_are_the_five_f248_measured():
    assert set(route_words.AGENT_WORDS) == {"conflicts", "settings", "sessions"}
    assert set(route_words.TASK_WORDS) == {"board", "boards"}
    assert "/queue/settings" in route_words.AGENT_WORDS["settings"]
    assert "/agent/sessions/{agent}" in route_words.AGENT_WORDS["sessions"]
    assert route_words.agent_route_word("Settings") is not None
    assert route_words.agent_route_word("settingsx") is None
    assert route_words.agent_route_word("conflict") is None
    assert route_words.task_route_word("BOARDS") is not None
    assert route_words.task_route_word("boardroom") is None


# --- the three agent doors ---------------------------------------------------------------------


async def _roster(app, auth_headers):
    resp = await app.get(f"{BASE}/agents", headers=auth_headers)
    return {row["name"] for row in resp.json()}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name, route",
    [
        ("conflicts", "/worktrees/conflicts"),
        ("settings", "/queue/settings"),
        ("Sessions", "/agent/sessions/{agent}"),
    ],
)
async def test_the_create_dialog_route_refuses_a_route_word(app, auth_headers, name, route):
    resp = await app.post(
        f"{BASE}/agents",
        json={"name": name, "provider": "claude", "model": CLAUDE_MODEL},
        headers=auth_headers,
    )

    assert resp.status_code == 400, resp.text
    # A sentence, not a list: the Add-agent dialog renders `detail` as text.
    assert isinstance(resp.json()["detail"], str)
    assert route in resp.json()["detail"]
    assert name not in await _roster(app, auth_headers)


async def _run_headers(agent="lead", run_id="run-route-words"):
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_an_agent_request_refuses_a_route_word(app, auth_headers, add_agent, bind_runner):
    headers = await _run_headers()
    await add_agent("template")
    await bind_runner("template", cli="claude")

    resp = await app.post(
        "/api/v1/agent-actions/agents/request",
        headers=headers,
        json={"name": "conflicts", "template": "template", "task": "work"},
    )

    assert resp.status_code == 400, resp.text
    assert "/worktrees/conflicts" in resp.json()["detail"]
    assert "conflicts" not in await _roster(app, auth_headers)


@pytest.mark.asyncio
async def test_a_session_sync_refuses_a_new_agent_named_for_a_route(app, auth_headers):
    resp = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {"conflicts": {}, "worker": {}}}},
        headers=auth_headers,
    )

    assert resp.status_code == 400, resp.text
    assert "/worktrees/conflicts" in resp.json()["detail"]
    assert await _roster(app, auth_headers) == set()


@pytest.mark.asyncio
async def test_an_existing_agent_holding_a_route_word_still_syncs_and_resolves(app, auth_headers):
    """D1/D2: the word is refused at creation only. A row that already holds it is not stopped."""
    from hub import worktrees
    from hub.utils import short_id

    async with async_session_factory() as session:
        session.add(
            Agent(id=f"agent-{short_id()}", project_id="proj-test", name="settings", color_index=0)
        )
        await session.commit()

    resp = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {"settings": {}}}},
        headers=auth_headers,
    )

    assert resp.status_code in (200, 201), resp.text
    assert "settings" in await _roster(app, auth_headers)
    worktrees.validate_agent_name("settings")  # no use-site check refuses it


def test_user_and_operator_keep_their_own_reason():
    from hub import worktrees

    with pytest.raises(ValueError, match="reserved agent name 'operator'"):
        worktrees.validate_agent_name("operator")
    with pytest.raises(ValueError, match="reserved agent name 'user'"):
        worktrees.validate_agent_name("user")


# --- the task doors ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_operator_task_door_refuses_a_route_word_id(app, auth_headers):
    resp = await app.post(
        f"{BASE}/tasks", json={"title": "A board", "id": "board"}, headers=auth_headers
    )

    assert resp.status_code == 422, resp.text
    assert "id" in str(resp.json()["detail"])
    listed = await app.get(f"{BASE}/tasks", headers=auth_headers)
    assert "A board" not in str(listed.json())


@pytest.mark.asyncio
async def test_the_agent_task_door_refuses_a_route_word_id_with_422_not_500(app, auth_headers):
    headers = await _run_headers("lead", "run-route-words-task")

    resp = await app.post(
        "/api/v1/agent-actions/tasks", json={"title": "Boards", "id": "Boards"}, headers=headers
    )

    assert resp.status_code == 422, resp.text
    assert "id" in str(resp.json()["detail"])


@pytest.mark.asyncio
async def test_a_loops_initial_task_with_a_route_word_id_is_refused_and_nothing_is_created(
    app, auth_headers, add_agent
):
    await add_agent("kimi")

    resp = await app.post(
        f"{BASE}/jobs",
        json={
            "name": "Route Word Loop",
            "agent": "kimi",
            "message": "work the queue",
            "cron": "0 2 * * *",
            "purpose": "x",
            "stop_when_queue_empties": True,
            "initial_tasks": [{"title": "Boards", "id": "boards"}],
        },
        headers=auth_headers,
    )

    assert resp.status_code == 422, resp.text
    assert "id" in resp.json()["detail"]
    jobs = await app.get(f"{BASE}/jobs", headers=auth_headers)
    assert "Route Word Loop" not in str(jobs.json())


# --- the controls: near misses are ordinary ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_near_miss_agent_and_task_are_created_and_answer_on_their_own_routes(
    app, auth_headers, add_agent
):
    await add_agent("conflict")

    created = await app.post(
        f"{BASE}/tasks",
        json={"title": "A boardroom", "id": "boardroom", "assignee": "conflict"},
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    assert (await app.get(f"{BASE}/queue/conflict", headers=auth_headers)).status_code == 200
    got = await app.get(f"{BASE}/tasks/boardroom", headers=auth_headers)
    assert got.status_code == 200 and got.json()["id"] == "boardroom"
