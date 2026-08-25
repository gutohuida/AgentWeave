"""Tests for task endpoints."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, Loop, Run, SpecDocument, Task


@pytest.mark.asyncio
async def test_create_and_list_task(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Build feature X", "assignee": "kimi", "priority": "high"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("task-")
    assert data["assignee"] == "kimi"
    assert data["status"] == "pending"

    resp2 = await app.get("/api/v1/projects/proj-test/tasks?agent=kimi", headers=auth_headers)
    assert resp2.status_code == 200
    tasks = resp2.json()
    assert any(t["id"] == data["id"] for t in tasks)


@pytest.mark.asyncio
async def test_update_task_status(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Update test task"},
        headers=auth_headers,
    )
    task_id = resp.json()["id"]

    resp2 = await app.patch(
        f"/api/v1/projects/proj-test/tasks/{task_id}",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_get_task_by_id(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Get test task", "description": "Full description"},
        headers=auth_headers,
    )
    task_id = resp.json()["id"]

    resp2 = await app.get(f"/api/v1/projects/proj-test/tasks/{task_id}", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["description"] == "Full description"


@pytest.mark.asyncio
async def test_task_responses_include_assignee_runtime_status(app, auth_headers):
    heartbeat = await app.post(
        "/api/v1/projects/proj-test/agents/kimi/heartbeat",
        json={"status": "running", "message": "Working on task"},
        headers=auth_headers,
    )
    assert heartbeat.status_code == 201

    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Runtime status task", "assignee": "kimi"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["assignee_status"] == "running"
    assert data["assignee_status_msg"] == "Working on task"
    assert data["assignee_last_seen"] is not None

    task_id = data["id"]
    resp2 = await app.get(f"/api/v1/projects/proj-test/tasks/{task_id}", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["assignee_status"] == "running"

    resp3 = await app.get("/api/v1/projects/proj-test/tasks?agent=kimi", headers=auth_headers)
    assert resp3.status_code == 200
    task = next(t for t in resp3.json() if t["id"] == task_id)
    assert task["assignee_status"] == "running"


@pytest.mark.asyncio
async def test_assigned_task_without_heartbeat_reports_idle(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "No heartbeat task", "assignee": "claude"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["assignee_status"] == "idle"
    assert resp.json()["assignee_status_msg"] is None
    assert resp.json()["assignee_last_seen"] is None


@pytest.mark.asyncio
async def test_agent_list_counts_task_assignees_without_session_sync(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Fallback agent task", "assignee": "codex-backend"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["assignee"] == "codex-backend"

    agents_resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert agents_resp.status_code == 200
    agents = agents_resp.json()
    codex = next((agent for agent in agents if agent["name"] == "codex-backend"), None)
    assert codex is not None
    assert codex["active_task_count"] == 1


@pytest.mark.asyncio
async def test_create_task_accepts_assigned_to_alias(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Alias assignment task", "assigned_to": "kimi"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["assignee"] == "kimi"


@pytest.mark.asyncio
async def test_create_task_honors_client_supplied_id(app, auth_headers):
    """When the client supplies a valid id, the Hub uses it and returns it
    in the response. This lets the MCP `create_task` tool return the same id
    the Hub stored, so subsequent get_task / update_task calls by id succeed.
    """
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Custom id", "id": "task-custom1234"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == "task-custom1234"

    # Subsequent get by that id must succeed.
    resp = await app.get("/api/v1/projects/proj-test/tasks/task-custom1234", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == "task-custom1234"


@pytest.mark.asyncio
async def test_create_task_generates_id_when_omitted(app, auth_headers):
    """When the client omits id, the Hub still generates one."""
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks", json={"title": "No id"}, headers=auth_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"].startswith("task-")
    assert len(body["id"]) == len("task-") + 12  # short_id() = 12 hex chars


@pytest.mark.asyncio
async def test_create_task_rejects_malformed_id(app, auth_headers):
    """An id with characters outside [A-Za-z0-9_-] or with leading digit
    is rejected — protects against path traversal and entity-type spoofing."""
    for bad in [
        "../etc/passwd",  # path traversal
        "task bad space",  # whitespace
        "1task-leading-digit",  # leading digit
        "",  # empty
    ]:
        resp = await app.post(
            "/api/v1/projects/proj-test/tasks",
            json={"title": "Bad id", "id": bad},
            headers=auth_headers,
        )
        assert resp.status_code == 422, f"expected 422 for id={bad!r}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_create_task_rejects_client_supplied_created_at(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Bad date", "created_at": "2026-01-01T00:00:00+00:00"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_task_rejects_overlong_title(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "x" * 257},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_task_rejects_overlong_description(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Big description", "description": "x" * 10001},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def _make_document(doc_id: str, phase: str) -> None:
    async with async_session_factory() as session:
        session.add(
            SpecDocument(id=doc_id, project_id="proj-test", path=f"spec/{doc_id}.md", phase=phase)
        )
        await session.commit()


async def _make_task(
    task_id: str, status: str, spec_document_id: str | None, loop_id: str | None = None
) -> None:
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title=task_id,
                status=status,
                spec_document_id=spec_document_id,
                loop_id=loop_id,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_spec_document_id_scopes_to_exactly_that_document_hiding_nothing(app, auth_headers):
    await _make_document("spdoc-scale-a", "archived")
    await _make_document("spdoc-scale-b", "approved")
    await _make_task("task-scale-1", "approved", "spdoc-scale-a")
    await _make_task("task-scale-2", "in_progress", "spdoc-scale-a")
    await _make_task("task-scale-3", "pending", "spdoc-scale-b")

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks?spec_document_id=spdoc-scale-a", headers=auth_headers
    )
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()}
    assert ids == {"task-scale-1", "task-scale-2"}


@pytest.mark.asyncio
async def test_exclude_archived_completed_hides_only_terminal_tasks_from_archived_documents(
    app, auth_headers
):
    await _make_document("spdoc-exc-archived", "archived")
    await _make_document("spdoc-exc-live", "approved")
    # Terminal + archived: excluded.
    await _make_task("task-exc-1", "approved", "spdoc-exc-archived")
    await _make_task("task-exc-2", "rejected", "spdoc-exc-archived")
    # Open work from an archived document: never excluded.
    await _make_task("task-exc-3", "in_progress", "spdoc-exc-archived")
    await _make_task("task-exc-4", "blocked", "spdoc-exc-archived")
    # Terminal, but the declaring document is not archived: not excluded.
    await _make_task("task-exc-5", "approved", "spdoc-exc-live")
    # No declaring document at all: never excluded, regardless of status.
    await _make_task("task-exc-6", "approved", None)

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks?exclude_archived_completed=true", headers=auth_headers
    )
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()}
    assert "task-exc-1" not in ids
    assert "task-exc-2" not in ids
    assert {"task-exc-3", "task-exc-4", "task-exc-5", "task-exc-6"} <= ids


@pytest.mark.asyncio
async def test_scoping_wins_over_the_exclusion_when_both_are_given(app, auth_headers):
    await _make_document("spdoc-both", "archived")
    await _make_task("task-both-1", "approved", "spdoc-both")

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks"
        "?spec_document_id=spdoc-both&exclude_archived_completed=true",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()}
    assert "task-both-1" in ids


@pytest.mark.asyncio
async def test_neither_parameter_returns_the_unfiltered_default(app, auth_headers):
    await _make_document("spdoc-default", "archived")
    await _make_task("task-default-1", "approved", "spdoc-default")

    resp = await app.get("/api/v1/projects/proj-test/tasks", headers=auth_headers)
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()}
    assert "task-default-1" in ids


@pytest.mark.asyncio
async def test_loop_id_scopes_to_exactly_that_loops_tasks_regardless_of_status(app, auth_headers):
    await _make_task("task-loop-1", "approved", None, loop_id="loop-scale-a")
    await _make_task("task-loop-2", "pending", None, loop_id="loop-scale-a")
    await _make_task("task-loop-3", "pending", None, loop_id="loop-scale-b")
    await _make_task("task-loop-4", "pending", None, loop_id=None)

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks?loop_id=loop-scale-a", headers=auth_headers
    )
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()}
    assert ids == {"task-loop-1", "task-loop-2"}

    # The agent-actions router's own list_tasks call site must still return 200 and must not
    # inherit loop scoping it was never asked for (the D7-regression shape this change's own
    # tasks.md names: a direct-call site silently defaulting a new parameter differently from
    # the router it wraps).
    token = "aw_run_task-loop-actor-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-task-loop-actor",
                project_id="proj-test",
                agent="loop-scoper",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    shared_resp = await app.get(
        "/api/v1/agent-actions/tasks", headers={"Authorization": f"Bearer {token}"}
    )
    assert shared_resp.status_code == 200
    shared_ids = {t["id"] for t in shared_resp.json()}
    assert "task-loop-3" in shared_ids


@pytest.mark.asyncio
async def test_creating_a_task_in_a_loop_reports_the_loop_it_joined(app, auth_headers):
    """`POST /tasks {"loop_id": …}` answered 201 with `loop_id: null` while the loop's own summary
    already counted the task in its queue (`scripts/drive/FINDINGS.md`, F16).

    The write worked; only the reply denied it, so there was no way to confirm from the create call
    that the task had joined the loop.
    """
    async with async_session_factory() as session:
        job = AIJob(
            id="job-echo",
            project_id="proj-test",
            name="Echo job",
            agent="builder",
            message="hello",
            cron="0 9 * * *",
            enabled=True,
        )
        session.add(job)
        await session.commit()
        session.add(
            Loop(id="loop-echo", project_id="proj-test", job_id=job.id, purpose="Echo the id back")
        )
        await session.commit()

    created = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Joins the loop", "loop_id": "loop-echo"},
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    assert created.json()["loop_id"] == "loop-echo"

    read_back = await app.get(
        f"/api/v1/projects/proj-test/tasks/{created.json()['id']}", headers=auth_headers
    )
    assert read_back.json()["loop_id"] == "loop-echo"


@pytest.mark.asyncio
async def test_a_task_in_no_loop_reports_none(app, auth_headers):
    """The field has to be able to say "no loop" as well, or it is not an answer."""
    created = await app.post(
        "/api/v1/projects/proj-test/tasks", json={"title": "Free-standing"}, headers=auth_headers
    )

    assert created.status_code == 201, created.text
    assert created.json()["loop_id"] is None


@pytest.mark.asyncio
async def test_task_loop_id_is_write_once_and_reassignment_leaves_the_task_unchanged(
    app, auth_headers
):
    """A5.1/A5.2 (design D14, `2026-08-18-a-loop-writes-its-own-queue`): `Task.loop_id` is set once,
    at creation, and never afterwards — a loop's queue history has to be able to answer what work it
    was ever given, which reassignment would break. Enforced in `update_task_for_actor`, not by a DB
    constraint SQLite could not later drop.
    """
    await _make_task("task-immutable-1", "pending", None, loop_id="loop-original")

    resp = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-immutable-1",
        json={"loop_id": "loop-hijacked"},
        headers=auth_headers,
    )
    assert resp.status_code == 403

    async with async_session_factory() as session:
        refreshed = await session.get(Task, "task-immutable-1")
        assert refreshed.loop_id == "loop-original"


@pytest.mark.asyncio
async def test_d15_an_archived_creators_run_no_longer_controls_its_loop(app):
    """Closes the D15 gap (design `2026-08-18-a-loop-writes-its-own-queue`'s A5.3), in the
    2026-08-19/20 autonomous run's P5.

    `_authorize_loop_task_creation` (tasks.py) checks who may add a task to a loop's queue by
    comparing `actor.agent` (a string) to `AIJob.agent` (also a string) — and `actor.agent` is
    itself just `Run.agent`, never looked up against the `agents` table
    (`agent_auth.py::get_agent_actor`). Before this fix, whoever the *name* belonged to now, not
    who currently held it as a live `Agent` row, controlled the loop.

    D15's own text is "a new agent taking an archived agent's name" via the roster — but that
    literal reproduction was already closed for the roster specifically before this fix: migration
    `0063_unique_agent_name_per_project` put an unconditional unique index on `(project_id, name)`
    that does **not** exempt archived rows (confirmed empirically: inserting a second `Agent` with
    an already-archived name's value raises `sqlite3.IntegrityError`), and nothing in this codebase
    lets an existing agent be renamed to free a name up either. So the roster cannot literally
    reproduce D15.

    What this test exercises instead is the same root cause one layer down, and does not need a
    duplicate `Agent` row at all: this `Run` is inserted directly (as `run-d15-successor`) rather
    than minted through `trigger_agent_directly` — that function now separately refuses to spawn
    a *new* run for an archived agent at all (its own guard, `hub/hub/api/v1/agent_trigger.py`),
    but this test's point is that the authorization check must not depend on runs only ever being
    minted through that one path. Whatever path put a `Run` on the books with `.agent` set to a
    name an `Agent` row currently holds archived, the check below now consults that row and
    refuses — the name match is necessary but no longer sufficient.

    This was recorded as "not a live vulnerability" — the Hub is local, single-operator, and the
    API key is the real boundary — but it was a real consequence of a name being load-bearing for
    permission. Operator decision: archiving strips the privilege outright, and names stay
    reusable (the roster still refuses literal reuse today, independently, via the unique index
    above; this fix does not depend on that remaining true).
    """
    async with async_session_factory() as session:
        original = Agent(id="agent-d15-original", project_id="proj-test", name="reused-loop-name")
        session.add(original)
        await session.commit()
        original.lifecycle = "archived"
        original.archived_at = datetime.now(timezone.utc)
        await session.commit()

        job = AIJob(
            id="job-d15",
            project_id="proj-test",
            name="D15 repro job",
            agent="reused-loop-name",
            message="hello",
            cron="0 9 * * *",
            enabled=True,
        )
        session.add(job)
        await session.commit()
        loop = Loop(id="loop-d15", project_id="proj-test", job_id=job.id, purpose="D15 repro")
        session.add(loop)
        await session.commit()

    token = "aw_run_task-d15-successor-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-d15-successor",
                project_id="proj-test",
                agent="reused-loop-name",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()

    resp = await app.post(
        "/api/v1/agent-actions/tasks",
        json={"title": "Claimed via the reused name", "loop_id": "loop-d15"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "creator" in resp.json()["detail"].lower()

    async with async_session_factory() as session:
        remaining = await session.execute(
            select(Task).where(Task.title == "Claimed via the reused name")
        )
        assert remaining.scalars().first() is None
