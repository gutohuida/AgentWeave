"""`exploring-ends-at-an-approved-plan`: check, approve and build are separate.

The acceptance drive of slice C of the roadmap "Flows that do not stall". Every test drives the real
routes. On master 1f02d86 each fails for the reason the slice exists: there is no Check route,
approval goes through `proposed` and checks no version, approval creates and starts the delivery's
flow, there is no Build and no "Approve and build", and nothing records or offers "already built".

Named by acceptance criterion: `-k check`, `-k proposed`, `-k approve_direct`, `-k stale`,
`-k starts_nothing`, `-k build_later`, `-k one_action`, `-k intake_already_built`.
"""

import sqlite3
from datetime import timedelta

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, Loop, Run, SpecDocument, SpecDocumentEvent, Task
from hub.scheduler import decide_firing
from hub.spec_payload import SCHEMA_VERSION

from .test_review_turn import _roster

P = "proj-test"
BASE = f"/api/v1/projects/{P}/project"
AGENT_DOCS = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/an-approved-plan/spec.json"

FLOW = {
    "mode": "flow",
    "agent": "dev",
    "reviewer": "qa",
    "stop_when_queue_empties": True,
    "cron": "*/10 * * * *",
}


@pytest.fixture
async def author_headers():
    """The agent run that writes the document."""
    token = "aw_run_plan-author-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-plan-author",
                project_id=P,
                agent="Architect",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _document(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "An approved plan",
        "problem": "Approval mixes three decisions.",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [{"key": "alpha", "statement": "It does alpha", "modal": "MUST"}],
        "acceptance_criteria": [
            {
                "key": "c1",
                "requirement": "alpha",
                "given": "g",
                "when": "w",
                "then": "t",
                "how_to_check": "pytest",
                "checked_by": "agent",
            }
        ],
        "tasks": [{"key": "t1", "description": "Build alpha", "requirements": ["alpha"]}],
        "delivery": {"mode": "none"},
    }
    payload.update(overrides)
    return payload


async def _create(app, auth_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "An approved plan"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text


async def _save(app, author_headers, document):
    saved = await app.post(
        AGENT_DOCS, json={"path": PATH, "document": document}, headers=author_headers
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


async def _written(app, auth_headers, author_headers, document):
    await _create(app, auth_headers)
    return await _save(app, author_headers, document)


async def _loaded(app, auth_headers):
    """What the operator's page loads: the document read, carrying the version it shows."""
    read = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert read.status_code == 200, read.text
    return read.json()


async def _approve(app, auth_headers, version, **body):
    return await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": "", "approve_anyway": True, "content_version": version, **body},
        headers=auth_headers,
    )


async def _rows(model, *where):
    async with async_session_factory() as db:
        return (await db.execute(select(model).where(*where))).scalars().all()


async def _document_row():
    (row,) = await _rows(SpecDocument, SpecDocument.path == PATH)
    return row


async def _phase_events():
    row = await _document_row()
    async with async_session_factory() as db:
        events = (
            (
                await db.execute(
                    select(SpecDocumentEvent)
                    .where(SpecDocumentEvent.document_id == row.id)
                    .order_by(SpecDocumentEvent.created_at)
                )
            )
            .scalars()
            .all()
        )
    return events


async def _agent(name):
    async with async_session_factory() as db:
        db.add(Agent(id=f"agt-{name}", project_id=P, name=name, lifecycle="open"))
        await db.commit()


# ---------------------------------------------------------------------------------------------
# check-while-editing (check-never-moves)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_reports_the_save_and_moves_nothing(app, auth_headers, author_headers):
    """Check shows what the agent's save returned, the phase stays exploring, and the agent saves
    again afterwards. On master there is no Check route (404): Propose was the only way to see
    readiness, and it moved the document."""
    one_gap = _document(
        tasks=[
            {
                "key": "t1",
                "description": "Build alpha",
                "requirements": ["alpha"],
                "depends_on": ["nowhere"],
            }
        ]
    )
    saved = await _written(app, auth_headers, author_headers, one_gap)
    assert [b["code"] for b in saved["blocking"]] == ["depends_on_unresolved"]

    checked = await app.get(f"{BASE}/documents/check", params={"path": PATH}, headers=auth_headers)

    assert checked.status_code == 200, checked.text
    body = checked.json()
    assert body["blocking"] == saved["blocking"]
    assert body["warnings"] == saved["warnings"]
    assert body["phase"] == "exploring"
    assert (await _document_row()).phase == "exploring"
    again = await _save(app, author_headers, _document())
    assert again["blocking"] == []
    assert (await _document_row()).phase == "exploring"


# ---------------------------------------------------------------------------------------------
# proposed-migrated (no-proposed-phase)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asking_for_proposed_is_refused(app, auth_headers, author_headers):
    """The old propose route and a phase move to proposed are both refused, and the document stays
    in exploring. On master the propose route moves it."""
    await _written(app, auth_headers, author_headers, _document())

    proposed = await app.post(
        f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers
    )
    moved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "proposed"},
        json={"reason": ""},
        headers=auth_headers,
    )

    assert proposed.status_code == 410, proposed.text
    assert proposed.json()["detail"]["code"] == "proposed_retired"
    assert moved.status_code == 409, moved.text
    assert moved.json()["detail"]["code"] == "proposed_retired"
    assert (await _document_row()).phase == "exploring"


def test_the_migration_moves_proposed_documents_back_to_exploring(tmp_path):
    """A database holding a proposed document: after the upgrade it is in exploring with an event
    naming the retirement, and the database refuses `proposed`. The downgrade lets it back in."""
    from .test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

    db_file = tmp_path / "proposed.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0148')")
        conn.commit()
    _downgrade_to(db_url, "0147")
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES ('p', 'p', '2026-01-01T00:00:00Z')"
        )
        for doc_id, phase in (("spdoc-a", "proposed"), ("spdoc-b", "approved")):
            conn.execute(
                "INSERT INTO spec_documents (id, project_id, path, title, kind, phase, rigor, "
                "explore_closed_at, created_at, updated_at) VALUES (?, 'p', ?, 't', "
                "'change-spec', ?, 'sketch', '2026-10-20T00:00:00Z', '2026-10-20T00:00:00Z', "
                "'2026-10-20T00:00:00Z')",
                (doc_id, f"spec/changes/{doc_id}/spec.json", phase),
            )
        conn.commit()

    _upgrade_to(db_url, "head")

    with sqlite3.connect(db_file) as conn:
        phases = dict(conn.execute("SELECT id, phase FROM spec_documents").fetchall())
        assert phases == {"spdoc-a": "exploring", "spdoc-b": "approved"}
        closed = conn.execute(
            "SELECT explore_closed_at FROM spec_documents WHERE id = 'spdoc-a'"
        ).fetchone()
        assert closed == (None,)
        events = conn.execute(
            "SELECT document_id, kind, actor_kind, detail FROM spec_document_events"
        ).fetchall()
        assert len(events) == 1
        document_id, kind, actor_kind, detail = events[0]
        assert (document_id, kind, actor_kind) == ("spdoc-a", "phase", "system")
        assert '"from": "proposed"' in detail and '"to": "exploring"' in detail
        assert "retired" in detail
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE spec_documents SET phase = 'proposed' WHERE id = 'spdoc-b'")

    _downgrade_to(db_url, "0147")
    with sqlite3.connect(db_file) as conn:
        conn.execute("UPDATE spec_documents SET phase = 'proposed' WHERE id = 'spdoc-a'")
        conn.commit()
        assert conn.execute("SELECT phase FROM spec_documents WHERE id = 'spdoc-a'").fetchone() == (
            "proposed",
        )


# ---------------------------------------------------------------------------------------------
# approve-direct (approve-from-exploring)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_direct_from_exploring(app, auth_headers, author_headers):
    """On master exploring -> approved is an illegal transition (409)."""
    await _written(app, auth_headers, author_headers, _document())
    loaded = await _loaded(app, auth_headers)

    approved = await _approve(app, auth_headers, loaded["content_version"])

    assert approved.status_code == 200, approved.text
    assert approved.json()["phase"] == "approved"
    moves = [
        (e.detail["from"], e.detail["to"])
        for e in await _phase_events()
        if e.kind == "phase" and "to" in (e.detail or {})
    ]
    assert moves == [("exploring", "approved")]


# ---------------------------------------------------------------------------------------------
# stale-approve-refused (approve-what-was-seen)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_stale_approval_is_refused_and_a_reloaded_one_accepted(
    app, auth_headers, author_headers
):
    """The operator loads the document, the agent then changes it, and the approval naming what
    was loaded is refused; reloading and approving succeeds. On master no version is read."""
    await _written(app, auth_headers, author_headers, _document())
    seen = (await _loaded(app, auth_headers))["content_version"]
    await _save(app, author_headers, _document(summary="Changed while the operator read it."))

    stale = await _approve(app, auth_headers, seen)

    assert stale.status_code == 409, stale.text
    detail = stale.json()["detail"]
    assert detail["code"] == "document_changed"
    assert "changed since it was loaded" in detail["message"]
    assert (await _document_row()).phase == "exploring"
    assert await _rows(Task) == []

    reloaded = (await _loaded(app, auth_headers))["content_version"]
    assert reloaded != seen
    approved = await _approve(app, auth_headers, reloaded)
    assert approved.status_code == 200, approved.text
    assert approved.json()["phase"] == "approved"


@pytest.mark.asyncio
async def test_a_stale_approval_names_no_version_is_refused(app, auth_headers, author_headers):
    """An approval that names no version is refused rather than accepted unseen."""
    await _written(app, auth_headers, author_headers, _document())

    response = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": "", "approve_anyway": True},
        headers=auth_headers,
    )

    assert response.status_code == 400, response.text
    assert "content_version" in response.text
    assert (await _document_row()).phase == "exploring"


# ---------------------------------------------------------------------------------------------
# approve-starts-nothing (approval-is-a-plan)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_starts_nothing(app, auth_headers, author_headers):
    """A flow delivery, approved: the tasks are on the board and nothing runs. On master approval
    creates the delivery's flow."""
    await _agent("dev")
    await _agent("qa")
    await _written(app, auth_headers, author_headers, _document(delivery=FLOW))
    runs_before = len(await _rows(Run))

    approved = await _approve(app, auth_headers, (await _loaded(app, auth_headers))["content_version"])

    assert approved.status_code == 200, approved.text
    row = await _document_row()
    assert [t.spec_task_key for t in await _rows(Task, Task.spec_document_id == row.id)] == ["t1"]
    assert await _rows(Loop, Loop.spec_document_id == row.id) == []
    assert await _rows(AIJob) == []
    assert len(await _rows(Run)) == runs_before
    assert "flow" not in approved.json()["approval_outcome"]


# ---------------------------------------------------------------------------------------------
# build-later (build-is-separate)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_later_starts_the_delivery_flow(app, auth_headers, author_headers, bind_runner):
    """Approved, and an hour later the operator presses Build: the delivery's flow exists with its
    agent, reviewer and cron, and fires; approval and build are two events."""
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _written(app, auth_headers, author_headers, _document(delivery=FLOW))
    approved = await _approve(app, auth_headers, (await _loaded(app, auth_headers))["content_version"])
    assert approved.status_code == 200, approved.text
    # An hour passes: the approval is moved back an hour rather than the clock forward.
    async with async_session_factory() as db:
        for event in (await db.execute(select(SpecDocumentEvent))).scalars().all():
            event.created_at = event.created_at - timedelta(hours=1)
        await db.commit()
    assert await _rows(AIJob) == []

    built = await app.post(
        f"{BASE}/documents/build", params={"path": PATH}, json={}, headers=auth_headers
    )

    assert built.status_code == 200, built.text
    outcome = built.json()["build_outcome"]
    (job,) = await _rows(AIJob)
    (loop,) = await _rows(Loop)
    row = await _document_row()
    assert (job.agent, job.cron, loop.spec_document_id) == ("dev", "*/10 * * * *", row.id)
    assert (outcome["flow"]["state"], outcome["flow"]["agent"]) == ("created", "dev")
    assert outcome["reviewer"] == "qa"
    async with async_session_factory() as db:
        fresh = (await db.execute(select(Loop).where(Loop.id == loop.id))).scalar_one()
        decision = await decide_firing(db, fresh, default_agent=job.agent)
    (task,) = await _rows(Task, Task.spec_document_id == row.id)
    assert [(s.task.id, s.agent) for s in decision.selections] == [(task.id, "dev")]
    events = await _phase_events()
    approval = [e for e in events if e.kind == "phase" and (e.detail or {}).get("to") == "approved"]
    builds = [e for e in events if e.kind == "build"]
    assert len(approval) == 1 and len(builds) == 1
    assert builds[0].created_at - approval[0].created_at >= timedelta(minutes=59)
    read = await _loaded(app, auth_headers)
    assert read["build_outcome"]["flow"]["job_id"] == job.id


@pytest.mark.asyncio
async def test_build_is_refused_before_approval(app, auth_headers, author_headers):
    await _written(app, auth_headers, author_headers, _document(delivery=FLOW))

    built = await app.post(
        f"{BASE}/documents/build", params={"path": PATH}, json={}, headers=auth_headers
    )

    assert built.status_code == 409, built.text
    assert built.json()["detail"]["code"] == "not_approved"
    assert await _rows(AIJob) == []


@pytest.mark.asyncio
async def test_build_of_a_none_delivery_leaves_the_tasks_on_the_board(
    app, auth_headers, author_headers
):
    await _written(app, auth_headers, author_headers, _document())
    await _approve(app, auth_headers, (await _loaded(app, auth_headers))["content_version"])

    built = await app.post(
        f"{BASE}/documents/build", params={"path": PATH}, json={}, headers=auth_headers
    )

    assert built.status_code == 200, built.text
    assert built.json()["build_outcome"]["flow"]["state"] == "none"
    assert await _rows(AIJob) == []
    (task,) = await _rows(Task)
    assert task.status == "pending"


# ---------------------------------------------------------------------------------------------
# one-action (approve-and-build)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_action_approves_and_builds(app, auth_headers, author_headers):
    await _agent("dev")
    await _agent("qa")
    await _written(app, auth_headers, author_headers, _document(delivery=FLOW))
    version = (await _loaded(app, auth_headers))["content_version"]

    response = await app.post(
        f"{BASE}/documents/approve-and-build",
        params={"path": PATH},
        json={"reason": "", "approve_anyway": True, "content_version": version},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "approved"
    assert body["build_outcome"]["flow"]["state"] == "created"
    (job,) = await _rows(AIJob)
    assert job.agent == "dev"
    kinds = [e.kind for e in await _phase_events()]
    assert "build" in kinds and kinds.index("build") > kinds.index("approval_report")


@pytest.mark.asyncio
async def test_one_action_with_a_changed_document_is_refused_like_approving(
    app, auth_headers, author_headers
):
    await _agent("dev")
    await _written(app, auth_headers, author_headers, _document(delivery=FLOW))
    seen = (await _loaded(app, auth_headers))["content_version"]
    await _save(app, author_headers, _document(delivery=FLOW, summary="Changed meanwhile."))

    response = await app.post(
        f"{BASE}/documents/approve-and-build",
        params={"path": PATH},
        json={"reason": "", "approve_anyway": True, "content_version": seen},
        headers=auth_headers,
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "document_changed"
    assert "changed since it was loaded" in response.json()["detail"]["message"]
    assert (await _document_row()).phase == "exploring"
    assert await _rows(Task) == [] and await _rows(AIJob) == [] and await _rows(Loop) == []


# ---------------------------------------------------------------------------------------------
# intake-already-built (already-built-at-intake)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_intake_already_built_offers_close_as_built(
    app, auth_headers, author_headers, tmp_path
):
    """Intake recorded the work as already built at a commit on main; approval offers slice B's
    close-as-built naming that commit, and taking it leaves no task pending."""
    from .test_task_integration import commit_on_branch, git, make_repo, set_main_branch

    make_repo(tmp_path)
    work = commit_on_branch(tmp_path, "feature", "built.py", "x = 1\n")
    git(tmp_path, "checkout", "-q", "main")
    git(tmp_path, "merge", "-q", "--ff-only", "feature")
    await set_main_branch("main")
    await _written(
        app,
        auth_headers,
        author_headers,
        _document(already_built={"built": True, "commits": [work[:12]]}),
    )

    approved = await _approve(app, auth_headers, (await _loaded(app, auth_headers))["content_version"])

    assert approved.status_code == 200, approved.text
    offer = approved.json()["approval_outcome"]["already_built"]
    assert offer["commits"] == [work[:12]]
    assert offer["route"].endswith(f"/documents/{PATH}/close-already-built")
    assert work[:12] in offer["message"]
    closed = await app.post(
        f"{BASE}/documents/{PATH}/close-already-built",
        json={"commits": offer["commits"]},
        headers=auth_headers,
    )
    assert closed.status_code == 200, closed.text
    statuses = {t.status for t in await _rows(Task)}
    assert statuses and "pending" not in statuses, statuses
