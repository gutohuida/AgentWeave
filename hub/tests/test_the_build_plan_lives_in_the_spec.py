"""`the-build-plan-lives-in-the-spec-and-every-task-goes-to-its-people`, task `plan-in-spec`.

One builder and one checker per task, plus the defaults (`one-checker`); an older document's
reviewer and tester still check its work (`old-names-still-build`); the operator's choices at Build
are written into the spec document beside the recommendation (`choices-in-the-spec`), read by agents
apart from `delivery` and named in a turn on one of the build's tasks (`agents-read-the-build`); and
a build's end is shown, the document keeping only the running and the most recent ended build
(`build-end-shown`).

Named by acceptance criterion: `-k one_checker`, `-k old_reviewer`, `-k choices_written`,
`-k agent_reads`, `-k build_ended`, `-k two_builds`.
"""

import json

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Build, Run, SpecDocument, Task
from hub.scheduler import decide_firing
from hub.spec_payload import SCHEMA_VERSION
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_review_turn import _roster

P = "proj-test"
BASE = f"/api/v1/projects/{P}/project"
AGENT_DOCS = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/the-plan-in-the-spec/spec.json"

PEOPLE = ("Developer", "DeveloperOpus", "QA", "QA2", "Architect")


@pytest.fixture
async def author_headers():
    token = "aw_run_plan-author-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-plan-author",
                project_id=P,
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _review_turn_reads_the_test_workspace(monkeypatch):
    # `review_turn` holds its own import of the resolver the app fixture patches on its module.
    from hub import project_workspace, review_turn

    monkeypatch.setattr(
        review_turn, "resolve_project_workspace", project_workspace.resolve_project_workspace
    )


def _document(tasks, delivery):
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "The plan in the spec",
        "problem": "The operator's build is kept only on the build record.",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [{"key": "alpha", "statement": "It does alpha", "modal": "MUST"}],
        "acceptance_criteria": [
            {
                "key": "c-alpha",
                "requirement": "alpha",
                "given": "g",
                "when": "w",
                "then": "t",
                "how_to_check": "pytest",
                "checked_by": "agent",
            }
        ],
        "tasks": tasks,
        "delivery": delivery,
    }


def _task(key, **people):
    return {"key": key, "description": f"Build {key}", "requirements": ["alpha"], **people}


FLOW_WITH_DEVELOPER = {
    "mode": "flow",
    "agent": "Developer",
    "stop_when_queue_empties": True,
    "cron": "*/10 * * * *",
}


async def _people(*names):
    async with async_session_factory() as db:
        for name in names:
            db.add(Agent(id=f"agt-{name}", project_id=P, name=name, lifecycle="open"))
        await db.commit()


async def _save(app, auth_headers, author_headers, document):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "The plan"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    return await app.post(
        AGENT_DOCS, json={"path": PATH, "document": document}, headers=author_headers
    )


async def _approved(app, auth_headers, author_headers, document):
    saved = await _save(app, auth_headers, author_headers, document)
    assert saved.status_code == 200, saved.text
    version = (await _read(app, auth_headers))["content_version"]
    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": "", "approve_anyway": True, "content_version": version},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text


async def _read(app, auth_headers):
    read = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert read.status_code == 200, read.text
    return read.json()


async def _agent_read(app, author_headers):
    read = await app.get(
        AGENT_DOCS, params={"path": PATH, "include": "full"}, headers=author_headers
    )
    assert read.status_code == 200, read.text
    return read.json()


async def _build(app, auth_headers, **settings):
    built = await app.post(
        f"{BASE}/documents/build", params={"path": PATH}, json=settings, headers=auth_headers
    )
    assert built.status_code == 200, built.text
    return built.json()["build_outcome"]["build"]["id"]


async def _stop(app, auth_headers, build_id):
    stopped = await app.post(
        f"/api/v1/projects/{P}/project/builds/{build_id}/stop", headers=auth_headers
    )
    assert stopped.status_code == 200, stopped.text
    return stopped.json()


def _file(tmp_path):
    """The stored document as it is on disk: the payload plus the Hub's block."""
    return json.loads((tmp_path / PATH).read_text(encoding="utf-8"))


async def _tasks_by_key():
    async with async_session_factory() as db:
        document = (
            (await db.execute(select(SpecDocument).where(SpecDocument.path == PATH)))
            .scalars()
            .one()
        )
        rows = (
            (await db.execute(select(Task).where(Task.spec_document_id == document.id)))
            .scalars()
            .all()
        )
        return {row.spec_task_key: row for row in rows}


# ---------------------------------------------------------------------------------------------
# one-checker
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_checker_per_task_and_one_default_each_round_trip(
    app, auth_headers, author_headers, tmp_path
):
    """ac-one-checker: t1 names builder DeveloperOpus and checker QA, the default checker is QA2.
    Saved and read back, t1 carries exactly one builder and one checker, and the document one
    default builder and one default checker."""
    delivery = {**FLOW_WITH_DEVELOPER, "builder": "Developer", "checker": "QA2"}
    document = _document(
        [_task("t1", builder="DeveloperOpus", checker="QA"), _task("t2")], delivery
    )

    saved = await _save(app, auth_headers, author_headers, document)

    assert saved.status_code == 200, saved.text
    read = await _agent_read(app, author_headers)
    t1, t2 = read["tasks"]
    assert (t1["builder"], t1["checker"]) == ("DeveloperOpus", "QA")
    assert "reviewer" not in t1 or t1["reviewer"] is None
    assert "checker" not in t2 and "builder" not in t2
    assert (read["delivery"]["builder"], read["delivery"]["checker"]) == ("Developer", "QA2")
    on_file = _file(tmp_path)
    assert (on_file["tasks"][0]["builder"], on_file["tasks"][0]["checker"]) == (
        "DeveloperOpus",
        "QA",
    )
    assert (on_file["delivery"]["builder"], on_file["delivery"]["checker"]) == ("Developer", "QA2")
    # The Build dialog is offered exactly those people.
    recommended = (await _read(app, auth_headers))["recommended_build"]
    assert (recommended["builder"], recommended["checker"]) == ("Developer", "QA2")
    assert recommended["task_builders"] == {"t1": "DeveloperOpus", "t2": None}
    assert recommended["task_checkers"] == {"t1": "QA", "t2": None}


@pytest.mark.asyncio
async def test_one_checker_a_second_name_for_a_different_checker_is_refused(
    app, auth_headers, author_headers
):
    """A task, or the delivery, naming a checker beside a different reviewer names two checkers,
    and is refused naming the field; the same name twice is one checker and is kept."""
    two = _document([_task("t1", checker="QA", reviewer="Architect")], FLOW_WITH_DEVELOPER)
    refused = await _save(app, auth_headers, author_headers, two)
    assert refused.status_code == 422, refused.text
    assert "one checker" in refused.text

    default_two = _document(
        [_task("t1")], {**FLOW_WITH_DEVELOPER, "checker": "QA", "tester": "QA2"}
    )
    refused = await app.post(
        AGENT_DOCS, json={"path": PATH, "document": default_two}, headers=author_headers
    )
    assert refused.status_code == 422, refused.text
    assert "one default checker" in refused.text

    same = _document([_task("t1", checker="QA", reviewer="QA")], FLOW_WITH_DEVELOPER)
    kept = await app.post(AGENT_DOCS, json={"path": PATH, "document": same}, headers=author_headers)
    assert kept.status_code == 200, kept.text


# ---------------------------------------------------------------------------------------------
# old-names-still-build
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_old_reviewer_and_tester_names_still_check_the_work(
    app, auth_headers, author_headers, bind_runner, monkeypatch
):
    """ac-old-reviewer: a document in the old shape -- delivery reviewer QA and tester QA2, t2's own
    reviewer Architect -- built as a flow at Reviewed: t2's check goes to Architect and every other
    task's to QA2 (the tester wins over the reviewer), without the document being edited."""
    from hub import task_integration
    from hub.requirement_evidence import ReviewTarget

    async def _reviewable(session, task, root=None):
        return ReviewTarget(commit_sha="a" * 40, branch=f"agentweave/task/{task.id}")

    monkeypatch.setattr(task_integration, "review_target", _reviewable)
    await _roster(app, auth_headers, bind_runner, "Developer", "QA", "QA2", "Architect")
    old = {**FLOW_WITH_DEVELOPER, "reviewer": "QA", "tester": "QA2"}
    await _approved(
        app,
        auth_headers,
        author_headers,
        _document([_task("t1"), _task("t2", reviewer="Architect"), _task("t3")], old),
    )
    build_id = await _build(
        app, auth_headers, driver="flow", level="reviewed", builders=["Developer"]
    )

    async with async_session_factory() as db:
        build = await db.get(Build, build_id)
        assert build.people["checker"] == "QA2"
        assert build.people["tasks"]["t2"]["checker"] == "Architect"
        assert build.people["tasks"]["t1"]["checker"] is None

    by_key = await _tasks_by_key()
    checked_by = {}
    for key in ("t1", "t2", "t3"):
        task = by_key[key]
        for status in ("in_progress", "completed"):
            async with async_session_factory() as db:
                row = await db.get(Task, task.id)
                await apply_transition(db, row, status, run_actor(f"run-dev-{key}", "Developer"))
                await db.commit()
        async with async_session_factory() as db:
            build = await db.get(Build, build_id)
            from hub.db.models import Loop

            loop = await db.get(Loop, build.loop_id)
            decision = await decide_firing(db, loop, default_agent="Developer")
        reviews = [s for s in decision.selections if s.is_review and s.task.id == task.id]
        assert reviews, (key, decision)
        checked_by[key] = reviews[0].agent
        # Clear the way for the next task's check.
        async with async_session_factory() as db:
            row = await db.get(Task, task.id)
            row.status = "approved"
            await db.commit()

    assert checked_by == {"t1": "QA2", "t2": "Architect", "t3": "QA2"}


# ---------------------------------------------------------------------------------------------
# choices-in-the-spec, agents-read-the-build
# ---------------------------------------------------------------------------------------------


async def _hand_build_by_architect(app, auth_headers, author_headers):
    await _people(*PEOPLE)
    await _approved(
        app,
        auth_headers,
        author_headers,
        _document(
            [_task("t1", checker="QA"), _task("t2", builder="DeveloperOpus")], FLOW_WITH_DEVELOPER
        ),
    )
    version = (await _read(app, auth_headers))["content_version"]
    build_id = await _build(app, auth_headers, driver="hand", builder="Architect", landing="main")
    return build_id, version


@pytest.mark.asyncio
async def test_choices_written_into_the_document_beside_the_recommendation(
    app, auth_headers, author_headers, tmp_path
):
    """ac-choices-written: a document recommending a flow with Developer, built by hand with
    builder Architect and landing main. The document shows a build marked as the operator's with
    driver hand, builder Architect and landing main; its delivery still reads flow with Developer,
    and the version the operator approved does not move."""
    build_id, version = await _hand_build_by_architect(app, auth_headers, author_headers)

    on_file = _file(tmp_path)
    (entry,) = on_file["hub"]["builds"]
    assert entry["id"] == build_id
    assert entry["chosen_by"] == "operator"
    assert (entry["state"], entry["driver"], entry["builder"], entry["landing"]) == (
        "running",
        "hand",
        "Architect",
        "main",
    )
    assert entry["level"] == "reviewed" and entry["checker"] is None
    assert entry["tasks"] == {
        "t1": {"builder": None, "checker": "QA"},
        "t2": {"builder": "DeveloperOpus", "checker": None},
    }
    for choice in ("lead", "budget_cap_usd", "window_start", "window_end", "builders", "checkers"):
        assert choice in entry, choice
    assert (on_file["delivery"]["mode"], on_file["delivery"]["agent"]) == ("flow", "Developer")
    assert "builds" not in on_file["delivery"]

    page = await _read(app, auth_headers)
    assert page["content_version"] == version, "writing the build moved the approved version"
    assert page.get("diverged") is not True
    (row,) = page["builds"]
    assert (row["chosen_by"], row["driver"], row["builder"]) == ("operator", "hand", "Architect")


@pytest.mark.asyncio
async def test_agent_reads_the_build_apart_from_delivery_and_its_turn_names_it(
    app, auth_headers, author_headers
):
    """ac-agent-reads-build: an agent's read_spec_document returns the hand build with driver hand
    and the operator's people, apart from delivery; Architect's turn on t1 names driver hand and
    t1's builder (Architect, the build's default) and checker (QA)."""
    from hub.api.v1.agents import _render_hub_agent_context

    build_id, _ = await _hand_build_by_architect(app, auth_headers, author_headers)

    read = await _agent_read(app, author_headers)
    running = read["build"]["running"]
    assert running["id"] == build_id
    assert (running["chosen_by"], running["driver"], running["builder"]) == (
        "operator",
        "hand",
        "Architect",
    )
    assert running["tasks"]["t1"] == {"builder": None, "checker": "QA"}
    assert read["build"]["last_ended"] is None
    assert "operator" in read["build"]["note"] and "recommendation" in read["build"]["note"]
    assert (read["delivery"]["mode"], read["delivery"]["agent"]) == ("flow", "Developer")
    assert "driver" not in read["delivery"]

    t1 = (await _tasks_by_key())["t1"]
    async with async_session_factory() as db:
        architect = (
            (
                await db.execute(
                    select(Agent).where(Agent.project_id == P, Agent.name == "Architect")
                )
            )
            .scalars()
            .one()
        )
        rendered = await _render_hub_agent_context(
            agent="Architect",
            project_id=P,
            db=db,
            session_data=None,
            agent_row=architect,
            work_dir="/tmp/project",
            task_spec_document=PATH,
            task_id=t1.id,
        )
    context = rendered["context"]
    assert "### The build this task belongs to" in context
    assert f"Build `{build_id}`" in context and "driver **hand**" in context
    assert f"`{t1.id}`'s builder: **Architect**; its checker: **QA**" in context


# ---------------------------------------------------------------------------------------------
# build-end-shown
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_ended_is_shown_with_when_and_is_no_longer_running(
    app, auth_headers, author_headers, tmp_path
):
    """ac-build-ended: the operator stops a running build; the document shows it stopped, with the
    time, and read_spec_document reports no running build. A later rewrite of the Hub block (a
    phase move's) keeps it."""
    from hub import spec_service
    from hub.project_workspace import resolve_project_workspace

    await _people(*PEOPLE)
    await _approved(
        app, auth_headers, author_headers, _document([_task("t1")], FLOW_WITH_DEVELOPER)
    )
    build_id = await _build(app, auth_headers, driver="flow", level="reviewed")
    assert _file(tmp_path)["hub"]["builds"][0]["state"] == "running"

    stopped = await _stop(app, auth_headers, build_id)

    (entry,) = _file(tmp_path)["hub"]["builds"]
    assert (entry["id"], entry["state"]) == (build_id, "stopped")
    assert entry["ended_at"] and entry["ended_at"] == stopped["stopped_at"]
    assert entry["stop_reason"] == "stopped by the operator"
    read = await _agent_read(app, author_headers)
    assert read["build"]["running"] is None
    assert (read["build"]["last_ended"]["id"], read["build"]["last_ended"]["state"]) == (
        build_id,
        "stopped",
    )

    async with async_session_factory() as db:
        document = (
            (await db.execute(select(SpecDocument).where(SpecDocument.path == PATH)))
            .scalars()
            .one()
        )
        await spec_service.rerender_phase(db, await resolve_project_workspace(db, P), document)
        await db.commit()
    assert [e["id"] for e in _file(tmp_path)["hub"]["builds"]] == [build_id]


@pytest.mark.asyncio
async def test_two_builds_kept_the_running_and_the_last_ended(
    app, auth_headers, author_headers, tmp_path
):
    """ac-two-builds-kept: a first build stopped, a second started and stopped, a third started.
    The document shows the third running and the second stopped; the first is not in it, and its
    build record still exists."""
    await _people(*PEOPLE)
    await _approved(
        app, auth_headers, author_headers, _document([_task("t1")], FLOW_WITH_DEVELOPER)
    )
    first = await _build(app, auth_headers, driver="hand")
    await _stop(app, auth_headers, first)
    second = await _build(app, auth_headers, driver="hand")
    await _stop(app, auth_headers, second)
    third = await _build(app, auth_headers, driver="hand")

    shown = [(e["id"], e["state"]) for e in _file(tmp_path)["hub"]["builds"]]
    assert shown == [(third, "running"), (second, "stopped")]
    read = await _agent_read(app, author_headers)
    assert read["build"]["running"]["id"] == third
    assert read["build"]["last_ended"]["id"] == second
    async with async_session_factory() as db:
        ids = set((await db.execute(select(Build.id))).scalars().all())
    assert ids == {first, second, third}
