"""Git answers about commit ids are remembered; ref names never are (`git_facts`, D4 of
`turn-starts-approvals-and-evidence-never-freeze-the-hub`).

Measured by the integrator on the 2026-10-25 operator copy: a steady-state `GET /loops` ran about
twenty git processes (ancestry, existence, `merge-tree`, the work-tree check) for 24 ms of SQL,
answering the same questions as the request before. Here a flow holds one task under review with
evidence awaiting its verdict -- the board then asks whether its approval is held -- and a second
identical `GET /loops` must run at most three git processes. The freshness half: a commit on the
main line or the task's branch changes the very next answer, because only commit ids are keys.
"""

from __future__ import annotations

import subprocess
import threading
from typing import List

import pytest
from sqlalchemy import select

from hub import git_facts, requirement_evidence, task_integration, worktrees
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Run, SpecDocument, Task

from .test_task_integration import (  # noqa: F401 -- `builder` is a fixture
    AGENT_BRANCH,
    PATH,
    builder,
    commit_on_branch,
    drive_to,
    git,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)

LOOPS = "/api/v1/projects/proj-test/loops"


class _CountedPopen(subprocess.Popen):
    """Counts git processes without replacing `subprocess.run`, which `git_facts` requires."""

    started: List[List[str]] = []
    lock = threading.Lock()

    def __init__(self, args, *rest, **kwargs):  # noqa: ANN001, ANN002, ANN003
        if isinstance(args, (list, tuple)) and args and "git" in str(args[0]):
            with self.lock:
                _CountedPopen.started.append([str(a) for a in args])
        super().__init__(args, *rest, **kwargs)


@pytest.fixture
def count_git(monkeypatch):
    _CountedPopen.started = []
    monkeypatch.setattr(subprocess, "Popen", _CountedPopen)
    git_facts.forget()
    yield _CountedPopen
    git_facts.forget()


async def _flow_with_a_task_under_review(app, auth_headers, builder, tmp_path):  # noqa: F811
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)
    moved = await drive_to(app, auth_headers, task, "assigned", "in_progress")
    assert moved.status_code == 200, moved.text
    # Two pieces on the task's own branch: one accepted (what approval would merge, so the board
    # asks whether it merges cleanly), and a later one still awaiting its verdict (so it asks).
    branch = worktrees.task_branch_name(task)
    accepted = commit_on_branch(tmp_path, branch, "feature.py", "print('hi')\n")
    first = await app.post(
        "/api/v1/agent-actions/spec/evidence",
        json={"identifier": "FR-1", "summary": "ran it", "task_id": task},
        headers=builder,
    )
    assert first.status_code == 201, first.text
    decided = await app.post(
        f"/api/v1/projects/proj-test/project/spec/evidence/{first.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert decided.status_code == 200, decided.text
    work = commit_on_branch(tmp_path, branch, "more.py", "y = 2\n", create=False)
    second = await app.post(
        "/api/v1/agent-actions/spec/evidence",
        json={"identifier": "FR-1", "summary": "ran it again", "task_id": task},
        headers=builder,
    )
    assert second.status_code == 201, second.text
    assert accepted != work
    git(tmp_path, "checkout", "-q", "main")
    moved = await drive_to(app, auth_headers, task, "completed", "under_review")
    assert moved.status_code == 200, moved.text
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        session.add(
            AIJob(
                id="job-facts",
                project_id="proj-test",
                name="facts",
                agent="builder",
                message="work the queue",
                cron="0 9 * * *",
                session_mode="new",
                enabled=False,
            )
        )
        await session.flush()
        session.add(
            Loop(
                id="loop-facts",
                project_id="proj-test",
                job_id="job-facts",
                purpose="facts",
                spec_document_id=document.id,
            )
        )
        await session.flush()
        # The run that recorded the evidence has ended, so the piece awaits its verdict.
        (await session.get(Run, "run-int")).status = "completed"
        row = await session.get(Task, task)
        row.loop_id = "loop-facts"
        row.assignee = "critic"  # a reviewer named, with no turn running: the board asks git
        await session.commit()
    return task, work


@pytest.mark.asyncio
async def test_a_steady_state_board_runs_at_most_three_git_processes(
    app, auth_headers, builder, tmp_path, count_git  # noqa: F811
):
    await _flow_with_a_task_under_review(app, auth_headers, builder, tmp_path)
    count_git.started = []
    first = await app.get(LOOPS, headers=auth_headers)
    assert first.status_code == 200, first.text
    asked_first = len(count_git.started)
    assert asked_first > 3, "the board asked git nothing, so this fixture measures nothing"

    count_git.started = []
    second = await app.get(LOOPS, headers=auth_headers)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert len(count_git.started) <= 3, count_git.started


@pytest.mark.asyncio
async def test_a_commit_changes_the_next_answer(
    app, auth_headers, builder, tmp_path, count_git  # noqa: F811
):
    """Only commit ids are keys: after the main line or the branch moves, the answer moves."""
    task, work = await _flow_with_a_task_under_review(app, auth_headers, builder, tmp_path)
    assert requirement_evidence.is_reachable_from(tmp_path, work, "main") is False
    assert task_integration.would_conflict(tmp_path, work, "main") == []

    # The main line takes a change to the same file: the work now conflicts, at once.
    commit_on_branch(tmp_path, "main", "feature.py", "print('main')\n", create=False)
    assert task_integration.would_conflict(tmp_path, work, "main") == ["feature.py"]

    # The work lands on the main line: it is reachable, at once.
    git(tmp_path, "checkout", "-q", "-B", "main", work)
    assert requirement_evidence.is_reachable_from(tmp_path, work, "main") is True

    # And the task's branch tip follows its branch, never a remembered name.
    branch = worktrees.task_branch_name(task)
    later = commit_on_branch(tmp_path, branch, "other.py", "x = 1\n", create=False)
    assert task_integration.resolve(tmp_path, branch) == later


@pytest.mark.asyncio
async def test_a_read_request_resolves_a_name_once_and_never_beyond_itself(
    app, auth_headers, builder, tmp_path, count_git  # noqa: F811
):
    """Within one read request a name is resolved once; the next request resolves it again."""
    await _flow_with_a_task_under_review(app, auth_headers, builder, tmp_path)
    await app.get(LOOPS, headers=auth_headers)
    count_git.started = []
    await app.get(LOOPS, headers=auth_headers)
    verifies = [argv for argv in count_git.started if "--verify" in argv and "main" in argv]
    assert len(verifies) <= 1, count_git.started
