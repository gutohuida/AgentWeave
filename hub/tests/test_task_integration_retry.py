"""A skip is not the end of it.

Integration runs on the transition *into* `approved`, and restating a status is deliberately a
no-op — so before this every skip was terminal. Three of the six reasons name a remediation the
operator can perform, and performing it accomplished nothing: the loop-7 run set the main branch
the skip had asked for and watched nothing happen. Recovery meant walking the task back through
`revision_needed`, which no agent can do and which falsifies the review history.

The helpers come from `test_task_integration.py`, which owns this area's fixtures.
"""

from unittest.mock import AsyncMock, patch

import pytest

from hub import task_integration
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run

from .test_task_integration import (
    AGENT_BRANCH,
    SETTINGS,
    TASKS,
    accept_evidence,
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


@pytest.fixture
async def builder():
    """Defined here rather than imported: importing a fixture shadows the parameter of the same
    name in every helper below, and pytest resolves fixtures by module namespace anyway."""
    async with async_session_factory() as session:
        session.add(Agent(id="ag-retry", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-retry",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_retry-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_retry-secret"}


RETRY = TASKS + "/{}/integrations/retry"
AGENT_RETRY = "/api/v1/agent-actions/tasks/{}/integrations/retry"
AGENT_INTEGRATIONS = "/api/v1/agent-actions/tasks/{}/integrations"


async def approved_task_with_work(app, auth_headers, builder, tmp_path, *, main_branch=None):
    """An approved task whose accepted evidence names a commit on the agent's branch."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    if main_branch:
        await set_main_branch(main_branch)

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200
    return task, work


@pytest.mark.asyncio
async def test_retry_merges_work_a_skip_left_behind(app, auth_headers, builder, tmp_path):
    """The loop-7 sequence exactly: approve with no branch named, name one, and the work lands."""
    task, work = await approved_task_with_work(app, auth_headers, builder, tmp_path)
    assert work not in commits_on(tmp_path, "main"), "the skip must be real or this proves nothing"

    await set_main_branch("main")
    retried = await app.post(RETRY.format(task), headers=auth_headers)
    assert retried.status_code == 200, retried.text

    assert work in commits_on(tmp_path, "main")
    assert [row["outcome"] for row in retried.json()["integrations"]] == ["skipped", "merged"]


@pytest.mark.asyncio
async def test_retry_refuses_a_task_that_is_not_approved(app, auth_headers, builder, tmp_path):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)

    refused = await app.post(RETRY.format(task), headers=auth_headers)
    assert refused.status_code == 409, refused.text
    assert "approved" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_retry_after_a_merge_records_already_integrated_and_merges_nothing(
    app, auth_headers, builder, tmp_path
):
    """Asked of the repository, not of the attempt log.

    `integrate` self-guards on reachability, so a second press is honest rather than refused.
    """
    task, work = await approved_task_with_work(
        app, auth_headers, builder, tmp_path, main_branch="main"
    )
    assert work in commits_on(tmp_path, "main")
    before = commits_on(tmp_path, "main")

    retried = await app.post(RETRY.format(task), headers=auth_headers)
    assert retried.status_code == 200, retried.text

    rows = retried.json()["integrations"]
    assert [row["outcome"] for row in rows] == ["merged", "skipped"]
    assert "already in" in rows[-1]["reason"]
    assert commits_on(tmp_path, "main") == before, "a retry must not merge twice"


@pytest.mark.asyncio
async def test_the_agent_plane_can_read_and_retry(app, auth_headers, builder, tmp_path):
    """`NOTHING_TO_MERGE` is the one skip an agent can genuinely clear, so it gets the route.

    The read is offered with it: an agent that can retry but cannot see the outcome retries blind.
    """
    task, work = await approved_task_with_work(app, auth_headers, builder, tmp_path)
    assert work not in commits_on(tmp_path, "main")

    readable = await app.get(AGENT_INTEGRATIONS.format(task), headers=builder)
    assert readable.status_code == 200, readable.text
    assert [row["outcome"] for row in readable.json()["integrations"]] == ["skipped"]

    await set_main_branch("main")
    retried = await app.post(AGENT_RETRY.format(task), headers=builder)
    assert retried.status_code == 200, retried.text
    assert work in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_the_agent_plane_refuses_another_projects_task(app, auth_headers, builder, tmp_path):
    """The agent plane is scoped to the actor's own project, as every route on it is."""
    from hub.db.engine import async_session_factory
    from hub.db.models import Project, Task

    task, _ = await approved_task_with_work(app, auth_headers, builder, tmp_path)
    async with async_session_factory() as session:
        session.add(Project(id="proj-elsewhere", name="Elsewhere"))
        await session.commit()
        moved = await session.get(Task, task)
        moved.project_id = "proj-elsewhere"
        await session.commit()

    refused = await app.post(AGENT_RETRY.format(task), headers=builder)
    assert refused.status_code == 404, refused.text
    unreadable = await app.get(AGENT_INTEGRATIONS.format(task), headers=builder)
    assert unreadable.status_code == 404, unreadable.text


@pytest.mark.asyncio
async def test_setting_a_main_branch_merges_what_was_waiting_for_one(
    app, auth_headers, builder, tmp_path
):
    """Saving the setting discharges the instruction the skip gave.

    Before this, following "choose one in the project's settings" did nothing at all.
    """
    task, work = await approved_task_with_work(app, auth_headers, builder, tmp_path)
    assert work not in commits_on(tmp_path, "main")

    saved = await app.put(SETTINGS, json={"main_branch": "main"}, headers=auth_headers)
    assert saved.status_code == 200, saved.text

    assert work in commits_on(tmp_path, "main"), "the merge must happen on save"
    assert [row["outcome"] for row in await integrations(app, auth_headers, task)] == [
        "skipped",
        "merged",
    ]


@pytest.mark.asyncio
async def test_setting_a_main_branch_leaves_a_dirty_checkout_skip_alone(
    app, auth_headers, builder, tmp_path
):
    """Naming a branch says nothing about the state of the checkout."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "README.md").write_text("edited by the operator\n", encoding="utf-8")

    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200
    assert (await integrations(app, auth_headers, task))[0]["outcome"] == "skipped"

    # A *different* branch, so the save is a real change and the sweep genuinely runs.
    git(tmp_path, "branch", "trunk", "main")
    saved = await app.put(SETTINGS, json={"main_branch": "trunk"}, headers=auth_headers)
    assert saved.status_code == 200, saved.text

    assert len(await integrations(app, auth_headers, task)) == 1, "no second attempt was wanted"


@pytest.mark.asyncio
async def test_a_settings_save_survives_a_failing_retry(app, auth_headers, builder, tmp_path):
    """The operator changed a setting. That stands or falls on its own terms."""
    await approved_task_with_work(app, auth_headers, builder, tmp_path)

    boom = AsyncMock(side_effect=RuntimeError("git exploded"))
    with patch("hub.task_integration.tasks_skipped_for_want_of_a_main_branch", boom):
        saved = await app.put(SETTINGS, json={"main_branch": "main"}, headers=auth_headers)
    assert saved.status_code == 200, saved.text

    reread = await app.get(SETTINGS, headers=auth_headers)
    assert reread.json()["main_branch"] == "main", "the setting must have been saved"


@pytest.mark.asyncio
async def test_apply_transition_still_integrates_through_the_public_function(
    app, auth_headers, builder, tmp_path
):
    """Pins the rename. Approval must keep merging through the coroutine the retry also uses."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")
    task = await linked_task(app, auth_headers)

    spy = AsyncMock(return_value=[])
    with patch("hub.task_transition_service.integrate_task", spy):
        assert (await approve(app, auth_headers, task)).status_code == 200
    spy.assert_awaited_once()


# ---------------------------------------------------------------------------
# 6.2a / 6.7 — retryability is decided by the Hub, and it answers for every reason
# ---------------------------------------------------------------------------


def test_is_retryable_answers_for_every_skip_reason():
    """The totality guard (design D7), and the reason the inverted default is safe.

    An unclassified reason is **not** retryable, deliberately: the defect being fixed is a button
    appearing on a reason nobody thought about. That default is only safe if adding a tenth reason
    without classifying it is loud, which is what this asserts — every member of `SKIP_REASONS`,
    with the templates formatted first, gets a definite answer.

    It also pins the split. Three of the reasons are `.format()` templates, so a classifier keyed on
    the constants would drop the dirty checkout — the single most retryable outcome there is — into
    "unclassified", which is the defect reproduced one layer down.
    """
    filled = {
        task_integration.CHECKOUT_ELSEWHERE.format(current="feature", target="main"),
        task_integration.ALREADY_INTEGRATED.format(commit="abc123def456", target="main"),
        task_integration.WORKSPACE_UNAVAILABLE.format(error="the directory is gone"),
    }
    reasons = {reason for reason in task_integration.SKIP_REASONS if "{" not in reason} | filled
    assert len(reasons) == len(task_integration.SKIP_REASONS), "a template was left unformatted"

    answers = {
        reason: task_integration.is_retryable(task_integration.SKIPPED, reason)
        for reason in reasons
    }
    assert all(isinstance(answer, bool) for answer in answers.values())

    retryable = {reason for reason, answer in answers.items() if answer}
    assert retryable == {
        task_integration.CHECKOUT_DIRTY,
        task_integration.CHECKOUT_ELSEWHERE.format(current="feature", target="main"),
        task_integration.WORKSPACE_UNAVAILABLE.format(error="the directory is gone"),
    }, answers


def test_a_failed_merge_is_retryable_whatever_it_says():
    """Answered on the outcome, before the reason is consulted.

    A `failed` row carries git's own stderr, truncated — it can never be matched, so classifying it
    by reason would lose the button on the outcome that most deserves one. The merge was tested
    clean at approval, so a failure means the world moved, and it can move back.
    """
    assert task_integration.is_retryable(task_integration.FAILED, "CONFLICT (add/add): x.py")
    assert task_integration.is_retryable(task_integration.FAILED, "")
    # And a merge is never retryable: there is nothing to repeat.
    assert not task_integration.is_retryable(task_integration.MERGED, "")


@pytest.mark.asyncio
async def test_the_read_and_retry_routes_both_carry_retryable(app, auth_headers, builder, tmp_path):
    """6.7: one shape, both routes — which is what `_integration_view`'s docstring promises."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    # Deliberately no main branch: an unretryable skip, and the one the UI used to special-case by
    # matching its sentence.
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")

    task = await linked_task(app, auth_headers)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    read = await app.get(f"{TASKS}/{task}/integrations", headers=auth_headers)
    assert read.status_code == 200, read.text
    assert [row["retryable"] for row in read.json()["integrations"]] == [False]

    # 6.7's other half, and the one that matters: the requirement constrains what is *offered*, not
    # what is permitted. Narrowing the route would breach the shipped sentence saying retrying is
    # available to the operator and to agents for any approved task.
    retried = await app.post(f"{TASKS}/{task}/integrations/retry", headers=auth_headers)
    assert retried.status_code == 200, retried.text
    rows = retried.json()["integrations"]
    assert len(rows) == 2
    assert [row["retryable"] for row in rows] == [False, False]


@pytest.mark.asyncio
async def test_a_dirty_checkout_skip_is_offered_a_retry(app, auth_headers, builder, tmp_path):
    """The positive case, through the route rather than the predicate — a skip whose sentence names
    a remediation must carry the flag that puts the button on screen."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "README.md").write_text("the operator is mid-edit\n", encoding="utf-8")

    task = await linked_task(app, auth_headers)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    read = await app.get(f"{TASKS}/{task}/integrations", headers=auth_headers)
    rows = read.json()["integrations"]
    assert [row["outcome"] for row in rows] == ["skipped"]
    assert rows[0]["reason"] == task_integration.CHECKOUT_DIRTY
    assert rows[0]["retryable"] is True
