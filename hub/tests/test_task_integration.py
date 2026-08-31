"""Approval puts the work in the product, or says exactly why it did not.

Before this, `approved` and `shipped` were unrelated facts: six approved tasks and 99 passing tests
sat on a branch nothing merged, and the product could not tell you. B3 made that reportable; these
tests are about closing it.

Two properties carry most of the risk and get the most attention here.

**A commit is merged, never a branch.** Agent branches are per agent, so one builder's branch holds
every task it ever worked on. `test_later_commits_on_the_branch_are_not_merged` is the one that
fails if that decision is ever quietly reversed, and its failure mode in production is shipping
somebody else's unreviewed work.

**Nothing here may block an approval.** Every "cannot merge" path is a recorded skip and a
successful transition. A repository problem is not a reason to reverse a human judgement that the
work was good — and a project that is not a repository at all must stay exactly as approvable as it
was before any of this existed.
"""

import subprocess

import pytest

from hub import worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Project, Run
from hub.spec_payload import SCHEMA_VERSION, extract_payload  # noqa: F401  (parity with siblings)

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SETTINGS = "/api/v1/projects/proj-test/settings"
SUBMIT = "/api/v1/agent-actions/spec/documents"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
PATH = "spec/changes/integration-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
AGENT_BRANCH = "agentweave/builder"


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, check=False
    )


def make_repo(root, main="main"):
    """A repository with one commit on *main*, and nothing else."""
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "checkout", "-q", "-b", main)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "base")
    return git(root, "rev-parse", "HEAD").stdout.strip()


def commit_on_branch(root, branch, filename, content, *, create=True):
    """Commit *content* to *filename* on *branch*, and return the new sha."""
    if create:
        git(root, "checkout", "-q", "-b", branch)
    else:
        git(root, "checkout", "-q", branch)
    (root / filename).write_text(content, encoding="utf-8")
    git(root, "add", filename)
    git(root, "commit", "-q", "-m", f"work on {filename}")
    return git(root, "rev-parse", "HEAD").stdout.strip()


def commits_on(root, branch):
    return git(root, "log", "--format=%H", branch).stdout.split()


def files_on(root, branch):
    return set(git(root, "ls-tree", "-r", "--name-only", branch).stdout.split())


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-int", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-int",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_int-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_int-secret"}


async def set_main_branch(name):
    """Set the merge target directly. The route validates against the repository, and several of
    these tests deliberately construct states the route would refuse to create."""
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.main_branch = name
        await session.commit()


async def make_document(app, auth_headers, run_headers):
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
                "requirements": [ALPHA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def linked_task(app, auth_headers, title="Build it"):
    created = await app.post(
        TASKS, json={"title": title, "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def accept_evidence(app, auth_headers, run_headers, summary="ran the tests"):
    """Record evidence as the agent and accept it as the operator.

    The footprint is captured from the workspace's HEAD *at this moment*, which is why every test
    below checks out the agent's branch before calling this and switches back afterwards.
    """
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": summary}, headers=run_headers
    )
    assert recorded.status_code == 201, recorded.text
    accepted = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text
    return recorded.json()["id"]


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


async def coverage_for(app, auth_headers, identifier):
    """What the coverage surface says about one requirement.

    `test_requirement_coverage.py` reaches `not_integrated` by setting `reachable_from_main = False`
    on the footprint by hand. This reaches it the way the product does — by failing a real merge —
    which is the difference between asserting the vocabulary exists and asserting the system uses it.
    """
    response = await app.get(f"{BASE}/spec/coverage", headers=auth_headers)
    assert response.status_code == 200, response.text
    report = response.json()
    rows = report if isinstance(report, list) else report.get("requirements", report)
    for row in rows:
        if row.get("identifier") == identifier:
            return row
    raise AssertionError(f"{identifier} absent from coverage: {rows}")


# ---------------------------------------------------------------------------
# The demonstrable case
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approving_a_task_puts_its_work_on_main(app, auth_headers, builder, tmp_path):
    """The whole change in one test: approve, and the work is in the product."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    assert work not in commits_on(tmp_path, "main")

    task = await linked_task(app, auth_headers)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    assert work in commits_on(tmp_path, "main")
    assert "feature.py" in files_on(tmp_path, "main")

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == ["merged"]
    assert recorded[0]["commit_sha"] == work
    assert recorded[0]["target_branch"] == "main"
    assert recorded[0]["mechanism"] == "local"


@pytest.mark.asyncio
async def test_the_approve_response_itself_reports_the_merge(app, auth_headers, builder, tmp_path):
    """Approving is what merges it, but the response used to say nothing about whether it had —
    only a separate `GET /tasks/{id}/integrations` call showed that. Echo the same fact onto the
    transition response (and onto plain `GET /tasks/{id}`) so a silent success stops being silent.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    latest = approved.json()["latest_integration"]
    assert latest is not None, approved.json()
    assert latest["outcome"] == "merged"
    assert latest["commit_sha"] == work
    assert latest["target_branch"] == "main"

    # GET tells the same story, not only the response to the transition that caused it.
    fetched = await app.get(f"{TASKS}/{task}", headers=auth_headers)
    assert fetched.json()["latest_integration"]["outcome"] == "merged"


@pytest.mark.asyncio
async def test_the_approve_response_reports_a_skip_too(app, auth_headers, builder, tmp_path):
    """The other half of the same gap: a skip was exactly as invisible as a merge was."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    # Deliberately no main_branch set.

    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    latest = approved.json()["latest_integration"]
    assert latest is not None, approved.json()
    assert latest["outcome"] == "skipped"
    assert "no main branch" in latest["reason"]


@pytest.mark.asyncio
async def test_latest_integration_is_null_before_any_approval(app, auth_headers, builder, tmp_path):
    """A task that has never reached `approved` has never had an integration attempt made for it —
    null, not an empty skip, is the honest answer."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    task = await linked_task(app, auth_headers)
    fetched = await app.get(f"{TASKS}/{task}", headers=auth_headers)
    assert fetched.json()["latest_integration"] is None


@pytest.mark.asyncio
async def test_later_commits_on_the_branch_are_not_merged(app, auth_headers, builder, tmp_path):
    """D1: what merges is the commit the evidence names, not the agent's branch.

    If this test fails, approving one task ships work the evidence never demonstrated — which is the
    failure the whole commit-not-branch decision exists to prevent.

    The mirror of that rule is asserted here too, and it is what rules out squashing the evidence
    commit's diff as F58's fix: an *earlier* commit on the same task's own branch is groundwork the
    demonstrated commit was built on top of, and it has to land with it. Only what came after the
    evidence stays out. The branch name is incidental to both halves — what decides them is the
    named commit's ancestry.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    # Groundwork this task's own demonstrated commit sits on top of, committed before the evidence.
    earlier = commit_on_branch(tmp_path, AGENT_BRANCH, "groundwork.py", "prep\n")
    demonstrated = commit_on_branch(tmp_path, AGENT_BRANCH, "done.py", "ok\n", create=False)
    await accept_evidence(app, auth_headers, builder)

    # Work that happened after the evidence was accepted, on the same branch.
    later = commit_on_branch(tmp_path, AGENT_BRANCH, "not-yet.py", "wip\n", create=False)
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200

    merged = commits_on(tmp_path, "main")
    assert demonstrated in merged
    assert earlier in merged
    assert later not in merged
    assert "done.py" in files_on(tmp_path, "main")
    assert "groundwork.py" in files_on(tmp_path, "main")
    assert "not-yet.py" not in files_on(tmp_path, "main")

    # The groundwork is on the record as having come in with the demonstrated commit rather than
    # having been demonstrated itself. It landed; the record still says which commit was reviewed.
    rows = await integrations(app, auth_headers, task)
    assert rows[-1]["rode_along_commits"] == [earlier]


@pytest.mark.asyncio
async def test_another_tasks_commits_do_not_ride_along(app, auth_headers, builder, tmp_path):
    """F58: approving one task must not ship another task's unreviewed work.

    This is the inversion of `test_rode_along_commits_names_what_actually_landed`, which asserted
    the bug — that `merge --no-ff` brings in a commit's entire ancestry, so an earlier commit made
    for a *different* task rode along uninvited — and only checked that the record named it. The
    design decision that test declined to make has been made: work is isolated per task, so the
    other task's commit is on the other task's branch and is not in this commit's ancestry at all.

    The branch names come from the product, not from this test. That is the point: what makes the
    two tasks' work separable is that the Hub can say where each task's work goes, and until it can
    there is nothing here to assert.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    other = await linked_task(app, auth_headers, title="Someone else's task")
    task = await linked_task(app, auth_headers)

    # An earlier, unrelated commit on a *different* task's branch - work-in-progress never named by
    # any accepted evidence, and never reviewed.
    earlier = commit_on_branch(tmp_path, worktrees.task_branch_name(other), "unrelated.py", "wip\n")

    # This task's own branch, cut from main rather than from whatever the other task left behind.
    git(tmp_path, "checkout", "-q", "main")
    demonstrated = commit_on_branch(tmp_path, worktrees.task_branch_name(task), "done.py", "ok\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    assert (await approve(app, auth_headers, task)).status_code == 200

    merged = commits_on(tmp_path, "main")
    assert demonstrated in merged
    assert earlier not in merged
    assert "unrelated.py" not in files_on(tmp_path, "main")

    rows = await integrations(app, auth_headers, task)
    newest = rows[-1]
    assert newest["outcome"] == "merged"
    assert newest["rode_along_commits"] == []


# ---------------------------------------------------------------------------
# The conflict refusal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_conflicting_branch_refuses_approval(app, auth_headers, builder, tmp_path):
    """Refused before anything is merged, naming the file — not discovered mid-merge."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    commit_on_branch(tmp_path, AGENT_BRANCH, "shared.txt", "from the agent\n")
    await accept_evidence(app, auth_headers, builder)

    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "shared.txt").write_text("from the operator\n", encoding="utf-8")
    git(tmp_path, "add", "shared.txt")
    git(tmp_path, "commit", "-q", "-m", "operator's own change")
    head_before = git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    task = await linked_task(app, auth_headers)
    refused = await approve(app, auth_headers, task)

    assert refused.status_code == 409, refused.text
    body = refused.json()["detail"]
    assert body["code"] == "gate_unsatisfied"
    assert body["unmergeable"], body
    assert "shared.txt" in str(body["unmergeable"])
    assert "shared.txt" in body["message"]

    # Nothing was attempted: the task did not move and the repository is untouched.
    task_now = await app.get(f"{TASKS}/{task}", headers=auth_headers)
    assert task_now.json()["status"] == "under_review"
    assert git(tmp_path, "rev-parse", "HEAD").stdout.strip() == head_before
    assert await integrations(app, auth_headers, task) == []

    # The third outcome: resolve the conflict on the branch, and the same approval merges. Without
    # this leg the refusal is only proven to be a wall, not a step in a path that goes somewhere.
    git(tmp_path, "checkout", "-q", AGENT_BRANCH)
    merged_in = git(tmp_path, "merge", "-q", "main", "-m", "take main's version")
    if merged_in.returncode != 0:
        (tmp_path / "shared.txt").write_text("from the operator\n", encoding="utf-8")
        git(tmp_path, "add", "shared.txt")
        git(tmp_path, "commit", "-q", "-m", "resolve against main")
    resolved = git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    await accept_evidence(app, auth_headers, builder, summary="re-ran after resolving")
    git(tmp_path, "checkout", "-q", "main")

    approved = await drive_to(app, auth_headers, task, "approved")
    assert approved.status_code == 200, approved.text
    assert resolved in commits_on(tmp_path, "main")
    assert [row["outcome"] for row in await integrations(app, auth_headers, task)] == ["merged"]


@pytest.mark.asyncio
async def test_a_failed_merge_leaves_the_approval_standing(app, auth_headers, builder, tmp_path):
    """D6: a git failure is not a reason to reverse a judgement that the work was good.

    The gate tested the merge before the transition, so reaching a failure means the world moved in
    between. Here that is an untracked file the merge would overwrite — the one thing untracked
    content genuinely does block, and the reason not counting it as "dirty" is safe rather than
    reckless. The task stays approved and the record says what happened.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "from the agent\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    # Untracked on main, and the merge wants to create it: git refuses rather than clobbering it.
    (tmp_path / "feature.py").write_text("someone's unsaved work\n", encoding="utf-8")

    task = await linked_task(app, auth_headers)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    task_now = await app.get(f"{TASKS}/{task}", headers=auth_headers)
    assert task_now.json()["status"] == "approved"

    recorded = await integrations(app, auth_headers, task)
    assert recorded[0]["outcome"] == "failed", recorded
    assert recorded[0]["reason"]
    assert work not in commits_on(tmp_path, "main")
    # The file the merge would have clobbered is untouched.
    assert (tmp_path / "feature.py").read_text(encoding="utf-8") == "someone's unsaved work\n"

    # The other half of D6, and the half that was unreachable until evidence stopped being
    # footprinted against the project checkout: coverage has to say the requirement is *verified*
    # and *not integrated* at the same time. Before the footprint fix this state could not occur —
    # the footprint named a commit already on main, so a merge that never happened still reported
    # `integrated`, which is precisely the lie this change exists to make impossible.
    entry = await coverage_for(app, auth_headers, "FR-1")
    assert entry["state"] == "verified"
    assert entry["integration"] == "not_integrated"


@pytest.mark.asyncio
async def test_work_on_two_branches_is_merged_from_both(app, auth_headers, builder, tmp_path):
    """One target per branch. Silently keeping only the newest across all of them would integrate
    half of what was approved, and the half that went missing would be the older one — the part
    nobody re-checks."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    first = commit_on_branch(tmp_path, AGENT_BRANCH, "one.py", "1\n")
    await accept_evidence(app, auth_headers, builder, summary="branch one")

    git(tmp_path, "checkout", "-q", "main")
    second = commit_on_branch(tmp_path, "agentweave/reviewer", "two.py", "2\n")
    await accept_evidence(app, auth_headers, builder, summary="branch two")

    git(tmp_path, "checkout", "-q", "main")
    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200

    merged = commits_on(tmp_path, "main")
    assert first in merged
    assert second in merged
    assert {row["outcome"] for row in await integrations(app, auth_headers, task)} == {"merged"}


@pytest.mark.asyncio
async def test_rejected_evidence_merges_nothing(app, auth_headers, builder, tmp_path):
    """Rejected evidence has been judged, and judged the other way. Merging on it would ship work
    a reviewer explicitly turned down."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "not good enough"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    rejected = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "rejected"},
        headers=auth_headers,
    )
    assert rejected.status_code == 200, rejected.text
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200
    assert work not in commits_on(tmp_path, "main")
    assert (await integrations(app, auth_headers, task))[0]["outcome"] == "skipped"


@pytest.mark.asyncio
async def test_a_commit_already_on_main_is_skipped_not_merged(app, auth_headers, builder, tmp_path):
    """The regression for the defect the 2026-08-13 end-to-end run found.

    `git merge <ancestor>` prints "Already up to date", exits 0 and creates nothing, so a no-op was
    recorded as `merged` — making "the work reached the product" indistinguishable from "nothing
    happened", which is the one distinction this record exists to make.

    The unchanged-sha assertion is the load-bearing half: without it this test passes on the code
    that shipped the defect.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    # Evidence recorded while the checkout is on main, so the footprint names a commit that is
    # already there — exactly the shape the live run produced.
    await accept_evidence(app, auth_headers, builder)
    before = git(tmp_path, "rev-parse", "main").stdout.strip()

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200

    recorded = await integrations(app, auth_headers, task)
    assert recorded[0]["outcome"] == "skipped", recorded
    assert "already in" in recorded[0]["reason"]
    assert git(tmp_path, "rev-parse", "main").stdout.strip() == before


@pytest.mark.asyncio
async def test_already_integrated_wins_over_a_dirty_checkout(app, auth_headers, builder, tmp_path):
    """Whether a commit is already in the target is a fact about the commit and the target.

    Telling an operator to commit or stash implies a merge would follow, and none would.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    await accept_evidence(app, auth_headers, builder)

    (tmp_path / "README.md").write_text("edited by the operator\n", encoding="utf-8")

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200

    reason = (await integrations(app, auth_headers, task))[0]["reason"]
    assert "already in" in reason
    assert "uncommitted" not in reason


@pytest.mark.asyncio
async def test_a_conflict_refuses_even_at_sketch_rigor(app, auth_headers, builder, tmp_path):
    """D3's accepted consequence. This is not a claim that the work is unproven — it is a claim
    that it cannot go where approval says it goes, and rigor has no opinion about that."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    document_rigor = await app.get(f"{BASE}/documents", headers=auth_headers)
    assert document_rigor.json()["documents"][0]["rigor"] == "sketch"

    commit_on_branch(tmp_path, AGENT_BRANCH, "shared.txt", "agent\n")
    await accept_evidence(app, auth_headers, builder)

    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "shared.txt").write_text("operator\n", encoding="utf-8")
    git(tmp_path, "add", "shared.txt")
    git(tmp_path, "commit", "-q", "-m", "conflict")

    task = await linked_task(app, auth_headers)
    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["unmergeable"]


@pytest.mark.asyncio
async def test_a_sketch_document_still_integrates(app, auth_headers, builder, tmp_path):
    """D5: rigor governs who can reach `approved`; integration is what `approved` means.

    Were the two coupled, lowering a gate to get unblocked would also silently stop shipping.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200
    assert work in commits_on(tmp_path, "main")


# ---------------------------------------------------------------------------
# Every way it declines to merge, and none of them blocks the approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_configured_main_branch_skips_without_blocking(
    app, auth_headers, builder, tmp_path
):
    """An existing project upgrades into this feature switched off, and notices nothing."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200
    assert work not in commits_on(tmp_path, "main")

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == ["skipped"]
    assert "no main branch" in recorded[0]["reason"]


@pytest.mark.asyncio
async def test_a_dirty_checkout_skips_without_blocking(app, auth_headers, builder, tmp_path):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "README.md").write_text("edited by the operator\n", encoding="utf-8")

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200
    assert work not in commits_on(tmp_path, "main")

    recorded = await integrations(app, auth_headers, task)
    assert recorded[0]["outcome"] == "skipped"
    assert "uncommitted" in recorded[0]["reason"]


@pytest.mark.asyncio
async def test_a_dirty_checkout_skip_points_at_the_retry_not_at_approving_again(
    app, auth_headers, builder, tmp_path
):
    """The skip used to end "and the next approval will merge".

    By the time the operator reads it the task is already `approved`, and restating a status is
    deliberately a no-op — so following the instruction provably did nothing. Measured on
    2026-08-14: committing the dirt and re-approving returned 200 with status `approved`, recorded
    no new attempt, and left the main branch where it was. Asserted through a real skip rather
    than by importing the constant, because comparing a string to itself is the one failure mode a
    wording change has.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "README.md").write_text("edited by the operator\n", encoding="utf-8")

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200

    reason = (await integrations(app, auth_headers, task))[0]["reason"]
    assert "retry the integration" in reason
    assert "next approval" not in reason
    assert "approve" not in reason.lower()


@pytest.mark.asyncio
async def test_untracked_files_do_not_block_the_merge(app, auth_headers, builder, tmp_path):
    """The Hub writes specification documents into the project directory, so any project that has
    ever had one carries untracked content essentially permanently.

    Counting that as "dirty" made the first version of this feature skip nearly every merge, and
    told the operator to clear a condition they could only clear by committing files the Hub had
    put there. Untracked files are also harmless: `git merge` refuses only over one it would
    overwrite, and that is caught as a failure rather than corrupting anything.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    (tmp_path / "scratch.txt").write_text("not tracked by anything\n", encoding="utf-8")
    assert git(tmp_path, "status", "--porcelain").stdout.strip(), "expected untracked content"

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200

    assert work in commits_on(tmp_path, "main")
    assert (await integrations(app, auth_headers, task))[0]["outcome"] == "merged"


@pytest.mark.asyncio
async def test_a_checkout_on_another_branch_skips_without_blocking(
    app, auth_headers, builder, tmp_path
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    # Left on the agent's branch rather than main.

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200
    assert work not in commits_on(tmp_path, "main")

    recorded = await integrations(app, auth_headers, task)
    assert recorded[0]["outcome"] == "skipped"
    assert AGENT_BRANCH in recorded[0]["reason"]
    assert "main" in recorded[0]["reason"]


@pytest.mark.asyncio
async def test_a_project_without_a_repository_approves_unchanged(
    app, auth_headers, builder, tmp_path
):
    """D7: a non-repository project is a supported shape, and must stay exactly as approvable."""
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    await accept_evidence(app, auth_headers, builder)

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200

    recorded = await integrations(app, auth_headers, task)
    assert recorded[0]["outcome"] == "skipped"
    assert "not a git repository" in recorded[0]["reason"]


@pytest.mark.asyncio
async def test_evidence_awaiting_review_merges_nothing(app, auth_headers, builder, tmp_path):
    """Only accepted evidence names a commit to merge. Merging on unreviewed evidence would make
    the review that gates the merge decorative.

    **The approval is now refused rather than allowed to record a skip** — changed by
    `approval-refuses-unaccepted-evidence` (F122), and the property this test names is unchanged and
    now stated more strongly. It used to assert that approval succeeded and recorded
    `NOTHING_TO_MERGE`, which was true of the merge and false about the world: the commit existed and
    was waiting for a person, and the task went terminal at `approved` with its work on a branch
    nothing merges. The refusal is what stops that, and the assertion that nothing reaches `main` is
    kept verbatim, because it is the half that was always the point.

    The full behaviour, including the acceptance that follows, lives in
    `test_approval_refuses_unaccepted_evidence.py`.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "not reviewed"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers)
    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    assert work not in commits_on(tmp_path, "main")

    assert await integrations(app, auth_headers, task) == []


# ---------------------------------------------------------------------------
# The record, and the boundary the whole feature rests on
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nothing_pushes(app, auth_headers, builder, tmp_path):
    """The single property that makes automatic merging safe: no remote is ever contacted.

    Asserted behaviourally against a configured remote that does not exist — a push would fail
    loudly — and by a source check, because "we did not call push" is a claim about the code rather
    than about one execution.
    """
    from pathlib import Path

    import hub.task_integration as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in ('"push"', "'push'", '"fetch"', '"remote"'):
        assert forbidden not in source, f"{forbidden} appears in task_integration.py"

    make_repo(tmp_path)
    git(tmp_path, "remote", "add", "origin", str(tmp_path / "nonexistent-remote.git"))
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200
    assert work in commits_on(tmp_path, "main")
    # A push would have failed against a remote path that does not exist; the merge succeeded.
    assert (await integrations(app, auth_headers, task))[0]["outcome"] == "merged"


@pytest.mark.asyncio
async def test_integration_records_are_append_only(app, auth_headers, builder, tmp_path):
    """No update path and no delete path. The system does not get to edit the account of what it
    wrote to the operator's repository."""
    from pathlib import Path

    routes = Path("hub/api/v1/tasks.py")
    if not routes.exists():  # pytest may run from the repo root or from hub/
        routes = Path("hub/hub/api/v1/tasks.py")
    source = routes.read_text(encoding="utf-8")
    assert "/integrations" in source
    for verb in ('@router.delete("/{task_id}/integrations', '@router.put("/{task_id}/integrations'):
        assert verb not in source

    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers)
    await approve(app, auth_headers, task)

    assert len(await integrations(app, auth_headers, task)) == 1
    assert (await app.delete(f"{TASKS}/{task}/integrations", headers=auth_headers)).status_code in (
        404,
        405,
    )


# ---------------------------------------------------------------------------
# The main branch is named, never inferred
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_detected_branch_is_only_a_suggestion(app, auth_headers, tmp_path):
    """The guess survives for reporting and stops short of writing. Nothing merges until an
    operator has accepted a name."""
    make_repo(tmp_path)

    response = await app.get(
        "/api/v1/projects/proj-test/main-branch-suggestion", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"suggestion": "main", "chosen": None, "is_repository": True}


@pytest.mark.asyncio
async def test_a_main_branch_that_does_not_exist_is_refused(app, auth_headers, tmp_path):
    """Refused where the operator is looking at the field, rather than becoming a skipped merge
    they discover days later."""
    make_repo(tmp_path)

    current = await app.get(SETTINGS, headers=auth_headers)
    assert current.status_code == 200, current.text

    refused = await app.put(
        SETTINGS, json={**current.json(), "main_branch": "nope"}, headers=auth_headers
    )
    assert refused.status_code == 400, refused.text
    assert "nope" in refused.json()["detail"]

    accepted = await app.put(
        SETTINGS, json={**current.json(), "main_branch": "main"}, headers=auth_headers
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["main_branch"] == "main"


@pytest.mark.asyncio
async def test_reporting_is_unchanged_when_no_branch_is_chosen(app, auth_headers, tmp_path):
    """Task 1.4: `MAIN_BRANCH_NAMES` keeps its reporting behaviour. The guess became illegal for
    writing, not for reading — an existing project's coverage answers must not move because this
    change was installed."""
    from hub import requirement_evidence

    make_repo(tmp_path)
    sha = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")

    # Unreachable from main, and reported so, with no project setting involved at all.
    assert requirement_evidence.is_reachable_from_main(tmp_path, sha) is False
    git(tmp_path, "checkout", "-q", "main")
    git(tmp_path, "merge", "-q", "--no-ff", "-m", "merge", AGENT_BRANCH)
    assert requirement_evidence.is_reachable_from_main(tmp_path, sha) is True
