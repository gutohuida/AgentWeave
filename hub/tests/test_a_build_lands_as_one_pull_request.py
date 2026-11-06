"""A build lands as one pull request (`a-build-lands-as-one-pull-request`), task `settings`.

FR-1 (off-by-default): PR landing is off in every project until the operator turns it on, and a
Build request naming landing 'pull_request' in a project with it off is refused naming the setting.
FR-2 (needs-github): turning it on, and starting such a build, are refused naming which of a GitHub
remote, the GitHub CLI and its login is missing. The CLI is the real `shutil.which` lookup over a
PATH holding only git and, where a test wants one, a stub `gh` that answers `auth status`.
FR-7 (squash-setting): the single-commit choice is a stored project setting (its push behaviour is
task `push`'s, in `test_a_build_lands_as_one_pull_request_push.py`).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys

import pytest

from hub import pull_requests
from hub.db.engine import async_session_factory
from hub.db.models import Build, Project

from .test_a_build_has_a_driver_a_level_and_its_people import (
    _approved,
    _build,
    _document,
    _read,
    _roster_rows,
    _rows,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_task_integration import git, make_repo, set_main_branch

SETTINGS = "/api/v1/projects/proj-test/settings"
GITHUB_URL = "https://github.com/example/example.git"


def _only_git_on_path(monkeypatch, tmp_path, *, gh_exit=None):
    """PATH holding git's directory and, with *gh_exit*, a stub `gh` exiting with it."""
    git_exe = shutil.which("git")
    assert git_exe, "git is needed for these tests"
    dirs = [os.path.dirname(git_exe)]
    if gh_exit is not None:
        stub = tmp_path / "gh-stub"
        stub.mkdir()
        if sys.platform == "win32":
            (stub / "gh.cmd").write_text(f"@exit /b {gh_exit}\r\n", encoding="utf-8")
        else:
            script = stub / "gh"
            script.write_text(f"#!/bin/sh\nexit {gh_exit}\n", encoding="utf-8")
            script.chmod(0o755)
        dirs.insert(0, str(stub))
    monkeypatch.setenv("PATH", os.pathsep.join(dirs))
    if gh_exit is None:
        assert shutil.which("gh") is None, "gh shares git's directory; this test cannot hide it"


async def _repo(tmp_path, bind_project_workspace, remote_url=GITHUB_URL):
    repo = tmp_path / "repo"
    repo.mkdir()
    make_repo(repo)
    if remote_url:
        git(repo, "remote", "add", "origin", remote_url)
    await set_main_branch("main")
    await bind_project_workspace(repo)
    return repo


async def _project():
    async with async_session_factory() as session:
        return await session.get(Project, "proj-test")


async def _set_pr_landing(on=True):
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.pr_landing = on
        await session.commit()


# --- off-ac1 -------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pr_landing_is_off_and_a_pull_request_build_is_refused_naming_the_setting(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path  # noqa: F811
):
    await _repo(tmp_path, bind_project_workspace)
    read = await app.get(SETTINGS, headers=auth_headers)
    assert read.status_code == 200, read.text
    assert read.json()["pr_landing"] is False
    assert read.json()["pr_single_commit"] is False

    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    refused = await _build(app, auth_headers, driver="hand", landing="pull_request")
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "pr_landing_off"
    assert "pr_landing" in detail["message"] and "PR landing" in detail["message"]
    assert await _rows(Build) == []


# --- gh-ac1 --------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "remote_url",
    [None, "C:/somewhere/bare.git" if sys.platform == "win32" else "/somewhere/bare.git"],
)
async def test_turning_it_on_without_a_github_remote_is_refused(
    app, auth_headers, bind_project_workspace, tmp_path, monkeypatch, remote_url
):
    await _repo(tmp_path, bind_project_workspace, remote_url=remote_url)
    _only_git_on_path(monkeypatch, tmp_path, gh_exit=0)
    refused = await app.put(SETTINGS, json={"pr_landing": True}, headers=auth_headers)
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == pull_requests.NO_GITHUB_REMOTE
    assert "GitHub remote" in refused.json()["detail"]["message"]
    assert (await _project()).pr_landing is False


@pytest.mark.asyncio
async def test_turning_it_on_without_the_github_cli_is_refused(
    app, auth_headers, bind_project_workspace, tmp_path, monkeypatch
):
    await _repo(tmp_path, bind_project_workspace)
    _only_git_on_path(monkeypatch, tmp_path)
    refused = await app.put(SETTINGS, json={"pr_landing": True}, headers=auth_headers)
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == pull_requests.NO_GITHUB_CLI
    assert "GitHub CLI" in refused.json()["detail"]["message"]
    assert (await _project()).pr_landing is False


@pytest.mark.asyncio
async def test_turning_it_on_with_the_cli_logged_out_is_refused(
    app, auth_headers, bind_project_workspace, tmp_path, monkeypatch
):
    await _repo(tmp_path, bind_project_workspace)
    _only_git_on_path(monkeypatch, tmp_path, gh_exit=1)
    refused = await app.put(SETTINGS, json={"pr_landing": True}, headers=auth_headers)
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == pull_requests.GITHUB_CLI_NOT_LOGGED_IN
    assert "not logged in" in refused.json()["detail"]["message"]
    assert (await _project()).pr_landing is False


@pytest.mark.asyncio
async def test_turned_on_where_github_is_ready_and_a_pull_request_build_starts(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    await _repo(tmp_path, bind_project_workspace)
    _only_git_on_path(monkeypatch, tmp_path, gh_exit=0)
    saved = await app.put(
        SETTINGS, json={"pr_landing": True, "pr_single_commit": True}, headers=auth_headers
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["pr_landing"] is True and saved.json()["pr_single_commit"] is True
    project = await _project()
    assert project.pr_landing is True and project.pr_single_commit is True

    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    built = await _build(app, auth_headers, driver="hand", landing="pull_request")
    assert built.status_code == 200, built.text
    (build,) = await _rows(Build)
    assert build.landing == "pull_request"
    running = (await _read(app, auth_headers))["builds"][0]
    assert running["landing"] == "pull_request"
    assert running["pull_request"] == {
        "number": None,
        "url": None,
        "state": None,
        "last_asked_at": None,
        "error": None,
    }


@pytest.mark.asyncio
async def test_a_pull_request_build_is_refused_when_github_stopped_being_ready(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    """The setting is on, but the CLI has since logged out: the Build is refused at the start."""
    await _repo(tmp_path, bind_project_workspace)
    await _set_pr_landing(True)
    _only_git_on_path(monkeypatch, tmp_path, gh_exit=1)
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    refused = await _build(app, auth_headers, driver="hand", landing="pull_request")
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == pull_requests.GITHUB_CLI_NOT_LOGGED_IN
    assert await _rows(Build) == []


# --- the readiness check's pieces ----------------------------------------------------------------


@pytest.mark.parametrize(
    "url,github",
    [
        ("https://github.com/gutohuida/AgentWeave.git", True),
        ("https://github.com/gutohuida/AgentWeave", True),
        ("https://token@github.com/o/r.git", True),
        ("git@github.com:gutohuida/AgentWeave.git", True),
        ("ssh://git@github.com/o/r.git", True),
        ("https://gitlab.com/o/r.git", False),
        ("https://github.com.evil.example/o/r.git", False),
        ("C:/repos/bare.git", False),
        ("/srv/git/r.git", False),
        ("", False),
    ],
)
def test_a_github_remote_is_recognised_by_its_url(url, github):
    assert pull_requests.is_github_url(url) is github


# --- migration 0168 ------------------------------------------------------------------------------


def test_0168_adds_the_columns_off_and_null_and_round_trips(tmp_path):
    from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

    from .test_migration_0151_the_hub_may_override_checks import _add_project, _columns

    db_file = tmp_path / "pr-landing.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0168')")
        conn.commit()
    _downgrade_to(db_url, "0167")
    with sqlite3.connect(db_file) as conn:
        assert not {"pr_landing", "pr_single_commit"} & _columns(conn, "projects")
        assert not {"pr_number", "pr_url", "pr_state"} & _columns(conn, "builds")
        _add_project(conn, "proj-old")
        conn.commit()
        before = conn.execute("SELECT * FROM projects").fetchall()

    _upgrade_to(db_url, "0168")

    with sqlite3.connect(db_file) as conn:
        assert {"pr_landing", "pr_single_commit"} <= _columns(conn, "projects")
        assert {
            "pr_number",
            "pr_url",
            "pr_state",
            "pr_last_asked_at",
            "pr_pushed_sha",
            "pr_error",
        } <= _columns(conn, "builds")
        row = conn.execute(
            "SELECT pr_landing, pr_single_commit FROM projects WHERE id = 'proj-old'"
        ).fetchone()
        assert row == (0, 0)
        after = conn.execute("SELECT * FROM projects").fetchall()
        assert [r[: len(before[0])] for r in after] == before
