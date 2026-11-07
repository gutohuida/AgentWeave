"""The PR's CI is the full check (`the-pr-s-ci-is-the-full-check`), task `settings`.

FR-1 (ci-setting): off until the operator turns it on; refused while PR landing is off, and turned
off with PR landing. FR-3 (counted-checks): the checks that count are GitHub's required ones on the
PR's base, else the project's list; with neither, turning the setting on and starting a PR build are
refused naming both. FR-10 (interval-setting): interval 1-60 and cutoff 5-1440 whole minutes, 2 and
60 by default, the cutoff no shorter than the interval, each refusal naming its rule.

GitHub is a fake `_run_gh` (the module's one seam), answering `gh api` reads of the branch and of
its rules as each case needs; the readiness check's `gh auth status` is a stub `gh` exiting 0.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess

import pytest

from hub import pull_requests
from hub.db.engine import async_session_factory
from hub.db.models import Build, Project

from .test_a_build_has_a_driver_a_level_and_its_people import (
    _approved,
    _build,
    _document,
    _roster_rows,
    _rows,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_a_build_lands_as_one_pull_request import (
    SETTINGS,
    _only_git_on_path,
    _project,
    _repo,
    _set_pr_landing,
)

BRANCH_READ = "repos/example/example/branches/main"
RULES_READ = "repos/example/example/rules/branches/main"


def _branch(contexts=(), enabled=True):
    return {
        "name": "main",
        "protection": {
            "enabled": enabled,
            "required_status_checks": {
                "contexts": list(contexts),
                "checks": [{"context": c, "app_id": None} for c in contexts],
            },
        },
    }


def _rules(contexts=()):
    if not contexts:
        return []
    return [
        {"type": "deletion"},
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": c} for c in contexts]},
        },
    ]


def _fake_github(monkeypatch, answers):
    """`_run_gh` answering each `gh api` path from *answers* (JSON, or an int: that exit code)."""
    calls = []

    def run(root, args):
        calls.append(list(args))
        answer = answers.get(args[1]) if args[:1] == ["api"] else None
        if answer is None or isinstance(answer, int):
            return subprocess.CompletedProcess(args, answer or 1, "", "HTTP 404: Not Found")
        return subprocess.CompletedProcess(args, 0, json.dumps(answer), "")

    monkeypatch.setattr(pull_requests, "_run_gh", run)
    return calls


async def _set(**columns):
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        for name, value in columns.items():
            setattr(project, name, value)
        await session.commit()


async def _ready(app, auth_headers, bind_project_workspace, tmp_path, monkeypatch):
    await _repo(tmp_path, bind_project_workspace)
    _only_git_on_path(monkeypatch, tmp_path, gh_exit=0)
    await _set_pr_landing(True)


# --- ac-setting (FR-1) ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_new_project_reads_the_setting_off_with_its_defaults(app, auth_headers):
    read = (await app.get(SETTINGS, headers=auth_headers)).json()
    assert read["pr_ci_full_check"] is False
    assert read["pr_ci_check_names"] == []
    assert (read["pr_ci_interval_minutes"], read["pr_ci_cutoff_minutes"]) == (2, 60)


@pytest.mark.asyncio
async def test_turning_it_on_with_pr_landing_off_is_refused_naming_pr_landing(
    app, auth_headers, bind_project_workspace, tmp_path, monkeypatch
):
    await _repo(tmp_path, bind_project_workspace)
    calls = _fake_github(monkeypatch, {BRANCH_READ: _branch(["ci-check"])})
    refused = await app.put(
        SETTINGS,
        json={"pr_ci_full_check": True, "pr_ci_check_names": ["ci-check"]},
        headers=auth_headers,
    )
    assert refused.status_code == 400, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "pr_landing_off"
    assert "PR landing" in detail["message"] and "pr_landing" in detail["message"]
    assert (await _project()).pr_ci_full_check is False
    assert calls == []


@pytest.mark.asyncio
async def test_turning_pr_landing_off_turns_the_setting_off(
    app, auth_headers, bind_project_workspace, tmp_path, monkeypatch
):
    await _ready(app, auth_headers, bind_project_workspace, tmp_path, monkeypatch)
    await _set(pr_ci_full_check=True, pr_ci_check_names=["ci-check"])
    assert (await app.get(SETTINGS, headers=auth_headers)).json()["pr_ci_full_check"] is True

    saved = await app.put(SETTINGS, json={"pr_landing": False}, headers=auth_headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["pr_landing"] is False and saved.json()["pr_ci_full_check"] is False
    read = (await app.get(SETTINGS, headers=auth_headers)).json()
    assert read["pr_landing"] is False and read["pr_ci_full_check"] is False
    assert (await _project()).pr_ci_full_check is False


@pytest.mark.asyncio
async def test_turning_pr_landing_off_while_asking_for_the_setting_on_is_refused(
    app, auth_headers, bind_project_workspace, tmp_path, monkeypatch
):
    await _ready(app, auth_headers, bind_project_workspace, tmp_path, monkeypatch)
    await _set(pr_ci_full_check=True, pr_ci_check_names=["ci-check"])
    refused = await app.put(
        SETTINGS, json={"pr_landing": False, "pr_ci_full_check": True}, headers=auth_headers
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == "pr_landing_off"
    project = await _project()
    assert project.pr_landing is True and project.pr_ci_full_check is True


# --- ac-counted (FR-3) ---------------------------------------------------------------------------


def test_only_the_required_check_decides_and_a_failing_other_check_does_not(tmp_path):
    required = pull_requests.RequiredChecks(["ci-check"])
    counted = pull_requests.counted_checks(required, ["lint"])
    assert counted == ["ci-check"]
    results = [{"name": "lint", "bucket": "fail"}, {"name": "ci-check", "bucket": "pass"}]
    assert pull_requests.judge(counted, results) == pull_requests.CHECK_PASSED
    results = [{"name": "lint", "bucket": "pass"}, {"name": "ci-check", "bucket": "fail"}]
    assert pull_requests.judge(counted, results) == pull_requests.CHECK_FAILED
    assert pull_requests.judge(counted, [{"name": "lint", "bucket": "pass"}]) == "pending"
    results = [{"name": "ci-check", "bucket": "pending"}]
    assert pull_requests.judge(counted, results) == pull_requests.CHECK_PENDING


def test_with_no_required_checks_the_listed_names_decide():
    for required in (
        pull_requests.RequiredChecks([]),
        pull_requests.RequiredChecks([], "HTTP 404: Not Found"),
    ):
        counted = pull_requests.counted_checks(required, ["lint", "", "lint", "tests"])
        assert counted == ["lint", "tests"]
        results = [
            {"name": "lint", "bucket": "pass"},
            {"name": "tests", "bucket": "pass"},
            {"name": "unlisted", "bucket": "fail"},
        ]
        assert pull_requests.judge(counted, results) == pull_requests.CHECK_PASSED
        results[1]["bucket"] = "fail"
        assert pull_requests.judge(counted, results) == pull_requests.CHECK_FAILED


def test_required_checks_are_read_from_the_branch_and_its_rules(tmp_path, monkeypatch):
    from .test_task_integration import git, make_repo

    make_repo(tmp_path)
    git(tmp_path, "remote", "add", "origin", "git@github.com:example/example.git")
    calls = _fake_github(
        monkeypatch,
        {BRANCH_READ: _branch(["ci-check"]), RULES_READ: _rules(["ci-check", "e2e"])},
    )
    read = pull_requests.required_checks(tmp_path, "main")
    assert read == pull_requests.RequiredChecks(["ci-check", "e2e"])
    assert calls == [["api", BRANCH_READ], ["api", RULES_READ]]

    _fake_github(monkeypatch, {BRANCH_READ: _branch(["ci-check"], enabled=False), RULES_READ: []})
    assert pull_requests.required_checks(tmp_path, "main").names == []

    _fake_github(monkeypatch, {RULES_READ: _rules(["e2e"])})
    read = pull_requests.required_checks(tmp_path, "main")
    assert read.names == ["e2e"] and "404" in (read.error or "")


@pytest.mark.parametrize(
    "call",
    [
        ["api", BRANCH_READ],
        ["api", RULES_READ],
        ["api", "repos/o/r/branches/feature/x"],
    ],
)
def test_the_only_gh_api_calls_are_reads_of_a_branch_and_its_rules(call):
    pull_requests.check_gh_call(call)


@pytest.mark.parametrize(
    "call",
    [
        ["api", "repos/o/r/branches/main/protection"],
        ["api", "repos/o/r/branches/main/protection/required_status_checks"],
        ["api", BRANCH_READ, "-X", "PATCH"],
        ["api", BRANCH_READ, "--jq", ".name"],
        ["api", "repos/o/r/pulls/1/merge"],
        ["api", "repos/o/r/rulesets"],
        ["api", "graphql"],
    ],
)
def test_any_other_gh_api_call_is_refused(call):
    with pytest.raises(pull_requests.RefusedGitHubCallError):
        pull_requests.check_gh_call(call)


@pytest.mark.asyncio
async def test_with_neither_turning_it_on_is_refused_naming_both(
    app, auth_headers, bind_project_workspace, tmp_path, monkeypatch
):
    await _ready(app, auth_headers, bind_project_workspace, tmp_path, monkeypatch)
    _fake_github(monkeypatch, {BRANCH_READ: _branch([]), RULES_READ: []})
    refused = await app.put(SETTINGS, json={"pr_ci_full_check": True}, headers=auth_headers)
    assert refused.status_code == 400, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == pull_requests.NOTHING_TO_WAIT_FOR
    assert "GitHub marks no status check required on main" in detail["message"]
    assert "lists no check names" in detail["message"]
    assert "pr_ci_check_names" in detail["message"]
    assert (await _project()).pr_ci_full_check is False


@pytest.mark.asyncio
async def test_where_github_cannot_be_read_and_nothing_is_listed_the_refusal_says_so(
    app, auth_headers, bind_project_workspace, tmp_path, monkeypatch
):
    await _ready(app, auth_headers, bind_project_workspace, tmp_path, monkeypatch)
    _fake_github(monkeypatch, {})
    refused = await app.put(SETTINGS, json={"pr_ci_full_check": True}, headers=auth_headers)
    assert refused.status_code == 400, refused.text
    message = refused.json()["detail"]["message"]
    assert "could not read which checks GitHub requires on main" in message
    assert "lists no check names" in message


@pytest.mark.asyncio
async def test_a_required_check_on_github_is_enough_to_turn_it_on(
    app, auth_headers, bind_project_workspace, tmp_path, monkeypatch
):
    await _ready(app, auth_headers, bind_project_workspace, tmp_path, monkeypatch)
    calls = _fake_github(monkeypatch, {BRANCH_READ: _branch(["ci-check"]), RULES_READ: []})
    saved = await app.put(SETTINGS, json={"pr_ci_full_check": True}, headers=auth_headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["pr_ci_full_check"] is True and saved.json()["pr_ci_check_names"] == []
    assert ["api", BRANCH_READ] in calls


@pytest.mark.asyncio
async def test_a_listed_name_is_enough_without_asking_github(
    app, auth_headers, bind_project_workspace, tmp_path, monkeypatch
):
    await _ready(app, auth_headers, bind_project_workspace, tmp_path, monkeypatch)
    calls = _fake_github(monkeypatch, {})
    saved = await app.put(
        SETTINGS,
        json={"pr_ci_full_check": True, "pr_ci_check_names": [" ci-check "]},
        headers=auth_headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["pr_ci_check_names"] == ["ci-check"]
    assert (await _project()).pr_ci_check_names == ["ci-check"]
    assert calls == []

    # Emptying the list while on is judged again: GitHub requires nothing here.
    _fake_github(monkeypatch, {BRANCH_READ: _branch([]), RULES_READ: []})
    refused = await app.put(SETTINGS, json={"pr_ci_check_names": []}, headers=auth_headers)
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == pull_requests.NOTHING_TO_WAIT_FOR
    assert (await _project()).pr_ci_check_names == ["ci-check"]


@pytest.mark.asyncio
async def test_with_neither_a_pull_request_build_is_refused_naming_both(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    """The setting was turned on while GitHub required a check; it no longer does."""
    await _ready(app, auth_headers, bind_project_workspace, tmp_path, monkeypatch)
    await _set(pr_ci_full_check=True, pr_ci_check_names=[])
    _fake_github(monkeypatch, {BRANCH_READ: _branch([]), RULES_READ: []})
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    refused = await _build(app, auth_headers, driver="hand", landing="pull_request")
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == pull_requests.NOTHING_TO_WAIT_FOR
    assert "GitHub marks no status check required on main" in detail["message"]
    assert "lists no check names" in detail["message"]
    assert await _rows(Build) == []

    _fake_github(monkeypatch, {BRANCH_READ: _branch(["ci-check"]), RULES_READ: []})
    built = await _build(app, auth_headers, driver="hand", landing="pull_request")
    assert built.status_code == 200, built.text


# --- ac-interval (FR-10) -------------------------------------------------------------------------


def _refusal(response) -> str:
    assert response.status_code == 422, response.text
    return " ".join(str(error.get("msg")) for error in response.json()["detail"])


@pytest.mark.asyncio
async def test_interval_and_cutoff_out_of_range_are_refused_naming_the_rule(
    app, auth_headers, bind_project_workspace, tmp_path, monkeypatch
):
    await _ready(app, auth_headers, bind_project_workspace, tmp_path, monkeypatch)
    await _set(pr_ci_full_check=True, pr_ci_check_names=["ci-check"])

    for interval in (0, 61):
        said = _refusal(
            await app.put(SETTINGS, json={"pr_ci_interval_minutes": interval}, headers=auth_headers)
        )
        assert "pr_ci_interval_minutes must be whole minutes from 1 to 60" in said
        assert f"; {interval} is not" in said
    for cutoff in (4, 1441):
        said = _refusal(
            await app.put(SETTINGS, json={"pr_ci_cutoff_minutes": cutoff}, headers=auth_headers)
        )
        assert "pr_ci_cutoff_minutes must be whole minutes from 5 to 1440" in said
    said = _refusal(
        await app.put(
            SETTINGS,
            json={"pr_ci_interval_minutes": 5, "pr_ci_cutoff_minutes": 3},
            headers=auth_headers,
        )
    )
    assert "pr_ci_cutoff_minutes (3) must not be shorter than pr_ci_interval_minutes (5)" in said
    said = _refusal(
        await app.put(
            SETTINGS,
            json={"pr_ci_interval_minutes": 30, "pr_ci_cutoff_minutes": 20},
            headers=auth_headers,
        )
    )
    assert "must not be shorter than pr_ci_interval_minutes (30)" in said
    assert "whole minutes from" not in said
    project = await _project()
    assert (project.pr_ci_interval_minutes, project.pr_ci_cutoff_minutes) == (2, 60)

    saved = await app.put(SETTINGS, json={"pr_ci_interval_minutes": 5}, headers=auth_headers)
    assert saved.status_code == 200, saved.text
    saved = await app.put(SETTINGS, json={"pr_ci_cutoff_minutes": 90}, headers=auth_headers)
    assert saved.status_code == 200, saved.text
    read = (await app.get(SETTINGS, headers=auth_headers)).json()
    assert (read["pr_ci_interval_minutes"], read["pr_ci_cutoff_minutes"]) == (5, 90)
    assert read["pr_ci_full_check"] is True


# --- migration 0169 ------------------------------------------------------------------------------


def test_0169_adds_the_columns_with_their_defaults_and_round_trips(tmp_path):
    from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

    from .test_migration_0151_the_hub_may_override_checks import _add_project, _columns

    names = {
        "pr_ci_full_check",
        "pr_ci_check_names",
        "pr_ci_interval_minutes",
        "pr_ci_cutoff_minutes",
    }
    db_file = tmp_path / "pr-ci.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0169')")
        conn.commit()
    _downgrade_to(db_url, "0168")
    with sqlite3.connect(db_file) as conn:
        assert not names & _columns(conn, "projects")
        _add_project(conn, "proj-old")
        conn.commit()
        before = conn.execute("SELECT * FROM projects").fetchall()

    _upgrade_to(db_url, "0169")

    with sqlite3.connect(db_file) as conn:
        assert names <= _columns(conn, "projects")
        row = conn.execute(
            "SELECT pr_ci_full_check, pr_ci_check_names, pr_ci_interval_minutes, "
            "pr_ci_cutoff_minutes FROM projects WHERE id = 'proj-old'"
        ).fetchone()
        assert row == (0, "[]", 2, 60)
        after = conn.execute("SELECT * FROM projects").fetchall()
        assert [r[: len(before[0])] for r in after] == before
