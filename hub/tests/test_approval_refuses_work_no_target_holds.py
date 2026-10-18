"""F681: approval refuses while the task's own branch holds work that approving would not merge.

Found on the 2026-10-18 sweep (group B). The builder recorded FR-1 evidence in a turn bound to no
task, at master's tip, then did the task's work on `agentweave/task/<id>` without recording any.
The operator accepted the evidence and Landed: 200, `approved`, and the integration was skipped as
"already in master; there was nothing to merge". The task's own commit never reached main while
FR-1 read verified.

What approval merges is the commit accepted evidence names. Where the task's branch holds commits
that are neither on main nor inside any commit approval would merge, approving records the work as
good and lands none of it, so the gate refuses, names the commits, and says what clears it:
evidence recorded from the task's own checkout. Both doors refuse: the PATCH and Land.
"""

import pytest

from hub import worktrees

from .test_task_integration import (
    TASKS,
    accept_evidence,
    approve,
    builder,  # noqa: F401  (fixture)
    commit_on_branch,
    commits_on,
    drive_to,
    git,
    integrations,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)


async def _task_with_unlanded_work(app, auth_headers, run_headers, root):
    """F681's shape: accepted evidence at main's tip, and the task's commit on its own branch."""
    make_repo(root)
    await make_document(app, auth_headers, run_headers)
    await set_main_branch("main")
    # Recorded while the checkout is on main: the footprint names main's tip, as the sweep's did.
    await accept_evidence(app, auth_headers, run_headers, summary="task-less, at main's tip")
    task = await linked_task(app, auth_headers)
    work = commit_on_branch(root, worktrees.task_branch_name(task), "README2.md", "the change\n")
    git(root, "checkout", "-q", "main")
    assert work not in commits_on(root, "main")
    return task, work


@pytest.mark.asyncio
async def test_approval_refuses_while_the_task_branch_holds_work_nothing_merges(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, work = await _task_with_unlanded_work(app, auth_headers, builder, tmp_path)

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    body = refused.json()["detail"]
    assert body["code"] == "gate_unsatisfied"
    assert [entry["commits"] for entry in body["unlanded"]] == [[work]], body
    assert body["unlanded"][0]["branch"] == worktrees.task_branch_name(task)
    message = body["message"]
    assert work[:12] in message
    assert worktrees.task_branch_name(task) in message
    assert "record" in message and "checkout" in message, message
    # The operator's PATCH is worded for the operator (F731 item 6), not for a reviewer.
    assert "If you are reviewing" not in message, message
    assert await integrations(app, auth_headers, task) == []

    # Land is the operator's other door: the same refusal.
    back = await drive_to(app, auth_headers, task, "revision_needed", "in_progress", "completed")
    assert back.status_code == 200, back.text
    landed = await app.post(f"{TASKS}/{task}/land", headers=auth_headers)
    assert landed.status_code == 409, landed.text
    land_body = landed.json()["detail"]
    assert land_body["unlanded"][0]["commits"] == [work]
    assert work[:12] in land_body["message"]
    assert "If you are reviewing" not in land_body["message"]
    assert (await app.get(f"{TASKS}/{task}", headers=auth_headers)).json()["status"] == "completed"
    assert await integrations(app, auth_headers, task) == []

    # The remedy the refusal names clears it: evidence recorded from the task's checkout.
    git(tmp_path, "checkout", "-q", worktrees.task_branch_name(task))
    await accept_evidence(app, auth_headers, builder, summary="from the task's checkout")
    git(tmp_path, "checkout", "-q", "main")

    approved = await app.post(f"{TASKS}/{task}/land", headers=auth_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert work in commits_on(tmp_path, "main")
    # Both accepted commits are targets: main's tip is skipped as already there, the task's merges.
    outcomes = {
        row["commit_sha"]: row["outcome"] for row in await integrations(app, auth_headers, task)
    }
    assert outcomes[work] == "merged", outcomes


@pytest.mark.asyncio
async def test_a_task_branch_already_merged_does_not_refuse(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    """Commits on main are not unlanded: the refusal is about work approval would leave behind."""
    task, work = await _task_with_unlanded_work(app, auth_headers, builder, tmp_path)
    git(tmp_path, "merge", "-q", "--no-ff", worktrees.task_branch_name(task), "-m", "by hand")
    assert work in commits_on(tmp_path, "main")

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text


@pytest.mark.asyncio
async def test_a_review_with_no_evidence_names_its_remedy(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    """F681's other half: the review dispatch refused 409 "has no recorded evidence" and stopped."""
    from hub import requirement_evidence
    from hub.db.engine import async_session_factory

    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    task = await linked_task(app, auth_headers)
    async with async_session_factory() as session:
        target = await requirement_evidence.commit_for_task_review(session, task)
    assert "has no recorded evidence" in target.refusal
    assert "record_evidence" in target.refusal
    assert "checkout" in target.refusal


def test_a_reviewer_meeting_the_refusal_is_told_to_send_it_back():
    """An agent reviewer's next step is revision_needed, never recording the author's evidence."""
    from hub.requirement_gate import GateRefusal

    refusal = GateRefusal(
        unlanded=[{"branch": "agentweave/task/t", "target_branch": "main", "commits": ["a" * 40]}]
    )
    assert refusal.refuses
    assert "If you are reviewing this task" in refusal.detail()
    assert "revision_needed" in refusal.detail()
    refusal.for_operator = True
    assert "If you are reviewing" not in refusal.detail()
    assert "aaaaaaaaaaaa" in refusal.detail()
