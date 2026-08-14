"""Evidence recorded mid-turn is re-pointed at the commit that actually contains the work.

The defect these tests exist for was found by driving the product. A builder recorded nine pieces of
evidence during its turn; the Hub committed that turn's work *after* the turn ended; every footprint
therefore named the commit the turn started from — on a fresh project, the `init` commit, holding
only `README.md`. Worse, that commit is already on `master`, so all nine were written
`reachable_from_main=True`: evidence for code that does not exist, reading as already shipped.

**Why the existing footprint suite missed it.** Every test in `test_evidence_footprint_root.py`
commits the agent's work *before* recording evidence, so the work is in HEAD when the footprint is
read. AgentWeave never produces that shape — an agent's work is dirty until the Hub snapshots it.
So every test here records against a **dirty** worktree, which is the only shape that can fail.
"""

import inspect
import re
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub import requirement_evidence, worktrees
from hub.agent_auth import hash_run_token
from hub.api.v1 import agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EvidenceFootprint, RequirementEvidence, Run, SpecRequirement
from hub.spec_payload import SCHEMA_VERSION

from .test_evidence_footprint_root import commit_in, git, head_of, init_repo

BASE = "/api/v1/projects/proj-test/project"
SUBMIT = "/api/v1/agent-actions/spec/documents"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
PATH = "spec/changes/restamp-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It records a check-in", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It records a check-out", "modal": "MUST"}


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-rs", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-rs",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_rs-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_rs-secret"}


async def make_document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Restamp demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Restamp demo",
                "requirements": [ALPHA, BETA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


def dirty(worktree, filename: str, content: str) -> None:
    """Leave work in the checkout *without* committing it — an agent mid-turn."""
    (worktree / filename).write_text(content, encoding="utf-8")


async def footprints() -> list:
    async with async_session_factory() as session:
        return (
            (await session.execute(select(EvidenceFootprint).order_by(EvidenceFootprint.id)))
            .scalars()
            .all()
        )


async def restamp(repo, *, run_id: str = "run-rs", commit_sha=None, main_branch=None) -> int:
    async with async_session_factory() as session:
        worktree = repo / ".agentweave" / "worktrees" / "builder"
        updated = await requirement_evidence.restamp_run_footprints(
            session,
            project_id="proj-test",
            run_id=run_id,
            root=worktree,
            commit_sha=commit_sha,
            main_branch=main_branch,
        )
        await session.commit()
        return updated


async def record_two(app, builder):
    for identifier in ("FR-1", "FR-2"):
        recorded = await app.post(
            AGENT_EVIDENCE,
            json={"identifier": identifier, "summary": f"ran the tests for {identifier}"},
            headers=builder,
        )
        assert recorded.status_code == 201, recorded.text


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restamp_names_the_snapshot_commit_not_its_parent(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """The test that fails on the code which shipped the defect.

    Before the fix both footprints name the pre-turn commit, which is `master` — so the run's
    evidence reads as already integrated while the work is uncommitted on a branch.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    before = head_of(worktree)

    await make_document(app, auth_headers, builder)
    dirty(worktree, "feature.py", "print('hi')\n")
    await record_two(app, builder)

    # The defect, asserted rather than assumed: recorded mid-turn, the footprint is the parent, and
    # it claims to be on the main line.
    stale = await footprints()
    assert [f.commit_sha for f in stale] == [before, before]
    assert [f.reachable_from_main for f in stale] == [True, True]

    snapshot = worktrees.snapshot_worktree(worktree, "builder")
    assert snapshot and snapshot != before

    assert await restamp(repo, commit_sha=snapshot) == 2

    fixed = await footprints()
    assert [f.commit_sha for f in fixed] == [snapshot, snapshot]
    assert all(f.branch == "agentweave/builder" for f in fixed)
    assert all("feature.py" in (f.entries or {}) for f in fixed)


@pytest.mark.asyncio
async def test_restamp_recomputes_entries_and_reachability_for_the_new_commit(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """`reachable_from_main` must be able to go *down*.

    `refresh_reachability` is upgrade-only, correctly, because for a fixed commit the answer only
    travels one way. This is a different commit, and carrying the parent's `True` over is exactly
    the poison being removed.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")

    await make_document(app, auth_headers, builder)
    dirty(worktree, "feature.py", "print('hi')\n")
    await record_two(app, builder)
    assert all(f.reachable_from_main is True for f in await footprints())

    snapshot = worktrees.snapshot_worktree(worktree, "builder")
    await restamp(repo, commit_sha=snapshot)

    fixed = await footprints()
    assert all(f.reachable_from_main is False for f in fixed), "the True must not be carried over"
    assert all("README.md" in (f.entries or {}) for f in fixed)
    assert all("feature.py" in (f.entries or {}) for f in fixed)


@pytest.mark.asyncio
async def test_restamp_prefers_the_configured_main_branch(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """A project integrating into a branch `MAIN_BRANCH_NAMES` would not guess."""
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")

    await make_document(app, auth_headers, builder)
    dirty(worktree, "feature.py", "print('hi')\n")
    await record_two(app, builder)
    snapshot = worktrees.snapshot_worktree(worktree, "builder")

    # A branch that *does* contain the work, so preferring it flips the answer the guess would give.
    git(repo, "branch", "develop", snapshot)
    await restamp(repo, commit_sha=snapshot, main_branch="develop")

    assert all(f.reachable_from_main is True for f in await footprints())


@pytest.mark.asyncio
async def test_restamp_creates_the_footprint_recording_could_not(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """Where the workspace could not be resolved at record time there is no footprint row at all.

    The pass has to be able to create as well as update, which is why the query is an outer join.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    await make_document(app, auth_headers, builder)
    dirty(worktree, "feature.py", "print('hi')\n")

    async with async_session_factory() as session:
        requirement = (
            await session.execute(
                select(SpecRequirement).where(SpecRequirement.identifier == "FR-1")
            )
        ).scalar_one()
        session.add(
            RequirementEvidence(
                id="ev-nofp",
                project_id="proj-test",
                requirement_id=requirement.id,
                digest=requirement.digest,
                digest_version=requirement.digest_version,
                kind="test_result",
                locator="",
                summary="recorded while the workspace was unavailable",
                actor_kind="agent",
                actor="builder",
                run_id="run-rs",
                review_state="awaiting",
            )
        )
        await session.commit()
    assert await footprints() == []

    snapshot = worktrees.snapshot_worktree(worktree, "builder")
    assert await restamp(repo, commit_sha=snapshot) == 1

    created = await footprints()
    assert len(created) == 1
    assert created[0].evidence_id == "ev-nofp"
    assert created[0].commit_sha == snapshot


@pytest.mark.asyncio
async def test_restamp_falls_back_to_head_when_nothing_was_committed(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """A `None` snapshot is not a reason to skip.

    An agent that commits its own work mid-turn leaves nothing dirty, so `snapshot_worktree` returns
    `None` — but the footprint is *still* stale, because it was read before that commit.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    before = head_of(worktree)

    await make_document(app, auth_headers, builder)
    dirty(worktree, "feature.py", "print('hi')\n")
    await record_two(app, builder)
    assert [f.commit_sha for f in await footprints()] == [before, before]

    # The agent commits its own work, so there is nothing left for the Hub to snapshot.
    own = commit_in(worktree, "feature.py", "print('hi')\n")
    assert worktrees.snapshot_worktree(worktree, "builder") is None

    assert await restamp(repo, commit_sha=None) == 2
    assert [f.commit_sha for f in await footprints()] == [own, own]


@pytest.mark.asyncio
async def test_restamp_is_a_no_op_when_the_commit_is_unchanged(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """An agent that changed nothing already has the right answer."""
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")

    await make_document(app, auth_headers, builder)
    await record_two(app, builder)
    assert worktrees.snapshot_worktree(worktree, "builder") is None

    assert await restamp(repo, commit_sha=None) == 0


@pytest.mark.asyncio
async def test_restamp_leaves_another_runs_footprints_alone(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """Scope is the run. A concurrent agent's evidence is about a different checkout."""
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    before = head_of(worktree)

    await make_document(app, auth_headers, builder)
    dirty(worktree, "feature.py", "print('hi')\n")
    await record_two(app, builder)
    snapshot = worktrees.snapshot_worktree(worktree, "builder")

    assert await restamp(repo, run_id="run-somebody-else", commit_sha=snapshot) == 0
    assert [f.commit_sha for f in await footprints()] == [before, before]


@pytest.mark.asyncio
async def test_restamp_corrects_an_accepted_row_and_leaves_its_review_untouched(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """Sparing decided rows would leave approval merging a commit that lacks the work.

    The footprint is a fact about where the work is; the review is the judgement. Correcting the
    first must not disturb the second, or correctness would depend on how fast a reviewer clicked.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")

    await make_document(app, auth_headers, builder)
    dirty(worktree, "feature.py", "print('hi')\n")
    await record_two(app, builder)

    async with async_session_factory() as session:
        rows = (await session.execute(select(RequirementEvidence))).scalars().all()
        for row in rows:
            row.review_state = "accepted"
        await session.commit()

    snapshot = worktrees.snapshot_worktree(worktree, "builder")
    assert await restamp(repo, commit_sha=snapshot) == 2

    assert [f.commit_sha for f in await footprints()] == [snapshot, snapshot]
    async with async_session_factory() as session:
        states = (await session.execute(select(RequirementEvidence.review_state))).scalars().all()
    assert states == ["accepted", "accepted"], "the decision must be untouched"


# ---------------------------------------------------------------------------
# The wiring. The tests above call the function directly, which proves it works and proves
# nothing about whether anything calls it.
# ---------------------------------------------------------------------------


def test_every_snapshot_site_restamps():
    """Both runner paths must re-stamp, and so must any third one added later.

    Asserted against the source because the alternative is driving two full runner processes to
    observe two lines. A new runner path that persists a snapshot and forgets this is exactly the
    regression that would restore the defect for one runner only — which is how the original was
    survivable for as long as it was.
    """
    source = inspect.getsource(agent_trigger)
    assignments = [m.start() for m in re.finditer(r"run\.snapshot_commit_sha = ", source)]
    assert len(assignments) >= 2, "expected the exec and app-server snapshot sites"

    for start in assignments:
        window = source[start : start + 600]
        assert "_restamp_evidence_footprints(" in window, (
            "a site persisting run.snapshot_commit_sha does not re-stamp its evidence "
            f"footprints; context: {window[:200]!r}"
        )


@pytest.mark.asyncio
async def test_the_helper_passes_the_projects_configured_main_branch(
    app, bind_project_workspace, tmp_path
):
    """The configured branch beats the guess, as it does everywhere else reachability is asked."""
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    async with async_session_factory() as session:
        from hub.db.models import Project

        project = await session.get(Project, "proj-test")
        project.main_branch = "develop"
        await session.commit()

    delegate = AsyncMock(return_value=0)
    with patch.object(requirement_evidence, "restamp_run_footprints", delegate):
        async with async_session_factory() as session:
            await agent_trigger._restamp_evidence_footprints(
                session,
                project_id="proj-test",
                run_id="run-rs",
                worktree=repo,
                snapshot_sha="deadbeef",
            )
    assert delegate.await_args.kwargs["main_branch"] == "develop"
    assert delegate.await_args.kwargs["commit_sha"] == "deadbeef"


@pytest.mark.asyncio
async def test_the_helper_does_nothing_without_a_worktree():
    """A run with no checkout has no work to have committed."""
    delegate = AsyncMock(return_value=0)
    with patch.object(requirement_evidence, "restamp_run_footprints", delegate):
        async with async_session_factory() as session:
            await agent_trigger._restamp_evidence_footprints(
                session,
                project_id="proj-test",
                run_id="run-rs",
                worktree=None,
                snapshot_sha="deadbeef",
            )
    delegate.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failing_restamp_does_not_worsen_the_run(app, bind_project_workspace, tmp_path):
    """Best-effort, exactly like the snapshot above it.

    A git failure while correcting a footprint must not turn a completed run into a failed one.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    boom = AsyncMock(side_effect=RuntimeError("git exploded"))
    with patch.object(requirement_evidence, "restamp_run_footprints", boom):
        async with async_session_factory() as session:
            await agent_trigger._restamp_evidence_footprints(
                session,
                project_id="proj-test",
                run_id="run-rs",
                worktree=repo,
                snapshot_sha="deadbeef",
            )
    boom.assert_awaited()


@pytest.mark.asyncio
async def test_integration_targets_the_snapshot_commit_after_a_restamp(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """The point of the whole phase: what gets merged is the commit that holds the work.

    Without the re-stamp, `integration_targets` names the pre-turn commit — which on this shape is
    the project's own `master` tip, so integration would report the work already in and merge
    nothing, exactly as loop 5 did.
    """
    from hub import task_integration
    from hub.db.models import Task

    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    before = head_of(worktree)

    await make_document(app, auth_headers, builder)
    dirty(worktree, "feature.py", "print('hi')\n")

    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran the tests"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    created = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Build it", "requirement_ids": ["FR-1"]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    accepted = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text

    async def targets():
        async with async_session_factory() as session:
            task = await session.get(Task, task_id)
            return await task_integration.integration_targets(session, task)

    # The defect: accepted evidence names the commit that does not contain the work.
    assert [t.commit_sha for t in await targets()] == [before]

    snapshot = worktrees.snapshot_worktree(worktree, "builder")
    await restamp(repo, commit_sha=snapshot)

    assert [t.commit_sha for t in await targets()] == [snapshot]


@pytest.mark.asyncio
async def test_retry_merges_the_snapshot_commit_after_a_restamp(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    """The two fixes composed, which is the only place their interaction is visible.

    Phase 1 corrects what a footprint names; phase 2 is the only surface that lets a corrected
    footprint reach main for work approved before the correction. Neither phase's own tests show
    this: the restamp tests never approve, and the retry tests pre-commit their work.
    """
    from hub.db.models import Project

    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")

    await make_document(app, auth_headers, builder)
    dirty(worktree, "feature.py", "print('hi')\n")
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran the tests"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text

    created = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Build it", "requirement_ids": ["FR-1"]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    accepted = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text

    snapshot = worktrees.snapshot_worktree(worktree, "builder")
    await restamp(repo, commit_sha=snapshot)

    # Approve with no main branch named, exactly as the loop-7 run did.
    for status in ("assigned", "in_progress", "completed", "under_review", "approved"):
        moved = await app.patch(
            f"/api/v1/projects/proj-test/tasks/{task_id}",
            json={"status": status},
            headers=auth_headers,
        )
        assert moved.status_code == 200, moved.text
    assert snapshot not in git(repo, "log", "--format=%H", "master").stdout.split()

    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.main_branch = "master"
        await session.commit()

    retried = await app.post(
        f"/api/v1/projects/proj-test/tasks/{task_id}/integrations/retry", headers=auth_headers
    )
    assert retried.status_code == 200, retried.text

    merged = [r for r in retried.json()["integrations"] if r["outcome"] == "merged"]
    assert merged, retried.json()["integrations"]
    assert merged[0]["commit_sha"] == snapshot, "the merged commit must be the one holding the work"
    assert snapshot in git(repo, "log", "--format=%H", "master").stdout.split()
