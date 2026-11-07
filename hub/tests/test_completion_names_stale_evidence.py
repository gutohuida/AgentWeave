"""F1141: completing a task names each requirement whose evidence would only be found in review.

After a send-back a builder fixed the code and recorded again only the pieces the verdict named.
The rest stayed held at the old commit, the Hub refused approval, and the reviewer sent the task
back again for bookkeeping. The completion's answer now names each such requirement: evidence
only held or rejected, or naming only a commit older than the task branch's tip. It warns; the
completion is never refused for it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import RequirementEvidence

from .test_approval_refuses_unaccepted_evidence import builder, record_evidence_for  # noqa: F401
from .test_evidence_judged_piece_by_piece import a_document
from .test_task_integration import (
    TASKS,
    commit_on_branch,
    drive_to,
    git,
    make_repo,
    set_main_branch,
)

FOUR = ["FR-1", "FR-2", "FR-3", "FR-4"]


async def _state(evidence_id, state):
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(RequirementEvidence).where(RequirementEvidence.id == evidence_id)
            )
        ).scalar_one()
        row.review_state = state
        await session.commit()


@pytest.mark.asyncio
async def test_completion_names_old_commit_held_and_rejected_evidence_and_still_completes(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    make_repo(tmp_path)
    await set_main_branch("main")
    await a_document(app, auth_headers, builder, 4)
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": FOUR}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    task = created.json()["id"]
    branch = worktrees.task_branch_name(task)

    commit_on_branch(tmp_path, branch, "feature.py", "print('due')\n")
    old = {n: await record_evidence_for(app, builder, n, task_id=task) for n in FOUR[:3]}
    tip = commit_on_branch(tmp_path, branch, "feature.py", "print('fixed')\n", create=False)
    fresh = await record_evidence_for(app, builder, "FR-4", task_id=task)
    git(tmp_path, "checkout", "-q", "main")
    await _state(old["FR-2"], "held")
    await _state(old["FR-3"], "rejected")
    assert fresh

    moved = await drive_to(app, auth_headers, task, "assigned", "in_progress", "completed")

    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["status"] == "completed"
    warnings = body["completion_warnings"]
    assert [w.split(" ", 1)[0] for w in warnings] == ["FR-1's", "FR-2", "FR-3"]
    assert "older commit" in warnings[0] and tip[:12] in warnings[0]
    assert "only held evidence" in warnings[1]
    assert "only rejected evidence" in warnings[2]


@pytest.mark.asyncio
async def test_other_moves_carry_no_completion_warnings(app, auth_headers):
    created = await app.post(TASKS, json={"title": "Plain"}, headers=auth_headers)
    moved = await drive_to(app, auth_headers, created.json()["id"], "assigned")
    assert moved.json()["completion_warnings"] == []
