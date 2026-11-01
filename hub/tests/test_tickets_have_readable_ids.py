# ruff: noqa: F811 -- `author_headers` is a fixture imported to be requested by name
"""`tickets-have-readable-ids`: a task's `BPS-3` beside its stored `task-<hex>`."""

import asyncio
import importlib.util
import re
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy import select, update

from hub import readable_ids, worktrees
from hub.agent_auth import hash_run_token
from hub.api.v1 import agents as agents_module
from hub.config import settings
from hub.db.engine import async_session_factory
from hub.db.models import AcronymCounter, Base, Project, Run, SpecDocument, Task
from hub.main import app as application
from hub.runner_events import redact_text_secrets
from hub.scheduler import _briefing_completion_lines

from ._routing import iter_api_routes
from .test_a_build_has_a_driver_a_level_and_its_people import (
    AGENT_DOCS,
    BASE,
    PATH,
    TASKS,
    _approved,
    _document,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_migrations import ALEMBIC_INI, _run_alembic_with

P = "proj-test"
OTHER = "proj-other"


async def _set_project_acronym(project_id=P, acronym="AW"):
    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        project.acronym = acronym
        session.add(AcronymCounter(project_id=project_id, acronym=acronym, high_water=0))
        await session.commit()


async def _new_document(app, auth_headers, title, path=None):
    path = path or f"spec/changes/{re.sub(r'[^a-z]+', '-', title.lower())}/spec.json"
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": title}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    async with async_session_factory() as session:
        return (
            await session.execute(
                select(SpecDocument).where(SpecDocument.project_id == P, SpecDocument.path == path)
            )
        ).scalar_one()


async def _create(app, auth_headers, **body):
    response = await app.post(TASKS, json={"title": "A task", **body}, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _task_of_spec(document_id, *, task_id="task-aaaaaaaaaaaa", readable="BPS-1"):
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id=P,
                title="t",
                spec_document_id=document_id,
                readable_id=readable,
            )
        )
        await session.commit()


# --- derivation --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title, expected",
    [
        ("AgentWeave", "AW"),
        ("Build Plan Spec", "BPS"),
        ("The build plan in the spec", "BPS"),
        ("Tasks", "TAS"),
        ("Task", "TAS"),
        ("Secret Keys", "SEK"),
        ("Totally Awesome Secret Keys", "TOASK"),
        ("Feature Requests", "FER"),
        ("2026 budget plan", "BP"),
        ("", "SPE"),
        ("日本語", "SPE"),
    ],
)
def test_an_acronym_is_derived_from_the_title(title, expected):
    assert next(readable_ids.candidates(title, "SPEC")) == expected


@pytest.mark.parametrize("title", ["Secret Keys", "Tasks", "Sk", "Task", "s k", "t a s k", ""])
def test_no_candidate_breaks_the_shape_or_the_refusals(title):
    produced = readable_ids.candidates(title, "SPEC")
    for _ in range(1200):
        candidate = next(produced)
        assert readable_ids.ACRONYM_RE.match(candidate), candidate
        assert candidate not in {"TASK", "SK"}


def _migration():
    path = (
        Path(readable_ids.__file__).parent
        / "migrations"
        / "versions"
        / "0158_tickets_have_readable_ids.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0158", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "title", ["AgentWeave", "Build Plan Spec", "Secret Keys", "Tasks", "", "Feature Requests", "a"]
)
def test_the_migration_derives_as_the_hub_does(title):
    restated, current = _migration()._candidates(title, "SPEC"), readable_ids.candidates(
        title, "SPEC"
    )
    assert [next(restated) for _ in range(40)] == [next(current) for _ in range(40)]


# --- minting -----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_mint_a_specs_tasks_take_its_acronym_and_a_loose_task_the_projects(
    app, auth_headers, author_headers
):
    await _set_project_acronym()
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Build Plan Spec"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        AGENT_DOCS,
        json={"path": PATH, "document": _document(title="Build Plan Spec")},
        headers=author_headers,
    )
    assert saved.status_code == 200, saved.text
    read = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={
            "reason": "",
            "approve_anyway": True,
            "content_version": read.json()["content_version"],
        },
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(Task.spec_task_key, Task.readable_id).where(Task.project_id == P)
            )
        ).all()
    assert dict(rows) == {"t1": "BPS-1", "t2": "BPS-2"}
    loose = await _create(app, auth_headers)
    assert loose["readable_id"] == "AW-1"


@pytest.mark.asyncio
async def test_a_project_made_through_its_door_holds_an_acronym(app, auth_headers, tmp_path):
    # The suite's seeded project is unbound, and the first open binds it rather than making one.
    for name in ("Seeded", "AgentWeave"):
        root = tmp_path / name
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        opened = await app.post(
            "/api/v1/projects/open",
            json={"path": str(root), "name": name},
            headers=auth_headers,
        )
    assert opened.status_code in (200, 201), opened.text
    async with async_session_factory() as session:
        project = await session.get(Project, opened.json()["id"])
    assert project.acronym == "AW"


@pytest.mark.asyncio
async def test_ac_unique_simultaneous_creates_never_collide_and_a_deleted_number_stays_spent(
    app, auth_headers, author_headers
):
    """Against the suite's file database, with the Hub's real sessions, so the write lock is real.
    The tasks reach the spec the way a real create does: naming one of its requirements."""
    await _approved(app, auth_headers, author_headers, _document(title="Build Plan Spec"))

    async def create():
        return await _create(app, auth_headers, requirement_ids=["FR-1"])

    # The document declared BPS-1 and BPS-2.
    assert (await create())["readable_id"] == "BPS-3"
    deleted = await app.delete(f"{TASKS}/bps-3", headers=auth_headers)
    assert deleted.status_code == 204, deleted.text

    made = await asyncio.gather(*(create() for _ in range(20)))
    assert sorted(t["readable_id"] for t in made) == sorted(f"BPS-{n}" for n in range(4, 24))


@pytest.mark.asyncio
async def test_a_create_that_fails_uses_up_no_number(app, auth_headers):
    await _set_project_acronym()
    await _create(app, auth_headers)
    refused = await app.post(
        TASKS, json={"title": "x", "depends_on": ["task-nothere"]}, headers=auth_headers
    )
    assert refused.status_code == 422
    assert (await _create(app, auth_headers))["readable_id"] == "AW-2"


@pytest.mark.asyncio
async def test_ac_stable_rename_reassign_and_link_change_nothing(app, auth_headers, add_agent):
    await _set_project_acronym()
    document = await _new_document(app, auth_headers, "Build Plan Spec")
    task = await _create(app, auth_headers)
    assert task["readable_id"] == "AW-1"
    async with async_session_factory() as session:
        await session.execute(
            update(Task).where(Task.id == task["id"]).values(spec_document_id=document.id)
        )
        await session.commit()
    read = await app.get(f"{TASKS}/{task['id']}", headers=auth_headers)
    assert read.json()["readable_id"] == "AW-1"

    # The spec holds a task now, so a retitle leaves its acronym too.
    async with async_session_factory() as session:
        row = await session.get(SpecDocument, document.id)
        row.title = "Something Else Entirely"
        await readable_ids.follow_title(session, row)
        await session.commit()
        assert row.acronym == "BPS"
    renamed = await app.patch(
        f"{TASKS}/{task['id']}", json={"title": "Renamed"}, headers=auth_headers
    )
    assert renamed.json()["readable_id"] == "AW-1"


# --- acronyms ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_acronym_a_second_spec_with_the_same_initials_gets_its_own(app, auth_headers):
    first = await _new_document(app, auth_headers, "Build Plan Spec")
    second = await _new_document(app, auth_headers, "Big Purple Sofa")
    assert first.acronym == "BPS"
    assert second.acronym != "BPS"
    assert readable_ids.ACRONYM_RE.match(second.acronym)


@pytest.mark.asyncio
async def test_a_spec_cannot_take_the_projects_acronym(app, auth_headers):
    await _set_project_acronym(acronym="BPS")
    assert (await _new_document(app, auth_headers, "Build Plan Spec")).acronym != "BPS"


@pytest.mark.asyncio
async def test_ac_refused_neither_derived_nor_edited_and_the_redactor_leaves_ids_alone(
    app, auth_headers
):
    secret = await _new_document(app, auth_headers, "Secret Keys")
    tasks = await _new_document(app, auth_headers, "Tasks")
    assert secret.acronym not in {"SK", "TASK"} and tasks.acronym not in {"SK", "TASK"}
    for value in ("sk", "SK", "Task", "TASK"):
        edit = await app.post(
            f"{BASE}/documents/acronym",
            params={"path": secret.path},
            json={"acronym": value},
            headers=auth_headers,
        )
        assert edit.status_code == 422, edit.text
        assert value.upper() in edit.json()["detail"]
    for text in (
        f"look at {secret.acronym.lower()}-12 now",
        f"look at {tasks.acronym.lower()}-3 now",
        "ask-12 and bps-3 and aw-1",
    ):
        assert redact_text_secrets(text) == text


@pytest.mark.parametrize("value", ["B", "TOOLONG", "1BC", "B-C", ""])
@pytest.mark.asyncio
async def test_an_edit_obeys_the_shape(app, auth_headers, value):
    document = await _new_document(app, auth_headers, "Build Plan Spec")
    edit = await app.post(
        f"{BASE}/documents/acronym",
        params={"path": document.path},
        json={"acronym": value},
        headers=auth_headers,
    )
    assert edit.status_code == 422, edit.text


@pytest.mark.asyncio
async def test_ac_edit_takes_effect_until_the_first_task_and_is_refused_after(
    app, auth_headers, author_headers
):
    document = await _new_document(app, auth_headers, "Build Plan Spec", path=PATH)
    taken = await _new_document(app, auth_headers, "Quiet Rivers")
    url = f"{BASE}/documents/acronym"

    held = await app.post(
        url, params={"path": PATH}, json={"acronym": taken.acronym}, headers=auth_headers
    )
    assert held.status_code == 409 and "already held" in held.json()["detail"]

    edit = await app.post(url, params={"path": PATH}, json={"acronym": "zed"}, headers=auth_headers)
    assert edit.status_code == 200, edit.text
    assert edit.json()["acronym"] == "ZED"
    read = await app.get(f"{BASE}/documents", headers=auth_headers)
    assert "ZED" in read.text

    # The acronym it gave up is free again, for anybody.
    freed = await _new_document(app, auth_headers, "Big Plan Sofa")
    assert freed.acronym == document.acronym

    saved = await app.post(
        AGENT_DOCS,
        json={"path": PATH, "document": _document(title="Retitled By The Author")},
        headers=author_headers,
    )
    assert saved.status_code == 200, saved.text
    # The operator chose it, so a title change does not re-derive it.
    read = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={
            "reason": "",
            "approve_anyway": True,
            "content_version": read.json()["content_version"],
        },
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    async with async_session_factory() as session:
        minted = (
            (await session.execute(select(Task.readable_id).where(Task.project_id == P)))
            .scalars()
            .all()
        )
    assert sorted(minted) == ["ZED-1", "ZED-2"]

    refused = await app.post(
        url, params={"path": PATH}, json={"acronym": "NEW"}, headers=auth_headers
    )
    assert refused.status_code == 409
    assert "never changes" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_a_placeholder_title_gives_way_to_the_real_one(app, auth_headers):
    """A document is created under a placeholder name; what it is named by follows its real title
    until something is built on it."""
    document = await _new_document(app, auth_headers, "Amber Griffin")
    assert document.acronym == "AG"
    async with async_session_factory() as session:
        row = await session.get(SpecDocument, document.id)
        row.title = "Build Plan Spec"
        await readable_ids.follow_title(session, row)
        await session.commit()
        assert row.acronym == "BPS"
    # And AG went back: nothing else was ever named by it.
    assert (await _new_document(app, auth_headers, "Anything Goes")).acronym == "AG"


# --- every door takes it -----------------------------------------------------------------------


#: Every route with a task in its path, and what to send it. A route added without an entry here
#: fails `test_every_task_route_is_in_this_test`, and one taking a raw id fails the test below it.
_ROUTE_BODIES = {
    ("GET", "/tasks/{task_id}"): None,
    ("PATCH", "/tasks/{task_id}"): {"notes": "by readable id"},
    ("DELETE", "/tasks/{task_id}"): None,
    ("GET", "/tasks/{task_id}/integrations"): None,
    ("GET", "/tasks/{task_id}/integration-preview"): None,
    ("GET", "/tasks/{task_id}/checks"): None,
    ("POST", "/tasks/{task_id}/landing/land"): None,
    ("POST", "/tasks/{task_id}/checks/run"): None,
    ("POST", "/tasks/{task_id}/integrations/retry"): None,
    ("POST", "/tasks/{task_id}/reassign"): {"assignee": "nobody-here"},
    ("POST", "/tasks/{task_id}/land"): None,
    ("GET", "/tasks/{task_id}/story"): None,
    ("GET", "/tasks/{task_id}/moves"): None,
    ("GET", "/tasks/{task_id}/transitions"): None,
    ("POST", "/tasks/{task_id}/dependencies"): {"depends_on": "bps-1"},
    ("DELETE", "/tasks/{task_id}/dependencies/{depends_on}"): None,
    ("POST", "/agent-actions/tasks/{task_id}/hand-out"): {"agent": "dev", "review": False},
    ("GET", "/agent-actions/tasks/{task_id}"): None,
    ("PATCH", "/agent-actions/tasks/{task_id}"): {"notes": "by readable id"},
    ("GET", "/agent-actions/tasks/{task_id}/integrations"): None,
    ("GET", "/agent-actions/tasks/{task_id}/transitions"): None,
    ("POST", "/agent-actions/tasks/{task_id}/integrations/retry"): None,
    ("POST", "/agent-actions/mender/tasks/{task_id}/branch"): {},
    ("POST", "/agent-actions/mender/tasks/{task_id}/reset"): {"status": "pending"},
}


def _task_routes():
    prefix = "/api/v1"
    found = {}
    for path, route in iter_api_routes(application):
        if not path.startswith(prefix) or not re.search(r"/tasks/\{", path):
            continue
        short = re.sub(r"^/api/v1(/projects/\{project_id\})?", "", path)
        for method in route.methods - {"HEAD", "OPTIONS"}:
            found[(method, short)] = route
    return found


def test_every_task_route_is_in_this_test():
    assert set(_task_routes()) == set(_ROUTE_BODIES)


def test_no_task_route_takes_a_raw_id():
    """A route reads the stored id only through a door that resolved it: `task_id` being a path
    parameter of the route itself means it reached the handler as the caller typed it."""
    for key, route in _task_routes().items():
        raw = {param.name for param in route.dependant.path_params}
        assert not raw & {"task_id", "depends_on"}, f"{key} takes {raw} unresolved"


async def _second_project_with_the_same_id():
    async with async_session_factory() as session:
        session.add(Project(id=OTHER, name="Other", acronym="BPS"))
        session.add(AcronymCounter(project_id=OTHER, acronym="BPS", high_water=3))
        session.add(
            Task(id="task-0the0other", project_id=OTHER, title="other", readable_id="BPS-3")
        )
        session.add(
            Task(id="task-1the1other", project_id=OTHER, title="other", readable_id="BPS-1")
        )
        await session.commit()


async def _agent_headers(name):
    token = f"aw_run_{name}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=f"run-{name}",
                project_id=P,
                agent=name,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("key", sorted(_ROUTE_BODIES), ids=lambda key: f"{key[0]} {key[1]}")
@pytest.mark.asyncio
async def test_ac_accepted_each_route_acts_on_this_projects_task_never_the_others(
    app, auth_headers, key
):
    """Compared with the same call by stored id on a twin: a door that did not resolve answers 404
    for `bps-3` where the twin answers something else, and one that reached across projects would
    touch the other project's row, which is checked unchanged."""
    method, path = key
    await _set_project_acronym("proj-test", "BPS")
    await _create(app, auth_headers)  # BPS-1, the prerequisite
    await _create(app, auth_headers)  # BPS-2
    task = await _create(app, auth_headers)
    twin = await _create(app, auth_headers, title="Twin")
    assert task["readable_id"] == "BPS-3"
    await _second_project_with_the_same_id()

    if "/mender/" in path:
        return await _mender_case(app, auth_headers, path, task, twin)
    if path.startswith("/agent-actions"):
        headers = await _agent_headers("somebody")
        url = "/api/v1" + path
    else:
        headers = auth_headers
        url = f"/api/v1/projects/{P}" + path
    body = _ROUTE_BODIES[key]

    async def call(reference):
        return await app.request(
            method,
            url.replace("{task_id}", reference).replace("{depends_on}", "bps-1"),
            json=body,
            headers=headers,
        )

    with patch("hub.project_checks.run_checks_now", create=True):
        by_stored = await call(twin["id"])
        by_readable = await call("bps-3")

    if not (method == "DELETE" and "dependencies" in path):
        assert (by_readable.status_code == 404) == (by_stored.status_code == 404), (
            by_stored.text,
            by_readable.text,
        )
    if by_readable.status_code == 404:
        assert "bps-3" not in by_readable.text.lower() or "dependencies" in path
    named = re.findall(r"task-[0-9a-z]+", by_readable.text)
    assert "task-0the0other" not in named
    async with async_session_factory() as session:
        other = await session.get(Task, "task-0the0other")
    assert other is not None and other.notes is None


async def _mender_case(app, auth_headers, path, task, twin):
    """Both mender routes name the task they reached, in their refusal or their answer."""
    from hub import stalls
    from hub.db.models import Agent

    async with async_session_factory() as session:
        session.add(
            Agent(
                id="agent-mender",
                project_id=P,
                name=stalls.MENDER,
                config={"hub_role": stalls.HUB_ROLE},
            )
        )
        await session.commit()
    headers = await _agent_headers(stalls.MENDER)
    verb = path.rsplit("/", 1)[-1]
    answer = await app.post(
        f"/api/v1/agent-actions/mender/tasks/bps-3/{verb}",
        json=_ROUTE_BODIES[("POST", path)],
        headers=headers,
    )
    assert answer.status_code != 404, answer.text
    assert "task-0the0other" not in answer.text


@pytest.mark.asyncio
async def test_a_readable_id_from_another_project_is_not_found(app, auth_headers):
    await _second_project_with_the_same_id()
    answer = await app.get(f"{TASKS}/bps-3", headers=auth_headers)
    assert answer.status_code == 404


@pytest.mark.asyncio
async def test_the_other_doors_store_the_stored_id(
    app, auth_headers, author_headers, add_agent
):
    """What is not in a path: a prerequisite, a message's task, evidence's task, a trace filter."""
    await _set_project_acronym("proj-test", "BPS")
    first = await _create(app, auth_headers)
    assert first["readable_id"] == "BPS-1"

    dependent = await _create(app, auth_headers, depends_on=["bps-1"])
    assert [p["id"] for p in dependent["prerequisites"]] == [first["id"]]
    assert dependent["prerequisites"][0]["readable_id"] == "BPS-1"

    second = await _create(app, auth_headers)
    added = await app.post(
        f"{TASKS}/{second['id']}/dependencies", json={"depends_on": "bps-1"}, headers=auth_headers
    )
    assert added.status_code == 201 and added.json()["depends_on"] == first["id"]
    removed = await app.delete(f"{TASKS}/bps-3/dependencies/bps-1", headers=auth_headers)
    assert removed.status_code == 204, removed.text

    from hub.db.models import Message

    await add_agent("someone")
    sent = await app.post(
        "/api/v1/agent-actions/messages",
        json={"recipient": "someone", "subject": "s", "content": "c", "task_id": "bps-1"},
        headers=author_headers,
    )
    assert sent.status_code < 300, sent.text
    async with async_session_factory() as session:
        stored = (await session.execute(select(Message.task_id))).scalars().all()
    assert stored == [first["id"]]

    traced = await app.get(
        f"/api/v1/projects/{P}/traces", params={"task_id": "bps-1"}, headers=auth_headers
    )
    assert traced.status_code == 200


@pytest.mark.asyncio
async def test_evidence_recorded_by_readable_id_holds_the_stored_id(
    app, auth_headers, author_headers
):
    await _approved(app, auth_headers, author_headers, _document(title="Build Plan Spec"))
    async with async_session_factory() as session:
        task = (await session.execute(select(Task).where(Task.spec_task_key == "t1"))).scalar_one()
    recorded = await app.post(
        "/api/v1/agent-actions/spec/evidence",
        json={
            "identifier": "FR-1",
            "document": PATH,
            "task_id": task.readable_id.lower(),
            "summary": "by readable id",
        },
        headers=author_headers,
    )
    assert recorded.status_code in (200, 201), recorded.text
    from hub.db.models import RequirementEvidence

    async with async_session_factory() as session:
        row = await session.get(RequirementEvidence, recorded.json()["id"])
    assert row.task_id == task.id


# --- old ids, shapes ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_old_a_stored_id_resolves_and_the_branch_keeps_its_name(app, auth_headers):
    await _set_project_acronym()
    task = await _create(app, auth_headers)
    assert task["id"].startswith("task-")
    assert (await app.get(f"{TASKS}/{task['id']}", headers=auth_headers)).json()["id"] == task["id"]
    assert worktrees.task_branch_name(task["id"]) == f"agentweave/task/{task['id']}"
    assert task["readable_id"] not in worktrees.task_branch_name(task["id"])


@pytest.mark.asyncio
async def test_a_stored_id_shaped_like_a_readable_one_keeps_its_meaning(app, auth_headers):
    """A caller could store `BPS-3` before this; it goes on meaning that task."""
    async with async_session_factory() as session:
        session.add(Task(id="BPS-3", project_id=P, title="old", readable_id="AW-1"))
        session.add(Task(id="task-abcabcabcabc", project_id=P, title="new", readable_id="BPS-3"))
        await session.commit()
    assert (await app.get(f"{TASKS}/BPS-3", headers=auth_headers)).json()["title"] == "old"
    assert (await app.get(f"{TASKS}/aw-1", headers=auth_headers)).json()["title"] == "old"


@pytest.mark.parametrize("value", ["BPS-3", "bps-3", "A1-9", "ABCDE-12"])
@pytest.mark.asyncio
async def test_ac_shape_a_caller_id_shaped_like_a_readable_one_is_refused(app, auth_headers, value):
    refused = await app.post(TASKS, json={"title": "x", "id": value}, headers=auth_headers)
    assert refused.status_code == 422, refused.text
    assert (
        "id" in refused.json()["detail"][0]["loc"]
        if isinstance(refused.json()["detail"], list)
        else "id" in refused.text
    )


@pytest.mark.parametrize("value", ["task-1", "task-abc123", "my_task", "ABCDEF-1"])
@pytest.mark.asyncio
async def test_other_caller_ids_are_still_taken(app, auth_headers, value):
    made = await app.post(TASKS, json={"title": "x", "id": value}, headers=auth_headers)
    assert made.status_code == 201, made.text
    assert made.json()["id"] == value and made.json()["readable_id"]


# --- what is shown -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_shown_a_turn_names_its_task_by_the_readable_id(app, auth_headers, tmp_path):
    await _set_project_acronym("proj-test", "BPS")
    await _create(app, auth_headers)
    await _create(app, auth_headers)
    made = await _create(app, auth_headers)
    async with async_session_factory() as session:
        task = await session.get(Task, made["id"])
        lines = "\n".join(_briefing_completion_lines(task, is_flow=True))
        assert 'update_task("BPS-3"' in lines
        assert task.id not in lines
        context = await agents_module._render_hub_agent_context(
            agent="dev",
            project_id=P,
            db=session,
            session_data=None,
            agent_row=None,
            task_spec_document="spec/changes/x/spec.json",
            task_id=task.id,
            task_readable_id=task.readable_id,
        )
    rendered = str(context)
    assert "`BPS-3`" in rendered and task.id in rendered


@pytest.mark.asyncio
async def test_the_board_payload_carries_both_ids(app, auth_headers):
    await _set_project_acronym()
    made = await _create(app, auth_headers)
    board = await app.get(TASKS, headers=auth_headers)
    row = next(t for t in board.json()["tasks"] if t["id"] == made["id"])
    assert row["readable_id"] == "AW-1"


# --- commits -----------------------------------------------------------------------------------


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.mark.asyncio
async def test_ac_commit_a_snapshot_names_both_ids(app, auth_headers, tmp_path):
    await _set_project_acronym("proj-test", "BPS")
    made = await _create(app, auth_headers)
    task_id = made["id"]
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "README").write_text("x", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "seed")
    checkout = repo / ".agentweave" / "tasks" / task_id
    _git(repo, "worktree", "add", "-q", "-b", f"agentweave/task/{task_id}", str(checkout))
    (checkout / "work.txt").write_text("work", encoding="utf-8")

    message = await readable_ids.snapshot_message(checkout, "dev")
    assert worktrees.snapshot_worktree(checkout, "dev", message=message)

    subject = _git(checkout, "log", "-1", "--format=%s")
    assert "BPS-1" in subject and task_id in subject
    assert _git(checkout, "rev-parse", "--abbrev-ref", "HEAD").strip() == (
        f"agentweave/task/{task_id}"
    )


def test_a_task_checkout_release_names_both_ids(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "README").write_text("x", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "seed")
    task_id = "task-abcdef123456"
    checkout = worktrees.task_worktree_path(repo, task_id)
    _git(repo, "worktree", "add", "-q", "-b", f"agentweave/task/{task_id}", str(checkout))
    (checkout / "work.txt").write_text("work", encoding="utf-8")
    name = readable_ids.commit_name(task_id, "BPS-3")
    worktrees.release_task_worktree(repo, task_id, name=name)
    subject = _git(repo, "log", "-1", "--format=%s", f"agentweave/task/{task_id}")
    assert "BPS-3" in subject and task_id in subject


def test_a_prerequisite_merge_names_both_ids(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "README").write_text("x", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "seed")
    _git(repo, "checkout", "-qb", "prereq")
    (repo / "p.txt").write_text("p", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "prereq work")
    sha = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "main")
    worktrees._merge_prerequisites(
        repo,
        "task-abcdef123456",
        (("task-000000000001", sha),),
        {"task-000000000001": "BPS-1 (task-000000000001)"},
    )
    subject = _git(repo, "log", "-1", "--format=%s")
    assert "BPS-1" in subject and "task-000000000001" in subject


# --- the migration -----------------------------------------------------------------------------


def _dump(path):
    """Every table's schema and rows, to tell a database from the one it was."""
    connection = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%' "
                "and name != 'alembic_version' order by name"
            )
        ]
        return {
            table: (
                [tuple(c) for c in connection.execute(f'pragma table_info("{table}")')],
                sorted(
                    (repr(row) for row in connection.execute(f'select * from "{table}"')),
                ),
            )
            for table in tables
        }
    finally:
        connection.close()


def test_ac_migrated_up_and_down_on_fixture_data(tmp_path):
    from alembic import command
    from alembic.config import Config

    db = tmp_path / "copy.db"
    url = f"sqlite+aiosqlite:///{db.as_posix()}"
    # An empty database's chain builds no base tables, so the schema comes from the models as a real
    # one's does (`init_db`), and is walked back to the revision before this one.
    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", url)
    with patch.object(settings, "database_url", url):
        command.stamp(cfg, "0158")
        command.downgrade(cfg, "0157")

    connection = sqlite3.connect(db)
    connection.executescript("""
        insert into projects (id, name, created_at) values
            ('p1', 'AgentWeave', '2026-01-01'), ('p2', 'AgentWeave', '2026-01-02');
        insert into spec_documents (id, project_id, path, title, kind, phase, created_at, updated_at)
            values
            ('d1', 'p1', 'a', 'Build Plan Spec', 'change-spec', 'approved', '2026-01-01', '2026-01-01'),
            ('d2', 'p1', 'b', 'Big Purple Sofa', 'change-spec', 'approved', '2026-01-02', '2026-01-02'),
            ('d3', 'p2', 'c', 'Build Plan Spec', 'change-spec', 'exploring', '2026-01-02', '2026-01-02');
        """)
    columns = {row[1]: row for row in connection.execute("pragma table_info(tasks)")}
    required = [
        name
        for name, row in columns.items()
        if row[3] and row[4] is None and name not in ("id", "project_id", "title", "created_at")
    ]
    fill = {
        "description": "''",
        "status": "'pending'",
        "priority": "'medium'",
        "updated": "'2026-01-01'",
    }
    names = ["id", "project_id", "title", "created_at", "spec_document_id", *required]
    rows = [
        # Inserted out of order: the number follows created_at, not rowid.
        ("t3", "p1", "2026-01-03", "d1"),
        ("t1", "p1", "2026-01-01", "d1"),
        ("t2", "p1", "2026-01-02", None),
        ("t4", "p1", "2026-01-04", "gone"),
        ("t5", "p1", "2026-01-05", "d2"),
        ("t6", "p2", "2026-01-01", "d3"),
        ("t7", "p2", "2026-01-01", "d1"),  # a spec of another project is no spec of this one's
    ]
    for task_id, project, created, document in rows:
        values = [f"'{task_id}'", f"'{project}'", "'x'", f"'{created}'"]
        values.append(f"'{document}'" if document else "NULL")
        values += [fill.get(name, "''") for name in required]
        connection.execute(f"insert into tasks ({', '.join(names)}) values ({', '.join(values)})")
    connection.commit()
    connection.close()
    before = _dump(db)

    _run_alembic_with(url, "0158")

    connection = sqlite3.connect(db)
    readable = dict(connection.execute("select id, readable_id from tasks"))
    assert readable == {
        "t1": "BPS-1",
        "t3": "BPS-2",
        "t2": "AW-1",
        "t4": "AW-2",
        "t5": readable["t5"],
        "t6": "BPS-1",
        "t7": "AW-1",
    }
    assert readable["t5"].endswith("-1") and not readable["t5"].startswith("BPS")
    counters = {
        (p, a): h
        for p, a, h in connection.execute(
            "select project_id, acronym, high_water from acronym_counters"
        )
    }
    assert counters[("p1", "BPS")] == 2 and counters[("p1", "AW")] == 2
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("update tasks set readable_id = 'BPS-1' where id = 't2'")
    connection.close()

    # Nothing the migration did not add has changed.
    after = _dump(db)
    for table, (_, table_rows) in before.items():
        if table not in {"tasks", "projects", "spec_documents"}:
            assert after[table][1] == table_rows, table

    with patch.object(settings, "database_url", url):
        command.downgrade(cfg, "0157")
    assert _dump(db) == before
