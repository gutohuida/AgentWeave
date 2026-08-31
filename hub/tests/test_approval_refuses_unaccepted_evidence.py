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

from hub import task_integration
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
    drive_to,
    files_on,
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


@pytest.fixture
async def reviewer():
    """A second agent, for the one remedy the refusal names that an agent can take.

    Necessarily a second one: `requirement_evidence.decide` refuses an agent deciding about its own
    work, so the builder cannot discharge its own refusal even if it were granted.
    """
    async with async_session_factory() as session:
        session.add(Agent(id="ag-unacc-rev", project_id="proj-test", name="reviewer"))
        session.add(
            Run(
                id="run-unacc-rev",
                project_id="proj-test",
                agent="reviewer",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_unaccrev-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_unaccrev-secret"}


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
# The scoping constraint. Both of these passed before this change and must still pass after it —
# if either fails, the change is wrong rather than the test. (The two reproductions that used to
# stand here, F122's approval-succeeds and its accept-merges-nothing, are inverted in group 5.)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Group 5 — the behaviour. 1.3 and 1.4 above are inverted here; 1.5's two wedges are unchanged and
# stay where they are, because "still approves" is the same assertion before and after.
# ---------------------------------------------------------------------------


async def approve_without_a_main_branch(app, auth_headers, builder, tmp_path):
    """An approved, unmerged task carrying awaiting evidence — the state the second half repairs.

    Reached the only honest way now that the refusal exists: a project with no configured main
    branch, where the refusal is deliberately silent because accepting the evidence there would
    merge nothing either. The branch is then set directly rather than through the settings route,
    which would fire the *other* retry path (`_integrate_what_was_waiting_for_a_branch`) and prove
    the wrong thing.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)

    task, evidence, work = await a_task_with_awaiting_evidence(app, auth_headers, builder, tmp_path)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["reason"] for row in recorded] == [task_integration.NO_MAIN_BRANCH]

    await set_main_branch("main")
    return task, evidence, work


@pytest.mark.asyncio
async def test_awaiting_evidence_refuses_approval(app, auth_headers, builder, tmp_path):
    """1.3 inverted. The task stays where it was and no attempt is recorded at all — an attempt row
    would be a claim that integration was tried, and it was not."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task, _evidence, work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "gate_unsatisfied"

    fetched = await app.get(f"{TASKS}/{task}", headers=auth_headers)
    assert fetched.json()["status"] == "under_review"
    assert await integrations(app, auth_headers, task) == []
    assert work not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_the_refusal_names_the_requirement_and_both_remedies(
    app, auth_headers, builder, tmp_path
):
    """The sentence is the feature. An agent that reads it can take neither remedy itself, and
    saying so is what stops it retrying the transition instead of asking."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task, _evidence, work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    message = detail["message"]

    assert "FR-1" in message, message
    assert work[:12] in message, message
    assert "accept" in message.lower(), message
    assert "grant" in message.lower(), message

    assert [entry["identifier"] for entry in detail["unaccepted"]] == ["FR-1"]
    assert detail["unaccepted"][0]["commit_sha"] == work
    assert detail["unaccepted"][0]["recorded_by_task"] == task
    assert detail["unaccepted"][0]["recorded_by_another_task"] is False


@pytest.mark.asyncio
async def test_the_refusal_names_the_task_that_recorded_the_evidence(
    app, auth_headers, builder, tmp_path
):
    """A requirement may be served by more than one task, and this task's integration is what would
    merge the other one's commit — so the reader needs a route back to the cause."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    other = await linked_task(app, auth_headers, title="The other one")
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    await record_evidence(app, builder, task_id=other)
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers, title="This one")
    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]

    assert detail["unaccepted"][0]["recorded_by_task"] == other
    assert detail["unaccepted"][0]["recorded_by_another_task"] is True
    assert other in detail["message"], detail["message"]


@pytest.mark.asyncio
async def test_the_refusal_names_both_waiting_commits_on_one_branch(
    app, auth_headers, builder, tmp_path
):
    """The behavioural half of the query split. Requirement: each waiting piece is named, not
    counted — and a shared per-branch reduction would have passed the previous test while naming
    one of these two."""
    make_repo(tmp_path)
    await make_two_requirement_document(app, auth_headers, builder)
    await set_main_branch("main")

    task = await linked_task_for(app, auth_headers, ["FR-1", "FR-2"])
    first = commit_on_branch(tmp_path, AGENT_BRANCH, "one.py", "1\n")
    await record_evidence_for(app, builder, "FR-1", task_id=task)
    second = commit_on_branch(tmp_path, AGENT_BRANCH, "two.py", "2\n", create=False)
    await record_evidence_for(app, builder, "FR-2", task_id=task)
    git(tmp_path, "checkout", "-q", "main")

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    message = refused.json()["detail"]["message"]
    assert first[:12] in message, message
    assert second[:12] in message, message


@pytest.mark.asyncio
async def test_the_refusal_fires_at_sketch_rigor(app, auth_headers, builder, tmp_path):
    """Where a default project lives. Anything conditional on rigor is absent from one, which is how
    this defect survived — so the fixture asserts the rigor rather than assuming it."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    documents = await app.get(f"{BASE}/documents", headers=auth_headers)
    assert documents.status_code == 200, documents.text
    rigors = {row["path"]: row.get("rigor") for row in documents.json()["documents"]}
    assert rigors[PATH] in (None, "sketch"), rigors

    task, _evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text


@pytest.mark.asyncio
async def test_rejected_evidence_approves_and_records_a_skip(app, auth_headers, builder, tmp_path):
    """It has been judged, the other way. Refusing here would wedge the task behind a decision its
    holder cannot reverse."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task, evidence, work = await a_task_with_awaiting_evidence(app, auth_headers, builder, tmp_path)
    await reject(app, auth_headers, evidence)

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == ["skipped"]
    assert recorded[0]["reason"] == task_integration.NOTHING_TO_MERGE
    assert work not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_no_main_branch_does_not_refuse(app, auth_headers, builder, tmp_path):
    """Accepting the evidence would merge nothing in this project, so refusing would block every
    task in it behind a remedy that changes nothing."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)

    task, _evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["reason"] for row in recorded] == [task_integration.NO_MAIN_BRANCH]


@pytest.mark.asyncio
async def test_a_project_that_is_not_a_repository_does_not_refuse(
    app, auth_headers, builder, tmp_path
):
    """ "A project that is not a repository SHALL be no less approvable than before this capability
    existed." The main branch is named, and there is no repository for it to name anything in."""
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task = await linked_task(app, auth_headers)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text


@pytest.mark.asyncio
async def test_accepting_merges_the_work_that_was_waiting(app, auth_headers, builder, tmp_path):
    """1.4 inverted, and the sentence "accept the evidence" made true.

    The task is already `approved` and unmerged. Approving again could not merge it — restating a
    status is deliberately a no-op — so the acceptance itself has to carry the integration.
    """
    task, evidence, work = await approve_without_a_main_branch(app, auth_headers, builder, tmp_path)

    await accept(app, auth_headers, evidence)

    assert work in commits_on(tmp_path, "main")
    assert "feature.py" in files_on(tmp_path, "main")

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == ["skipped", "merged"]

    # Not reopened to achieve it. The judgement that the work was good was already made.
    fetched = await app.get(f"{TASKS}/{task}", headers=auth_headers)
    assert fetched.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_a_granted_agent_accepting_merges_the_work_too(
    app, auth_headers, builder, reviewer, tmp_path
):
    """The remedy the refusal names is available to both, so the discharge of it must be too — an
    agent granted the capability is the whole point of naming it as a way out."""
    task, evidence, work = await approve_without_a_main_branch(app, auth_headers, builder, tmp_path)

    granted = await app.patch(
        "/api/v1/projects/proj-test/agents/reviewer",
        json={"can_accept_evidence": True},
        headers=auth_headers,
    )
    assert granted.status_code == 200, granted.text

    decided = await app.post(
        f"/api/v1/agent-actions/spec/evidence/{evidence}/decision",
        json={"decision": "accepted"},
        headers=reviewer,
    )
    assert decided.status_code == 200, decided.text

    assert work in commits_on(tmp_path, "main")
    recorded = await integrations(app, auth_headers, task)
    assert recorded[-1]["outcome"] == "merged"
    # Whose decision caused it, not the operator's. A record naming the operator for an agent's
    # decision is a false account of who caused the merge.
    assert recorded[-1]["actor"] == "reviewer"
    assert recorded[-1]["actor_kind"] == "run"


@pytest.mark.asyncio
async def test_rejecting_attempts_nothing(app, auth_headers, builder, tmp_path):
    task, evidence, work = await approve_without_a_main_branch(app, auth_headers, builder, tmp_path)

    await reject(app, auth_headers, evidence)

    assert work not in commits_on(tmp_path, "main")
    assert [row["outcome"] for row in await integrations(app, auth_headers, task)] == ["skipped"]


@pytest.mark.asyncio
async def test_an_attempt_that_cannot_proceed_records_why(app, auth_headers, builder, tmp_path):
    """Round 2 inverted this. The trigger is a commit that is not in the product, not the previous
    attempt's reason — so a dirty checkout is attempted again and says so a second time. "You
    accepted this, and here is why it still did not land" is the account the operator needs;
    suppressing it is how work goes missing quietly."""
    task, evidence, work = await approve_without_a_main_branch(app, auth_headers, builder, tmp_path)
    (tmp_path / "README.md").write_text("edited, uncommitted\n", encoding="utf-8")

    await accept(app, auth_headers, evidence)

    assert work not in commits_on(tmp_path, "main")
    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == ["skipped", "skipped"]
    assert recorded[-1]["reason"] == task_integration.CHECKOUT_DIRTY


@pytest.mark.asyncio
async def test_a_commit_already_in_main_is_recorded_not_merged_again(
    app, auth_headers, builder, tmp_path
):
    """The other "already there" case, answered differently on purpose: the repository is asked, and
    what it says is a fact the reader does not otherwise have."""
    task, evidence, work = await approve_without_a_main_branch(app, auth_headers, builder, tmp_path)
    git(tmp_path, "merge", "--no-ff", "-m", "by hand", work)
    assert work in commits_on(tmp_path, "main")

    await accept(app, auth_headers, evidence)

    recorded = await integrations(app, auth_headers, task)
    assert recorded[-1]["outcome"] == "skipped"
    assert "already in main" in recorded[-1]["reason"], recorded[-1]["reason"]


@pytest.mark.asyncio
async def test_the_decision_stands_when_the_attempt_raises(
    app, auth_headers, builder, tmp_path, monkeypatch
):
    """The decision is a judgement about the evidence, and a repository failure must not reverse
    it."""
    _task, evidence, work = await approve_without_a_main_branch(
        app, auth_headers, builder, tmp_path
    )

    def _explode(*args, **kwargs):
        raise RuntimeError("the repository fell over")

    monkeypatch.setattr(task_integration, "tasks_awaiting_this_commit", _explode)
    await accept(app, auth_headers, evidence)

    async with async_session_factory() as session:
        row = await session.get(RequirementEvidence, evidence)
        assert row.review_state == "accepted"
    assert work not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_task_that_is_not_approved_is_left_alone(app, auth_headers, builder, tmp_path):
    """Accepting evidence for work still in review merges nothing: approval is what places work in
    the product, and it has not happened."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task, evidence, work = await a_task_with_awaiting_evidence(app, auth_headers, builder, tmp_path)
    await accept(app, auth_headers, evidence)

    assert work not in commits_on(tmp_path, "main")
    assert await integrations(app, auth_headers, task) == []


# ---------------------------------------------------------------------------
# The mixed case (D3). Both halves, because the first half alone is the defect in miniature.
# ---------------------------------------------------------------------------


async def a_mixed_task(app, auth_headers, builder, tmp_path, *, second_branch=None):
    """Accepted evidence naming commit A, awaiting evidence naming commit B.

    `second_branch` puts B on a branch of its own; without it B sits on A's branch, which is the
    ordinary shape of a task worked in two sittings. Both are driven because the per-branch
    reduction in `integration_targets` treats them differently.
    """
    make_repo(tmp_path)
    await make_two_requirement_document(app, auth_headers, builder)
    await set_main_branch("main")

    task = await linked_task_for(app, auth_headers, ["FR-1", "FR-2"])
    first = commit_on_branch(tmp_path, AGENT_BRANCH, "one.py", "1\n")
    accepted = await record_evidence_for(app, builder, "FR-1", task_id=task)
    git(tmp_path, "checkout", "-q", "main")
    await accept(app, auth_headers, accepted)

    if second_branch:
        git(tmp_path, "checkout", "-q", AGENT_BRANCH)
        git(tmp_path, "checkout", "-q", "main")
        second = commit_on_branch(tmp_path, second_branch, "two.py", "2\n")
    else:
        second = commit_on_branch(tmp_path, AGENT_BRANCH, "two.py", "2\n", create=False)
    awaiting = await record_evidence_for(app, builder, "FR-2", task_id=task)
    git(tmp_path, "checkout", "-q", "main")

    return task, first, second, awaiting


@pytest.mark.asyncio
async def test_the_mixed_case_approves_merges_and_reports_the_rest(
    app, auth_headers, builder, tmp_path
):
    """Refusing here would block work that is genuinely ready because a second piece is still in
    review. The waiting piece is reported on the approval instead."""
    task, first, second, _awaiting = await a_mixed_task(app, auth_headers, builder, tmp_path)

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text
    assert first in commits_on(tmp_path, "main")
    assert second not in commits_on(tmp_path, "main")

    report = approved.json()["approval_report"]
    awaiting_entries = [row for row in report if row.get("kind") == "awaiting_evidence"]
    assert [row["identifier"] for row in awaiting_entries] == ["FR-2"]
    assert awaiting_entries[0]["commit_sha"] == second


@pytest.mark.asyncio
async def test_the_mixed_case_merges_the_rest_when_it_is_accepted(
    app, auth_headers, builder, tmp_path
):
    """The second half, and without it the first half is the defect one commit smaller: the most
    recent attempt here is a *merge*, so no rule expressed in terms of the last attempt's reason
    could ever reach this commit."""
    task, _first, second, awaiting = await a_mixed_task(app, auth_headers, builder, tmp_path)
    assert (await approve(app, auth_headers, task)).status_code == 200

    await accept(app, auth_headers, awaiting)

    assert second in commits_on(tmp_path, "main")
    assert "two.py" in files_on(tmp_path, "main")
    fetched = await app.get(f"{TASKS}/{task}", headers=auth_headers)
    assert fetched.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_the_mixed_case_merges_a_second_branch_when_it_is_accepted(
    app, auth_headers, builder, tmp_path
):
    """The same pair with the awaiting commit on a branch of its own, where the per-branch reduction
    keeps two targets rather than collapsing to one."""
    task, first, second, awaiting = await a_mixed_task(
        app, auth_headers, builder, tmp_path, second_branch="agentweave/second"
    )
    assert (await approve(app, auth_headers, task)).status_code == 200
    assert first in commits_on(tmp_path, "main")
    assert second not in commits_on(tmp_path, "main")

    await accept(app, auth_headers, awaiting)
    assert second in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_commit_this_task_already_merged_is_not_attempted_again(
    app, auth_headers, builder, tmp_path
):
    """The one "already there" case answered by suppression rather than by a record: repeating it
    could only append a row saying nothing happened, to a record that exists to distinguish a no-op
    from work reaching the product."""
    make_repo(tmp_path)
    await make_two_requirement_document(app, auth_headers, builder)
    await set_main_branch("main")

    task = await linked_task_for(app, auth_headers, ["FR-1", "FR-2"])
    work = commit_on_branch(tmp_path, AGENT_BRANCH, "one.py", "1\n")
    accepted = await record_evidence_for(app, builder, "FR-1", task_id=task)
    awaiting = await record_evidence_for(app, builder, "FR-2", task_id=task)
    git(tmp_path, "checkout", "-q", "main")
    await accept(app, auth_headers, accepted)

    assert (await approve(app, auth_headers, task)).status_code == 200
    assert work in commits_on(tmp_path, "main")
    before = await integrations(app, auth_headers, task)

    await accept(app, auth_headers, awaiting)

    assert await integrations(app, auth_headers, task) == before


# ---------------------------------------------------------------------------
# Group 6 — the surfaces the sentence has to reach.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_agent_plane_sees_the_refusal(app, auth_headers, builder, tmp_path):
    """This change's entire premise is that a refusal reaches the agent that has to act on it, so
    it is asserted rather than reasoned about from `update_task_for_actor` being shared."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task, _evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    walked = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review"
    )
    assert walked.status_code == 200, walked.text

    refused = await app.patch(
        f"/api/v1/agent-actions/tasks/{task}", json={"status": "approved"}, headers=builder
    )
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "gate_unsatisfied", detail
    assert "FR-1" in detail["message"]
    assert "grant" in detail["message"].lower()


def test_a_dict_detail_reaches_an_agent_as_its_sentence():
    """F152. `_readable_detail` special-cased the Pydantic list shape and stringified everything
    else, so every gate refusal arrived at an agent as a Python dict repr with the sentence buried
    inside it — precisely the failure its own docstring says it exists to prevent.

    Asserted against a real `to_dict()` payload rather than a hand-built dict, because the shape is
    what the app-level handler actually sends.
    """
    from hub import mcp_server
    from hub.requirement_gate import ACCEPT_OR_GRANT, REPORT_AWAITING_EVIDENCE, GateRefusal

    refusal = GateRefusal(
        unaccepted=[
            {
                "kind": REPORT_AWAITING_EVIDENCE,
                "evidence_id": "ev-1",
                "identifier": "FR-1",
                "commit_sha": "0123456789abcdef",
                "remedy": ACCEPT_OR_GRANT,
            }
        ]
    )
    readable = mcp_server._readable_detail(refusal.to_dict())

    assert readable == refusal.detail()
    assert "FR-1" in readable
    assert "{" not in readable and "}" not in readable, readable
    assert "'code'" not in readable, readable


def test_a_dict_without_a_message_keeps_the_old_behaviour():
    """The guard is the shape of the fix, not a precaution: a detail that is a plain string, or a
    dict carrying no sentence, must keep arriving exactly as it did."""
    from hub import mcp_server

    assert mcp_server._readable_detail("this run is not bound to that task") == (
        "this run is not bound to that task"
    )
    assert mcp_server._readable_detail({"code": "x"}) == str({"code": "x"})
    assert mcp_server._readable_detail({"code": "x", "message": ""}) == str(
        {"code": "x", "message": ""}
    )
