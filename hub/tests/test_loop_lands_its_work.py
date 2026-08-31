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
async def test_an_evidence_free_loop_tasks_work_reaches_the_main_branch(
    app, auth_headers, builder, tmp_path
):
    """Break 1, closed. This is the reproduction, flipped.

    It was committed first asserting the defect — `outcome='skipped'`, reason
    `NOTHING_TO_MERGE`, and the commit sitting on `agentweave/task/<id>` unreachable from `main`
    (commit `4ce13c9`, which is where the measurement lives). The declaration and the resolver turn
    those same three assertions over: the branch tip merges, and approval finally means what the
    record says.

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
    assert [row["outcome"] for row in recorded] == [task_integration.MERGED]
    assert recorded[0]["commit_sha"] == work
    assert recorded[0]["target_branch"] == "main"

    # The whole change in two lines: approved, and the work is in the product.
    assert work in commits_on(tmp_path, "main")
    assert "feature.py" in files_on(tmp_path, "main")


# ---------------------------------------------------------------------------
# 1.5 — break 7 at the API level: the button is offered and does nothing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrying_after_the_work_merged_says_so_rather_than_repeating_a_skip(
    app, auth_headers, builder, tmp_path
):
    """Break 7's measurement, flipped by break 1's fix.

    As committed at `4ce13c9` this asserted the defect: two identical `skipped` rows reading `no
    accepted evidence names a commit`, because pressing "Try again" re-ran a resolution that could
    never produce a different answer. With the merge target resolved from the task's own branch,
    the first attempt merges and the retry says the honest thing instead — the commit is already
    in the target.

    Break 7 itself is not closed here. What is offered for an unretryable reason is group 6's
    subject; this is the API-level record that the button no longer sits on top of a skip that
    nothing could ever clear.
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
        task_integration.MERGED,
        task_integration.SKIPPED,
    ]
    assert rows[1]["reason"] == task_integration.ALREADY_INTEGRATED.format(
        commit=rows[0]["commit_sha"][:12], target="main"
    )


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


async def declare(loop_id, value):
    """Set the loop's declaration directly.

    Group 3 puts this on `POST /jobs`; the resolver is what these tests are about, and reaching it
    through a route that does not exist yet would only mean these tests could not be written until
    after the thing they guard.
    """
    async with async_session_factory() as session:
        loop = await session.get(Loop, loop_id)
        loop.work_needs_evidence = value
        await session.commit()


@pytest.mark.asyncio
async def test_a_loop_that_declares_it_needs_evidence_merges_nothing_without_any(
    app, auth_headers, builder, tmp_path
):
    """Task 1.7's first clause and 4.3b: the operator's word wins over the documentless default.

    Same fixture as the reproduction, one column different. The reason is the evidence one, not
    `NO_TASK_BRANCH`, because on this loop evidence is what governs — and telling the operator the
    task has no branch when it plainly has one would be the wrong sentence.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Evidence, please")
    await declare(loop, True)
    task = await loop_task(app, auth_headers, loop)

    work = commit_on_task_branch(tmp_path, task, "feature.py", "print(1)\n")
    git(tmp_path, "checkout", "-q", "main")

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.SKIPPED]
    assert recorded[0]["reason"] == task_integration.NOTHING_TO_MERGE
    assert work not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_declaration_of_no_evidence_wins_over_a_requirement_link(
    app, auth_headers, builder, tmp_path
):
    """Task 4.3d's second half: arm 3 beats arm 5.

    The same task as the D11 guard — documentless loop, real requirement link, accepted evidence —
    with the loop declaring that its work needs none. The branch tip is what the record names as
    the target, which is the operator's declaration being obeyed *against* the product's own
    default rather than merely alongside it.
    """
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Declared, and linked")
    await declare(loop, False)
    task = await loop_task(app, auth_headers, loop, requirement_ids=["FR-1"])
    assert len(await _links(task)) == 1

    demonstrated = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print(1)\n")
    await record_and_accept(app, auth_headers, builder, "FR-1")

    tip = commit_on_task_branch(tmp_path, task, "later.py", "the tip\n")
    git(tmp_path, "checkout", "-q", "main")
    assert tip != demonstrated

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.MERGED]
    assert recorded[0]["commit_sha"] == tip
    assert "later.py" in files_on(tmp_path, "main")
    # The task branch descends from the demonstrated commit, so that commit rides along — honestly,
    # and `rode_along_commits` is what says so. What this test pins is the *target*, asserted above.
    assert demonstrated in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_flow_task_with_only_awaiting_evidence_is_still_refused(
    app, auth_headers, builder, tmp_path
):
    """4.3b, the regression D10 describes, caught at the gate rather than at the merge.

    If a flow ever resolved to its branch tip, this approval would succeed and merge a commit no
    reviewer had accepted — `approval-refuses-unaccepted-evidence` would still exist and would
    simply never fire. The refusal is the observable that proves evidence still governs a flow.
    """
    make_repo(tmp_path)
    document = await make_flow_document(app, auth_headers, builder)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="A flow again", document_id=document)
    task = await loop_task(app, auth_headers, loop, requirement_ids=["FR-1"])

    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print(1)\n")
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    commit_on_task_branch(tmp_path, task, "later.py", "the tip\n")
    git(tmp_path, "checkout", "-q", "main")

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "gate_unsatisfied"
    assert refused.json()["detail"]["unaccepted"], refused.json()
    assert "later.py" not in files_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_grandfathered_loop_task_skips_and_no_agent_branch_is_merged(
    app, auth_headers, builder, tmp_path
):
    """4.6: `NO_TASK_BRANCH`, and emphatically not the agent's branch.

    A task stamped `workspace_scheme='agent'` by migration `0095` has no branch of its own and
    never will. The agent branch it actually worked on carries every task that agent ever touched,
    so falling back to it would ship other people's unreviewed work — the one thing this module
    refuses to do. The assertion is about the repository, not only the outcome string: a `skipped`
    recorded while the agent branch was merged anyway would pass a weaker test.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Grandfathered")
    task = await loop_task(app, auth_headers, loop)
    async with async_session_factory() as session:
        row = await session.get(Task, task)
        row.workspace_scheme = "agent"
        await session.commit()

    somebody_elses = commit_on_branch(tmp_path, AGENT_BRANCH, "other-task.py", "not mine\n")
    git(tmp_path, "checkout", "-q", "main")

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.SKIPPED]
    assert recorded[0]["reason"] == task_integration.NO_TASK_BRANCH
    assert somebody_elses not in commits_on(tmp_path, "main")
    assert "other-task.py" not in files_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_commit_made_after_approval_stays_out(app, auth_headers, builder, tmp_path):
    """4.6: what merged is the tip approval saw, not the branch.

    The evidence route's own `test_later_commits_on_the_branch_are_not_merged` makes this claim for
    a commit; this makes it for a branch tip, where the temptation to merge the *ref* is stronger
    because a ref is what was resolved.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Still working")
    task = await loop_task(app, auth_headers, loop)
    first = commit_on_task_branch(tmp_path, task, "first.py", "one\n")
    git(tmp_path, "checkout", "-q", "main")

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text
    assert first in commits_on(tmp_path, "main")

    later = commit_on_task_branch(tmp_path, task, "second.py", "two\n", create=False)
    git(tmp_path, "checkout", "-q", "main")
    assert later not in commits_on(tmp_path, "main")
    assert "second.py" not in files_on(tmp_path, "main")


# ---------------------------------------------------------------------------
# 4.8 — the preview
# ---------------------------------------------------------------------------


async def preview(app, auth_headers, task_id):
    response = await app.get(f"{TASKS}/{task_id}/integration-preview", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_the_preview_names_the_branch_tip_for_an_evidence_free_loop_task(
    app, auth_headers, builder, tmp_path
):
    """4.8: the drawer stops saying "nothing will merge" beside a button that merges."""
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Preview me")
    task = await loop_task(app, auth_headers, loop)
    tip = commit_on_task_branch(tmp_path, task, "feature.py", "print(1)\n")
    git(tmp_path, "checkout", "-q", "main")

    answer = await preview(app, auth_headers, task)
    assert answer["will_merge"] is True
    assert answer["reason"] == ""
    assert answer["targets"] == [
        {"commit_sha": tip, "source_branch": worktrees.task_branch_name(task)}
    ]


@pytest.mark.asyncio
async def test_the_preview_is_unchanged_where_evidence_governs(
    app, auth_headers, builder, tmp_path
):
    """4.8's other half, and the condition design D5 put on the change: an evidence-governed task's
    preview stays exactly as worded — and, unassertable here but stated there, exactly as cheap."""
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Evidence preview")
    await declare(loop, True)
    task = await loop_task(app, auth_headers, loop)
    commit_on_task_branch(tmp_path, task, "feature.py", "print(1)\n")
    git(tmp_path, "checkout", "-q", "main")

    answer = await preview(app, auth_headers, task)
    assert answer["will_merge"] is False
    assert answer["reason"] == task_integration.NOTHING_TO_MERGE
    assert answer["targets"] == []


@pytest.mark.asyncio
async def test_the_preview_says_no_branch_rather_than_no_evidence(
    app, auth_headers, builder, tmp_path
):
    """The empty case has two spellings on the two routes, and the preview uses the right one."""
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="No branch yet")
    task = await loop_task(app, auth_headers, loop)

    answer = await preview(app, auth_headers, task)
    assert answer["will_merge"] is False
    assert answer["reason"] == task_integration.NO_TASK_BRANCH


# ---------------------------------------------------------------------------
# 5.3 / 5.4 — the gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_conflicting_task_branch_refuses_approval(app, auth_headers, builder, tmp_path):
    """5.3: the same refusal the evidence route gets, for the branch-tip route.

    The gate sees what will merge, which is one change rather than a second rule (design D8). Had
    `_merge_situation` stayed on `integration_targets`, this approval would succeed, the merge
    would fail afterwards, and the operator would meet the conflict in a record instead of in a
    refusal that names the file.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Conflicting")
    task = await loop_task(app, auth_headers, loop)
    commit_on_task_branch(tmp_path, task, "shared.txt", "from the agent\n")

    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "shared.txt").write_text("from the operator\n", encoding="utf-8")
    git(tmp_path, "add", "shared.txt")
    git(tmp_path, "commit", "-q", "-m", "the operator's own change")
    head_before = git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    body = refused.json()["detail"]
    assert body["code"] == "gate_unsatisfied"
    assert "shared.txt" in str(body["unmergeable"])

    fetched = await app.get(f"{TASKS}/{task}", headers=auth_headers)
    assert fetched.json()["status"] == "under_review"
    assert git(tmp_path, "rev-parse", "HEAD").stdout.strip() == head_before
    assert await integrations(app, auth_headers, task) == []


@pytest.mark.asyncio
async def test_no_configured_main_branch_approves_exactly_as_before(
    app, auth_headers, builder, tmp_path
):
    """5.4: `_merge_situation` returns `None` and nothing refuses.

    A project with no merge target chosen stays exactly as approvable as it was before any of this
    existed. The new resolver must not turn a supported project shape into a refusal.
    """
    make_repo(tmp_path)
    # Deliberately no main branch set.

    loop = await make_loop(app, auth_headers, name="No target")
    task = await loop_task(app, auth_headers, loop)
    commit_on_task_branch(tmp_path, task, "feature.py", "print(1)\n")
    git(tmp_path, "checkout", "-q", "main")

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.SKIPPED]
    assert recorded[0]["reason"] == task_integration.NO_MAIN_BRANCH
