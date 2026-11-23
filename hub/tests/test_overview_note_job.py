"""The overview-note manager job (`overview-at-a-glance-with-dashboard-and-briefing-tabs`, task
visits-and-note): ac-note-on-visit, the Hub half of ac-note-failure, and what a firing keeps.

As in `test_chapters_job.py` the worker is faked: a test hands `overview_note_job.run_worker` what
the model would answer and counts the calls, so what is checked is when the Hub fires and what it
does with the answer. The real Haiku turn is the acceptance drive's
(`scripts/drive/overview_glance.py`)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest
from sqlalchemy import select

from hub import manager, overview_note_job
from hub.db.engine import async_session_factory
from hub.db.models import OverviewNote, OverviewVisit, Task, TaskIntegration
from hub.worker import WorkerResult, WorkerUsage

from .conftest import TEST_PROJECT_ID

P = TEST_PROJECT_ID
BASE = f"/api/v1/projects/{P}"
HAIKU = "claude-haiku-4-5-20251001"
NOW = datetime.now(timezone.utc)
T = NOW - timedelta(hours=3)


class _Worker:
    """Stands in for `run_worker`: answers each call with the next scripted result."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls: List[Dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> WorkerResult:
        self.calls.append(kwargs)
        answer = self.answers.pop(0) if self.answers else ("A quiet day.", [])
        if isinstance(answer, WorkerResult):
            return answer
        text, cites = answer
        return WorkerResult(
            "ok",
            parsed=overview_note_job.NoteAnswer(
                text=text, cites=[overview_note_job.NoteCite(**c) for c in cites]
            ),
            usage=WorkerUsage(input_tokens=11, output_tokens=7, cost_usd_micros=1200),
            duration_ms=5,
        )


@pytest.fixture
def worker(monkeypatch):
    def install(*answers: Any) -> _Worker:
        fake = _Worker(*answers)
        monkeypatch.setattr(overview_note_job, "run_worker", fake)
        return fake

    return install


@pytest.fixture
def announced(monkeypatch):
    from hub.sse import sse_manager

    seen: List[tuple] = []

    async def capture(project_id, event_type, data):
        seen.append((event_type, data))

    monkeypatch.setattr(sse_manager, "broadcast", capture)
    return seen


async def _configure(app, auth_headers, *, runner: bool = True, **fields: Any) -> None:
    body: Dict[str, Any] = {"enabled": True, **fields}
    if runner:
        made = await app.post(
            f"{BASE}/runners",
            json={"name": "noter", "cli": "claude", "model": HAIKU},
            headers=auth_headers,
        )
        assert made.status_code == 201, made.text
        body["runner_id"] = made.json()["id"]
    patched = await app.patch(f"{BASE}/manager/jobs/overview-note", json=body, headers=auth_headers)
    assert patched.status_code == 200, patched.text


async def _add(*rows: Any) -> None:
    async with async_session_factory() as db:
        for row in rows:
            db.add(row)
            await db.flush()
        await db.commit()


async def _note_at_t() -> None:
    await _add(
        OverviewNote(
            id="onote-t", project_id=P, written_at=T, trigger="button", text="Earlier.", cites=[]
        )
    )


async def _last_visit(ago: timedelta) -> None:
    await _add(OverviewVisit(project_id=P, last_visit_at=NOW - ago, previous_visit_at=None))


async def _landed_since_t(task_id: str = "t-landed") -> None:
    await _add(
        Task(id=task_id, project_id=P, title="Landed after the note", status="approved"),
        TaskIntegration(
            id=f"tint-{task_id}",
            project_id=P,
            task_id=task_id,
            outcome="merged",
            actor_kind="operator",
            created_at=T + timedelta(minutes=30),
        ),
    )


async def _firings() -> List[Dict[str, Any]]:
    async with async_session_factory() as db:
        return await manager.list_firings(db, P, job="overview-note")


async def _notes() -> List[str]:
    async with async_session_factory() as db:
        return list(
            (await db.execute(select(OverviewNote.id).where(OverviewNote.project_id == P)))
            .scalars()
            .all()
        )


async def _visit(app, auth_headers) -> Dict[str, Any]:
    response = await app.post(f"{BASE}/overview/visit", headers=auth_headers)
    assert response.status_code == 200, response.text
    await overview_note_job.settled()
    return response.json()


async def _overview(app, auth_headers) -> Dict[str, Any]:
    response = await app.get(f"{BASE}/overview", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# ac-note-on-visit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_visit_within_30_minutes_starts_no_note_though_work_landed(
    app, auth_headers, worker
):
    """(a) a visit 10 minutes after the last, with a task landed since T."""
    fake = worker()
    await _configure(app, auth_headers)
    await _note_at_t()
    await _last_visit(timedelta(minutes=10))
    await _landed_since_t()
    assert (await _visit(app, auth_headers))["note_started"] is False
    assert fake.calls == [] and await _firings() == []
    assert (await _overview(app, auth_headers))["note"]["id"] == "onote-t"


@pytest.mark.asyncio
async def test_a_new_visit_with_nothing_changed_starts_no_note(app, auth_headers, worker):
    """(b) a visit 2 hours after the last, with nothing changed since T."""
    fake = worker()
    await _configure(app, auth_headers)
    await _note_at_t()
    await _last_visit(timedelta(hours=2))
    assert (await _visit(app, auth_headers))["note_started"] is False
    assert fake.calls == [] and await _firings() == []
    assert (await _overview(app, auth_headers))["note"]["id"] == "onote-t"


@pytest.mark.asyncio
async def test_a_new_visit_with_work_landed_since_the_note_writes_one(
    app, auth_headers, worker, announced
):
    """(c) a visit 2 hours after the last, with a task landed since T: one firing, trigger visit."""
    fake = worker(
        ("Task t-landed landed.", [{"type": "task", "id": "t-landed", "label": "t-landed"}])
    )
    await _configure(app, auth_headers)
    await _note_at_t()
    await _last_visit(timedelta(hours=2))
    await _landed_since_t()
    answered = await _visit(app, auth_headers)
    assert answered["note_started"] is True
    assert len(fake.calls) == 1
    assert fake.calls[0]["initiator"] == "autonomous"
    assert "t-landed" in fake.calls[0]["prompt"]

    firings = await _firings()
    assert [(f["trigger"], f["outcome"]) for f in firings] == [("visit", "written")]
    assert firings[0]["duration_ms"] == 5
    assert firings[0]["usage"]["cost_usd_micros"] == 1200

    read = await _overview(app, auth_headers)
    assert read["note"]["trigger"] == "visit"
    assert read["note"]["text"] == "Task t-landed landed."
    assert read["note"]["cites"] == [{"type": "task", "id": "t-landed", "label": "t-landed"}]
    assert read["note"]["written_at"] > T.isoformat()
    assert read["note_writing"] is False
    assert read["note_last_attempt"]["outcome"] == "written"
    assert read["note_last_attempt"]["reason"] is None

    names = [name for name, _ in announced]
    assert names == ["overview_note_started", "overview_note_written"]
    assert announced[0][1] == {"trigger": "visit"}
    assert announced[1][1] == {"note_id": read["note"]["id"]}


@pytest.mark.asyncio
async def test_a_new_visit_with_the_job_disabled_starts_no_note(app, auth_headers, worker):
    """(d) as (c), with the job off."""
    fake = worker()
    await _configure(app, auth_headers)
    patched = await app.patch(
        f"{BASE}/manager/jobs/overview-note", json={"enabled": False}, headers=auth_headers
    )
    assert patched.status_code == 200
    await _note_at_t()
    await _last_visit(timedelta(hours=2))
    await _landed_since_t()
    assert (await _visit(app, auth_headers))["note_started"] is False
    assert fake.calls == [] and await _firings() == []
    assert (await _overview(app, auth_headers))["note"]["id"] == "onote-t"


@pytest.mark.asyncio
async def test_a_button_only_job_does_not_fire_on_a_visit(app, auth_headers, worker):
    fake = worker()
    await _configure(app, auth_headers, mode="button")
    await _note_at_t()
    await _last_visit(timedelta(hours=2))
    await _landed_since_t()
    assert (await _visit(app, auth_headers))["note_started"] is False
    assert fake.calls == []


@pytest.mark.asyncio
async def test_a_second_new_visit_with_nothing_new_since_the_visit_note_fires_once(
    app, auth_headers, worker
):
    """The note the visit wrote is the new 'since': the next new visit with nothing new is idle."""
    fake = worker()
    await _configure(app, auth_headers)
    await _note_at_t()
    await _last_visit(timedelta(hours=2))
    await _landed_since_t()
    assert (await _visit(app, auth_headers))["note_started"] is True
    async with async_session_factory() as db:
        row = await db.get(OverviewVisit, P)
        row.last_visit_at = row.last_visit_at - timedelta(hours=2)
        await db.commit()
    assert (await _visit(app, auth_headers))["note_started"] is False
    assert len(fake.calls) == 1


# ---------------------------------------------------------------------------
# Refresh note and ac-note-failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_note_writes_one_whether_or_not_anything_changed(app, auth_headers, worker):
    fake = worker()
    await _configure(app, auth_headers)
    await _note_at_t()
    response = await app.post(f"{BASE}/manager/jobs/overview-note/run", headers=auth_headers)
    assert response.status_code == 202, response.text
    assert response.json() == {"started": True}
    await overview_note_job.settled()
    assert len(fake.calls) == 1 and fake.calls[0]["initiator"] == "operator"
    assert [(f["trigger"], f["outcome"]) for f in await _firings()] == [("button", "written")]
    read = await _overview(app, auth_headers)
    assert read["note"]["trigger"] == "button" and read["note"]["id"] != "onote-t"
    assert len(await _notes()) == 2  # kept, not overwritten


@pytest.mark.asyncio
async def test_refresh_note_with_no_runner_says_why_keeps_the_note_and_records_the_firing(
    app, auth_headers, worker, announced
):
    fake = worker()
    await _configure(app, auth_headers, runner=False)
    await _note_at_t()
    response = await app.post(f"{BASE}/manager/jobs/overview-note/run", headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_runner"
    assert "no runner" in response.json()["detail"]["reason"]
    assert fake.calls == []

    firings = await _firings()
    assert [(f["trigger"], f["outcome"]) for f in firings] == [("button", "failed")]
    read = await _overview(app, auth_headers)
    assert read["note"]["id"] == "onote-t"
    assert read["note"]["written_at"] == T.isoformat()
    assert read["note_last_attempt"]["outcome"] == "failed"
    assert "no runner" in read["note_last_attempt"]["reason"]
    assert ("overview_note_failed", {"reason": response.json()["detail"]["reason"]}) in announced


@pytest.mark.asyncio
async def test_refresh_note_with_a_failing_runner_keeps_the_note_and_records_the_failure(
    app, auth_headers, worker, announced
):
    worker(WorkerResult("failed", error="claude exited 1: overloaded", duration_ms=40))
    await _configure(app, auth_headers)
    await _note_at_t()
    response = await app.post(f"{BASE}/manager/jobs/overview-note/run", headers=auth_headers)
    assert response.status_code == 202
    await overview_note_job.settled()

    firings = await _firings()
    assert [(f["trigger"], f["outcome"]) for f in firings] == [("button", "failed")]
    assert firings[0]["duration_ms"] == 40
    read = await _overview(app, auth_headers)
    assert read["note"]["id"] == "onote-t"
    assert read["note_last_attempt"]["reason"] == "claude exited 1: overloaded"
    assert read["note_writing"] is False
    assert [n for n, _ in announced] == ["overview_note_started", "overview_note_failed"]
    assert await _notes() == ["onote-t"]


@pytest.mark.asyncio
async def test_refresh_note_while_the_job_is_off_is_refused_disabled(app, auth_headers, worker):
    worker()
    response = await app.post(f"{BASE}/manager/jobs/overview-note/run", headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "disabled"
    assert await _firings() == []


@pytest.mark.asyncio
async def test_refresh_note_while_one_is_being_written_is_refused_already_running(
    app, auth_headers, worker
):
    worker()
    await _configure(app, auth_headers)
    overview_note_job._writing.add(P)
    try:
        assert (await _overview(app, auth_headers))["note_writing"] is True
        response = await app.post(f"{BASE}/manager/jobs/overview-note/run", headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "already_running"
    finally:
        overview_note_job._writing.discard(P)


# ---------------------------------------------------------------------------
# cites
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_cite_that_does_not_resolve_is_answered_back_once_then_dropped(
    app, auth_headers, worker
):
    await _add(Task(id="t-real", project_id=P, title="Real", status="approved"))
    bad = [
        {"type": "task", "id": "t-real", "label": "t-real"},
        {"type": "task", "id": "task-invented", "label": "invented"},
    ]
    fake = worker(("See t-real and invented.", bad), ("See t-real and invented.", bad))
    await _configure(app, auth_headers)
    response = await app.post(f"{BASE}/manager/jobs/overview-note/run", headers=auth_headers)
    assert response.status_code == 202
    await overview_note_job.settled()

    assert len(fake.calls) == 2
    assert "task-invented" in fake.calls[1]["prompt"]
    firing = (await _firings())[0]
    assert firing["outcome"] == "written"
    assert firing["usage"]["input_tokens"] == 22  # both spawns
    assert firing["dropped_cites"]
    note = (await _overview(app, auth_headers))["note"]
    assert note["cites"] == [{"type": "task", "id": "t-real", "label": "t-real"}]


@pytest.mark.asyncio
async def test_a_retry_that_fixes_the_cites_is_kept_whole(app, auth_headers, worker):
    await _add(Task(id="t-real", project_id=P, title="Real", status="approved"))
    fake = worker(
        ("See x.", [{"type": "build", "id": "build-nope", "label": "x"}]),
        ("See t-real.", [{"type": "task", "id": "t-real", "label": "t-real"}]),
    )
    await _configure(app, auth_headers)
    await app.post(f"{BASE}/manager/jobs/overview-note/run", headers=auth_headers)
    await overview_note_job.settled()
    assert len(fake.calls) == 2
    note = (await _overview(app, auth_headers))["note"]
    assert note["text"] == "See t-real."
    assert note["cites"] == [{"type": "task", "id": "t-real", "label": "t-real"}]
    assert "dropped_cites" not in (await _firings())[0]


@pytest.mark.asyncio
async def test_cites_resolve_only_within_the_project(app, auth_headers):
    await _add(Task(id="t-mine", project_id=P, title="Mine", status="approved", readable_id="X-1"))
    async with async_session_factory() as db:
        kept, problems = await overview_note_job.resolve_cites(
            db,
            P,
            [
                overview_note_job.NoteCite(type="task", id="X-1", label="X-1"),
                overview_note_job.NoteCite(type="question", id="q-nope", label="q"),
                overview_note_job.NoteCite(type="vault", id="src-1", label="v"),
            ],
        )
    assert kept == [{"type": "task", "id": "t-mine", "label": "X-1"}]
    assert len(problems) == 2


def test_the_job_is_registered_with_its_button():
    spec = manager.job_spec("overview-note")
    assert spec is not None and spec.firing_choice is not None
    assert spec.firing_choice.button == "Refresh note"
    assert "overview-note" in manager.HAS_BUTTON
