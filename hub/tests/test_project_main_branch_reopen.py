"""A main branch the operator cleared stays cleared when the folder is opened again (F1016).

An empty `main_branch` means two things: "never chosen" and, once the operator has emptied the field
in Settings -> Integration, "nothing merges". `_adopt_detected_main_branch` could not tell them apart,
so reopening the folder wrote the detected branch over the operator's "nothing merges", recorded no
settings event, and merged the approved work that had been waiting. Told apart now by the settings
events: adoption happens only for a project whose main branch no event ever set or cleared, and is
itself recorded the way an operator's change is.
"""

# ruff: noqa: F811  (`builder` is an imported fixture, then a test argument)

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import EventLog, Project

from .test_project_open_adopts_main_branch import init_repo
from .test_task_integration import (  # noqa: F401  (builder is a fixture)
    AGENT_BRANCH,
    accept_evidence,
    approve,
    builder,
    commit_on_branch,
    commits_on,
    git,
    integrations,
    linked_task,
    make_document,
    make_repo,
)

SETTINGS = "/api/v1/projects/proj-test/settings"
OPEN = "/api/v1/projects/open"


async def _settings_events(project_id: str) -> list[dict]:
    """The `main_branch` entries of the project's settings events, oldest first."""
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(EventLog)
                    .where(
                        EventLog.project_id == project_id,
                        EventLog.event_type == "project_settings_updated",
                    )
                    .order_by(EventLog.timestamp)
                )
            )
            .scalars()
            .all()
        )
    return [
        row.data["changed"]["main_branch"] for row in rows if "main_branch" in row.data["changed"]
    ]


@pytest.mark.asyncio
async def test_a_cleared_main_branch_survives_reopening_and_nothing_merges(
    app, auth_headers, builder, bind_project_workspace, tmp_path
):
    make_repo(tmp_path, "master")
    await bind_project_workspace(tmp_path)
    await make_document(app, auth_headers, builder)

    # The operator names the branch, then empties the field: "nothing merges".
    named = await app.put(SETTINGS, json={"main_branch": "master"}, headers=auth_headers)
    assert named.status_code == 200, named.text
    cleared = await app.put(SETTINGS, json={"main_branch": None}, headers=auth_headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["main_branch"] is None

    work = commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    await accept_evidence(app, auth_headers, builder)
    git(tmp_path, "checkout", "-q", "master")
    task = await linked_task(app, auth_headers)
    assert (await approve(app, auth_headers, task)).status_code == 200
    assert [row["outcome"] for row in await integrations(app, auth_headers, task)] == ["skipped"]

    opened = await app.post(OPEN, json={"path": str(tmp_path)}, headers=auth_headers)

    assert opened.status_code == 200, opened.text
    settings = await app.get(SETTINGS, headers=auth_headers)
    assert settings.json()["main_branch"] in (None, "")
    assert work not in commits_on(tmp_path, "master")
    assert [row["outcome"] for row in await integrations(app, auth_headers, task)] == ["skipped"]


@pytest.mark.asyncio
async def test_a_project_that_never_chose_still_adopts_and_the_adoption_is_an_event(
    app, auth_headers, bind_project_workspace, tmp_path
):
    repo = init_repo(tmp_path / "repo")
    project = await bind_project_workspace(repo)
    assert await _settings_events(project.id) == [], "or this proves nothing"

    opened = await app.post(OPEN, json={"path": str(repo)}, headers=auth_headers)

    assert opened.status_code == 200, opened.text
    async with async_session_factory() as session:
        assert (await session.get(Project, project.id)).main_branch == "master"
    assert await _settings_events(project.id) == [{"was": None, "now": "master"}]


@pytest.mark.asyncio
async def test_reopening_twice_adopts_once(app, auth_headers, bind_project_workspace, tmp_path):
    repo = init_repo(tmp_path / "repo")
    project = await bind_project_workspace(repo)

    for _ in range(2):
        opened = await app.post(OPEN, json={"path": str(repo)}, headers=auth_headers)
        assert opened.status_code == 200, opened.text

    assert await _settings_events(project.id) == [{"was": None, "now": "master"}]
