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
    assert len(firings) == 1
    # An empty first answer leaves every knot out, so it is answered back once (F1042), and the
    # one firing carries both spawns' usage.
    assert len(fake.calls) == 2 and firings[0]["retried_for"]
    assert firings[0]["trigger"] == chapters_job.DOCUMENT_APPROVED
    assert firings[0]["subject"] == {"document": PATH}
    assert firings[0]["usage"] == {"input_tokens": 22, "output_tokens": 14}
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


def test_git_digest_groups_commits_under_each_release_tag(tmp_path):
    """The digest names every release tag (for-each-ref must emit a real unit separator), with the
    commits it shipped, and a tagless tail under the unreleased heading."""
    import subprocess

    def git(*args, when):
        env = {
            "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_DATE": when,
            "GIT_AUTHOR_NAME": "Ana",
            "GIT_AUTHOR_EMAIL": "a@x.io",
            "GIT_COMMITTER_NAME": "Ana",
            "GIT_COMMITTER_EMAIL": "a@x.io",
        }
        import os

        subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            check=True,
            capture_output=True,
            env={**os.environ, **env},
        )

    git("init", "-q", when="2026-01-01T10:00:00Z")
    for n, (day, tag) in enumerate([("01", "v1"), ("05", "v2"), ("09", None)]):
        when = f"2026-01-{day}T10:00:00Z"
        git("commit", "--allow-empty", "-q", "-m", f"change {n}", when=when)
        if tag:
            git("tag", "-a", tag, "-m", tag, when=when)

    digest = chapters_job.git_digest(tmp_path, datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert "v1 (2026-01-01): 1 commits" in digest
    assert "v2 (2026-01-05): 1 commits" in digest
    assert f"{chapters.UNRELEASED}: 1 commits" in digest
    assert "Ana: change 1" in digest


@pytest.mark.asyncio
async def test_a_surface_key_cited_or_a_bad_cite_does_not_discard_the_answer(
    app, auth_headers, worker
):
    await seed(doc(1, 0))
    await _configure(app, auth_headers)
    knots = await _knots()
    worker(("story", [draft("a", knots, cites=[knots[0], "task-nope"])]))
    assert await _fire(chapters_job.REQUESTED) == "written"

    async with async_session_factory() as session:
        state = await chapters.read(session, P)
    assert [c["id"] for c in state["chapters"]] == ["a"]
    assert state["chapters"][0]["cites"] == []
    assert (await _firings())[0]["dropped_cites"] == ["task-nope"]


def test_both_prompts_demand_end_to_end_git_coverage_and_the_check_names_gaps():
    from hub import chapters_job

    for asked_for in (True, False):
        text = chapters_job._PROMPT.format(
            asked=chapters_job._ASKED if asked_for else chapters_job._UNASKED,
            surface="",
            current="",
            versions="",
            git="",
        )
        assert "covered end to end" in text
        assert "never in cites" in text

    shown = {"v1": ["abc1234"], "v2": ["def5678"], "v3": ["0123456"]}
    drafts = [{"cites": ["tag:v1", "commit:def5678"]}]
    assert chapters_job.uncovered_buckets(shown, drafts) == ["v3"]


# ---------------------------------------------------------------------------
# F1042: the first run on a real project, where every knot is new
# ---------------------------------------------------------------------------


def test_the_prompt_never_invites_leaving_a_knot_out():
    """The save requires every knot of the previous version, and on a first version every knot
    (`every-knot-once`); a prompt saying new knots "may be left out" made the model leave 146 out
    of AgentWeave's first run, and the whole answer was refused."""
    for asked_for in (True, False):
        text = chapters_job._PROMPT.format(
            asked=chapters_job._ASKED if asked_for else chapters_job._UNASKED,
            surface="",
            current="",
            versions="",
            git="",
        )
        assert "left out" not in text.split("- A surface key")[0].split("Rules the Hub")[1]
        assert "Leave none out" in text


@pytest.mark.asyncio
async def test_unplaced_knots_are_answered_back_once_and_both_spawns_are_counted(
    app, auth_headers, worker
):
    await seed(doc(1, 0), doc(2, 5))
    await _configure(app, auth_headers)
    knots = await _knots()
    fake = worker(
        ("first try", [draft("a", knots[:1])]),
        ("placed them", [draft("a", knots)]),
    )
    assert await _fire(chapters_job.REQUESTED) == "written"

    assert len(fake.calls) == 2
    retry = fake.calls[1]["prompt"]
    assert retry.startswith(fake.calls[0]["prompt"])
    for key in knots[1:]:
        assert key in retry.split(chapters_job.RETRY_START)[1]
    firing = (await _firings())[0]
    assert firing["retried_for"] == sorted(knots[1:])
    assert firing["usage"]["input_tokens"] == 22 and firing["usage"]["output_tokens"] == 14
    async with async_session_factory() as session:
        state = await chapters.read(session, P)
    assert [c["members"] for c in state["chapters"]] == [sorted(knots)]


@pytest.mark.asyncio
async def test_a_second_refusal_is_not_retried_again(app, auth_headers, worker):
    await seed(doc(1, 0), doc(2, 5))
    await _configure(app, auth_headers)
    knots = await _knots()
    fake = worker(("one", [draft("a", knots[:1])]), ("two", [draft("a", knots[:1])]))
    assert await _fire(chapters_job.REQUESTED) == "failed"
    assert len(fake.calls) == 2
    assert "is in no chapter" in (await _firings())[0]["detail"]


@pytest.mark.asyncio
async def test_a_refusal_for_anything_else_is_not_retried(app, auth_headers, worker):
    await seed(doc(1, 0))
    await _configure(app, auth_headers)
    knots = await _knots()
    fake = worker(("twice", [draft("a", knots), draft("b", knots, title="Again")]))
    assert await _fire(chapters_job.REQUESTED) == "failed"
    assert len(fake.calls) == 1
