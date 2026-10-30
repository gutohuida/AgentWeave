"""A checks send-back returns the task's accepted evidence
(`a-checks-send-back-returns-the-task-s-accepted-evidence`, D1; F1081).

When the project's checks send a task back -- a failed check run at completion, or a failing landing
batch -- its own accepted evidence names the commits that failed. Left accepted, they stay what the
next completion's check judges, so no fix could ever be checked: the archive task stalled 9 hours on
f7cf6d3 and the vault-tab task's check judged fd8aa77 again after its fix (chk-2edc3a8bd93b).

Driven through the routes over a real repository and a real configured check, as
`test_checks_run_before_review.py` and `test_evidence_judged_piece_by_piece.py` are.
"""

from __future__ import annotations

import sys

import pytest
from sqlalchemy import select

from hub import landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import EvidenceReview, Project, RequirementEvidence, Task, TaskCheckRun

from . import test_evidence_judged_piece_by_piece as _pieces
from .test_approval_refuses_unaccepted_evidence import accept, record_evidence_for
from .test_evidence_judged_piece_by_piece import a_document, outcome, send_back
from .test_task_integration import (
    AGENT_BRANCH,
    TASKS,
    commit_on_branch,
    drive_to,
    git,
    make_repo,
    set_main_branch,
)

PY = f'"{sys.executable}"'
BAD = "print('due')  # BAD\n"
FIXED = "print('due, fixed')\n"
THREE = ["FR-1", "FR-2", "FR-3"]

#: The builder recording evidence and the reviewer with no `can_accept_evidence` grant.
builder = _pieces.builder
reviewer = _pieces.reviewer


@pytest.fixture(autouse=True)
def _window(monkeypatch):
    """A batch starts only when the test drains the queue."""
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    yield
    landing_queue.cancel_timers()


def _check(tmp_path_factory, needs=None) -> dict:
    """The suite: fails where `feature.py` holds `# BAD` -- and, given *needs*, only in a tree that
    also holds that file, so the work can pass alone and fail merged with what main gained after."""
    outside = tmp_path_factory.mktemp("check")
    script = outside / "suite.py"
    gate = f"if not os.path.exists({needs!r}):\n    sys.exit(0)\n" if needs else ""
    script.write_text(
        "import os, sys\n"
        f"{gate}"
        "if os.path.exists('feature.py') and '# BAD' in open('feature.py').read():\n"
        "    print('FAILED tests/test_feature.py::test_due - the BAD line')\n"
        "    sys.exit(1)\n"
        "print('suite ok')\n",
        encoding="utf-8",
    )
    return {"name": "hub-tests", "command": f'{PY} "{script}"', "timeout_seconds": 120}


async def _configure(checks):
    async with async_session_factory() as session:
        (await session.get(Project, "proj-test")).checks = checks
        await session.commit()


async def _task(app, auth_headers, identifiers) -> str:
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": identifiers}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _record_at(app, builder, tmp_path, task, identifiers, content, *, create):
    """Commit *content* on the builder's branch and record a piece per identifier there."""
    sha = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", content, create=create)
    pieces = {
        identifier: await record_evidence_for(app, builder, identifier, task_id=task)
        for identifier in identifiers
    }
    git(tmp_path, "checkout", "-q", "main")
    return sha, pieces


async def _runs(task):
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(TaskCheckRun)
                    .where(TaskCheckRun.task_id == task)
                    .order_by(TaskCheckRun.started_at)
                )
            ).scalars()
        )


async def _status(task):
    async with async_session_factory() as session:
        return (await session.get(Task, task)).status


async def _reviews(evidence_id):
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(EvidenceReview)
                    .where(EvidenceReview.evidence_id == evidence_id)
                    .order_by(EvidenceReview.sequence)
                )
            ).scalars()
        )


async def _states(pieces):
    async with async_session_factory() as session:
        return {
            identifier: (await session.get(RequirementEvidence, evidence_id)).review_state
            for identifier, evidence_id in pieces.items()
        }


async def _last_note(app, auth_headers, task) -> str:
    """The send-back's note, read through the task history route."""
    response = await app.get(f"{TASKS}/{task}/transitions", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    rows = body if isinstance(body, list) else body.get("transitions", body.get("items", []))
    back = [row for row in rows if row.get("to_status") == "revision_needed"]
    assert back, rows
    return back[-1].get("note") or ""


async def _check_run_and_drain(task):
    """Ask for the task's check run and wait for it. Not asserted started: where the targets are a
    commit already judged, no new run starts and the latest run stays the one on that commit.

    Drained first: the completion schedules a request of its own before its transaction commits,
    which can read the task before it is completed and start nothing, and while it is starting it
    refuses this one (`request_run`'s `_starting`; F1084)."""
    await project_checks.drain()
    await project_checks.request_run("proj-test", task)
    await project_checks.drain()


# --- the two shapes a checks send-back comes in -------------------------------------------------


async def _sent_back_by_a_check_run(app, auth_headers, builder, tmp_path, tmp_path_factory):
    """FR-1 and FR-2 accepted at failing commit A, FR-3 awaiting there; completed; the check run
    fails on A and `return_failed_work` sends the task back. Returns `(task, A, pieces)`."""
    make_repo(tmp_path)
    await set_main_branch("main")
    await a_document(app, auth_headers, builder, 3)
    task = await _task(app, auth_headers, THREE)
    sha_a, pieces = await _record_at(app, builder, tmp_path, task, THREE, BAD, create=True)
    for identifier in ("FR-1", "FR-2"):
        await accept(app, auth_headers, pieces[identifier])
    walked = await drive_to(app, auth_headers, task, "assigned", "in_progress", "completed")
    assert walked.status_code == 200, walked.text
    await _configure([_check(tmp_path_factory)])

    await _check_run_and_drain(task)

    [run] = await _runs(task)
    assert (run.state, list(run.target_shas)) == ("failed", [sha_a])
    assert await _status(task) == "revision_needed"
    return task, sha_a, pieces


async def _sent_back_by_a_landing(app, auth_headers, builder, tmp_path, tmp_path_factory):
    """F1081's shape: approved with every piece accepted at commit A, then a landing batch that
    fails on A sends the task back. Returns `(task, A, pieces)`."""
    make_repo(tmp_path)
    await set_main_branch("main")
    await a_document(app, auth_headers, builder, 3)
    task = await _task(app, auth_headers, THREE)
    sha_a, pieces = await _record_at(app, builder, tmp_path, task, THREE, BAD, create=True)
    await _configure([_check(tmp_path_factory, needs="moved.py")])
    walked = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review", "approved"
    )
    assert walked.status_code == 200, walked.text
    assert set((await _states(pieces)).values()) == {"accepted"}

    # The completion's run may have started, and may pass; it must end before main moves. Main then
    # gains what the batch's check fails on A with, as the surface ceiling failed on fd8aa77. A new
    # tree, so that the batch runs its check: a pass of the tree it would merge is reused, and it
    # lands (`project_checks.passes_on_tree`), so a check changed behind an unchanged tree tests
    # nothing but whether the completion's run got to start.
    await project_checks.drain()
    (tmp_path / "moved.py").write_text("x = 1\n", encoding="utf-8")
    git(tmp_path, "add", "moved.py")
    git(tmp_path, "commit", "-q", "-m", "main moves under the approval")
    await landing_queue.drain()
    # The batch's failure is confirmed by a second run on A, which can still be executing when the
    # task is sent back; a completion requested meanwhile starts no run of its own
    # (`project_checks.request_run` refuses while one executes). Waited for, as the author's next
    # turn would be.
    await project_checks.drain()

    assert await _status(task) == "revision_needed"
    assert sha_a not in git(tmp_path, "rev-list", "main").stdout.split()
    assert "failed" in {run.state for run in await _runs(task)}, "the batch's check ran and failed"
    return task, sha_a, pieces


async def _fixed_and_completed(app, auth_headers, builder, tmp_path, task):
    """The author's fix B on the same branch, every requirement recorded again at B, completed and
    checked. Returns B."""
    sha_b, _ = await _record_at(app, builder, tmp_path, task, THREE, FIXED, create=False)
    walked = await drive_to(app, auth_headers, task, "in_progress", "completed")
    assert walked.status_code == 200, walked.text
    await _check_run_and_drain(task)
    return sha_b


# --- FR-1 -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_run_holds_accepted(app, auth_headers, builder, tmp_path, tmp_path_factory):
    task, _sha_a, pieces = await _sent_back_by_a_check_run(
        app, auth_headers, builder, tmp_path, tmp_path_factory
    )

    assert await _states(pieces) == {"FR-1": "held", "FR-2": "held", "FR-3": "held"}
    [run] = await _runs(task)
    for identifier in THREE:
        latest = (await _reviews(pieces[identifier]))[-1]
        assert latest.decision == "held", identifier
        assert run.id in latest.reason and "BAD" in latest.reason, latest.reason


@pytest.mark.asyncio
async def test_landing_holds_accepted(app, auth_headers, builder, tmp_path, tmp_path_factory):
    task, _sha_a, pieces = await _sent_back_by_a_landing(
        app, auth_headers, builder, tmp_path, tmp_path_factory
    )

    assert await _states(pieces) == {"FR-1": "held", "FR-2": "held", "FR-3": "held"}
    for identifier in THREE:
        latest = (await _reviews(pieces[identifier]))[-1]
        assert latest.decision == "held", identifier
        assert "Landing batch" in latest.reason, latest.reason


# --- FR-2 -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_others_untouched(app, auth_headers, builder, tmp_path, tmp_path_factory):
    """T2's accepted FR-1 evidence, on main, and T1's own accepted FR-2 piece whose commit is
    already on main, both stay accepted; T1's piece at failing commit A is held."""
    make_repo(tmp_path)
    await set_main_branch("main")
    await a_document(app, auth_headers, builder, 2)
    t2 = await _task(app, auth_headers, ["FR-1"])
    t1 = await _task(app, auth_headers, ["FR-1", "FR-2"])
    # Already landed: one commit on main, which T2's FR-1 and T1's FR-2 evidence both name.
    landed = commit_on_branch(tmp_path, "agentweave/landed", "landed.py", "x = 1\n")
    theirs = await record_evidence_for(app, builder, "FR-1", task_id=t2)
    t1_landed = await record_evidence_for(app, builder, "FR-2", task_id=t1)
    git(tmp_path, "checkout", "-q", "main")
    git(tmp_path, "merge", "-q", "--ff-only", "agentweave/landed")
    assert landed in git(tmp_path, "rev-list", "main").stdout.split()
    await accept(app, auth_headers, theirs)
    await accept(app, auth_headers, t1_landed)
    async with async_session_factory() as session:
        (await session.get(Task, t2)).status = "approved"
        await session.commit()
    # T1's own work at A, which fails.
    _sha_a, mine = await _record_at(app, builder, tmp_path, t1, ["FR-1"], BAD, create=True)
    await accept(app, auth_headers, mine["FR-1"])
    walked = await drive_to(app, auth_headers, t1, "assigned", "in_progress", "completed")
    assert walked.status_code == 200, walked.text
    await _configure([_check(tmp_path_factory)])
    reviews_before = len(await _reviews(theirs))

    await _check_run_and_drain(t1)

    assert await _status(t1) == "revision_needed"
    assert (await _states(mine))["FR-1"] == "held"
    assert await _states({"theirs": theirs, "landed": t1_landed}) == {
        "theirs": "accepted",
        "landed": "accepted",
    }
    assert len(await _reviews(theirs)) == reviews_before, "no new review on another task's piece"


# --- FR-3 -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fix_is_checked_after_check_run(
    app, auth_headers, builder, tmp_path, tmp_path_factory
):
    task, sha_a, _ = await _sent_back_by_a_check_run(
        app, auth_headers, builder, tmp_path, tmp_path_factory
    )

    sha_b = await _fixed_and_completed(app, auth_headers, builder, tmp_path, task)

    latest = (await _runs(task))[-1]
    assert list(latest.target_shas) == [sha_b], (latest.target_shas, sha_a, sha_b)
    assert latest.state == "passed"
    reviewing = await app.patch(
        f"{TASKS}/{task}", json={"status": "under_review", "assignee": None}, headers=auth_headers
    )
    assert reviewing.status_code == 200, reviewing.text
    assert await _status(task) == "under_review"


@pytest.mark.asyncio
async def test_fix_is_checked_after_landing(app, auth_headers, builder, tmp_path, tmp_path_factory):
    task, sha_a, _ = await _sent_back_by_a_landing(
        app, auth_headers, builder, tmp_path, tmp_path_factory
    )

    sha_b = await _fixed_and_completed(app, auth_headers, builder, tmp_path, task)

    latest = (await _runs(task))[-1]
    assert list(latest.target_shas) == [sha_b], (latest.target_shas, sha_a, sha_b)
    assert latest.state == "passed"
    reviewing = await app.patch(
        f"{TASKS}/{task}", json={"status": "under_review", "assignee": None}, headers=auth_headers
    )
    assert reviewing.status_code == 200, reviewing.text
    assert await _status(task) == "under_review"


# --- FR-4 -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_note_names_returned_pieces(app, auth_headers, builder, tmp_path, tmp_path_factory):
    task, sha_a, _ = await _sent_back_by_a_check_run(
        app, auth_headers, builder, tmp_path, tmp_path_factory
    )

    note = await _last_note(app, auth_headers, task)

    returned, _, rest = note.partition("Evidence:")
    assert "Accepted evidence returned: FR-1, FR-2" in returned, note
    assert sha_a[:7] in returned, note
    assert "FR-3" not in returned, note
    assert "FR-3 held" in rest, note


# --- FR-5 -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reviewer_unchanged(app, auth_headers, builder, reviewer, tmp_path):
    make_repo(tmp_path)
    await set_main_branch("main")
    await a_document(app, auth_headers, builder, 2)
    task = await _task(app, auth_headers, ["FR-1", "FR-2"])
    _sha, pieces = await _record_at(
        app, builder, tmp_path, task, ["FR-1", "FR-2"], FIXED, create=True
    )
    await accept(app, auth_headers, pieces["FR-1"])
    walked = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review"
    )
    assert walked.status_code == 200, walked.text

    sent = await send_back(
        app, reviewer, task, failing=[{"piece": "FR-2", "reason": "it does not do thing 2"}]
    )

    assert sent.status_code == 200, sent.text
    assert await _states(pieces) == {"FR-1": "accepted", "FR-2": "rejected"}
    assert (await outcome(pieces["FR-1"]))[1] == "accepted"
