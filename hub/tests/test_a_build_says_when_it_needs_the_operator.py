"""`profiles-threads-and-builds-everywhere` (FR-3, FR-4; design D2, D3): a build says when it needs
the operator, through one definition both `GET /project/builds` and the build read report, and the
operator can dismiss a build that is not running until what it needs changes.

Rows are written by hand: builds of several states with the stalls and questions the Hub records.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Build, Question, SpecDocument, Stall, Task

P = "proj-test"
BUILDS = f"/api/v1/projects/{P}/project/builds"
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _build(key: str, state: str, hours_ago: int, **fields) -> Build:
    return Build(
        id=f"build-{key}",
        project_id=P,
        document_id=f"spdoc-{key}",
        state=state,
        driver="flow",
        level="reviewed",
        created_at=NOW - timedelta(hours=hours_ago),
        stopped_at=None if state == "running" else NOW - timedelta(hours=hours_ago - 1),
        **fields,
    )


def _task(key: str, n: int, status: str) -> Task:
    return Task(
        id=f"t-{key}-{n}",
        project_id=P,
        title=f"{key} {n}",
        status=status,
        build_id=f"build-{key}",
        created_at=NOW - timedelta(hours=100 - n),
    )


def _stall(key: str, task_id: str, outcome: str, reason: str) -> Stall:
    return Stall(
        id=f"stall-{key}",
        project_id=P,
        key=f"stuck_task:{task_id}:{key}",
        cause="stuck_task",
        reason=reason,
        task_id=task_id,
        outcome=outcome,
        outcome_detail="the mender could not land it" if outcome == "gave_up" else "",
    )


#: Each build of the set, and what it needs (None for nothing).
EXPECTED = {
    "build-running": "stalled",
    "build-stopped": "stopped",
    "build-finished": None,
    "build-reopened": "stalled",
    "build-gave-up": "gave-up",
    "build-question": "question",
    "build-stopped-done": None,
}


async def _seed() -> None:
    async with async_session_factory() as db:
        for key in (k.removeprefix("build-") for k in EXPECTED):
            db.add(
                SpecDocument(
                    id=f"spdoc-{key}",
                    project_id=P,
                    path=f"spec/changes/{key}/spec.json",
                    title=f"The {key} build",
                    kind="change-spec",
                    phase="approved",
                )
            )
        db.add_all(
            [
                _build("running", "running", 1),
                _build("stopped", "stopped", 2, stop_reason="stopped by the operator"),
                _build("finished", "finished", 3),
                _build("reopened", "finished", 4),
                _build("gave-up", "finished", 5),
                _build("question", "finished", 6),
                _build("stopped-done", "stopped", 7, stop_reason="stopped by the operator"),
            ]
        )
        await db.flush()
        db.add_all(
            [
                _task("running", 1, "in_progress"),
                _task("stopped", 1, "approved"),
                # Stopped before all its tasks were approved, with no stall or question anywhere.
                _task("stopped", 2, "assigned"),
                _task("finished", 1, "approved"),
                _task("finished", 2, "rejected"),
                # A task of the finished build was reopened and stalled.
                _task("reopened", 1, "in_progress"),
                _task("gave-up", 1, "revision_needed"),
                _task("question", 1, "assigned"),
                _task("stopped-done", 1, "approved"),
            ]
        )
        await db.flush()
        db.add_all(
            [
                _stall("running", "t-running-1", "open", "QA could not start"),
                _stall("reopened", "t-reopened-1", "open", "the reopened task is stuck"),
                _stall("gave-up", "t-gave-up-1", "gave_up", "the merge conflicts"),
                # The stall of a task since approved needs nothing.
                _stall("finished", "t-finished-1", "open", "long since approved"),
                Question(
                    id="q-question",
                    project_id=P,
                    from_agent="dev",
                    question="Which way?",
                    blocking=True,
                    blocked_task_id="t-question-1",
                ),
            ]
        )
        await db.commit()


async def _rows(app, auth_headers):
    listed = await app.get(BUILDS, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return {row["id"]: row for row in listed.json()["builds"]}


def _in_sidebar(row) -> bool:
    """D2's rule for the sidebar, as the client applies it to `GET /builds`."""
    return row["state"] == "running" or (
        row["needs_operator"] is not None and not row["attention_dismissed"]
    )


@pytest.mark.asyncio
async def test_a_stopped_build_needs_the_operator(app, auth_headers):
    """stopped-needs-operator: stopped before all its tasks were approved, no stall, no question."""
    await _seed()
    read = await app.get(f"{BUILDS}/build-stopped/tasks", headers=auth_headers)
    assert read.status_code == 200, read.text
    build = read.json()["build"]
    assert build["needs_operator"] == {"kind": "stopped", "text": "stopped by the operator"}
    assert build["attention_dismissed"] is False
    # No task of it needs anything: the need is the build's own.
    assert [t["needs_operator"] for t in read.json()["tasks"]] == [None, None]

    # Stopped with every task approved, it needs nothing.
    done = (await app.get(f"{BUILDS}/build-stopped-done/tasks", headers=auth_headers)).json()
    assert done["build"]["needs_operator"] is None


@pytest.mark.asyncio
async def test_the_build_list_and_each_build_read_agree_on_what_needs_the_operator(
    app, auth_headers
):
    """needs-parity: a build that is not running is in the sidebar exactly when its read says it
    needs the operator, for every build in the set."""
    await _seed()
    rows = await _rows(app, auth_headers)
    assert set(rows) == set(EXPECTED)
    for build_id, kind in EXPECTED.items():
        read = (await app.get(f"{BUILDS}/{build_id}/tasks", headers=auth_headers)).json()
        need = read["build"]["needs_operator"]
        assert (need and need["kind"]) == kind, build_id
        assert rows[build_id]["needs_operator"] == need, build_id
        if rows[build_id]["state"] != "running":
            assert _in_sidebar(rows[build_id]) == (need is not None), build_id
    assert {b for b, row in rows.items() if _in_sidebar(row)} == {
        "build-running",
        "build-stopped",
        "build-reopened",
        "build-gave-up",
        "build-question",
    }


@pytest.mark.asyncio
async def test_a_dismissed_build_stays_gone_until_what_it_needs_changes(app, auth_headers):
    """build-dismissed (the Hub's half): a running build cannot be dismissed; a dismissed stopped
    build stays gone on every later read; restarted it is listed because it runs; stopped again,
    it is back."""
    await _seed()

    refused = await app.post(f"{BUILDS}/build-running/attention/dismiss", headers=auth_headers)
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "build_running"
    nothing = await app.post(f"{BUILDS}/build-finished/attention/dismiss", headers=auth_headers)
    assert nothing.status_code == 409
    assert nothing.json()["detail"]["code"] == "nothing_needed"

    dismissed = await app.post(f"{BUILDS}/build-stopped/attention/dismiss", headers=auth_headers)
    assert dismissed.status_code == 200, dismissed.text
    assert dismissed.json()["id"] == "build-stopped"
    assert dismissed.json()["attention_dismissed"] is True

    # A reload: a fresh read of the list, and of the build.
    rows = await _rows(app, auth_headers)
    assert rows["build-stopped"]["attention_dismissed"] is True
    assert not _in_sidebar(rows["build-stopped"])
    # It still needs the operator; the build view says so.
    read = (await app.get(f"{BUILDS}/build-stopped/tasks", headers=auth_headers)).json()
    assert read["build"]["needs_operator"]["kind"] == "stopped"
    assert read["build"]["attention_dismissed"] is True
    async with async_session_factory() as db:
        stored = (await db.get(Build, "build-stopped")).attention_dismissed
    assert stored["fingerprint"] and stored["at"]

    # Restarted, and one of its tasks stalls: listed again, because it is running.
    async with async_session_factory() as db:
        build = await db.get(Build, "build-stopped")
        build.state, build.stopped_at, build.stop_reason = "running", None, None
        db.add(_stall("restarted", "t-stopped-2", "open", "dev could not start"))
        await db.commit()
    rows = await _rows(app, auth_headers)
    assert rows["build-stopped"]["needs_operator"]["kind"] == "stalled"
    assert rows["build-stopped"]["attention_dismissed"] is False
    assert _in_sidebar(rows["build-stopped"])

    # Stopped again: its needs are not the ones dismissed, so it is back.
    async with async_session_factory() as db:
        build = await db.get(Build, "build-stopped")
        build.state, build.stopped_at = "stopped", NOW
        await db.commit()
    rows = await _rows(app, auth_headers)
    assert rows["build-stopped"]["attention_dismissed"] is False
    assert _in_sidebar(rows["build-stopped"])


@pytest.mark.asyncio
async def test_a_new_stall_brings_a_dismissed_build_back(app, auth_headers):
    await _seed()
    answer = await app.post(f"{BUILDS}/build-gave-up/attention/dismiss", headers=auth_headers)
    assert answer.status_code == 200, answer.text
    assert not _in_sidebar((await _rows(app, auth_headers))["build-gave-up"])
    async with async_session_factory() as db:
        db.add(_stall("again", "t-gave-up-1", "open", "stuck again"))
        await db.commit()
    row = (await _rows(app, auth_headers))["build-gave-up"]
    assert row["needs_operator"]["kind"] == "stalled"
    assert _in_sidebar(row)


@pytest.mark.asyncio
async def test_another_projects_build_cannot_be_dismissed(app, auth_headers):
    answer = await app.post(f"{BUILDS}/build-nope/attention/dismiss", headers=auth_headers)
    assert answer.status_code == 404
