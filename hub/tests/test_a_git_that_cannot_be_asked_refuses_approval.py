"""F424: when the approval gate cannot ask git, approval is refused with a stated reason, not a 500.

`task_integration._git` is a bare `subprocess.run(timeout=60)`, and the gate's merge question calls it
through `is_repository`, `branch_exists`, `task_branch_tip` and `would_conflict`. A `TimeoutExpired`
or `OSError` was neither a `TransitionRefusedError` nor a `TaskBindingError`, so every approval
surface (operator PATCH, land, the agent plane and MCP, which share the transition) answered a bare
500 after up to a minute. The operator's repair (2026-09-24): refuse, saying git could not be asked,
so nothing is approved that might not merge and the operator can retry.
"""

import subprocess
from unittest.mock import patch

import pytest

from hub import task_integration

from .test_conflict_refusal_names_what_clears_it import (
    builder,  # noqa: F401 - the fixture, used by name
    conflicted,
    drive_to,
)

TASKS = "/api/v1/projects/proj-test/tasks"


def _failing(error):
    def _git(*_args, **_kwargs):
        raise error

    return _git


ERRORS = [subprocess.TimeoutExpired(["git", "merge-tree"], 60), OSError("git is not installed")]


@pytest.mark.parametrize("error", ERRORS, ids=["timeout", "oserror"])
@pytest.mark.asyncio
async def test_operator_approval_is_refused_when_git_cannot_be_asked(
    app, auth_headers, builder, tmp_path, error  # noqa: F811
):
    task_id, _ = await conflicted(app, auth_headers, builder, tmp_path)
    await drive_to(
        app, auth_headers, task_id, "assigned", "in_progress", "completed", "under_review"
    )

    with patch.object(task_integration, "_git", _failing(error)):
        refused = await app.patch(
            f"{TASKS}/{task_id}", json={"status": "approved"}, headers=auth_headers
        )

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert "could not ask git" in detail
    assert type(error).__name__ in detail
    got = await app.get(f"{TASKS}/{task_id}", headers=auth_headers)
    assert got.json()["status"] == "under_review"


@pytest.mark.asyncio
async def test_landing_is_refused_when_git_cannot_be_asked(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task_id, _ = await conflicted(app, auth_headers, builder, tmp_path)
    await drive_to(app, auth_headers, task_id, "assigned", "in_progress", "completed")

    with patch.object(task_integration, "_git", _failing(ERRORS[0])):
        refused = await app.post(f"{TASKS}/{task_id}/land", headers=auth_headers)

    assert refused.status_code == 409, refused.text
    assert "could not ask git" in refused.text
    got = await app.get(f"{TASKS}/{task_id}", headers=auth_headers)
    assert got.json()["status"] == "completed"
