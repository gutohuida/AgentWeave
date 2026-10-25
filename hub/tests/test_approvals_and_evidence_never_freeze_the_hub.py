"""Approval, evidence, run-end restamp, review staffing, the mender brief and drift run their git
off the event loop, with the same records and git state as before.

`turn-starts-approvals-and-evidence-never-freeze-the-hub`: FR-2 (approval-no-stall), FR-3
(evidence-no-stall) and FR-8 (same-outcomes). Measured on the operator's Hub before this change:
releasing a checkout 4.2 s average, the merge up to 2.1 s, evidence 332 ms, the run-end restamp
345 ms, review staffing up to 2.9 s and the mender's `git status` up to 2.9 s, all on the loop.

`slow_git` adds 250 ms to every git process, so any one call left on the loop fails the 100 ms
bound; the outcome assertions are the ones the existing suites make for the same paths.
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import select

from hub import requirement_evidence, review_turn, stalls, worktrees
from hub.api.v1 import agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import EvidenceFootprint, Stall, Task

from ._loop_lag import STALL_LIMIT, LagProbe, slow_git
from .test_task_integration import (  # noqa: F401 -- `builder` is a fixture
    AGENT_BRANCH,
    BASE,
    TASKS,
    accept_evidence,
    builder,
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

_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree
_REAL_ENSURE_REVIEW_CHECKOUT = worktrees.ensure_review_checkout


def _assert_off_the_loop(log, probe) -> None:
    assert log.calls, "nothing ran git, so this measured nothing"
    assert not log.on_loop, [call.argv[:4] for call in log.on_loop]
    assert probe.worst < STALL_LIMIT, f"the loop stalled {probe.worst * 1000:.0f} ms"


async def _completed_task_with_accepted_work(app, auth_headers, builder, tmp_path):  # noqa: F811
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")
    task = await linked_task(app, auth_headers)
    moved = await drive_to(app, auth_headers, task, "assigned", "in_progress", "completed")
    assert moved.status_code == 200, moved.text
    return task, work


@pytest.mark.asyncio
async def test_approving_releases_and_merges_without_stalling_the_loop(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, work = await _completed_task_with_accepted_work(app, auth_headers, builder, tmp_path)
    # The task's own checkout, as its turns provisioned it: approval releases it.
    checkout = _REAL_ENSURE_TASK_WORKTREE(tmp_path, task, "main")
    assert checkout.exists()
    moved = await drive_to(app, auth_headers, task, "under_review")
    assert moved.status_code == 200, moved.text

    with slow_git(threading.current_thread()) as log:
        async with LagProbe() as probe:
            approved = await app.patch(
                f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers
            )
    assert approved.status_code == 200, approved.text
    _assert_off_the_loop(log, probe)
    # FR-8: the same outcome the integration suite asserts -- merged, recorded, released.
    assert work in commits_on(tmp_path, "main")
    assert [row["outcome"] for row in await integrations(app, auth_headers, task)] == ["merged"]
    assert not checkout.exists()
    assert git(tmp_path, "rev-parse", "--verify", worktrees.task_branch_name(task)).returncode == 0


@pytest.mark.asyncio
async def test_recording_evidence_and_detecting_drift_never_stall_the_loop(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")

    with slow_git(threading.current_thread()) as log:
        async with LagProbe() as probe:
            recorded = await app.post(
                f"{BASE}/spec/evidence",
                json={"identifier": "FR-1", "locator": "feature.py", "summary": "read it"},
                headers=auth_headers,
            )
    assert recorded.status_code == 201, recorded.text
    _assert_off_the_loop(log, probe)
    footprint = recorded.json()["footprint"]
    assert footprint["commit_sha"] == git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    assert footprint["branch"] == AGENT_BRANCH

    # The file it watches changes on its line of work: drift is a candidate, as before.
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('bye')\n", create=False)
    with slow_git(threading.current_thread()) as log:
        async with LagProbe() as probe:
            detected = await app.post(f"{BASE}/spec/drift/detect", headers=auth_headers)
    assert detected.status_code == 200, detected.text
    _assert_off_the_loop(log, probe)
    assert len(detected.json()["raised"]) == 1


@pytest.mark.asyncio
async def test_a_run_ends_restamp_never_stalls_the_loop(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    git(tmp_path, "checkout", "-q", "-b", AGENT_BRANCH)
    recorded = await app.post(
        "/api/v1/agent-actions/spec/evidence",
        json={"identifier": "FR-1", "locator": "feature.py", "summary": "wrote it"},
        headers=builder,
    )
    assert recorded.status_code == 201, recorded.text
    snapshot = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n", create=False)

    with slow_git(threading.current_thread()) as log:
        async with LagProbe() as probe:
            async with async_session_factory() as session:
                await agent_trigger._restamp_evidence_footprints(
                    session,
                    project_id="proj-test",
                    run_id="run-int",
                    worktree=tmp_path,
                    snapshot_sha=snapshot,
                )
                await session.commit()
    _assert_off_the_loop(log, probe)
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(EvidenceFootprint).where(
                    EvidenceFootprint.evidence_id == recorded.json()["id"]
                )
            )
        ).scalar_one()
    assert row.commit_sha == snapshot
    assert row.branch == AGENT_BRANCH
    assert row.watched_from == ["locator"]
    assert set(row.entries) == {"feature.py"}


@pytest.mark.asyncio
async def test_staffing_a_review_never_stalls_the_loop(
    app, auth_headers, builder, tmp_path, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)
    moved = await drive_to(app, auth_headers, task, "assigned", "in_progress")
    assert moved.status_code == 200, moved.text
    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    recorded = await app.post(
        "/api/v1/agent-actions/spec/evidence",
        json={"identifier": "FR-1", "summary": "ran it", "task_id": task},
        headers=builder,
    )
    assert recorded.status_code == 201, recorded.text
    git(tmp_path, "checkout", "-q", "main")
    moved = await drive_to(app, auth_headers, task, "completed")
    assert moved.status_code == 200, moved.text
    with slow_git(threading.current_thread()) as log:
        async with LagProbe() as probe:
            async with async_session_factory() as session:
                context = await review_turn.prepare_review_turn(
                    session,
                    project_id="proj-test",
                    reviewer="critic",
                    task_id=task,
                    repo_root=tmp_path,
                )
    _assert_off_the_loop(log, probe)
    assert context.commit_sha == work
    assert git(context.workspace, "rev-parse", "HEAD").stdout.strip() == work


@pytest.mark.asyncio
async def test_briefing_the_mender_never_stalls_the_loop(app, auth_headers, tmp_path):
    make_repo(tmp_path)
    (tmp_path / "loose.txt").write_text("x\n", encoding="utf-8")
    async with async_session_factory() as session:
        stall = Stall(
            id="stall-lag",
            project_id="proj-test",
            key="integration_failed:task-x",
            cause="integration_failed",
            reason="the merge failed",
        )
        session.add(stall)
        await session.commit()
    with slow_git(threading.current_thread()) as log:
        async with LagProbe() as probe:
            async with async_session_factory() as session:
                brief = await stalls.brief(session, await session.get(Stall, "stall-lag"))
    _assert_off_the_loop(log, probe)
    assert "?? loose.txt" in brief


@pytest.mark.asyncio
async def test_refreshing_reachability_answers_as_before_from_one_hop(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    """The bound on distinct commits still stops at the same row (MAX_REACHABILITY_CHECKS)."""
    task, work = await _completed_task_with_accepted_work(app, auth_headers, builder, tmp_path)
    git(tmp_path, "merge", "-q", "--no-ff", "-m", "land", work)
    async with async_session_factory() as session:
        with slow_git(threading.current_thread()) as log:
            async with LagProbe() as probe:
                updated = await requirement_evidence.refresh_reachability(
                    session, "proj-test", tmp_path, main_branch="main"
                )
        _assert_off_the_loop(log, probe)
        assert updated == 1
        row = (await session.execute(select(EvidenceFootprint))).scalars().one()
        assert row.reachable_from_main is True
        assert (await session.get(Task, task)) is not None
