"""The approval preview asks the gate's merge question (F141;
`the-approval-preview-asks-the-gates-merge-question`, design D1).

A refusal for a conflict with the main branch named the commit and the paths, and then nothing
remembered it: the drawer's preview kept saying "whether it merges cleanly is checked at approval".
The preview now asks `git merge-tree` itself, through the gate's own preconditions and probe, so the
answer exists before the first approve and after a refusal, and is recomputed each time. It is never
stored, and a git failure is an answer, not a 500.
"""

import subprocess

import pytest

from hub import requirement_gate, task_integration

from .test_conflict_refusal_names_what_clears_it import (
    AGENT_BRANCH,
    ALPHA,
    BETA,
    accept_evidence,
    approve,
    builder,  # noqa: F401 - the fixture, used by name
    commit_on_branch,
    conflicted,
    git,
    linked_task,
    make_document,
    make_repo,
    resolve_on_branch,
    set_main_branch,
)
from .test_loop_lands_its_work import commit_on_task_branch, declare, loop_task, make_loop

TASKS = "/api/v1/projects/proj-test/tasks"


async def preview(app, auth_headers, task_id):
    response = await app.get(f"{TASKS}/{task_id}/integration-preview", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


def _hung(*_a, **_k):
    raise subprocess.TimeoutExpired(["git"], 60)


@pytest.mark.asyncio
async def test_the_preview_names_the_conflict_before_approval(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, judged = await conflicted(app, auth_headers, builder, tmp_path)
    main_before = git(tmp_path, "rev-parse", "main").stdout
    status_before = git(tmp_path, "status", "--porcelain").stdout

    answer = await preview(app, auth_headers, task)

    assert answer["conflicts"] == [
        {"commit_sha": judged, "source_branch": AGENT_BRANCH, "paths": ["shared.txt"]}
    ]
    assert "approval will be refused" in answer["reason"]
    assert "shared.txt" in answer["reason"] and judged[:12] in answer["reason"]
    # Asking changed no branch, no working tree, no index.
    assert git(tmp_path, "rev-parse", "main").stdout == main_before
    assert git(tmp_path, "status", "--porcelain").stdout == status_before


@pytest.mark.asyncio
async def test_the_preview_repeats_what_the_refusal_said(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, _ = await conflicted(app, auth_headers, builder, tmp_path)

    refused = await approve(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    unmergeable = refused.json()["detail"]["unmergeable"]

    answer = await preview(app, auth_headers, task)
    assert [(c["commit_sha"], c["paths"]) for c in answer["conflicts"]] == [
        (entry["commit_sha"], entry["paths"]) for entry in unmergeable
    ]


@pytest.mark.asyncio
async def test_once_resolved_the_preview_says_it_merges_cleanly(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, _ = await conflicted(app, auth_headers, builder, tmp_path)
    resolve_on_branch(tmp_path)
    await accept_evidence(app, auth_headers, builder, summary="re-ran after resolving")
    git(tmp_path, "checkout", "-q", "main")

    answer = await preview(app, auth_headers, task)

    assert answer["conflicts"] == []
    assert answer["reason"] == (
        "approval will merge one commit into main; it merges cleanly as of now"
    )


@pytest.mark.asyncio
async def test_work_already_on_main_is_not_counted_as_merging(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    """F522. On `:8010` the preview said "approval will merge 2 commits into master" for two
    commits already on master; approving then recorded `skipped`, "already in master". The preview
    now asks the reachability question the checks gate asks (F518)."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    commit_on_branch(tmp_path, AGENT_BRANCH, "alpha.txt", "alpha\n")
    await accept_evidence(app, auth_headers, builder, identifier="FR-1")
    git(tmp_path, "checkout", "-q", "main")
    git(tmp_path, "merge", "-q", "--no-ff", "-m", "landed elsewhere", AGENT_BRANCH)
    task = await linked_task(app, auth_headers)

    answer = await preview(app, auth_headers, task)

    assert answer["targets"] == []
    assert answer["will_attempt_merge"] is False
    assert "already in main" in answer["reason"]
    assert "will merge" not in answer["reason"]


@pytest.mark.asyncio
async def test_two_clean_targets_are_counted(app, auth_headers, builder, tmp_path):  # noqa: F811
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder, requirements=(ALPHA, BETA))
    await set_main_branch("main")
    commit_on_branch(tmp_path, AGENT_BRANCH, "alpha.txt", "alpha\n")
    await accept_evidence(app, auth_headers, builder, identifier="FR-1")
    git(tmp_path, "checkout", "-q", "main")
    commit_on_branch(tmp_path, "agentweave/other", "beta.txt", "beta\n")
    await accept_evidence(app, auth_headers, builder, identifier="FR-2")
    git(tmp_path, "checkout", "-q", "main")
    task = await linked_task(app, auth_headers, requirements=("FR-1", "FR-2"))

    answer = await preview(app, auth_headers, task)

    assert len(answer["targets"]) == 2, answer
    assert answer["conflicts"] == []
    assert answer["reason"] == (
        "approval will merge 2 commits into main; it merges cleanly as of now"
    )


@pytest.mark.asyncio
async def test_a_probe_that_raises_is_an_answer(
    app, auth_headers, builder, tmp_path, monkeypatch  # noqa: F811
):
    task, judged = await conflicted(app, auth_headers, builder, tmp_path)
    monkeypatch.setattr(task_integration, "would_conflict", _hung)

    answer = await preview(app, auth_headers, task)

    assert answer["conflicts"] is None
    # Governed: the database still names the target after git failed, and the hedge stands.
    assert [t["commit_sha"] for t in answer["targets"]] == [judged]
    assert "whether it merges cleanly is checked at approval" in answer["reason"]


@pytest.mark.asyncio
async def test_a_precondition_that_raises_is_an_answer(
    app, auth_headers, builder, tmp_path, monkeypatch  # noqa: F811
):
    task, judged = await conflicted(app, auth_headers, builder, tmp_path)
    monkeypatch.setattr(task_integration, "branch_exists", _hung)

    answer = await preview(app, auth_headers, task)

    assert answer["conflicts"] is None
    assert [t["commit_sha"] for t in answer["targets"]] == [judged]


async def _ungoverned_task_with_a_branch(app, auth_headers, tmp_path):
    make_repo(tmp_path)
    await set_main_branch("main")
    loop = await make_loop(app, auth_headers, name="Preview me")
    task = await loop_task(app, auth_headers, loop)
    commit_on_task_branch(tmp_path, task, "feature.py", "print(1)\n")
    git(tmp_path, "checkout", "-q", "main")
    return task


@pytest.mark.asyncio
async def test_git_failing_on_an_ungoverned_task_is_said_once(
    app, auth_headers, builder, tmp_path, monkeypatch  # noqa: F811
):
    """The listing used when the probe cannot run was outside any wrap for a task evidence does not
    govern: a hung git became a bare 500. It is asked once, and the failure is stated."""
    task = await _ungoverned_task_with_a_branch(app, auth_headers, tmp_path)
    calls = []

    def hung(*args, **_k):
        calls.append(args)
        raise subprocess.TimeoutExpired(["git"], 60)

    monkeypatch.setattr(task_integration, "_git", hung)
    answer = await preview(app, auth_headers, task)

    assert answer["conflicts"] is None
    assert answer["targets"] == []
    assert answer["will_attempt_merge"] is False
    assert answer["reason"] == task_integration.GIT_UNANSWERED
    assert answer["reason"] != task_integration.NO_TASK_BRANCH
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_the_ungoverned_listing_is_wrapped_on_its_own(
    app, auth_headers, builder, tmp_path, monkeypatch  # noqa: F811
):
    task = await _ungoverned_task_with_a_branch(app, auth_headers, tmp_path)

    async def not_asked(*_a, **_k):
        return None

    def broken(*_a, **_k):
        raise OSError("git is not there")

    monkeypatch.setattr(requirement_gate, "merge_situation", not_asked)
    monkeypatch.setattr(task_integration, "task_branch_tip", broken)
    answer = await preview(app, auth_headers, task)

    assert answer["reason"] == task_integration.GIT_UNANSWERED


@pytest.mark.asyncio
async def test_nothing_to_merge_is_never_read_as_merges_cleanly(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    """A merge situation with nothing to merge has no conflicts, and must still say nothing will
    merge (operator review, control 1.7)."""
    make_repo(tmp_path)
    await set_main_branch("main")
    loop = await make_loop(app, auth_headers, name="Evidence preview")
    await declare(loop, True)
    task = await loop_task(app, auth_headers, loop)
    commit_on_task_branch(tmp_path, task, "feature.py", "print(1)\n")
    git(tmp_path, "checkout", "-q", "main")

    answer = await preview(app, auth_headers, task)

    assert answer["reason"] == task_integration.NOTHING_TO_MERGE
    assert answer["targets"] == []
    assert answer["conflicts"] == []
    assert "merges cleanly" not in answer["reason"]
