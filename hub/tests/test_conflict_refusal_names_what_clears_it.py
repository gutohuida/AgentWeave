"""F155: the conflict refusal must name a remedy the party it refuses can actually take.

Found live 2026-08-30. Approval was refused with *"Resolve the conflict on the branch, then approve
— approving is what merges it."* The reviewer did exactly that, approved again, and got the same
sentence back, byte for byte. On the evidence route the sentence is not merely unhelpful, it is
**false**: what integration merges is the commit the accepted evidence names, so a resolution commit
no evidence names changes nothing, and the answer cannot change however many times approval is
retried. The reviewer's next move was `git reset --hard` on a branch holding the only copy of an
agent's work.

These are the reproduction tests for `openspec/changes/a-conflict-refusal-names-what-clears-it`,
written and read failing before `_merge_detail` was touched. They come in two kinds and the
difference matters:

* Tests of the **sentence** fail today and pass once the change lands.
* Tests of the **world** — that resolving on the branch changes nothing, that recording from the
  branch is what changes something — pass both before and after. They are what makes the new
  sentence true rather than merely different, and they are here so that a later reader who softens
  the wording finds out that they have.

Three of them assert **non-guarantees** (1.3a, 1.3c). This change is prose-only and does not fix the
states they describe; they exist so the wording cannot quietly promise them away.
"""

import subprocess
from pathlib import Path

import pytest

from hub import requirement_evidence, task_integration, worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EvidenceFootprint, Project, RequirementEvidence, Run, Task
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
PATH = "spec/changes/f155/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It says when the list was last refreshed", "modal": "MUST"}
AGENT_BRANCH = "agentweave/builder"

#: The sentence F155 is about. Asserted as a literal rather than by a keyword, because the defect is
#: this exact instruction being given on a route where following it does nothing.
BRANCH_REMEDY = "Resolve the conflict on the branch"


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, check=False
    )


def make_repo(root, main="main"):
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "checkout", "-q", "-b", main)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "base")
    return git(root, "rev-parse", "HEAD").stdout.strip()


def commit_on_branch(root, branch, filename, content, *, create=True):
    git(root, "checkout", "-q", "-b", branch) if create else git(root, "checkout", "-q", branch)
    (root / filename).write_text(content, encoding="utf-8")
    git(root, "add", filename)
    git(root, "commit", "-q", "-m", f"work on {filename}")
    return git(root, "rev-parse", "HEAD").stdout.strip()


def commits_on(root, branch):
    return git(root, "log", "--format=%H", branch).stdout.split()


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-f155", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-f155",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_f155-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_f155-secret"}


async def set_main_branch(name):
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.main_branch = name
        await session.commit()


async def make_document(app, auth_headers, run_headers, requirements=(ALPHA,)):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "F155"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "F155",
                "requirements": list(requirements),
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def linked_task(app, auth_headers, *, title="Build it", requirements=("FR-1",)):
    created = await app.post(
        TASKS,
        json={"title": title, "requirement_ids": list(requirements)},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def record_as_agent(app, run_headers, *, identifier="FR-1", summary="ran the tests"):
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": identifier, "summary": summary},
        headers=run_headers,
    )
    assert recorded.status_code == 201, recorded.text
    return recorded.json()["id"]


async def accept(app, auth_headers, evidence_id):
    decided = await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert decided.status_code == 200, decided.text


async def accept_evidence(app, auth_headers, run_headers, **kwargs):
    evidence_id = await record_as_agent(app, run_headers, **kwargs)
    await accept(app, auth_headers, evidence_id)
    return evidence_id


async def drive_to(app, auth_headers, task_id, *statuses):
    response = None
    for next_status in statuses:
        response = await app.patch(
            f"{TASKS}/{task_id}", json={"status": next_status}, headers=auth_headers
        )
        if response.status_code != 200:
            return response
    return response


async def approve(app, auth_headers, task_id):
    return await drive_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )


async def integrations(app, auth_headers, task_id):
    response = await app.get(f"{TASKS}/{task_id}/integrations", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["integrations"]


async def conflicted(app, auth_headers, builder, tmp_path, *, requirements=(ALPHA,)):
    """The F155 shape: accepted evidence naming a commit that conflicts with the main branch.

    Returns `(task_id, judged_commit)`. The agent's footprint is read from `tmp_path`'s HEAD, which
    is why the branch is checked out before the evidence is recorded and `main` restored after —
    the same construction every sibling in `test_task_integration.py` uses.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder, requirements=requirements)
    await set_main_branch("main")

    judged = commit_on_branch(tmp_path, AGENT_BRANCH, "shared.txt", "from the agent\n")
    await accept_evidence(app, auth_headers, builder)

    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "shared.txt").write_text("from the operator\n", encoding="utf-8")
    git(tmp_path, "add", "shared.txt")
    git(tmp_path, "commit", "-q", "-m", "the operator's own change")

    identifiers = tuple(f"FR-{index + 1}" for index in range(len(requirements)))
    task = await linked_task(app, auth_headers, requirements=identifiers)
    return task, judged


def resolve_on_branch(tmp_path, branch=AGENT_BRANCH, main="main"):
    """Do what the refusal says today: a real merge commit on the branch, resolving the conflict.

    Returns the resolved commit. The old commit stays reachable from the branch — this is the
    reasonable resolution, not a rewrite, which is the point: the refusal is unchanged by it.
    """
    git(tmp_path, "checkout", "-q", branch)
    merged = git(tmp_path, "merge", "-q", main, "-m", "take the main branch's version")
    if merged.returncode != 0:
        (tmp_path / "shared.txt").write_text("from the operator\n", encoding="utf-8")
        git(tmp_path, "add", "shared.txt")
        git(tmp_path, "commit", "-q", "-m", "resolve against the main branch")
    return git(tmp_path, "rev-parse", "HEAD").stdout.strip()


# ---------------------------------------------------------------------------
# 1.1 / 1.2 — the defect, in the sentence and in the world
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_evidence_route_is_not_answered_with_resolve_it_on_the_branch(
    app, auth_headers, builder, tmp_path
):
    """1.1 — the sentence, which is what this change moves.

    Two independent assertions, because they fail for different reasons and a later reader deserves
    to know which one broke: the instruction that does not work must be gone, and the commit that
    was judged must be **in the sentence**, not only in the structured half a UI may never render.
    """
    task, judged = await conflicted(app, auth_headers, builder, tmp_path)

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    body = refused.json()["detail"]
    assert body["code"] == "gate_unsatisfied"
    assert body["unmergeable"], body

    message = body["message"]
    assert BRANCH_REMEDY not in message, message
    assert judged[:12] in message, message
    # The remedy that does work, in the terms the requirement states it: record evidence naming the
    # resolved commit, and have it accepted.
    assert "record" in message.lower(), message


@pytest.mark.asyncio
async def test_resolving_on_the_branch_leaves_the_refusal_identical(
    app, auth_headers, builder, tmp_path
):
    """1.2 — the world, which this change does **not** move, and must not claim to.

    This is the defect itself rather than its wording: the reviewer followed the instruction and got
    the same response back. It passes today and it passes after, deliberately. What the change fixes
    is that the product stops giving the instruction; what stays true is that the instruction would
    not have worked. A test asserting only the prose would let someone reinstate the old sentence
    beside a new one and call it a compromise.
    """
    task, judged = await conflicted(app, auth_headers, builder, tmp_path)

    first = await approve(app, auth_headers, task)
    assert first.status_code == 409, first.text
    before = first.json()["detail"]["message"]

    resolved = resolve_on_branch(tmp_path)
    assert resolved != judged
    assert judged in commits_on(tmp_path, AGENT_BRANCH)  # a merge, not a rewrite
    git(tmp_path, "checkout", "-q", "main")

    # Retried from where the first refusal left the task — `under_review`. Re-driving from
    # `assigned` would be refused by the status machine instead, and the refusal read back would be
    # a different one entirely.
    second = await drive_to(app, auth_headers, task, "approved")
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["message"] == before

    # And the reason, stated so the equality above is not mistaken for a caching artefact: what
    # integration would merge is still the commit the accepted evidence names.
    async with async_session_factory() as session:
        row = await session.get(Task, task)
        targets = await task_integration.integration_targets(session, row)
    assert [target.commit_sha for target in targets] == [judged]


# ---------------------------------------------------------------------------
# 1.3 — what does clear it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_recorded_from_the_branch_supersedes_and_clears_it(
    app, auth_headers, builder, tmp_path
):
    """1.3 — the remedy the new sentence states, proven before it is stated.

    Round 2 answered design open question 1 at the source: the agent route is safe because
    `_take_footprint` gates the named-commit path on `actor.kind == "operator"`
    (`requirement_evidence.py:282`), so an agent's footprint is its checkout's HEAD and lands on the
    branch it is standing on. This test holds that answer rather than discovering it.
    """
    task, judged = await conflicted(app, auth_headers, builder, tmp_path)
    assert (await approve(app, auth_headers, task)).status_code == 409

    resolved = resolve_on_branch(tmp_path)
    # Recorded *from a checkout of the branch the refusal names* — the condition the new remedy
    # states, and the whole of what makes it work.
    await accept_evidence(app, auth_headers, builder, summary="re-ran after resolving")
    git(tmp_path, "checkout", "-q", "main")

    async with async_session_factory() as session:
        row = await session.get(Task, task)
        targets = await task_integration.integration_targets(session, row)
    assert [target.commit_sha for target in targets] == [resolved], targets
    assert judged not in [target.commit_sha for target in targets]

    approved = await drive_to(app, auth_headers, task, "approved")
    assert approved.status_code == 200, approved.text
    assert resolved in commits_on(tmp_path, "main")
    assert [row["outcome"] for row in await integrations(app, auth_headers, task)] == ["merged"]


@pytest.mark.asyncio
async def test_an_operator_naming_the_resolved_sha_does_not_supersede(
    app, auth_headers, builder, tmp_path
):
    """1.3a — the operator hazard round 2 found, asserted as a **non-guarantee**.

    An operator who reads the remedy and records evidence whose `locator` is the resolved sha gets
    its branch from `_branch_at`, which answers `""` unless that commit is exactly one branch's tip
    (`requirement_evidence.py:516-529`). Here it is not — a later commit has moved the branch on —
    so the fresh row lands under a second key in `integration_targets`' per-branch reduction and
    the stale accepted row survives beside it.

    This change is prose-only and does not fix that. The test is here so the wording cannot promise
    it away, and so a later reader finds the state named rather than having to rediscover it. The
    remedy's phrasing — *recorded from a checkout of that branch* — is what steers around it.
    """
    task, judged = await conflicted(app, auth_headers, builder, tmp_path)
    resolved = resolve_on_branch(tmp_path)
    # The branch moves on, so `resolved` is no longer any branch's tip. Ordinary: an agent keeps
    # working, or the operator writes the resolution and then a follow-up.
    (tmp_path / "notes.md").write_text("more\n", encoding="utf-8")
    git(tmp_path, "add", "notes.md")
    git(tmp_path, "commit", "-q", "-m", "carry on")
    git(tmp_path, "checkout", "-q", "main")

    recorded = await app.post(
        f"{BASE}/spec/evidence",
        json={"identifier": "FR-1", "summary": "resolved it", "locator": resolved},
        headers=auth_headers,
    )
    assert recorded.status_code == 201, recorded.text
    footprint = recorded.json()["footprint"]
    assert footprint["commit_sha"] == resolved
    assert footprint["branch"] == "", footprint

    async with async_session_factory() as session:
        row = await session.get(Task, task)
        targets = await task_integration.integration_targets(session, row)
    shas = sorted(target.commit_sha for target in targets)
    assert shas == sorted([judged, resolved]), targets

    # And so the refusal stands: the stale row is still one of the things approval would merge.
    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    assert judged[:12] in str(refused.json()["detail"]["unmergeable"])


@pytest.mark.asyncio
async def test_fresh_evidence_for_a_different_requirement_supersedes(
    app, auth_headers, builder, tmp_path
):
    """1.3b, first property — the reduction keys on branch alone, not on branch and requirement.

    The new remedy must not tell a reader that the fresh evidence has to demonstrate the same
    requirement, because it does not. `integration_targets` writes `newest[target.branch]`
    (`task_integration.py:283-286`), so any accepted footprint recorded later on that branch
    displaces the one being judged, whichever requirement it is about.
    """
    task, judged = await conflicted(
        app, auth_headers, builder, tmp_path, requirements=(ALPHA, BETA)
    )
    assert (await approve(app, auth_headers, task)).status_code == 409

    resolved = resolve_on_branch(tmp_path)
    await accept_evidence(app, auth_headers, builder, identifier="FR-2", summary="the other one")
    git(tmp_path, "checkout", "-q", "main")

    async with async_session_factory() as session:
        row = await session.get(Task, task)
        targets = await task_integration.integration_targets(session, row)
    assert [target.commit_sha for target in targets] == [resolved], targets
    assert judged not in [target.commit_sha for target in targets]


@pytest.mark.asyncio
async def test_a_restamp_does_not_reorder_the_evidence(app, auth_headers, builder, tmp_path):
    """1.3b, second property — `observed_at` is what orders the reduction, and a restamp leaves it.

    `_apply_footprint` writes `kind`, `commit_sha`, `branch`, `entries` and `reachable_from_main`
    and does not touch `observed_at` (`requirement_evidence.py:375-387`). If it did, a restamp of
    the run that recorded the *stale* evidence would push it back to the front of the ordering and
    the remedy would come undone at a moment nobody was watching.
    """
    task, judged = await conflicted(app, auth_headers, builder, tmp_path)
    resolved = resolve_on_branch(tmp_path)
    await accept_evidence(app, auth_headers, builder, summary="re-ran after resolving")

    async with async_session_factory() as session:
        stamps_before = dict(
            (
                await session.execute(
                    EvidenceFootprint.__table__.select().with_only_columns(
                        EvidenceFootprint.evidence_id, EvidenceFootprint.observed_at
                    )
                )
            ).all()
        )
        moved = await requirement_evidence.restamp_run_footprints(
            session,
            project_id="proj-test",
            run_id="run-f155",
            root=Path(tmp_path),
            commit_sha=resolved,
            main_branch="main",
        )
        await session.commit()
    assert moved >= 1

    async with async_session_factory() as session:
        stamps_after = dict(
            (
                await session.execute(
                    EvidenceFootprint.__table__.select().with_only_columns(
                        EvidenceFootprint.evidence_id, EvidenceFootprint.observed_at
                    )
                )
            ).all()
        )
        row = await session.get(Task, task)
        targets = await task_integration.integration_targets(session, row)

    assert stamps_after == stamps_before, (stamps_before, stamps_after)
    # Both rows now name the resolved commit, so the reduction has nothing stale left to pick.
    assert [target.commit_sha for target in targets] == [resolved], targets
    assert judged not in [target.commit_sha for target in targets]


@pytest.mark.asyncio
async def test_an_agent_whose_workspace_is_gone_does_not_supersede(
    app, auth_headers, builder, tmp_path
):
    """1.3c — round 3's correction to D2a, asserted as a **non-guarantee**.

    Round 2 wrote that an agent's footprint is *always* taken in a worktree checked out on the task
    branch. `footprint_root` has three answers, not one (`requirement_evidence.py:334-340`): the
    recorded run directory only while it still exists, then the per-agent checkout, then
    `workspace.root` — which is on the main branch. On either fallback the fresh footprint carries
    a different branch, `newest` gains a second key rather than replacing the first, and the
    refusal stands.

    So nothing the change writes may say the branch takes care of itself. Reached here the way the
    product reaches it: the recording happens while the workspace is checked out on the main
    branch, which is what `workspace.root` gives a released or never-recorded run.
    """
    task, judged = await conflicted(app, auth_headers, builder, tmp_path)
    resolved = resolve_on_branch(tmp_path)

    # The fallback state: no run workspace to read, so the footprint is taken at the project
    # checkout, which is sitting on the main branch.
    async with async_session_factory() as session:
        run = await session.get(Run, "run-f155")
        assert run.workspace_dir is None
        assert worktrees.existing_worktree(Path(tmp_path), "builder") is None
    git(tmp_path, "checkout", "-q", "main")

    await accept_evidence(app, auth_headers, builder, summary="recorded from the wrong tree")

    async with async_session_factory() as session:
        row = await session.get(Task, task)
        targets = await task_integration.integration_targets(session, row)
        branches = sorted(target.branch or "" for target in targets)
        shas = sorted(target.commit_sha for target in targets)
    assert branches == sorted([AGENT_BRANCH, "main"]), targets
    assert judged in shas, targets
    assert resolved not in shas, targets

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    assert judged[:12] in str(refused.json()["detail"]["unmergeable"])


# ---------------------------------------------------------------------------
# A guard on the fixture itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_shape_is_the_evidence_route_not_the_branch_tip(
    app, auth_headers, builder, tmp_path
):
    """Everything above depends on the target coming from accepted evidence rather than a branch
    tip, and the two routes take opposite remedies. `merge_targets` picks between them
    (`task_integration.py:390-408`), so assert which one this shape lands on rather than assuming
    it — a fixture that quietly became a branch-tip task would make every test above vacuous.
    """
    task, judged = await conflicted(app, auth_headers, builder, tmp_path)
    async with async_session_factory() as session:
        row = await session.get(Task, task)
        assert await task_integration.evidence_governs(session, row) is True
        targets = await task_integration.merge_targets(session, row, Path(tmp_path))
    assert [target.commit_sha for target in targets] == [judged]
    assert [target.evidence_id for target in targets] != [None]


@pytest.mark.asyncio
async def test_the_evidence_row_is_this_tasks_own(app, auth_headers, builder, tmp_path):
    """The attribution baseline for 2.2a/3.3b: this shape's evidence is recorded by nobody else."""
    task, _ = await conflicted(app, auth_headers, builder, tmp_path)
    async with async_session_factory() as session:
        rows = (await session.execute(RequirementEvidence.__table__.select())).all()
    assert rows
    assert all(row.task_id in (None, task) for row in rows), rows
