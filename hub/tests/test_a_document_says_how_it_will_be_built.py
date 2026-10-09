"""`a-document-says-how-it-will-be-built-and-approval-starts-it`.

This file grows with the change (design.md's rounds; `openspec/changes/
a-document-says-how-it-will-be-built-and-approval-starts-it/tasks.md`). Task 1.1 is `delivery`'s
shape at save time; 1.2 is proposing (D4); 1.3 onward is approval: the board in a savepoint, the
delivery's flow, and the report (D5-D7). Tests are named by the task they cover.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from hub import spec_completeness, spec_tasks
from hub import sse as sse_module
from hub.agent_auth import hash_run_token
from hub.api.v1 import jobs as jobs_api
from hub.api.v1 import spec as spec_api
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    EventLog,
    Loop,
    ProjectSession,
    Run,
    SpecDocument,
    SpecDocumentEvent,
    SpecRequirement,
    Task,
    TaskRequirementLink,
)
from hub.spec_documents import parse_stored
from hub.spec_payload import (
    SCHEMA_VERSION,
    PayloadError,
    payload_to_dict,
    validate_payload,
)

from .test_spec_documents_api import PATH as DOC_PATH
from .test_spec_documents_api import _create, _document
from .test_spec_documents_api import _submit as _submit_document

BASE = "/api/v1/projects/proj-test/project"
AGENT = "/api/v1/agent-actions/spec/documents"


@pytest.fixture
async def run_headers():
    token = "aw_run_delivery-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-delivery",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _payload(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Demo",
        "summary": "Original summary",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Shape (validate_payload)
# ---------------------------------------------------------------------------


def test_delivery_absent_validates():
    payload = validate_payload(_payload())
    assert payload.delivery is None


def test_a_flow_delivery_validates():
    payload = validate_payload(
        _payload(
            delivery={
                "mode": "flow",
                "agent": "dev",
                "stop_when_queue_empties": True,
                "cron": "*/5 * * * *",
            }
        )
    )
    assert payload.delivery is not None
    assert payload.delivery.mode == "flow"
    assert payload.delivery.agent == "dev"


def test_a_none_delivery_validates():
    payload = validate_payload(_payload(delivery={"mode": "none"}))
    assert payload.delivery.mode == "none"


def test_an_unknown_mode_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_payload(delivery={"mode": "maybe"}))
    assert "delivery.mode" in exc.value.field


def test_an_unparseable_cron_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_payload(delivery={"mode": "flow", "cron": "not a cron"}))
    assert exc.value.field == "delivery.cron"


def test_a_stop_at_with_no_timezone_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_payload(delivery={"mode": "flow", "stop_at": "2026-10-01T00:00:00"}))
    assert exc.value.field == "delivery.stop_at"


def test_a_stop_at_with_a_timezone_is_accepted():
    payload = validate_payload(
        _payload(delivery={"mode": "flow", "stop_at": "2026-10-01T00:00:00+01:00"})
    )
    assert payload.delivery.stop_at == "2026-10-01T00:00:00+01:00"


def test_a_cron_over_128_characters_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_payload(delivery={"mode": "flow", "cron": "*/5 * * * *" + " " * 120}))
    assert "delivery.cron" in exc.value.field


def test_an_agent_over_32_characters_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_payload(delivery={"mode": "flow", "agent": "a" * 33}))
    assert "delivery.agent" in exc.value.field


# ---------------------------------------------------------------------------
# `payload_to_dict` — no `delivery: null` for a document that never declared one (R3)
# ---------------------------------------------------------------------------


def test_payload_to_dict_drops_an_absent_delivery():
    payload = validate_payload(_payload())
    data = payload_to_dict(payload)
    assert "delivery" not in data


def test_payload_to_dict_keeps_a_present_delivery():
    payload = validate_payload(_payload(delivery={"mode": "none"}))
    data = payload_to_dict(payload)
    assert data["delivery"] == {
        "mode": "none",
        "agent": None,
        "reviewer": None,
        "stop_when_queue_empties": False,
        "stop_at": None,
        "cron": "*/5 * * * *",
    }


# ---------------------------------------------------------------------------
# End to end: a `contract` document written without the `delivery` key answers an unchanged
# resubmission with `unchanged` containing `metadata` and zero proposals — the regression D1
# guards against (a stored-null `delivery` would otherwise diff against an absent one).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unchanged_resubmission_with_no_delivery_key_proposes_nothing(
    app, auth_headers, run_headers
):
    path = "spec/changes/delivery-demo/spec.json"
    document = _payload(
        requirements=[{"key": "alpha", "statement": "It responds within 200ms", "modal": "MUST"}]
    )
    await app.post(f"{BASE}/documents", json={"path": path, "title": "Demo"}, headers=auth_headers)
    write = await app.post(AGENT, json={"path": path, "document": document}, headers=run_headers)
    assert write.status_code == 200, write.text
    rigor = await app.post(
        f"{BASE}/documents/{path}/rigor", json={"rigor": "gate"}, headers=auth_headers
    )
    assert rigor.status_code == 200, rigor.text

    response = await app.post(AGENT, json={"path": path, "document": document}, headers=run_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["proposals"] == []
    assert "metadata" in body["unchanged"]


# ---------------------------------------------------------------------------
# 1.2 (refusal half) — proposing a change-spec is refused while `delivery` is
# unanswered or an incomplete flow (D4). `_document()` (test_spec_documents_api) already
# carries a requirement, a criterion and a task that satisfy every other completeness check,
# so the only finding these fixtures can produce is the one under test.
# ---------------------------------------------------------------------------


async def _close_exploration(app, auth_headers, path=DOC_PATH):
    closed = await app.post(
        f"{BASE}/documents/close-exploration", params={"path": path}, headers=auth_headers
    )
    assert closed.status_code == 200, closed.text


async def _propose(app, auth_headers, path=DOC_PATH):
    return await app.post(f"{BASE}/documents/propose", params={"path": path}, headers=auth_headers)


@pytest.mark.asyncio
async def test_proposing_with_no_delivery_warns(app, auth_headers, run_headers):
    await _create(app, auth_headers)
    await _submit_document(app, run_headers, _document(delivery=None))
    await _close_exploration(app, auth_headers)

    response = await _propose(app, auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    # A gap (approve-lists-what-is-missing FR-3): proposal passes it and lists it.
    assert body["phase"] == "proposed"
    assert "delivery_unanswered" in {w["code"] for w in body["warnings"]}


@pytest.mark.asyncio
async def test_proposing_a_flow_with_no_agent_warns(app, auth_headers, run_headers):
    await _create(app, auth_headers)
    await _submit_document(
        app,
        run_headers,
        _document(delivery={"mode": "flow", "stop_when_queue_empties": True}),
    )
    await _close_exploration(app, auth_headers)

    response = await _propose(app, auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "proposed"
    assert "delivery_flow_incomplete" in {w["code"] for w in body["warnings"]}


@pytest.mark.asyncio
async def test_proposing_a_flow_with_no_stop_condition_warns(app, auth_headers, run_headers):
    await _create(app, auth_headers)
    await _submit_document(
        app,
        run_headers,
        _document(delivery={"mode": "flow", "agent": "dev"}),
    )
    await _close_exploration(app, auth_headers)

    response = await _propose(app, auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "proposed"
    assert "delivery_flow_incomplete" in {w["code"] for w in body["warnings"]}


# ---------------------------------------------------------------------------
# 1.2 (remainder) — a `none` delivery proposes; a roadmap is never asked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_none_delivery_proposes(app, auth_headers, run_headers):
    await _create(app, auth_headers)
    await _submit_document(app, run_headers, _document(delivery={"mode": "none"}))
    await _close_exploration(app, auth_headers)

    response = await _propose(app, auth_headers)

    assert response.status_code == 200, response.text
    assert response.json()["phase"] == "proposed"
    assert response.json()["blocking"] == []


def test_a_roadmap_with_no_delivery_gets_neither_code():
    payload = validate_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "roadmap",
            "title": "Plan",
            # A roadmap carries slices, not requirements (C1a, `spec-roadmaps`).
            "slices": [{"key": "s1", "title": "First slice"}],
        }
    )
    codes = {finding.code for finding in spec_completeness.check(payload)}
    assert "delivery_unanswered" not in codes
    assert "delivery_flow_incomplete" not in codes


# ---------------------------------------------------------------------------
# 1.3-1.10 — approval creates the delivery's flow, and reports what it did (D5-D7)
# ---------------------------------------------------------------------------

FLOW = {"mode": "flow", "agent": "dev", "stop_when_queue_empties": True}


@pytest.fixture
def published(monkeypatch):
    """Every frame, as `SSEManager.publish` sees it: a deferred frame never calls `broadcast`."""
    frames: list = []
    real = sse_module.sse_manager.publish

    def spy(project_id, event_type, payload):
        frames.append((event_type, payload))
        return real(project_id, event_type, payload)

    monkeypatch.setattr(sse_module.sse_manager, "publish", spy)
    return frames


async def _agent(name, lifecycle="open"):
    async with async_session_factory() as db:
        db.add(Agent(id=f"agt-{name}", project_id="proj-test", name=name, lifecycle=lifecycle))
        await db.commit()


async def _set_lifecycle(name, lifecycle):
    async with async_session_factory() as db:
        agent = (await db.execute(select(Agent).where(Agent.name == name))).scalar_one()
        agent.lifecycle = lifecycle
        await db.commit()


async def _proposed(app, auth_headers, run_headers, document, *, title="Demo", path=DOC_PATH):
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": title}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    written = await _submit_document(app, run_headers, document, path=path)
    assert written.status_code == 200, written.text
    await _close_exploration(app, auth_headers, path)
    proposed = await _propose(app, auth_headers, path)
    assert proposed.json()["phase"] == "proposed", proposed.text


async def _forced_proposed(app, auth_headers, run_headers, document, path=DOC_PATH):
    """A document at `proposed` that propose (and, with B5, `transition()`) would refuse: set in
    the database, as a document proposed before this change was (tasks.md 1.3)."""
    await _create(app, auth_headers, path)
    written = await _submit_document(app, run_headers, document, path=path)
    assert written.status_code == 200, written.text
    async with async_session_factory() as db:
        row = (await db.execute(select(SpecDocument).where(SpecDocument.path == path))).scalar_one()
        row.phase = "proposed"
        row.explore_closed_at = datetime.now(timezone.utc)
        await db.commit()


async def _phase(app, auth_headers, to, path=DOC_PATH, **body):
    return await app.post(
        f"{BASE}/documents/phase",
        params={"path": path, "to": to},
        json={"reason": "test", **body},
        headers=auth_headers,
    )


async def _approve(app, auth_headers, path=DOC_PATH, **body):
    body.setdefault("approve_anyway", True)
    response = await _phase(app, auth_headers, "approved", path, **body)
    assert response.status_code == 200, response.text
    assert response.json()["phase"] == "approved"
    return response.json()


async def _reopen_and_repropose(app, auth_headers, run_headers, document, path=DOC_PATH):
    reopened = await _phase(app, auth_headers, "exploring", path)
    assert reopened.status_code == 200, reopened.text
    written = await _submit_document(app, run_headers, document, path=path)
    assert written.status_code == 200, written.text
    await _close_exploration(app, auth_headers, path)
    proposed = await _propose(app, auth_headers, path)
    assert proposed.json()["phase"] == "proposed", proposed.text


async def _rows(model, *where):
    async with async_session_factory() as db:
        return (await db.execute(select(model).where(*where))).scalars().all()


async def _document_id(path=DOC_PATH):
    (row,) = await _rows(SpecDocument, SpecDocument.path == path)
    return row.id


def _two_tasks():
    return _document(
        delivery=FLOW,
        tasks=[
            {"key": "t1", "description": "Build it", "requirements": ["alpha"]},
            {"key": "t2", "description": "Test it", "requirements": ["alpha"]},
        ],
    )


@pytest.mark.asyncio
async def test_1_3_approving_a_document_proposed_with_no_delivery(app, auth_headers, run_headers):
    """Fails without D4's approval-time exclusion: the document could never be approved."""
    await _forced_proposed(app, auth_headers, run_headers, _document(delivery=None))

    body = await _approve(app, auth_headers)

    assert len(body["tasks_created"]) == 1
    assert body["approval_outcome"]["flow"] == {
        "state": "none",
        "messages": ["No delivery was declared."],
    }
    assert await _rows(Loop) == []


@pytest.mark.asyncio
async def test_1_4_approving_a_flow_delivery_creates_the_flow(
    app, auth_headers, run_headers, published
):
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))
    published.clear()
    before = datetime.now(timezone.utc)

    body = await _approve(app, auth_headers)

    document_id = await _document_id()
    (loop,) = await _rows(Loop)
    (job,) = await _rows(AIJob)
    assert loop.spec_document_id == document_id and loop.job_id == job.id
    assert loop.stop_when_queue_empties is True
    assert (job.agent, job.name, job.cron, job.enabled) == ("dev", "Demo", "*/5 * * * *", True)
    tasks = await _rows(Task, Task.spec_document_id == document_id)
    assert [task.loop_id for task in tasks] == [loop.id]
    # First firing at the next tick: the next five-minute boundary, and nothing started now.
    next_run = job.next_run if job.next_run.tzinfo else job.next_run.replace(tzinfo=timezone.utc)
    assert next_run > before and next_run.minute % 5 == 0 and next_run.second == 0
    assert await _rows(Run, Run.agent == "dev") == []
    assert [e.event_type for e in await _rows(EventLog, EventLog.event_type == "job_created")] == [
        "job_created"
    ]
    kinds = [
        kind for kind, _ in published if kind in ("spec_updated", "task_updated", "job_created")
    ]
    assert kinds == ["spec_updated", "task_updated", "job_created"]
    flow = body["approval_outcome"]["flow"]
    assert (flow["state"], flow["job_id"], flow["agent"]) == ("created", job.id, "dev")
    assert body["tasks_created"] == [task.id for task in tasks]


@pytest.mark.asyncio
async def test_1_4_a_long_title_is_cut_to_a_job_name(app, auth_headers, run_headers):
    await _agent("dev")
    title = "x" * 300
    await _proposed(
        app, auth_headers, run_headers, _document(delivery=FLOW, title=title), title=title
    )

    await _approve(app, auth_headers)

    (job,) = await _rows(AIJob)
    assert job.name == "x" * 256


@pytest.mark.asyncio
async def test_1_5_an_archived_delivery_agent_starts_no_flow(app, auth_headers, run_headers):
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))
    await _set_lifecycle("dev", "archived")

    body = await _approve(app, auth_headers)

    assert len(body["tasks_created"]) == 1
    assert body["approval_outcome"]["flow"]["state"] == "not_created"
    assert "dev is archived" in body["approval_outcome"]["flow"]["messages"][0]
    assert await _rows(Loop) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("roster", ["empty", "legacy"])
async def test_1_5_a_name_the_project_does_not_have_starts_no_flow(
    app, auth_headers, run_headers, roster
):
    """Both rosters `_check_agent_exists` accepts; approval must agree with the page (1.9)."""
    if roster == "legacy":
        async with async_session_factory() as db:
            db.add(ProjectSession(project_id="proj-test", data={"agents": {"dev": {}}}))
            await db.commit()
    await _forced_proposed(app, auth_headers, run_headers, _document(delivery=FLOW))

    body = await _approve(app, auth_headers)

    assert "dev is not an agent on this project" in body["approval_outcome"]["flow"]["messages"][0]
    assert await _rows(Loop) == []


@pytest.mark.asyncio
async def test_1_5_the_operator_replaces_a_stale_agent_at_approval(
    app, auth_headers, run_headers, tmp_path
):
    await _agent("dev")
    await _agent("old")
    await _proposed(app, auth_headers, run_headers, _document(delivery={**FLOW, "agent": "old"}))
    await _set_lifecycle("old", "archived")
    file_before = (tmp_path / DOC_PATH).read_text(encoding="utf-8")

    body = await _approve(app, auth_headers, delivery_agent="dev")

    (job,) = await _rows(AIJob)
    assert job.agent == "dev"
    assert body["approval_outcome"]["delivery_agent"] == "dev"
    # Approving never rewrites the author's content: the file still names `old`.
    assert '"agent": "old"' in (tmp_path / DOC_PATH).read_text(encoding="utf-8")
    assert '"agent": "old"' in file_before


@pytest.mark.asyncio
async def test_1_5_choosing_no_flow_at_approval(app, auth_headers, run_headers):
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))

    body = await _approve(app, auth_headers, delivery_agent="")

    assert body["approval_outcome"]["flow"]["messages"] == ["You chose no flow at approval."]
    assert await _rows(Loop) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "delivery, said",
    [
        ({"mode": "flow", "agent": "dev"}, "sets no stop condition"),
        (
            {"mode": "flow", "agent": "dev", "stop_at": "2020-01-01T00:00:00+00:00"},
            "has passed",
        ),
    ],
)
async def test_1_5_a_flow_that_could_not_stop_or_already_stopped_is_not_created(
    app, auth_headers, run_headers, delivery, said
):
    await _agent("dev")
    await _forced_proposed(app, auth_headers, run_headers, _document(delivery=delivery))

    body = await _approve(app, auth_headers)

    assert said in body["approval_outcome"]["flow"]["messages"][0]
    assert await _rows(Loop) == []


@pytest.mark.asyncio
async def test_1_6_re_approval_reports_the_flow_already_building_the_document(
    app, auth_headers, run_headers, published
):
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))
    await _approve(app, auth_headers)
    (flow_job,) = await _rows(AIJob)
    (loop,) = await _rows(Loop)
    await _reopen_and_repropose(app, auth_headers, run_headers, _two_tasks())
    published.clear()

    body = await _approve(app, auth_headers)

    assert len(await _rows(Loop, Loop.archived_at.is_(None))) == 1
    (new_task_id,) = body["tasks_created"]
    (new_task,) = await _rows(Task, Task.id == new_task_id)
    assert new_task.loop_id == loop.id
    flow = body["approval_outcome"]["flow"]
    assert (flow["state"], flow["job_id"], flow["flow_state"]) == (
        "existing",
        flow_job.id,
        "running",
    )
    assert flow["messages"] == [f"The flow {flow_job.name} already builds this document."]
    assert "job_created" not in [kind for kind, _ in published]


@pytest.mark.asyncio
async def test_1_6a_a_claim_race_is_reported_as_already_claimed(
    app, auth_headers, run_headers, published, monkeypatch
):
    """Fails, reporting "The flow could not be created.", if the loop is not flushed before
    adoption: the adoption's `UPDATE` autoflushes it outside the handler that maps the 409."""
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))
    await _approve(app, auth_headers)
    await _reopen_and_repropose(app, auth_headers, run_headers, _two_tasks())

    async def no_existing_flow(*args, **kwargs):
        return None

    async def no_conflict(*args, **kwargs):
        return None

    monkeypatch.setattr(spec_api, "_existing_flow_entry", no_existing_flow)
    monkeypatch.setattr(jobs_api, "_check_spec_document_conflict", no_conflict)
    published.clear()

    body = await _approve(app, auth_headers)

    assert "already claimed by another loop" in body["approval_outcome"]["flow"]["messages"][0]
    assert len(await _rows(Loop, Loop.archived_at.is_(None))) == 1
    assert len(await _rows(AIJob)) == 1
    assert "job_created" not in [kind for kind, _ in published]


@pytest.mark.asyncio
async def test_1_6b_a_failure_after_adoption_leaves_the_approval_and_the_board(
    app, auth_headers, run_headers, published, monkeypatch
):
    """Fails with a `MissingGreenlet` 500 if anything read after the savepoint rolled back is an
    ORM row the adoption touched."""
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))
    real = jobs_api._adopt_document_tasks

    async def adopt_then_raise(session, project_id, loop):
        await real(session, project_id, loop)
        raise RuntimeError("after adoption")

    monkeypatch.setattr(jobs_api, "_adopt_document_tasks", adopt_then_raise)
    published.clear()

    body = await _approve(app, auth_headers)

    assert body["approval_outcome"]["flow"]["messages"] == ["The flow could not be created."]
    (task,) = await _rows(Task, Task.id.in_(body["tasks_created"]))
    assert task.loop_id is None
    assert await _rows(Loop) == [] and await _rows(AIJob) == []
    assert await _rows(EventLog, EventLog.event_type == "job_created") == []
    assert "job_created" not in [kind for kind, _ in published]


@pytest.mark.asyncio
async def test_1_6_an_ended_flow_is_not_reported_as_building(app, auth_headers, run_headers):
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))
    await _approve(app, auth_headers)
    async with async_session_factory() as db:
        loop = (await db.execute(select(Loop))).scalar_one()
        job = (await db.execute(select(AIJob))).scalar_one()
        loop.ending_state = "completed"
        job.enabled = False
        await db.commit()
    await _reopen_and_repropose(app, auth_headers, run_headers, _two_tasks())

    body = await _approve(app, auth_headers)

    assert len(await _rows(Loop)) == 1
    flow = body["approval_outcome"]["flow"]
    assert flow["flow_state"] == "ended"
    assert "has ended; the new tasks wait for it" in flow["messages"][0]
    assert "already builds" not in " ".join(flow["messages"])


@pytest.mark.asyncio
async def test_1_6_a_flow_started_by_hand_is_reported_on_re_approval(
    app, auth_headers, run_headers
):
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery={"mode": "none"}))
    await _approve(app, auth_headers)
    started = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "By hand",
            "agent": "dev",
            "message": "Work it",
            "cron": "*/5 * * * *",
            "purpose": "",
            "stop_when_queue_empties": True,
            "spec_document_id": await _document_id(),
        },
        headers=auth_headers,
    )
    assert started.status_code == 201, started.text
    await _reopen_and_repropose(
        app, auth_headers, run_headers, {**_two_tasks(), "delivery": {"mode": "none"}}
    )

    body = await _approve(app, auth_headers)

    flow = body["approval_outcome"]["flow"]
    assert (flow["state"], flow["name"]) == ("existing", "By hand")


@pytest.mark.asyncio
@pytest.mark.parametrize("to, delivery", [("exploring", FLOW), ("approved", {"mode": "none"})])
async def test_1_6_a_delivery_agent_that_cannot_be_honoured_is_refused(
    app, auth_headers, run_headers, to, delivery
):
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=delivery))

    response = await _phase(app, auth_headers, to, delivery_agent="dev")

    assert response.status_code == 400, response.text
    (row,) = await _rows(SpecDocument)
    assert row.phase == "proposed"


@pytest.mark.asyncio
async def test_1_6_a_chosen_agent_an_existing_flow_makes_moot_is_reported(
    app, auth_headers, run_headers
):
    """Opus note 4: the strip still offers a choice on re-approval, and nothing used it."""
    await _agent("dev")
    await _agent("qa")
    await _agent("old")
    stale = {**FLOW, "agent": "old"}
    await _proposed(app, auth_headers, run_headers, _document(delivery=stale))
    await _set_lifecycle("old", "archived")
    await _approve(app, auth_headers, delivery_agent="dev")
    await _reopen_and_repropose(app, auth_headers, run_headers, {**_two_tasks(), "delivery": stale})

    body = await _approve(app, auth_headers, delivery_agent="qa")

    (job,) = await _rows(AIJob)
    assert job.agent == "dev"
    messages = body["approval_outcome"]["flow"]["messages"]
    assert any("The agent you chose, qa, was not applied" in m for m in messages)
    assert f"The flow {job.name} runs as dev, not old." in messages


@pytest.mark.asyncio
async def test_1_6c_a_failed_board_starts_no_flow(app, auth_headers, run_headers, monkeypatch):
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))

    async def fails(*args, **kwargs):
        raise RuntimeError("board down")

    monkeypatch.setattr(spec_tasks, "materialise", fails)

    body = await _approve(app, auth_headers)

    outcome = body["approval_outcome"]
    assert outcome["failed"] == "RuntimeError: board down"
    assert outcome["flow"]["messages"] == [spec_api._NO_TASKS]
    assert await _rows(Loop) == [] and await _rows(AIJob) == []
    assert await _rows(EventLog, EventLog.event_type == "job_created") == []


@pytest.mark.asyncio
async def test_1_6c_a_board_already_served_by_hand_starts_no_flow(app, auth_headers, run_headers):
    """Every declared entry is skipped, and the hand-made task is not this document's to adopt."""
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))
    async with async_session_factory() as db:
        requirement = (await db.execute(select(SpecRequirement))).scalars().first()
        db.add(Task(id="task-byhand", project_id="proj-test", title="By hand", status="pending"))
        await db.flush()
        db.add(
            TaskRequirementLink(
                id="trl-byhand",
                project_id="proj-test",
                task_id="task-byhand",
                requirement_id=requirement.id,
            )
        )
        await db.commit()

    body = await _approve(app, auth_headers)

    outcome = body["approval_outcome"]
    assert outcome["created"] == []
    assert outcome["already_served"] == [{"key": "t1", "requirements": ["alpha"]}]
    assert outcome["flow"]["messages"] == [spec_api._NO_TASKS]
    assert await _rows(Loop) == []


@pytest.mark.asyncio
async def test_1_7_a_board_that_fails_mid_flush_leaves_the_approval_and_no_partial_board(
    app, auth_headers, run_headers, monkeypatch
):
    """Fails with a 500 (`PendingRollbackError`) without the savepoint."""
    await _proposed(app, auth_headers, run_headers, _document(delivery={"mode": "none"}))
    await _approve(app, auth_headers)
    await _reopen_and_repropose(
        app, auth_headers, run_headers, {**_two_tasks(), "delivery": {"mode": "none"}}
    )
    real = spec_tasks.requirement_links.link

    async def collide(session, task, requirements, **kwargs):
        session.add(Task(id=task.id, project_id="proj-test", title="dup", status="pending"))
        await session.flush()

    monkeypatch.setattr(spec_tasks.requirement_links, "link", collide)

    body = await _approve(app, auth_headers)
    monkeypatch.setattr(spec_tasks.requirement_links, "link", real)

    assert body["approval_outcome"]["failed"].startswith("IntegrityError")
    assert body["approval_outcome"]["dependencies_not_honoured"] == []
    tasks = await _rows(Task, Task.spec_document_id == await _document_id())
    assert [task.spec_task_key for task in tasks] == ["t1"]


@pytest.mark.asyncio
async def test_1_7_a_board_that_raises_after_its_first_add_leaves_nothing(
    app, auth_headers, run_headers, monkeypatch
):
    """Leaves a partial board without the savepoint."""
    await _proposed(app, auth_headers, run_headers, _document(delivery={"mode": "none"}))
    await _approve(app, auth_headers)
    await _reopen_and_repropose(
        app, auth_headers, run_headers, {**_two_tasks(), "delivery": {"mode": "none"}}
    )

    async def raise_after_add(session, task, requirements, **kwargs):
        raise RuntimeError("after the first add")

    monkeypatch.setattr(spec_tasks.requirement_links, "link", raise_after_add)

    body = await _approve(app, auth_headers)

    assert body["approval_outcome"]["failed"] == "RuntimeError: after the first add"
    tasks = await _rows(Task, Task.spec_document_id == await _document_id())
    assert [task.spec_task_key for task in tasks] == ["t1"]


@pytest.mark.asyncio
async def test_1_8_the_report_names_what_was_skipped_and_not_honoured_in_order(
    app, auth_headers, run_headers
):
    # Imports from a document that does not exist: the one unresolvable reference B5's gate lets
    # reach approval (`import_not_approved` is excluded there), so it is resolved at materialise.
    ghost = "spec/changes/ghost/spec.json"
    document = _document(
        delivery={"mode": "none"},
        tasks=[
            {"key": "zz", "from": {"document": ghost, "key": "zz"}, "requirements": ["alpha"]},
            {"key": "aa", "from": {"document": ghost, "key": "aa"}, "requirements": ["alpha"]},
            {"key": "mm", "from": {"document": ghost, "key": "mm"}, "requirements": ["alpha"]},
            {"key": "t1", "description": "Build it", "requirements": ["alpha"]},
            {
                "key": "t2",
                "description": "Test",
                "requirements": ["alpha"],
                "depends_on": ["zz", "aa"],
            },
            {"key": "t3", "description": "Ship", "requirements": ["alpha"], "depends_on": ["mm"]},
        ],
    )
    await _forced_proposed(app, auth_headers, run_headers, document)

    body = await _approve(app, auth_headers)

    references = [
        (row["task_key"], row["reference"])
        for row in body["approval_outcome"]["dependencies_not_honoured"]
    ]
    # Declaration order (t2 before t3), then by reference within a task: t2 declares `zz` first,
    # so insertion order would put it before `aa`.
    assert references == [("t2", "aa"), ("t2", "zz"), ("t3", "mm")]
    assert all(row["reason"] for row in body["approval_outcome"]["dependencies_not_honoured"])
    got = await app.get(f"{BASE}/spec", params={"path": DOC_PATH}, headers=auth_headers)
    assert got.json()["approval_outcome"] == body["approval_outcome"]


@pytest.mark.asyncio
async def test_1_8_the_newest_report_wins_a_created_at_tie(app, auth_headers, run_headers):
    """Fails if the Hub orders by `rowid ASC` (Opus finding 3). Ordering by `created_at` alone is
    not caught here, measured: on an exact tie SQLite happens to return the later row first, so that
    mutation passes. The tie-break is what makes the answer defined rather than lucky.

    The tie is made in the database: `created_at`'s default captured `_now` when the model was
    defined, so patching the function would not freeze it. On this machine's 15.625 ms clock the
    same tie happens on its own.
    """
    await _proposed(app, auth_headers, run_headers, _document(delivery={"mode": "none"}))
    await _approve(app, auth_headers)
    await _reopen_and_repropose(
        app, auth_headers, run_headers, {**_two_tasks(), "delivery": {"mode": "none"}}
    )
    second = await _approve(app, auth_headers)
    tied = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    async with async_session_factory() as db:
        reports = (
            (
                await db.execute(
                    select(SpecDocumentEvent).where(SpecDocumentEvent.kind == "approval_report")
                )
            )
            .scalars()
            .all()
        )
        assert len(reports) == 2
        for report in reports:
            report.created_at = tied
        await db.commit()

    got = await app.get(f"{BASE}/spec", params={"path": DOC_PATH}, headers=auth_headers)

    assert got.json()["approval_outcome"] == second["approval_outcome"]
    assert [task["key"] for task in second["approval_outcome"]["created"]] == ["t2"]


@pytest.mark.asyncio
async def test_1_8_a_roadmap_approval_writes_a_report_too(app, auth_headers, run_headers):
    path = "spec/roadmap.json"
    created = await app.post(
        f"{BASE}/documents",
        json={"path": path, "title": "Plan", "kind": "roadmap"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    roadmap = {
        "schema_version": SCHEMA_VERSION,
        "kind": "roadmap",
        "title": "Plan",
        "scope": {"in_scope": ["the plan"], "non_goals": ["the rest"]},
        # A roadmap carries slices, not requirements or tasks (C1a, `spec-roadmaps`).
        "slices": [
            {
                "key": "s1",
                "title": "First slice",
                "intent": "i",
                "done": "the first slice works end to end",
            }
        ],
    }
    written = await _submit_document(app, run_headers, roadmap, path=path)
    assert written.status_code == 200, written.text
    await _close_exploration(app, auth_headers, path)
    proposed = await _propose(app, auth_headers, path)
    assert proposed.json()["phase"] == "proposed", proposed.text

    body = await _approve(app, auth_headers, path)

    assert body["approval_outcome"]["flow"]["state"] == "not_applicable"
    assert "Only a change document declares a delivery" in (
        body["approval_outcome"]["flow"]["messages"][0]
    )


@pytest.mark.asyncio
async def test_1_9_delivery_status_follows_the_roster(app, auth_headers, run_headers, tmp_path):
    async def status_of():
        got = await app.get(f"{BASE}/spec", params={"path": DOC_PATH}, headers=auth_headers)
        assert got.status_code == 200, got.text
        return got.json().get("delivery_status")

    await _create(app, auth_headers)
    await _submit_document(app, run_headers, _document(delivery=None))
    assert await status_of() == {"state": "absent"}
    await _submit_document(app, run_headers, _document(delivery={"mode": "none"}))
    assert await status_of() == {"state": "none"}
    await _submit_document(app, run_headers, _document(delivery=FLOW))
    assert await status_of() == {"state": "stale", "agent": "dev", "reason": "unknown"}
    async with async_session_factory() as db:
        db.add(ProjectSession(project_id="proj-test", data={"agents": {"dev": {}}}))
        await db.commit()
    # Legacy session data knows `dev`; approval would still refuse it, so the page says stale.
    assert await status_of() == {"state": "stale", "agent": "dev", "reason": "unknown"}
    await _agent("dev")
    assert await status_of() == {"state": "ok", "agent": "dev"}
    digest = (tmp_path / DOC_PATH).read_bytes()
    await _set_lifecycle("dev", "archived")
    assert await status_of() == {"state": "stale", "agent": "dev", "reason": "archived"}
    assert (tmp_path / DOC_PATH).read_bytes() == digest, "a read must not rewrite the file"

    await _set_lifecycle("dev", "open")
    await _close_exploration(app, auth_headers)
    await _propose(app, auth_headers)
    await _approve(app, auth_headers)
    assert await status_of() is None, "not computed for an approved document"


@pytest.mark.asyncio
async def test_1_10_a_loop_insert_that_hits_the_claim_index_is_a_409_leaving_no_job(
    app, auth_headers, run_headers, monkeypatch
):
    """Fails today twice over: the job was committed first, and the answer was a 500."""
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))
    await _approve(app, auth_headers)

    async def no_conflict(*args, **kwargs):
        return None

    monkeypatch.setattr(jobs_api, "_check_spec_document_conflict", no_conflict)

    response = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Second",
            "agent": "dev",
            "message": "Work it",
            "cron": "*/5 * * * *",
            "purpose": "",
            "stop_when_queue_empties": True,
            "spec_document_id": await _document_id(),
        },
        headers=auth_headers,
    )

    assert response.status_code == 409, response.text
    assert "already claimed by another loop" in response.json()["detail"]
    assert [job.name for job in await _rows(AIJob)] == ["Demo"]


# ---------------------------------------------------------------------------
# 1.12 — `delivery` round-trips through the tool surface (D3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_1_12_submit_spec_document_round_trips_delivery_through_mcp(
    app, auth_headers, run_headers, tmp_path, monkeypatch
):
    """`mcp_server.submit_spec_document(delivery=...)` builds a body the real agent-actions
    route accepts, and the `delivery` it sends reaches the stored payload — the same join
    `test_mcp_body_contract.py` checks for every other tool, carried one step further into
    the file the Hub actually writes."""
    from hub.mcp_server import submit_spec_document

    await _create(app, auth_headers)

    sent: dict = {}

    def fake_urlopen(request, timeout=10):
        sent["body"] = json.loads(request.data)
        response = MagicMock()
        response.read.return_value = b"{}"
        response.__enter__ = lambda value: value
        response.__exit__ = MagicMock(return_value=False)
        return response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("HUB_URL", "http://localhost:8000")
    monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_delivery-secret")

    submit_spec_document(
        path=DOC_PATH,
        title="Demo",
        kind="change-spec",
        delivery={"mode": "flow", "agent": "dev", "stop_when_queue_empties": True},
    )

    assert sent["body"]["document"]["delivery"] == {
        "mode": "flow",
        "agent": "dev",
        "stop_when_queue_empties": True,
    }

    response = await app.post(AGENT, json=sent["body"], headers=run_headers)
    assert response.status_code == 200, response.text

    stored = parse_stored((tmp_path / DOC_PATH).read_text(encoding="utf-8"))
    assert stored["delivery"] == {
        "mode": "flow",
        "agent": "dev",
        "reviewer": None,
        "stop_when_queue_empties": True,
        "stop_at": None,
        "cron": "*/5 * * * *",
    }


@pytest.mark.asyncio
async def test_1_12_submit_spec_document_round_trips_delivery_through_the_http_route(
    app, auth_headers, run_headers, tmp_path
):
    """The same field, submitted directly against the HTTP agent-actions route (what an agent
    without MCP uses), reaches the same stored payload."""
    await _create(app, auth_headers)

    response = await _submit_document(app, run_headers, _document(delivery={"mode": "none"}))
    assert response.status_code == 200, response.text

    stored = parse_stored((tmp_path / DOC_PATH).read_text(encoding="utf-8"))
    assert stored["delivery"] == {
        "mode": "none",
        "agent": None,
        "reviewer": None,
        "stop_when_queue_empties": False,
        "stop_at": None,
        "cron": "*/5 * * * *",
    }
