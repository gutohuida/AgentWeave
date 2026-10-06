"""F520 acceptance: a task's accepted evidence lands through that task's own approval, never earlier
through a sibling that serves the same requirement.

Driven on the trial Hub `:8010` (2026-10-06, the F510 slice): task 1 was approved and merged; task 2
served the same FR-1..3 and was still `under_review`, its checks never having passed. The operator
accepted task 2's evidence, `integrate_what_was_waiting_for_this_evidence` re-ran task 1's
integration, and task 1's merge targets -- every accepted footprint for its requirements, whoever
recorded it -- put task 2's two commits on master. Task 2's review verdict and its checks gate were
both bypassed. This file is the reproduction, through the real routes and a real repository.
"""

import pytest

from .test_task_integration import (
    AGENT_EVIDENCE,
    BASE,
    approve,
    builder,  # noqa: F401 - fixture
    commit_on_branch,
    commits_on,
    git,
    integrations,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)


async def _evidence(app, auth_headers, run_headers, task_id, summary):
    """Recorded by the task's own run while its branch is checked out, then accepted."""
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": summary, "task_id": task_id},
        headers=run_headers,
    )
    assert recorded.status_code == 201, recorded.text
    return recorded.json()["id"]


async def _accept(app, auth_headers, evidence_id):
    accepted = await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text


async def _two_tasks_first_landed(app, auth_headers, builder, root):  # noqa: F811
    make_repo(root)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")

    first = await linked_task(app, auth_headers, title="Tests")
    one = commit_on_branch(root, "agentweave/task/one", "one.py", "x = 1\n")
    await _accept(app, auth_headers, await _evidence(app, auth_headers, builder, first, "one"))
    git(root, "checkout", "-q", "main")
    assert (await approve(app, auth_headers, first)).status_code == 200
    assert one in commits_on(root, "main")

    second = await linked_task(app, auth_headers, title="Fix")
    two = commit_on_branch(root, "agentweave/task/two", "two.py", "y = 2\n")
    evidence = await _evidence(app, auth_headers, builder, second, "two")
    git(root, "checkout", "-q", "main")
    return first, second, two, evidence


@pytest.mark.asyncio
async def test_accepting_a_siblings_evidence_does_not_land_it_through_an_approved_task(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    first, second, two, evidence = await _two_tasks_first_landed(
        app, auth_headers, builder, tmp_path
    )

    await _accept(app, auth_headers, evidence)

    assert two not in commits_on(tmp_path, "main"), "task 2's work landed without its approval"
    merged_by_first = [
        row for row in await integrations(app, auth_headers, first) if row["outcome"] == "merged"
    ]
    assert [row["commit_sha"] for row in merged_by_first] != [] and two not in {
        row["commit_sha"] for row in merged_by_first
    }


@pytest.mark.asyncio
async def test_the_siblings_own_approval_lands_it(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    first, second, two, evidence = await _two_tasks_first_landed(
        app, auth_headers, builder, tmp_path
    )
    await _accept(app, auth_headers, evidence)

    assert (await approve(app, auth_headers, second)).status_code == 200
    assert two in commits_on(tmp_path, "main")
    assert "merged" in [row["outcome"] for row in await integrations(app, auth_headers, second)]
