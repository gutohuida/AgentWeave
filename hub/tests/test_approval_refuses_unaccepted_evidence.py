"""Approval is refused while evidence that would merge sits unaccepted (F122).

The defect this file is about: an agent commits its work, records evidence naming that commit, and
nobody accepts it — because no agent is granted `can_accept_evidence` by default and the operator was
never told there was anything to do. Approval then *succeeds*, records `no accepted evidence names a
commit, so there is nothing to merge`, and the task sits terminal at `approved` with its commit on a
branch nothing merges. The account is true about the merge and false about the world.

Two halves, and the second is the one that would be missed. Refusing approval tells the reader to
accept the evidence; accepting it afterwards has to actually merge the work, or the system asked for
something and then ignored it being done — approving again cannot merge it, because restating a
status is deliberately a no-op.

**The scoping constraint is the whole design.** The refusal fires only where evidence *exists* and is
unaccepted. A task with no evidence at all, evidence naming no commit, evidence that was rejected,
and any project where integration could not have been attempted anyway all stay exactly as
approvable as they were. Approval must never be blocked by the *absence* of an integration, only by
one that would fail.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import EvidenceFootprint, RequirementEvidence, TaskRequirementLink

from .test_task_integration import (  # noqa: F401  (`builder` is a fixture, used by name)
    AGENT_BRANCH,
    AGENT_EVIDENCE,
    BASE,
    approve,
    builder,
    commit_on_branch,
    commits_on,
    git,
    integrations,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)

# ---------------------------------------------------------------------------
# The fixture. `test_task_integration.py` already drives a real repository through the real routes;
# everything below reuses it rather than assembling rows by hand, because a fixture that skips the
# footprint proves nothing — the whole predicate is about a `git` footprint carrying a commit.
# ---------------------------------------------------------------------------


async def record_evidence(app, run_headers, *, summary="ran the tests"):
    """Record evidence as the agent and leave it where an agent's evidence lands: `awaiting`.

    The sibling helper in `test_task_integration.py` accepts it in the same breath, which is exactly
    the step the live flow cannot take.
    """
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": summary}, headers=run_headers
    )
    assert recorded.status_code == 201, recorded.text
    return recorded.json()["id"]


async def accept(app, auth_headers, evidence_id):
    accepted = await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text
    return accepted


async def reject(app, auth_headers, evidence_id):
    rejected = await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "rejected", "reason": "not what the wording says"},
        headers=auth_headers,
    )
    assert rejected.status_code == 200, rejected.text
    return rejected


async def assert_awaiting_git_evidence(evidence_id, task_id, commit_sha, branch=AGENT_BRANCH):
    """Read the rows back and assert they are what the fixture claims.

    B-IMPL found two fixture defects this way, and each would have made an assertion pass without
    the behaviour existing. Every test here rests on four facts: the evidence is awaiting, its
    footprint is `git`, that footprint names the commit the work is on, and the task actually links
    to the requirement the evidence was recorded against.
    """
    async with async_session_factory() as session:
        evidence = await session.get(RequirementEvidence, evidence_id)
        assert evidence is not None, evidence_id
        assert evidence.review_state == "awaiting", evidence.review_state
        footprint = (
            await session.execute(
                select(EvidenceFootprint).where(EvidenceFootprint.evidence_id == evidence_id)
            )
        ).scalar_one()
        assert footprint.kind == "git", footprint.kind
        assert footprint.commit_sha == commit_sha, (footprint.commit_sha, commit_sha)
        assert footprint.branch == branch, footprint.branch
        links = (
            (
                await session.execute(
                    select(TaskRequirementLink).where(TaskRequirementLink.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )
        assert [link.requirement_id for link in links] == [evidence.requirement_id]


async def make_paths_footprint(evidence_id):
    """Turn a recorded footprint into the `paths` shape.

    Written directly rather than driven, and the reason is that the two states cannot coexist in one
    project: a `paths` footprint is what a *non-repository* workspace produces, and every test here
    needs a repository with a configured main branch for the refusal's preconditions to be met at
    all. The row is the thing the predicate reads, so the row is what the fixture sets.
    """
    async with async_session_factory() as session:
        footprint = (
            await session.execute(
                select(EvidenceFootprint).where(EvidenceFootprint.evidence_id == evidence_id)
            )
        ).scalar_one()
        footprint.kind = "paths"
        footprint.commit_sha = None
        footprint.branch = None
        await session.commit()


async def a_task_with_awaiting_evidence(app, auth_headers, builder, tmp_path, title="Build it"):
    """The shape the whole change is about: a real commit, evidence naming it, nobody has judged it.

    Returns `(task_id, evidence_id, commit_sha)`. The checkout is left on `main`, which is where the
    integration path expects to find it.
    """
    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    evidence = await record_evidence(app, builder)
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers, title=title)
    await assert_awaiting_git_evidence(evidence, task, work)
    assert work not in commits_on(tmp_path, "main")
    return task, evidence, work


# ---------------------------------------------------------------------------
# Group 1 — F122 as it behaves today. These pass against unmodified code; group 5 inverts them.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_awaiting_evidence_approves_and_merges_nothing(app, auth_headers, builder, tmp_path):
    """F122's reproduction. Approval succeeds and records the skip that reads like an absence."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task, _evidence, work = await a_task_with_awaiting_evidence(app, auth_headers, builder, tmp_path)

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == ["skipped"]
    from hub import task_integration

    assert recorded[0]["reason"] == task_integration.NOTHING_TO_MERGE
    assert work not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_accepting_afterwards_merges_nothing(app, auth_headers, builder, tmp_path):
    """The second half's reproduction — the sentence "accept the evidence", measured being ignored.

    The task is already `approved` and unmerged. The operator does the one thing that could make the
    evidence count, and the commit stays exactly where it was.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task, evidence, work = await a_task_with_awaiting_evidence(app, auth_headers, builder, tmp_path)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    before = await integrations(app, auth_headers, task)
    await accept(app, auth_headers, evidence)

    after = await integrations(app, auth_headers, task)
    assert len(after) == len(before)
    assert work not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_evidence_naming_no_commit_does_not_block_approval(
    app, auth_headers, builder, tmp_path
):
    """First wedge the scoping constraint exists to prevent, and it must keep passing afterwards.

    Accepting a `paths` footprint could not change what integration merges, so refusing on it would
    state a remedy that does not work.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    evidence = await record_evidence(app, builder)
    git(tmp_path, "checkout", "-q", "main")
    await make_paths_footprint(evidence)

    task = await linked_task(app, auth_headers)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_a_task_with_no_evidence_at_all_approves(app, auth_headers, builder, tmp_path):
    """Second wedge, and the more important one: research, documentation and decision work produces
    no commit and must not be blocked by machinery about merging."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task = await linked_task(app, auth_headers)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
