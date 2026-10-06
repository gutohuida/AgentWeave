"""A task sent back for revision is briefed with why it came back (F504).

Found by the 2026-10-06 acceptance drive: a reviewer moved a task to `revision_needed` because its
branch no longer merged into main, and the flow's rework brief carried the task's original
description and nothing else. The author re-ran its green tests, completed the same conflicting
commit again, and the next review was refused for the same conflict. The brief now carries the
reviewer's verdict notes, who gave them, and — measured, not remembered — whether the task's own
branch still merges into the main branch.
"""

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskTransition

from .test_briefing_names_its_contract import _brief, _loop, _task
from .test_task_integration import commit_on_branch, git, make_repo, set_main_branch

pytestmark = pytest.mark.asyncio


async def _sent_back(db, task, *, by, notes):
    row = (await db.execute(select(Task).where(Task.id == task.id))).scalar_one()
    row.notes = notes
    db.add(
        TaskTransition(
            id=f"ttr-{task.id}-back",
            project_id=row.project_id,
            task_id=row.id,
            from_status="under_review",
            to_status="revision_needed",
            actor_kind="run",
            actor_agent=by,
        )
    )
    await db.commit()


async def test_the_reviewers_notes_and_name_reach_the_author(app):
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="why", document="doc-why")
        task = await _task(db, loop, "why", status="revision_needed")
        await _sent_back(
            db, task, by="checker", notes="Conflicts with master in tests/test_store.py"
        )

    briefing = await _brief(loop, task, is_review=False)

    assert "Why it came back" in briefing
    assert "checker" in briefing
    assert "Conflicts with master in tests/test_store.py" in briefing


async def test_a_branch_that_no_longer_merges_is_named_with_its_files(app, tmp_path):
    make_repo(tmp_path)
    await set_main_branch("main")
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="conflict", document="doc-conflict")
        task = Task(
            id="task-0dd5c0f11c7a",
            project_id="proj-test",
            title="Make search case-insensitive",
            status="revision_needed",
            loop_id=loop.id,
            assignee="contract-owner",
        )
        db.add(task)
        await db.commit()
        await _sent_back(db, task, by="checker", notes="")

    commit_on_branch(tmp_path, worktrees.task_branch_name(task.id), "shared.py", "theirs\n")
    git(tmp_path, "checkout", "-q", "main")
    commit_on_branch(tmp_path, "main", "shared.py", "ours\n", create=False)

    briefing = await _brief(loop, task, is_review=False)

    assert "no longer merges into main" in briefing
    assert "shared.py" in briefing


async def test_a_task_not_sent_back_gets_no_such_section(app):
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="fresh", document="doc-fresh")
        task = await _task(db, loop, "fresh")

    assert "Why it came back" not in await _brief(loop, task, is_review=False)


def test_a_conflict_refusal_tells_its_reviewer_to_send_the_task_back():
    """The slice-2 drive: two reviewers in a row met the conflict refusal, retried `approved`, and
    ended their turns with the task still `under_review`, so no rework was ever briefed. The
    refusal named what has to happen and never that the reviewer's own move is `revision_needed`."""
    from hub.requirement_gate import GateRefusal

    for named in (True, False):
        refusal = GateRefusal(
            unmergeable=[
                {
                    "paths": ["tasktrack/store.py"],
                    "target_branch": "master",
                    "commit_sha": "c36b2d3d6c5e",
                    "source_branch": "agentweave/task/task-cc8f85f29e9b",
                    "named_by_evidence": named,
                }
            ]
        )
        assert "revision_needed" in refusal.detail(), refusal.detail()
