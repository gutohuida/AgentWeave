"""Opening a repository takes the branch the repository already names.

`GET /projects/{id}/main-branch-suggestion` could answer `"master"` the instant a repository was
opened, and the project's `main_branch` stayed null until the operator went to settings and confirmed
that same answer by hand (`scripts/drive/FINDINGS.md`, F4). Everything that needs a base branch —
worktree isolation, conflict detection, evidence footprint re-stamping, and above all the merge that
approval performs — was degraded until they did, with nothing on screen saying so.

Note `ProjectSummary`, which is what `POST /projects/open` answers with, has never carried
`main_branch` at all; the field is read through `GET /projects/{id}/settings` and through the
suggestion route's `chosen`. So these assert on the stored value, which is the thing that was wrong.
"""

import subprocess
from pathlib import Path

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Project


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)


def init_repo(path: Path, branch: str = "master") -> Path:
    """A repository on *branch* with one commit.

    `master` deliberately, not `main`: it is the *second* name `MAIN_BRANCH_NAMES` tries, so a test
    cannot pass by accident of ordering.
    """
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", branch)
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "test")
    (path / "README.md").write_text("base\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "base")
    return path


async def stored_main_branch(project_id: str):
    async with async_session_factory() as session:
        return (await session.get(Project, project_id)).main_branch


@pytest.mark.asyncio
async def test_opening_a_repository_adopts_its_main_branch(
    app, auth_headers, bind_project_workspace, tmp_path
) -> None:
    repo = init_repo(tmp_path / "repo")
    project = await bind_project_workspace(repo)
    assert await stored_main_branch(project.id) is None, "or this proves nothing"

    opened = await app.post("/api/v1/projects/open", json={"path": str(repo)}, headers=auth_headers)

    assert opened.status_code == 200, opened.text
    assert await stored_main_branch(opened.json()["id"]) == "master"

    suggestion = await app.get(
        f"/api/v1/projects/{opened.json()['id']}/main-branch-suggestion", headers=auth_headers
    )
    assert suggestion.json() == {"suggestion": "master", "chosen": "master", "is_repository": True}


@pytest.mark.asyncio
async def test_reopening_does_not_overwrite_a_chosen_branch(
    app, auth_headers, bind_project_workspace, tmp_path
) -> None:
    """Re-opening is the ordinary way a project is reached after the first time. A branch the
    operator chose is a statement, and adoption must only ever fill a null."""
    repo = init_repo(tmp_path / "repo")
    project = await bind_project_workspace(repo)
    git(repo, "branch", "release")
    async with async_session_factory() as session:
        row = await session.get(Project, project.id)
        row.main_branch = "release"
        await session.commit()

    opened = await app.post("/api/v1/projects/open", json={"path": str(repo)}, headers=auth_headers)

    assert opened.status_code == 200, opened.text
    assert await stored_main_branch(opened.json()["id"]) == "release"


@pytest.mark.asyncio
async def test_opening_a_plain_directory_adopts_nothing(
    app, auth_headers, bind_project_workspace, tmp_path
) -> None:
    """A project without a repository is a supported first-class case, and there is no branch to
    take. It must open exactly as before rather than acquire an invented one."""
    plain = tmp_path / "plain"
    plain.mkdir()
    project = await bind_project_workspace(plain)

    opened = await app.post(
        "/api/v1/projects/open", json={"path": str(plain)}, headers=auth_headers
    )

    assert opened.status_code == 200, opened.text
    assert await stored_main_branch(project.id) is None
