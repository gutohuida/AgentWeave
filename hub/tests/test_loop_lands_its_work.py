"""A loop's approved work reaches the main branch, or the record says so (break 1, F124).

The defect: a loop with no spec document has no requirements, so its tasks carry no
`TaskRequirementLink`, so `integration_targets` is **structurally empty forever** — there is no
evidence that could ever be recorded against a requirement that does not exist. Approval therefore
records `no accepted evidence names a commit, so there is nothing to merge`, which is true about
the evidence and false about the world: the work is sitting on `agentweave/task/<id>`, committed,
approved, and unreachable from the main branch. Break 7 is the same defect one layer up — the
"Try again" button is offered for that skip, and pressing it appends an identical second skip.

**Every test in group 1 is written against unmodified code, and every one of them passes there.**
That is what makes them reproductions rather than assertions of an intention. Four of them are
guards that must go on passing afterwards, and two of those are the whole reason this file is
careful:

- `test_a_flow_task_merges_the_commit_its_evidence_names` (task 1.7) is what would have caught
  design D10 — `Loop` is the row for a **flow** as well as a loop, so a flat "a loop merges its
  branch tip" default would silently switch every flow onto its branch tip and degrade
  `approval-refuses-unaccepted-evidence` to an advisory product-wide.
- `test_a_documentless_loop_task_with_a_requirement_link_merges_its_evidence` (task 1.7a) is what
  would have caught design D11 — a documentless loop's task created with `requirement_ids` gets
  real links, and `record_evidence` resolves against the *project's* index rather than a document's,
  so that task **merges today**. Stopping the resolver at "does this loop have a document" would
  stop work that currently merges, with the record still saying `merged`.

Both write a **different** commit to the task's own branch than the one the evidence names, so the
two possible answers are distinguishable. A guard where both answers coincide proves nothing.
"""

import pytest
from sqlalchemy import select

from hub import task_integration, worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Loop, Run, SpecDocument, Task, TaskRequirementLink

from .test_task_integration import (
    AGENT_BRANCH,
    AGENT_EVIDENCE,
    BASE,
    PATH,
    TASKS,
    approve,
    commit_on_branch,
    commits_on,
    files_on,
    git,
    integrations,
    make_document,
    make_repo,
    set_main_branch,
)

JOBS = "/api/v1/projects/proj-test/jobs"


@pytest.fixture
async def builder():
    """The agent the loop's job names, and the run that records evidence.

    Declared here rather than imported: a fixture imported by name shadows itself in every
    signature that takes it, which is why ten sibling files each declare their own.
    """
    async with async_session_factory() as session:
        session.add(Agent(id="ag-loop-lands", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-loop-lands",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_loop_lands-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_loop_lands-secret"}


# ---------------------------------------------------------------------------
# Fixture helpers. Everything git-shaped is imported from `test_task_integration`; the only new
# part is the *task branch*, and that is where task 1.3's read-it-back rule is spent.
# ---------------------------------------------------------------------------


async def make_loop(app, auth_headers, *, name="Loop", document_id=None):
    """A `Loop` row, created the way the product creates one — through `POST /jobs`.

    `stop_when_queue_empties` is the opt-in that costs nothing else (`jobs._loop_opts_in`).
    Passing *document_id* is what makes the row a **flow** rather than a loop; nothing else in the
    schema distinguishes them, which is design D10's entire point.
    """
    body = {
        "name": name,
        "agent": "builder",
        "message": "work the queue",
        "cron": "0 2 * * *",
        "stop_when_queue_empties": True,
    }
    if document_id is not None:
        body["spec_document_id"] = document_id
    created = await app.post(JOBS, json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    loop = created.json()["loop"]
    assert loop is not None, created.json()
    return loop["id"]


async def make_flow_document(app, auth_headers, run_headers):
    """The imported document (`PATH`, one requirement `FR-1`), and the id a flow's `Loop` points at.

    Deliberately the *same* document the task's requirement resolves against: a flow whose loop
    names one document while its tasks link to another would be a shape the product never builds,
    and a guard about flows has to be about the flow shape that exists.
    """
    await make_document(app, auth_headers, run_headers)
    async with async_session_factory() as session:
        document = (
            await session.execute(
                select(SpecDocument).where(
                    SpecDocument.project_id == "proj-test", SpecDocument.path == PATH
                )
            )
        ).scalar_one()
    return document.id


async def loop_task(app, auth_headers, loop_id, *, title="Loop work", requirement_ids=None):
    """A task on *loop_id*'s queue, created by the operator (who is exempt from the loop's
    authorship gate), with its stored `loop_id` read back before anything is asserted about it."""
    body = {"title": title, "loop_id": loop_id}
    if requirement_ids is not None:
        body["requirement_ids"] = requirement_ids
    created = await app.post(TASKS, json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    async with async_session_factory() as session:
        row = await session.get(Task, task_id)
        assert row is not None
        assert row.loop_id == loop_id, f"task {task_id} was not attached to {loop_id}"
    return task_id


def commit_on_task_branch(root, task_id, filename, content, *, create=True):
    """Real work on the branch the product would have given this task.

    `worktrees.task_branch_name` rather than a literal, so a change to the naming scheme fails
    here instead of making these tests pass against a branch nothing reads.
    """
    return commit_on_branch(
        root, worktrees.task_branch_name(task_id), filename, content, create=create
    )


async def _links(task_id):
    async with async_session_factory() as session:
        result = await session.execute(
            select(TaskRequirementLink).where(TaskRequirementLink.task_id == task_id)
        )
        return list(result.scalars().all())


async def record_and_accept(app, auth_headers, run_headers, identifier, summary="ran the tests"):
    """Record evidence as the agent and accept it as the operator.

    The footprint is captured from the workspace's HEAD *at this moment*, so the caller checks out
    the branch whose commit it wants named before calling this.
    """
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": identifier, "summary": summary}, headers=run_headers
    )
    assert recorded.status_code == 201, recorded.text
    accepted = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text
    return recorded.json()["id"]


# ---------------------------------------------------------------------------
# 1.3 / 1.4 — the reproduction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_evidence_free_loop_task_approves_and_merges_nothing(
    app, auth_headers, builder, tmp_path
):
    """Break 1, measured: approval succeeds, records `nothing to merge`, and the work stays put.

    The fixture is read back before any behaviour is asserted — the loop row exists, the task
    carries its id, the task has no requirement link at all, and the branch really holds the
    commit. B-IMPL found two fixture defects this way, each of which would have made an assertion
    pass without the behaviour existing.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Documentless loop")
    async with async_session_factory() as session:
        row = await session.get(Loop, loop)
        assert row is not None and row.spec_document_id is None

    task = await loop_task(app, auth_headers, loop)
    assert await _links(task) == [], "the reproduction requires a task with no requirement link"

    work = commit_on_task_branch(tmp_path, task, "feature.py", "print('hi')\n")
    git(tmp_path, "checkout", "-q", "main")
    assert work in commits_on(tmp_path, worktrees.task_branch_name(task))
    assert work not in commits_on(tmp_path, "main")

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.SKIPPED]
    assert recorded[0]["reason"] == task_integration.NOTHING_TO_MERGE

    # The whole finding in two lines: approved, and the work is not in the product.
    assert work not in commits_on(tmp_path, "main")
    assert "feature.py" not in files_on(tmp_path, "main")


# ---------------------------------------------------------------------------
# 1.5 — break 7 at the API level: the button is offered and does nothing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrying_the_unmergeable_skip_appends_an_identical_skip(
    app, auth_headers, builder, tmp_path
):
    """Break 7, measured without a browser.

    `TaskIntegrationNote` offers "Try again" for every non-merged row whose reason is not the
    missing-main-branch sentence, so it offers it here. The retry route accepts it, re-runs the
    same resolution, and appends a second row identical in outcome and reason. Nothing the
    operator can do from that button will ever change the answer.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Retry loop")
    task = await loop_task(app, auth_headers, loop)
    commit_on_task_branch(tmp_path, task, "feature.py", "print('hi')\n")
    git(tmp_path, "checkout", "-q", "main")

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    retried = await app.post(f"{TASKS}/{task}/integrations/retry", headers=auth_headers)
    assert retried.status_code == 200, retried.text

    rows = retried.json()["integrations"]
    assert [row["outcome"] for row in rows] == [
        task_integration.SKIPPED,
        task_integration.SKIPPED,
    ]
    assert {row["reason"] for row in rows} == {task_integration.NOTHING_TO_MERGE}


# ---------------------------------------------------------------------------
# 1.7 — the guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_loop_task_with_no_loop_at_all_is_untouched(app, auth_headers, builder, tmp_path):
    """An ordinary task — no loop — keeps today's behaviour exactly.

    Arm 1 of the resolver. The commit on the task's own branch is deliberately present, so if a
    later change ever answered "branch tip" for a task with `loop_id IS NULL`, this fails.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    created = await app.post(TASKS, json={"title": "Ordinary work"}, headers=auth_headers)
    assert created.status_code == 201, created.text
    task = created.json()["id"]
    async with async_session_factory() as session:
        assert (await session.get(Task, task)).loop_id is None

    work = commit_on_task_branch(tmp_path, task, "ordinary.py", "x\n")
    git(tmp_path, "checkout", "-q", "main")

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.SKIPPED]
    assert recorded[0]["reason"] == task_integration.NOTHING_TO_MERGE
    assert work not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_flow_task_merges_the_commit_its_evidence_names(
    app, auth_headers, builder, tmp_path
):
    """Task 1.7 — the guard that would have caught design D10.

    A **flow** is a `Loop` row with a `spec_document_id`, and its `work_needs_evidence` is NULL for
    exactly the same reason a documentless loop's is: nothing sets it. A resolver that reads NULL
    as "merge the branch tip" would switch every flow in the product onto its branch tip, which is
    a commit no reviewer accepted.

    The task's own branch carries a *different, later* commit than the one the evidence names, so
    "merged the evidence" and "merged the tip" cannot be confused.
    """
    make_repo(tmp_path)
    document = await make_flow_document(app, auth_headers, builder)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="A flow", document_id=document)
    async with async_session_factory() as session:
        assert (await session.get(Loop, loop)).spec_document_id == document

    task = await loop_task(app, auth_headers, loop, requirement_ids=["FR-1"])
    assert len(await _links(task)) == 1, "the guard requires a real requirement link"

    demonstrated = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    await record_and_accept(app, auth_headers, builder, "FR-1")

    tip = commit_on_task_branch(tmp_path, task, "later.py", "not demonstrated\n")
    git(tmp_path, "checkout", "-q", "main")
    assert tip != demonstrated

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.MERGED]
    assert recorded[0]["commit_sha"] == demonstrated
    assert "feature.py" in files_on(tmp_path, "main")
    assert "later.py" not in files_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_documentless_loop_task_with_a_requirement_link_merges_its_evidence(
    app, auth_headers, builder, tmp_path
):
    """Task 1.7a — the guard that would have caught design D11.

    The population design decision D-B's `raise_it_if` fired on: a **documentless** loop whose task
    was created with `requirement_ids`. `resolve_identifiers` answers from the *project's* index,
    not the loop's document, so the links are real; `record_evidence` resolves the same way and does
    not 404. This task merges its evidence **today**, so switching it to its branch tip on the
    strength of "its loop has no document" would stop work that currently merges — and because
    `_targets` deliberately includes evidence another task recorded against a shared requirement, a
    per-task branch tip could not carry that commit at all.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Documentless, but linked")
    async with async_session_factory() as session:
        assert (await session.get(Loop, loop)).spec_document_id is None

    task = await loop_task(app, auth_headers, loop, requirement_ids=["FR-1"])
    links = await _links(task)
    assert len(links) == 1, f"the guard requires a real requirement link, got {links}"

    demonstrated = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    await record_and_accept(app, auth_headers, builder, "FR-1")

    tip = commit_on_task_branch(tmp_path, task, "later.py", "not demonstrated\n")
    git(tmp_path, "checkout", "-q", "main")
    assert tip != demonstrated

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.MERGED]
    assert recorded[0]["commit_sha"] == demonstrated
    assert "feature.py" in files_on(tmp_path, "main")
    assert "later.py" not in files_on(tmp_path, "main")
