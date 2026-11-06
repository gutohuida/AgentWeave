"""The known-failing list and its owner tasks (`failures-already-known-are-on-a-list-not-re-
argued`, task `list`: FR-1 to FR-6, FR-13, FR-14).

Real git repositories and a real pytest check where a criterion is about what a run found (the
check writes a JUnit report and re-runs failing tests through the project's wrapper, as in
`test_a_red_main_does_not_hold_the_night.py`); recorded check runs read by `known_failing` where a
criterion is about the list's own rules. One test per criterion, named after it.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from sqlalchemy import func, select

from hub import assigned_task_start, known_failing, landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    Build,
    InboundQueueEntry,
    KnownFailingTest,
    MainCheckRun,
    Run,
    Task,
    TaskCheckRun,
    UnlistedTestFailure,
)

from .test_a_red_main_does_not_hold_the_night import (
    TASK,
    TASK2,
    TEST_A,
    TEST_B,
    _checked,
    _configure,
    _flaky_test,
    _latest_run,
    _loop,
    _repo,
    _reviewer_approves,
    _task,
)
from .test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to
from .test_task_integration import commits_on, git

pytestmark = pytest.mark.asyncio

ROUTE = "/api/v1/projects/proj-test/checks/known-failing"
#: Main is green: both ledger tests pass there.
GREEN = {"ledger.py": "A = 2\nB = 2\n"}
FLAKY_ID = "test_timing::test_flaky"


@pytest.fixture(autouse=True)
def _no_landing_timers():
    yield
    landing_queue.cancel_timers()


@pytest.fixture(autouse=True)
async def _agents(app):
    """The agents a fix task can be assigned to: a task cannot be held by a name that is none."""
    async with async_session_factory() as session:
        for name in ("builder", "DeveloperOpus", "someone-else"):
            session.add(Agent(id=f"ag-{name}", project_id="proj-test", name=name))
        await session.commit()


async def _entries() -> list:
    async with async_session_factory() as session:
        return await known_failing.entries(session, "proj-test")


async def _get(model, key):
    async with async_session_factory() as session:
        return await session.get(model, key)


async def _count(model, *where) -> int:
    async with async_session_factory() as session:
        return (
            await session.execute(select(func.count()).select_from(model).where(*where))
        ).scalar()


async def _status(task_id: str) -> str:
    return (await _get(Task, task_id)).status


async def _run_row(run_id: str, results: list, *, task_id: str = TASK, main_sha="m" * 40) -> str:
    async with async_session_factory() as session:
        session.add(
            TaskCheckRun(
                id=run_id,
                project_id="proj-test",
                task_id=task_id,
                main_sha=main_sha,
                target_shas=[],
                state="passed",
                results=results,
                error="",
            )
        )
        await session.commit()
    return run_id


async def _main_row(run_id: str, results: list, *, main_sha="c" * 40) -> str:
    async with async_session_factory() as session:
        session.add(
            MainCheckRun(
                id=run_id,
                project_id="proj-test",
                main_sha=main_sha,
                reason=known_failing.OUTSIDE_COMMIT,
                tests=[],
                state="failed",
                results=results,
                error="",
            )
        )
        await session.commit()
    return run_id


async def _plain_task(task_id: str, *, status="completed", **fields) -> None:
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title=f"Task {task_id}",
                description="",
                status=status,
                priority="medium",
                **fields,
            )
        )
        await session.commit()


async def _entry(test: str, kind: str, *, fix_task_id=None, check="pytest") -> str:
    async with async_session_factory() as session:
        entry = KnownFailingTest(
            id=f"kf-{test[-8:]}-{kind[:3]}",
            project_id="proj-test",
            check_name=check,
            test=test,
            kind=kind,
            fix_task_id=fix_task_id,
        )
        session.add(entry)
        await session.commit()
        return entry.id


def _flaked(test: str) -> dict:
    """A check result whose one failing test passed when re-run on its own."""
    return {
        "name": "pytest",
        "exit_code": 0,
        "timed_out": False,
        "output_tail": "",
        "flaky": {"how": "tests", "tests": [test], "first": {"failed_tests": [test]}},
        "flaky_tests": [test],
    }


def _passed(*tests: str) -> dict:
    return {"name": "pytest", "exit_code": 0, "timed_out": False, "watched_passed": list(tests)}


# --- FR-1 ----------------------------------------------------------------------------------------


async def test_ac_entry_each_entry_carries_its_fields_on_the_route(app, auth_headers):
    await _plain_task(TASK, assignee="builder")
    run_id = await _run_row("chk-flake1", [_flaked(TEST_B)])
    whole = {
        "name": "lint",
        "exit_code": 1,
        "timed_out": False,
        "whole_check": project_checks.NO_REPORT_CONFIGURED,
        "confirmed": {"how": "check", "exit_code": 1, "timed_out": False},
    }
    main_id = await _main_row("mchk-whole1", [whole])
    assert await known_failing.record_run(run_id)
    assert await known_failing.record_run(main_id)

    response = await app.get(ROUTE, headers=auth_headers)
    assert response.status_code == 200, response.text
    by_check = {e["check"]: e for e in response.json()["entries"]}
    flaky, lint = by_check["pytest"], by_check["lint"]
    assert (flaky["test"], flaky["whole_check"], flaky["kind"]) == (TEST_B, False, "flaky")
    assert (lint["test"], lint["whole_check"], lint["kind"]) == (None, True, "fails on main")
    assert flaky["added_by_run"] == run_id and lint["added_by_run"] == main_id
    for entry in (flaky, lint):
        assert entry["first_seen"] and entry["last_seen"], entry
        assert entry["fix_task"]["id"].startswith("task-"), entry
    assert flaky["fix_task"]["assignee"] == "builder"
    assert lint["fix_task"]["assignee"] is None


def _rows(conn, table: str) -> list:
    return sorted(conn.execute(f"SELECT * FROM {table}").fetchall(), key=repr)


def test_ac_seeded_the_migration_lists_the_open_fix_tasks_tests(tmp_path):
    db_file = tmp_path / "seed.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0166')")
        conn.commit()
    _downgrade_to(db_url, "0165")
    with sqlite3.connect(db_file) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "known_failing_tests" not in tables
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES ('proj-s', 'S', '2026-11-01')"
        )
        for task_id, status in (
            ("task-open1", "pending"),
            ("task-open2", "in_progress"),
            ("task-done", "approved"),
        ):
            conn.execute(
                "INSERT INTO tasks (id, project_id, title, description, status, priority, "
                "created_at, updated) VALUES (?, 'proj-s', ?, '', ?, 'high', '2026-11-01', "
                "'2026-11-01')",
                (task_id, task_id, status),
            )
        filings = [
            ("ev1", "task-open1", ["t::a"], {"t::a": "fails on main"}, "2026-11-02 10:00:00"),
            ("ev2", "task-open2", ["t::b"], {"t::b": "flaky"}, "2026-11-03 10:00:00"),
            ("ev3", "task-done", ["t::c"], {"t::c": "fails on main"}, "2026-11-04 10:00:00"),
        ]
        for event_id, task_id, tests, kinds, at in filings:
            data = json.dumps(
                {
                    "task_id": task_id,
                    "tests": tests,
                    "kinds": kinds,
                    "checks": ["hub-tests"],
                    "run_id": f"chk-{event_id}",
                    "main_sha": "abc",
                    "found_by": "task-x",
                }
            )
            conn.execute(
                "INSERT INTO event_logs (id, project_id, event_type, data, severity, timestamp) "
                "VALUES (?, 'proj-s', 'checks_fix_task_filed', ?, 'info', ?)",
                (event_id, data, at),
            )
        conn.commit()
        before = {t: _rows(conn, t) for t in ("projects", "tasks", "event_logs")}

    _upgrade_to(db_url, "0166")
    with sqlite3.connect(db_file) as conn:
        rows = conn.execute(
            "SELECT project_id, check_name, test, kind, fix_task_id, added_by_run, first_seen "
            "FROM known_failing_tests ORDER BY test"
        ).fetchall()
        assert rows == [
            ("proj-s", "hub-tests", "t::a", "fails on main", "task-open1", "chk-ev1",
             "2026-11-02 10:00:00"),
            ("proj-s", "hub-tests", "t::b", "flaky", "task-open2", "chk-ev2",
             "2026-11-03 10:00:00"),
        ]  # fmt: skip
        assert {t: _rows(conn, t) for t in ("projects", "tasks", "event_logs")} == before

    _downgrade_to(db_url, "0165")
    with sqlite3.connect(db_file) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not {"known_failing_tests", "unlisted_test_failures", "main_check_runs"} & tables
        assert {t: _rows(conn, t) for t in ("projects", "tasks", "event_logs")} == before


# --- FR-2 ----------------------------------------------------------------------------------------


async def test_ac_flaky_a_flake_is_listed_and_the_task_is_not_sent_back(
    app, tmp_path, tmp_path_factory
):
    counter = tmp_path_factory.mktemp("flake") / "count.txt"
    _repo(tmp_path, {**GREEN, "test_timing.py": _flaky_test(counter)})
    await _loop()
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()

    run_id = await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()

    run = await _get(TaskCheckRun, run_id)
    assert run.state == "passed", run.results
    [entry] = await _entries()
    assert (entry.test, entry.kind, entry.added_by_run) == (FLAKY_ID, "flaky", run_id)
    assert await _status(TASK) == "completed"
    fix = await _get(Task, entry.fix_task_id)
    # The loop's developer owns it (`_loop`'s job agent), and it is on no loop (FR-5, FR-6).
    assert (fix.assignee, fix.status, fix.loop_id, fix.build_id) == (
        "builder",
        "pending",
        None,
        None,
    )


# --- FR-3 ----------------------------------------------------------------------------------------


async def test_ac_main_added_an_outside_commit_is_run_once_and_its_failure_listed(app, tmp_path):
    _repo(tmp_path, GREEN)
    await _configure()
    await project_checks.watch_main_once()  # the first look records the tip
    (tmp_path / "test_new.py").write_text(
        "def test_new():\n    assert False, 'broken by hand'\n", encoding="utf-8"
    )
    git(tmp_path, "add", "test_new.py")
    git(tmp_path, "commit", "-q", "-m", "a commit made by hand")
    tip = git(tmp_path, "rev-parse", "main").stdout.strip()

    await project_checks.watch_main_once()
    await known_failing.drain()
    await project_checks.watch_main_once()  # nothing moved: nothing more runs
    assert await known_failing.run_on_main("proj-test", tip) is None
    await known_failing.drain()

    runs = await _count(
        MainCheckRun, MainCheckRun.main_sha == tip, MainCheckRun.reason == "outside_commit"
    )
    assert runs == 1
    [entry] = await _entries()
    assert (entry.test, entry.kind) == ("test_new::test_new", "fails on main")
    assert entry.added_by_run.startswith("mchk-")
    assert (await _get(Task, entry.fix_task_id)).assignee is None  # found on main


# --- FR-13 ---------------------------------------------------------------------------------------


async def _single_runs() -> list:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(MainCheckRun).where(MainCheckRun.reason == known_failing.SINGLE_TEST)
                )
            ).scalars()
        )


async def test_ac_twice_with_main_failing_it_is_listed_and_neither_task_goes_back(app, tmp_path):
    _repo(tmp_path)  # main is red on test_a
    await _loop()
    await _task(tmp_path, TASK, {"a.py": "x = 1\n"})
    await _task(tmp_path, TASK2, {"b.py": "y = 1\n"})
    await _configure()

    await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()
    assert await _single_runs() == []
    assert await _entries() == []
    await project_checks.request_run("proj-test", TASK2)
    await project_checks.drain()

    [single] = await _single_runs()
    assert (single.tests, single.state) == ([TEST_A], "failed")
    [entry] = await _entries()
    assert (entry.test, entry.kind, entry.added_by_run) == (TEST_A, "fails on main", single.id)
    [result] = (await _latest_run(TASK2)).results
    assert result["shared_tests"] == [TEST_A] and result["preexisting"], result
    assert await _status(TASK2) == "completed"
    # TASK's run ended before main was asked: its unlisted failure was its own then, and went back
    # (FR-7). Once listed it is not held against TASK: its run is judged again and the task says so.
    [first] = (await _latest_run(TASK)).results
    assert first["shared_tests"] == [TEST_A] and first["preexisting"], first
    assert await _status(TASK) == "revision_needed"
    notes = (await _get(Task, TASK)).notes
    assert "known-failing list" in str(notes), notes


async def test_ac_twice_with_main_passing_both_tasks_go_back(app, tmp_path):
    _repo(tmp_path, GREEN)
    await _loop()
    await _task(tmp_path, TASK, {"ledger.py": "A = 2\nB = 3\n"})
    await _task(tmp_path, TASK2, {"ledger.py": "A = 2\nB = 4\n"})
    await _configure()

    await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()
    await project_checks.request_run("proj-test", TASK2)
    await project_checks.drain()

    [single] = await _single_runs()
    assert (single.tests, single.state) == ([TEST_B], "passed")
    assert await _entries() == []
    [result] = (await _latest_run(TASK2)).results
    assert result["own_tests"] == [TEST_B] and not result["preexisting"], result
    assert (await _status(TASK), await _status(TASK2)) == ("revision_needed", "revision_needed")


# --- FR-4, FR-14 ---------------------------------------------------------------------------------


async def test_ac_removed_a_landed_batch_removes_what_it_ran_and_passed(app, tmp_path):
    _repo(tmp_path, GREEN)
    await _loop()
    await _plain_task("task-fix-a", status="pending")
    await _plain_task("task-fix-b", status="pending")
    first = await _entry(TEST_A, "fails on main", fix_task_id="task-fix-a")
    second = await _entry("test_ledger::test_gone", "fails on main")
    flaky = await _entry(TEST_B, "flaky", fix_task_id="task-fix-b")
    work = await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    await _checked(TASK)

    approved = await _reviewer_approves(app, TASK)
    assert approved.status_code == 200, approved.text
    await landing_queue.drain()
    assert work in commits_on(tmp_path, "main")
    landed = git(tmp_path, "rev-parse", "main").stdout.strip()

    assert {e.id for e in await _entries()} == {second, flaky}
    # ac-kept: its fix task is still open, with a note naming the main commit.
    fix = await _get(Task, "task-fix-a")
    assert fix.status == "pending" and landed[:12] in fix.notes, fix.notes
    assert first not in {e.id for e in await _entries()}

    # The flaky test's fix task is approved; the next landed batch that passes it removes it.
    async with async_session_factory() as session:
        (await session.get(Task, "task-fix-b")).status = "approved"
        await session.commit()
    work2 = await _task(tmp_path, TASK2, {"feature2.py": "y = 1\n"})
    await _checked(TASK2)
    approved = await _reviewer_approves(app, TASK2)
    assert approved.status_code == 200, approved.text
    await landing_queue.drain()
    assert work2 in commits_on(tmp_path, "main")
    assert {e.id for e in await _entries()} == {second}


async def test_ac_removed_a_flaky_entry_comes_off_after_20_consecutive_passes(app):
    await _plain_task(TASK)
    await _plain_task("task-fix-f", status="pending")
    flaky = await _entry(TEST_B, "flaky", fix_task_id="task-fix-f")

    for n in range(known_failing.FLAKY_PASSES_TO_CLEAR - 1):
        await known_failing.record_run(await _run_row(f"chk-p{n}", [_passed(TEST_B)]))
        # A run that did not run the test counts nothing and breaks nothing.
        await known_failing.record_run(await _run_row(f"chk-n{n}", [_passed()]))
    # The same run read twice counts once.
    await known_failing.record_run("chk-p0")
    assert [e.id for e in await _entries()] == [flaky]
    assert (await _get(KnownFailingTest, flaky)).passes == known_failing.FLAKY_PASSES_TO_CLEAR - 1

    # A failure starts the count again.
    await known_failing.record_run(await _run_row("chk-fail", [_flaked(TEST_B)]))
    assert (await _get(KnownFailingTest, flaky)).passes == 0
    for n in range(known_failing.FLAKY_PASSES_TO_CLEAR):
        await known_failing.record_run(await _run_row(f"chk-q{n}", [_passed(TEST_B)]))
    assert await _entries() == []
    fix = await _get(Task, "task-fix-f")
    assert fix.status == "pending" and ("m" * 12) in fix.notes, fix.notes


async def test_ac_kept_a_removed_entrys_fix_task_stays_open_with_the_main_commit(app):
    await _plain_task(TASK)
    await _plain_task("task-fix-k", status="in_progress", notes="working on it")
    await _entry(TEST_A, "fails on main", fix_task_id="task-fix-k")
    sha = "d" * 40
    # A run that is not on main's tree passes it: it stays.
    await known_failing.record_run(await _run_row("chk-k0", [_passed(TEST_A)]))
    assert len(await _entries()) == 1
    await known_failing.record_run(await _main_row("mchk-k1", [_passed(TEST_A)], main_sha=sha))
    assert await _entries() == []
    fix = await _get(Task, "task-fix-k")
    assert fix.status == "in_progress"
    assert fix.notes.startswith("working on it") and sha[:12] in fix.notes, fix.notes


# --- FR-5, FR-6 ----------------------------------------------------------------------------------


async def test_ac_owner_one_fix_task_assigned_to_the_builds_developer(app):
    async with async_session_factory() as session:
        session.add(
            Build(
                id="build-own",
                project_id="proj-test",
                document_id="doc-own",
                driver="flow",
                level="reviewed",
                builders=[],
                reviewers=[],
                people={"builder": "DeveloperOpus", "checker": "QA", "tasks": {}},
            )
        )
        await session.commit()
    await _plain_task(TASK, build_id="build-own", assignee="someone-else")
    await _plain_task(TASK2, build_id="build-own", assignee="someone-else")

    first = await known_failing.record_run(await _run_row("chk-o1", [_flaked(TEST_B)]))
    again = await known_failing.record_run(
        await _run_row("chk-o2", [_flaked(TEST_B)], task_id=TASK2)
    )
    on_main = {
        "name": "pytest",
        "exit_code": 1,
        "timed_out": False,
        "failed_tests": [TEST_A],
        "confirmed": {"how": "tests", "exit_code": 1, "timed_out": False},
        "compared_tests": [TEST_A],
    }
    found_on_main = await known_failing.record_run(await _main_row("mchk-o3", [on_main]))
    assert len(first) == 1 and again == [] and len(found_on_main) == 1

    entries = {e.test: e for e in await _entries()}
    async with async_session_factory() as session:
        named_b = (
            (await session.execute(select(Task).where(Task.title.contains(TEST_B)))).scalars().all()
        )
    [fix] = named_b
    assert fix.id == entries[TEST_B].fix_task_id and fix.assignee == "DeveloperOpus"
    for part in ("pytest", TEST_B, "flaky", "chk-o1"):
        assert part in fix.description, (part, fix.description)
    main_fix = await _get(Task, entries[TEST_A].fix_task_id)
    assert main_fix.assignee is None and "mchk-o3" in main_fix.description


async def test_ac_not_started_a_fix_task_is_on_no_loop_and_no_turn_starts(app):
    await _loop(live=True)
    await _plain_task(TASK, loop_id="loop-red-main", assignee="builder")
    await known_failing.record_run(await _run_row("chk-ns", [_flaked(TEST_B)]))
    [entry] = await _entries()

    # What would start an assigned task outside a flow, asked as its backstop sweep asks it.
    await assigned_task_start.sweep()
    fix = await _get(Task, entry.fix_task_id)
    assert (fix.status, fix.assignee, fix.loop_id, fix.build_id) == (
        "pending",
        "builder",
        None,
        None,
    )
    assert await _count(Run, Run.task_id == fix.id) == 0
    assert await _count(InboundQueueEntry, InboundQueueEntry.task_id == fix.id) == 0


async def test_a_listed_test_is_no_longer_a_sighting(app):
    """FR-13's bookkeeping: a test noted as failed while unlisted is forgotten once it passes or
    is listed, so a later failure starts a new streak."""
    await _plain_task(TASK)
    async with async_session_factory() as session:
        session.add(
            UnlistedTestFailure(
                id="utf-1",
                project_id="proj-test",
                check_name="pytest",
                test=TEST_A,
                task_id=TASK,
                run_id="chk-x",
            )
        )
        await session.commit()
    await known_failing.record_run(await _run_row("chk-s1", [_passed(TEST_A)]))
    assert await _count(UnlistedTestFailure) == 0


async def test_runs_are_told_the_listed_tests(app):
    await _entry(TEST_A, "fails on main")
    await _entry("", "fails on main", check="lint")
    checks = await known_failing.watching(
        "proj-test", [{"name": "pytest"}, {"name": "lint"}, {"name": "other"}]
    )
    assert checks == [
        {"name": "pytest", "watch_tests": [TEST_A]},
        {"name": "lint"},
        {"name": "other"},
    ]
