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

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    EvidenceFootprint,
    RequirementEvidence,
    Run,
    TaskRequirementLink,
)
from hub.spec_payload import SCHEMA_VERSION

from .test_task_integration import (
    AGENT_BRANCH,
    AGENT_EVIDENCE,
    ALPHA,
    BASE,
    PATH,
    SUBMIT,
    TASKS,
    approve,
    commit_on_branch,
    commits_on,
    git,
    integrations,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)

BETA = {"key": "beta", "statement": "It says what is overdue", "modal": "MUST"}


@pytest.fixture
async def builder():
    """The agent whose work is waiting to be judged.

    Defined here rather than imported: ten sibling files each declare their own, and a fixture
    imported by name shadows itself in every signature that takes it.
    """
    async with async_session_factory() as session:
        session.add(Agent(id="ag-unacc", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-unacc",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_unacc-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_unacc-secret"}


# ---------------------------------------------------------------------------
# The fixture. `test_task_integration.py` already drives a real repository through the real routes;
# everything below reuses it rather than assembling rows by hand, because a fixture that skips the
# footprint proves nothing — the whole predicate is about a `git` footprint carrying a commit.
# ---------------------------------------------------------------------------


async def record_evidence(app, run_headers, *, task_id=None, summary="ran the tests"):
    """Record evidence as the agent and leave it where an agent's evidence lands: `awaiting`.

    The sibling helper in `test_task_integration.py` accepts it in the same breath, which is exactly
    the step the live flow cannot take.
    """
    return await record_evidence_for(app, run_headers, "FR-1", task_id=task_id, summary=summary)


async def record_evidence_for(
    app, run_headers, identifier, *, task_id=None, summary="ran the tests"
):
    """One piece of evidence, named against *identifier*, recorded by the agent.

    `task_id` is passed explicitly because the run in these tests is not bound to a task, and an
    unbound run records evidence with a null `task_id` — which is the product's real behaviour and
    exactly what the refusal has to tolerate, but not the ordinary shape an agent working a task
    produces. Both are exercised: the fixture below names the task, and one test deliberately does
    not.
    """
    body = {"identifier": identifier, "summary": summary}
    if task_id is not None:
        body["task_id"] = task_id
    recorded = await app.post(AGENT_EVIDENCE, json=body, headers=run_headers)
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
        assert evidence.task_id == task_id, evidence.task_id


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
    task = await linked_task(app, auth_headers, title=title)
    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    evidence = await record_evidence(app, builder, task_id=task)
    git(tmp_path, "checkout", "-q", "main")

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

    task, _evidence, work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )

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


# ---------------------------------------------------------------------------
# Group 2 — `awaiting_targets` on its own terms, before anything reads it.
# ---------------------------------------------------------------------------


async def make_two_requirement_document(app, auth_headers, run_headers):
    """The same document `make_document` creates, declaring FR-1 and FR-2.

    Needed for the one case the shared filter's scope has to be tested against: evidence recorded
    for a requirement this task is *not* linked to must not appear among its targets, accepted or
    awaiting.
    """
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Integration demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Integration demo",
                "requirements": [ALPHA, BETA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def linked_task_for(app, auth_headers, identifiers, title="Build it"):
    created = await app.post(
        TASKS, json={"title": title, "requirement_ids": identifiers}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def targets_of(task_id):
    """`(awaiting, accepted)` for one task, read through the real queries."""
    from hub import task_integration
    from hub.db.models import Task

    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        awaiting = await task_integration.awaiting_targets(session, task)
        accepted = await task_integration.integration_targets(session, task)
        return awaiting, accepted


@pytest.mark.asyncio
async def test_awaiting_targets_returns_the_unjudged_commit(app, auth_headers, builder, tmp_path):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task, evidence, work = await a_task_with_awaiting_evidence(app, auth_headers, builder, tmp_path)

    awaiting, accepted = await targets_of(task)
    assert [target.commit_sha for target in awaiting] == [work]
    assert awaiting[0].branch == AGENT_BRANCH
    assert awaiting[0].evidence_id == evidence
    assert awaiting[0].task_id == task
    assert accepted == []


@pytest.mark.asyncio
async def test_accepted_evidence_is_not_awaiting(app, auth_headers, builder, tmp_path):
    """The two lists partition. Accepting moves a row from one to the other and never doubles it."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task, evidence, work = await a_task_with_awaiting_evidence(app, auth_headers, builder, tmp_path)
    await accept(app, auth_headers, evidence)

    awaiting, accepted = await targets_of(task)
    assert awaiting == []
    assert [target.commit_sha for target in accepted] == [work]


@pytest.mark.asyncio
async def test_rejected_evidence_is_not_awaiting(app, auth_headers, builder, tmp_path):
    """Rejected evidence has been judged, the other way. Refusing on it would wedge the task behind
    a decision its holder cannot reverse."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    await reject(app, auth_headers, evidence)

    awaiting, accepted = await targets_of(task)
    assert awaiting == []
    assert accepted == []


@pytest.mark.asyncio
async def test_a_paths_footprint_is_not_a_target(app, auth_headers, builder, tmp_path):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    evidence = await record_evidence(app, builder)
    git(tmp_path, "checkout", "-q", "main")
    await make_paths_footprint(evidence)

    task = await linked_task(app, auth_headers)
    awaiting, _accepted = await targets_of(task)
    assert awaiting == []


@pytest.mark.asyncio
async def test_a_git_footprint_with_an_empty_commit_is_not_a_target(
    app, auth_headers, builder, tmp_path
):
    """The empty-string guard. It used to sit inside `integration_targets`' reduction loop, where
    `awaiting_targets` would not have inherited it — and the refusal would then fire on a footprint
    the merge silently ignores, with no commit to name and no remedy that clears it."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    evidence = await record_evidence(app, builder)
    git(tmp_path, "checkout", "-q", "main")
    async with async_session_factory() as session:
        footprint = (
            await session.execute(
                select(EvidenceFootprint).where(EvidenceFootprint.evidence_id == evidence)
            )
        ).scalar_one()
        footprint.commit_sha = ""
        await session.commit()

    task = await linked_task(app, auth_headers)
    awaiting, _accepted = await targets_of(task)
    assert awaiting == []


@pytest.mark.asyncio
async def test_evidence_for_an_unlinked_requirement_is_not_a_target(
    app, auth_headers, builder, tmp_path
):
    """The scope is the task's own links. Evidence for a requirement this task does not serve is
    not part of what its approval would merge, so it is not part of what its approval waits for."""
    make_repo(tmp_path)
    await make_two_requirement_document(app, auth_headers, builder)
    await set_main_branch("main")

    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    await record_evidence_for(app, builder, "FR-2")
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task_for(app, auth_headers, ["FR-1"])
    awaiting, _accepted = await targets_of(task)
    assert awaiting == []


@pytest.mark.asyncio
async def test_two_awaiting_commits_on_one_branch_are_both_returned(
    app, auth_headers, builder, tmp_path
):
    """The split, tested where it is observable.

    `integration_targets` keys by branch, so these two rows accepted collapse to one target — which
    is right, because merging the newer carries the older. `awaiting_targets` must return both,
    because a refusal has to name each piece that is waiting rather than only how many there are.
    This is the test that would have caught a shared reduction.
    """
    make_repo(tmp_path)
    await make_two_requirement_document(app, auth_headers, builder)
    await set_main_branch("main")

    first = commit_on_branch(tmp_path, AGENT_BRANCH, "one.py", "1\n")
    evidence_one = await record_evidence_for(app, builder, "FR-1")
    second = commit_on_branch(tmp_path, AGENT_BRANCH, "two.py", "2\n", create=False)
    evidence_two = await record_evidence_for(app, builder, "FR-2")
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task_for(app, auth_headers, ["FR-1", "FR-2"])

    awaiting, _accepted = await targets_of(task)
    assert sorted(target.commit_sha for target in awaiting) == sorted([first, second])
    assert {target.branch for target in awaiting} == {AGENT_BRANCH}
    assert sorted(target.evidence_id for target in awaiting) == sorted([evidence_one, evidence_two])

    await accept(app, auth_headers, evidence_one)
    await accept(app, auth_headers, evidence_two)
    _awaiting, accepted = await targets_of(task)
    assert [target.commit_sha for target in accepted] == [second]
