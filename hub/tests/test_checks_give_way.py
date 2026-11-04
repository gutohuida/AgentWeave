"""Checks give way to the user (`checks-know-their-phase-and-give-way-to-the-user`, FR-5, FR-6,
FR-11).

While a project's `checks_give_way` is on, every process a check starts, the processes those start
included, runs below normal scheduling priority; it is off for every project until the operator
turns it on. And beside each check's time limit the settings show how long it usually takes.
"""

import sys
import textwrap
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from hub import project_checks
from hub.db.engine import async_session_factory
from hub.db.models import Project, Task, TaskCheckRun

SETTINGS = "/api/v1/projects/proj-test/settings"
DURATIONS = "/api/v1/projects/proj-test/checks/usual-durations"

#: Windows priority classes (`GetPriorityClass`).
NORMAL_PRIORITY_CLASS = 0x20
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
IDLE_PRIORITY_CLASS = 0x40

#: Writes its own scheduling priority to `<out>/<role>`; as `parent` it first starts itself as
#: `child`, so the child is a process the check's command started, not one the Hub did.
_REPORTER = textwrap.dedent("""
    import os, subprocess, sys

    def priority():
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
            return kernel32.GetPriorityClass(kernel32.GetCurrentProcess())
        return os.nice(0)

    out, role = sys.argv[1], sys.argv[2]
    if role == "parent":
        subprocess.run([sys.executable, __file__, out, "child"], check=True)
    with open(os.path.join(out, role), "w") as handle:
        handle.write(str(priority()))
    """)


def _reporting_check(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    script = tmp_path / "report_priority.py"
    script.write_text(_REPORTER, encoding="utf-8")
    out = tmp_path / "priorities"
    out.mkdir()
    command = f'"{sys.executable}" "{script}" "{out}" parent'
    return {"name": "suite", "command": command, "timeout_seconds": 60}, out


def _run_and_read(project, check, out, cwd):
    """Run *project*'s copy of *check* as every check run does (`configured_checks` then `run_one`)
    and answer the priorities the check's process and its child reported."""
    (configured,) = project_checks.configured_checks(project)
    result = project_checks.run_one(configured, cwd)
    assert result["exit_code"] == 0, result["output_tail"]
    return int((out / "parent").read_text()), int((out / "child").read_text())


def _below_normal(priority):
    if sys.platform == "win32":
        return priority in (BELOW_NORMAL_PRIORITY_CLASS, IDLE_PRIORITY_CLASS)
    return priority >= 10


def _normal(priority):
    return priority == (NORMAL_PRIORITY_CLASS if sys.platform == "win32" else 0)


@pytest.mark.asyncio
async def test_a_check_and_its_child_run_below_normal_while_the_project_gives_way(
    app, auth_headers, tmp_path
):
    """ac-priority (FR-5)."""
    check, out = _reporting_check(tmp_path)
    saved = await app.put(
        SETTINGS, json={"checks": [check], "checks_give_way": True}, headers=auth_headers
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["checks_give_way"] is True
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")

    parent, child = _run_and_read(project, check, out, tmp_path)

    assert _below_normal(parent), parent
    assert _below_normal(child), child


@pytest.mark.asyncio
async def test_giving_way_is_off_for_an_existing_and_a_new_project_and_changes_nothing(
    app, auth_headers, tmp_path
):
    """ac-priority-default-off (FR-6): a row written without the column (as every project that
    existed before migration 0161 was) and a project created through the route both read off, and
    the same check runs at normal priority in each."""
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO projects (id, name, created_at) "
                "VALUES ('proj-before', 'Before', CURRENT_TIMESTAMP)"
            )
        )
        await session.commit()
    created = await app.post(
        "/api/v1/projects/create",
        json={"path": str(tmp_path / "created"), "name": "Created"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    new_id = created.json()["id"]

    for project_id in ("proj-before", new_id):
        read = await app.get(f"/api/v1/projects/{project_id}/settings", headers=auth_headers)
        assert read.status_code == 200, read.text
        assert read.json()["checks_give_way"] is False

    for project_id in ("proj-before", new_id):
        check, out = _reporting_check(tmp_path / project_id)
        async with async_session_factory() as session:
            project = await session.get(Project, project_id)
            project.checks = [check]
            await session.commit()
            await session.refresh(project)
        parent, child = _run_and_read(project, check, out, tmp_path)
        assert _normal(parent), (project_id, parent)
        assert _normal(child), (project_id, child)


@pytest.mark.asyncio
async def test_giving_way_does_not_change_what_makes_a_pass_reusable():
    """Priority changes how fast a check runs, not what it finds: a pass recorded before the
    setting was turned on is still the same check's pass (`check_digest`)."""
    check = {"name": "suite", "command": "pytest", "timeout_seconds": 900}
    off = project_checks.configured_checks(Project(checks=[check], checks_give_way=False))[0]
    on = project_checks.configured_checks(Project(checks=[check], checks_give_way=True))[0]
    assert (off["give_way"], on["give_way"]) == (False, True)
    assert project_checks.check_digest(off) == project_checks.check_digest(on)


def _passed(name, seconds, **extra):
    return {"name": name, "exit_code": 0, "timed_out": False, "duration_seconds": seconds, **extra}


async def _seed_runs(results_newest_first):
    """One decided check run per entry, the first the newest, as the project's history."""
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        session.add(Task(id="task-gw", project_id="proj-test", title="checked", status="approved"))
        await session.commit()
        for i, results in enumerate(results_newest_first):
            session.add(
                TaskCheckRun(
                    id=f"chk-gw-{i:02d}",
                    project_id="proj-test",
                    task_id="task-gw",
                    main_sha="a" * 40,
                    target_shas=["b" * 40],
                    state="passed",
                    results=results,
                    error="",
                    started_at=now - timedelta(minutes=i),
                    ended_at=now - timedelta(minutes=i),
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_the_settings_show_a_checks_median_and_longest_of_its_last_20_passes(
    app, auth_headers
):
    """ac-duration (FR-11): only clean passes count (not a failure, a skip, a pass reused from
    another run or a flaky pass, whose time is two attempts), and only the newest 20 of them."""
    checks = [
        {"name": "suite", "command": "pytest", "timeout_seconds": 900},
        {"name": "lint", "command": "ruff check .", "timeout_seconds": 120},
    ]
    assert (await app.put(SETTINGS, json={"checks": checks}, headers=auth_headers)).is_success
    # Newest first: 20 passes of 10..29 s, then older passes far longer that fall outside them.
    newest = [[_passed("suite", 10.0 + i)] for i in range(20)]
    ignored = [
        _passed("suite", 500.0, reused_from="chk-x"),
        _passed("suite", 0.0, skipped=True),
        _passed("suite", 700.0, flaky={"first": {}}),
        {"name": "suite", "exit_code": 1, "timed_out": False, "duration_seconds": 800.0},
        {"name": "lint", "exit_code": None, "timed_out": True, "duration_seconds": 120.0},
    ]
    older = [[_passed("suite", 900.0)] for _ in range(5)]
    await _seed_runs([ignored[:3], ignored[3:]] + newest + older)

    read = await app.get(DURATIONS, headers=auth_headers)

    assert read.status_code == 200, read.text
    assert read.json() == {
        "suite": {"median_seconds": 19.5, "longest_seconds": 29.0, "passes": 20},
        "lint": None,
    }


@pytest.mark.asyncio
async def test_a_project_with_no_checks_has_no_durations(app, auth_headers):
    read = await app.get(DURATIONS, headers=auth_headers)
    assert read.status_code == 200, read.text
    assert read.json() == {}
