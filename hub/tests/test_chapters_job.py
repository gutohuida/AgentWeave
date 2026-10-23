"""The manager's chapters job: its triggers, its controls, and what a firing may change.

`the-thread-reads-as-chapters-the-manager-writes` ("A chapters firing"). As in
`test_vault_spec_check.py` the worker is faked: a test hands `chapters_job.run_worker` what the model
would answer, so what is checked is what the Hub does with it. The real spawn is the acceptance
drive's (`scripts/drive/chapters_drive.py`).
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from hub import chapters, chapters_job, manager, project_thread
from hub.db.engine import async_session_factory
from hub.db.models import Task
from hub.worker import WorkerResult, WorkerUsage

from .test_chapters_store import doc, seed
from .test_spec_archive import PATH, _approved_document, run_headers  # noqa: F401

P = "proj-test"
BASE = f"/api/v1/projects/{P}"
HAIKU = "claude-haiku-4-5-20251001"
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def at(minutes):
    return (T0 + timedelta(minutes=minutes)).isoformat()


def draft(cid, members, a=0, b=5, title=None, cites=()):
    return chapters_job.ChapterDraft(
        id=cid,
        title=title or f"Chapter {cid}",
        summary="s",
        start=at(a),
        end=at(b),
        members=list(members),
        cites=list(cites),
    )


class _Worker:
    """Stands in for `run_worker`: answers each call with the next scripted (reason, drafts)."""

    def __init__(self, *answers) -> None:
        self.answers = list(answers)
        self.calls: list = []

    async def __call__(self, **kwargs) -> WorkerResult:
        self.calls.append(kwargs)
        reason, drafts = self.answers.pop(0) if self.answers else ("nothing", [])
        return WorkerResult(
            "ok",
            parsed=chapters_job.ChaptersAnswer(reason=reason, chapters=drafts),
            usage=WorkerUsage(input_tokens=11, output_tokens=7),
            duration_ms=5,
        )


@pytest.fixture
def worker(monkeypatch):
    def install(*answers) -> _Worker:
        fake = _Worker(*answers)
        monkeypatch.setattr(chapters_job, "run_worker", fake)
        return fake

    return install


async def _configure(app, auth_headers, **fields):
    runner = await app.post(
        f"{BASE}/runners",
        json={"name": "weaver", "cli": "claude", "model": HAIKU},
        headers=auth_headers,
    )
    assert runner.status_code == 201, runner.text
    patched = await app.patch(
        f"{BASE}/manager/jobs/chapters",
        json={"enabled": True, "runner_id": runner.json()["id"], **fields},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    return patched.json()


async def _firings():
    async with async_session_factory() as session:
        return await manager.list_firings(session, P, job="chapters")


async def _knots():
    async with async_session_factory() as session:
        return chapters.surface_keys(await project_thread.build(session, P))


async def _seed_task(i, minutes, status="in_progress", document=None):
    async with async_session_factory() as session:
        session.add(
            Task(
                id=f"task-{i}",
                project_id=P,
                title=f"Task {i}",
                status=status,
                spec_document_id=document,
                created_at=T0 + timedelta(minutes=minutes),
            )
        )
        await session.commit()


async def _approve_document(app, auth_headers, run_headers):  # noqa: F811
    await _approved_document(app, auth_headers, run_headers)
    await chapters_job.settled()


async def _wait_for_firings(count):
    for _ in range(100):
        if len(await _firings()) >= count:
            return
        await asyncio.sleep(0.05)


async def _fire(trigger):
    plan = await chapters_job.prepare(P, trigger=trigger)
    return await chapters_job.weave(plan, trigger=trigger, subject={})


# ---------------------------------------------------------------------------
# controls and triggers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_job_is_off_by_default_and_fires_nothing(
    app, auth_headers, run_headers, worker  # noqa: F811
):
    fake = worker()
    listed = (await app.get(f"{BASE}/manager/jobs", headers=auth_headers)).json()["jobs"]
    job = next(j for j in listed if j["key"] == "chapters")
    assert job["enabled"] is False and job["mode"] == "automatic"

    await _approve_document(app, auth_headers, run_headers)

    assert await _firings() == [] and fake.calls == []
    pressed = await app.post(f"{BASE}/manager/jobs/chapters/run", headers=auth_headers)
    assert pressed.status_code == 409, pressed.text


@pytest.mark.asyncio
async def test_an_approval_fires_once_when_automatic(
    app, auth_headers, run_headers, worker  # noqa: F811
):
    fake = worker(("first look", []))
    await _configure(app, auth_headers)

    await _approve_document(app, auth_headers, run_headers)

    firings = await _firings()
    assert len(firings) == 1 and len(fake.calls) == 1
    assert firings[0]["trigger"] == chapters_job.DOCUMENT_APPROVED
    assert firings[0]["subject"] == {"document": PATH}
    assert firings[0]["usage"] == {"input_tokens": 11, "output_tokens": 7}
    assert fake.calls[0]["initiator"] == "autonomous"


@pytest.mark.asyncio
async def test_an_archive_fires_once_when_automatic(app, auth_headers, worker):
    worker()
    await _configure(app, auth_headers)
    await app.post(
        f"{BASE}/project/documents", json={"path": PATH, "title": "Mistake"}, headers=auth_headers
    )
    archived = await app.post(
        f"{BASE}/project/documents/phase",
        params={"path": PATH, "to": "archived"},
        json={"reason": "by mistake"},
        headers=auth_headers,
    )
    assert archived.status_code == 200, archived.text
    await chapters_job.settled()

    assert [f["trigger"] for f in await _firings()] == [chapters_job.DOCUMENT_ARCHIVED]


@pytest.mark.asyncio
async def test_button_only_ignores_triggers_and_the_press_fires_as_asked(
    app, auth_headers, run_headers, worker  # noqa: F811
):
    fake = worker(("by hand", []))
    job = await _configure(app, auth_headers, mode="button", model=HAIKU)
    assert job["mode"] == "button" and job["automatic"] is False

    await _approve_document(app, auth_headers, run_headers)
    assert await _firings() == []

    pressed = await app.post(f"{BASE}/manager/jobs/chapters/run", headers=auth_headers)
    assert pressed.status_code == 202, pressed.text
    await _wait_for_firings(1)
    (firing,) = await _firings()
    assert firing["trigger"] == chapters_job.REQUESTED
    assert (firing["runner_id"], firing["model"]) == (job["runner_id"], HAIKU)
    assert fake.calls[0]["initiator"] == "operator"


@pytest.mark.asyncio
async def test_mode_is_only_for_the_chapters_job(app, auth_headers):
    refused = await app.patch(
        f"{BASE}/manager/jobs/conversation-titles", json={"mode": "button"}, headers=auth_headers
    )
    assert refused.status_code == 400, refused.text


@pytest.mark.asyncio
async def test_the_last_open_task_of_a_document_is_found_and_a_trigger_stages_once(app):
    await _seed_task(1, 0, status="approved", document="spdoc-x")
    await _seed_task(2, 1, status="in_progress", document="spdoc-x")
    await _seed_task(3, 2, status="in_progress", document="spdoc-x")
    async with async_session_factory() as session:
        two, three = await session.get(Task, "task-2"), await session.get(Task, "task-3")
        two.status = "approved"
        assert await chapters_job.is_last_open_task(session, two) is False
        three.status = "rejected"
        assert await chapters_job.is_last_open_task(session, two) is True
        for _ in range(2):
            chapters_job.fire_after_commit(
                session, P, chapters_job.LAST_TASK_APPROVED, {"task": "task-2"}
            )
        assert len(session.sync_session.info[chapters_job._PENDING_KEY]) == 1
        await session.rollback()
        assert chapters_job._PENDING_KEY not in session.sync_session.info


# ---------------------------------------------------------------------------
# what a firing may change, and what it is given
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unasked_firing_adds_but_never_retitles(app, auth_headers, worker):
    await seed(doc(1, 0))
    await _configure(app, auth_headers)
    old = await _knots()
    fake = worker(("story so far", [draft("a", old, title="Original")]))
    assert await _fire(chapters_job.DOCUMENT_APPROVED) == "written"

    await seed(doc(2, 10))
    new = sorted(set(await _knots()) - set(old))
    fake.answers.append(
        (
            "new work",
            [draft("a", old, title="Retitled"), draft("b", new, 10, 12, title="Fresh")],
        )
    )
    assert await _fire(chapters_job.DOCUMENT_APPROVED) == "written"

    async with async_session_factory() as session:
        state = await chapters.read(session, P)
    assert {c["id"]: c["title"] for c in state["chapters"]} == {"a": "Original", "b": "Fresh"}
    assert (await _firings())[0]["dropped"] == ["Original (a)"]


@pytest.mark.asyncio
async def test_an_asked_firing_may_retitle_and_is_kept_as_a_new_version(app, auth_headers, worker):
    await seed(doc(1, 0))
    await _configure(app, auth_headers)
    keys = await _knots()
    worker(
        ("story so far", [draft("a", keys, title="Original")]),
        ("a better title", [draft("a", keys, title="Retitled")]),
    )
    await _fire(chapters_job.DOCUMENT_APPROVED)
    await _fire(chapters_job.REQUESTED)

    async with async_session_factory() as session:
        state = await chapters.read(session, P)
    assert state["chapters"][0]["title"] == "Retitled"
    assert [v["version"] for v in state["versions"]] == [2, 1]
    assert state["versions"][0]["asked_by"] == "operator"


@pytest.mark.asyncio
async def test_the_next_firing_is_given_every_version_with_who_asked_and_why(
    app, auth_headers, worker
):
    await seed(doc(1, 0))
    await _configure(app, auth_headers)
    keys = await _knots()
    fake = worker(
        ("automatic reason", [draft("a", keys)]),
        ("requested reason", [draft("a", keys, title="Asked")]),
    )
    await _fire(chapters_job.DOCUMENT_APPROVED)
    await _fire(chapters_job.REQUESTED)
    async with async_session_factory() as session:
        await chapters.save(
            session,
            P,
            chapters=[draft("a", keys, title="By agent").model_dump()],
            surface=keys,
            author="Developer",
            reason="agent reason",
            asked_for=True,
            asked_by="operator",
        )

    plan = await chapters_job.prepare(P, trigger=chapters_job.REQUESTED)

    for expected in (
        "automatic reason",
        "requested reason",
        "agent reason",
        "by Developer",
        "by manager",
        "nobody asked",
        "asked by operator",
    ):
        assert expected in plan.prompt, expected
    assert fake.calls[0]["kind"] == "chapters"
