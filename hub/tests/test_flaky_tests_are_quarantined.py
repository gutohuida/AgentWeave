"""Flaky tests are quarantined (`the-slow-checks-run-once-per-landing-not-once-per-task-and-flaky-
tests-are-quarantined`, task `quarantine-core`, FR-1 to FR-10).

The seams: `check_history.record`, which every check run calls with its outcomes and which reads
them into quarantine (entry on a flip, exit by passes); a task's pre-review run (`project_checks.
request_run`) and a landing batch's (`landing_queue.run_batch_checks`) with a real pytest check and
its own report; the known-failing list reading a landed batch's run (`known_failing.record_run`);
and the routes the UI calls (`/checks/quarantine`, `/checks/quarantine/marks`, the project's
settings).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import pytest
from sqlalchemy import select

from hub import check_history, known_failing, landing_queue, project_checks, quarantine
from hub.db.engine import async_session_factory
from hub.db.models import (
    KnownFailingTest,
    Project,
    QuarantinedTest,
    Task,
    TaskCheckRun,
)
from hub.flaky_tests import FIX_TASK_EVENT
from hub.utils import persist_event

from .test_a_check_run_records_its_slot import _also_completed, _landing
from .test_a_landing_timeout_is_unjudged import _batch
from .test_checks_run_before_review import PY, _flow_task_completed, _scripts
from .test_landing_first_and_test_history import _history, _runs
from .test_task_integration import git

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"
CHECK = "pytest"
SETTINGS = f"/api/v1/projects/{PROJECT}/settings"
QUARANTINE = f"/api/v1/projects/{PROJECT}/checks/quarantine"
MARKS = f"{QUARANTINE}/marks"

_run_counter = {"n": 0}


async def _record(test: str, outcome: str, check: str = CHECK) -> str:
    """One check run recording *test*'s *outcome* through `check_history.record`, as every gate
    does: `flipped` is a failure its confirmation re-run passed. Its run id."""
    _run_counter["n"] += 1
    run_id = f"chk-q{_run_counter['n']:05d}"
    failed = outcome in (check_history.FAILED, check_history.FLIPPED)
    await check_history.record(
        project_id=PROJECT,
        check_run_id=run_id,
        phase=check_history.PHASE_REVIEW,
        commit_sha="c" * 40,
        check_name=check,
        taken=({test: check_history.FAILED if failed else check_history.PASSED}, {}),
        result={check_history.FLIPPED_KEY: [test]} if outcome == check_history.FLIPPED else {},
    )
    return run_id


async def _quarantined(test: Optional[str] = None) -> List[QuarantinedTest]:
    async with async_session_factory() as db:
        query = select(QuarantinedTest).where(QuarantinedTest.project_id == PROJECT)
        if test is not None:
            query = query.where(QuarantinedTest.test_id == test)
        return list((await db.execute(query)).scalars())


async def _set(**fields) -> None:
    async with async_session_factory() as db:
        project = await db.get(Project, PROJECT)
        for name, value in fields.items():
            setattr(project, name, value)
        await db.commit()


async def _quarantine(test: str, check: str = CHECK, fix_task_id: Optional[str] = None) -> None:
    async with async_session_factory() as db:
        db.add(
            QuarantinedTest(
                id=f"qt-{abs(hash((check, test))) % 10**10:010d}",
                project_id=PROJECT,
                check_name=check,
                test_id=test,
                flake_rate=0.1,
                flips=2,
                entered_by_run="chk-seed",
                passes=0,
                fix_task_id=fix_task_id,
            )
        )
        await db.commit()


async def _fix_tasks() -> List[Task]:
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(Task).where(
                        Task.project_id == PROJECT, Task.title.like("Fix quarantined%")
                    )
                )
            ).scalars()
        )


# --- FR-1: entry on a flip ------------------------------------------------------------------------


async def test_a_second_flip_at_20_runs_quarantines_the_test_and_records_when(app):
    """ac-enters: 19 recorded runs, one flipped; the 20th run records its second flip (rate 0.1,
    above the default 0.05): quarantined for its check, its entry time recorded."""
    history = ["passed"] * 19
    history[5] = "flipped"
    await _runs(history, test_id="t::flaky")
    assert await _quarantined() == [], "premise: one flip at 19 runs has no rate"
    run_id = await _record("t::flaky", check_history.FLIPPED)
    (row,) = await _quarantined("t::flaky")
    assert row.check_name == CHECK
    assert row.flake_rate == pytest.approx(0.1)
    assert row.flips == 2
    assert row.entered_at is not None
    assert row.entered_by_run == run_id


async def test_a_test_with_no_rate_does_not_enter(app):
    """ac-no-rate-no-entry: 10 recorded runs, the third flip recorded: no rate, not quarantined."""
    history = ["passed"] * 9
    history[2], history[6] = "flipped", "flipped"
    await _runs(history, test_id="t::young")
    await _record("t::young", check_history.FLIPPED)
    assert await _quarantined() == []


async def test_an_outright_failure_does_not_readmit_a_test_that_left_and_a_new_flip_does(app):
    """ac-no-reentry-without-flip: a test that left after 20 passes, its rate still above the
    threshold, fails outright: not back; a later flip: back."""
    history = ["passed"] * 20
    for k in (1, 4, 8):
        history[k] = "flipped"
    await _runs(history, test_id="t::back")
    await _record("t::back", check_history.FLIPPED)
    assert len(await _quarantined("t::back")) == 1
    for _ in range(20):
        await _record("t::back", check_history.PASSED)
    assert await _quarantined("t::back") == [], "premise: it left after 20 passes"
    async with async_session_factory() as db:
        (figures,) = await check_history.flake_rates(db, PROJECT, test_id="t::back")
    assert figures["flake_rate"] > 0.05, "premise: its rate is still above the threshold"

    await _record("t::back", check_history.FAILED)
    assert await _quarantined("t::back") == [], "an outright failure readmitted it"
    await _record("t::back", check_history.FLIPPED)
    assert len(await _quarantined("t::back")) == 1


# --- FR-7: exit by consecutive passes -------------------------------------------------------------


async def test_it_leaves_after_the_exit_number_of_consecutive_passes(app):
    """ac-leaves: exit 3; pass, pass, fail, then pass three times: still quarantined after the
    fail, released by the third pass after it."""
    await _set(quarantine_exit_passes=3)
    await _quarantine("t::exit")
    for outcome in ("passed", "passed", "failed", "passed", "passed"):
        await _record("t::exit", outcome)
        assert len(await _quarantined("t::exit")) == 1, f"left early, after {outcome}"
    (row,) = await _quarantined("t::exit")
    assert row.passes == 2
    await _record("t::exit", "passed")
    assert await _quarantined("t::exit") == []


# --- FR-9: the two settings -----------------------------------------------------------------------


async def test_the_settings_default_and_a_change_applies_at_the_next_decision(app, auth_headers):
    """ac-settings: defaults 0.05 and 20; changed to 0.2 and 5, a test flipping to 0.1 is not
    quarantined, and the test already quarantined is not released by the change."""
    read = await app.get(SETTINGS, headers=auth_headers)
    assert read.status_code == 200, read.text
    assert read.json()["quarantine_threshold"] == pytest.approx(0.05)
    assert read.json()["quarantine_exit_passes"] == 20

    await _quarantine("t::held")
    async with async_session_factory() as db:
        held = (await db.execute(select(QuarantinedTest))).scalar_one()
        held.passes = 7  # more than the new exit number: the change alone releases nothing
        await db.commit()
    saved = await app.put(
        SETTINGS,
        json={"quarantine_threshold": 0.2, "quarantine_exit_passes": 5},
        headers=auth_headers,
    )
    assert saved.status_code == 200, saved.text
    read = await app.get(SETTINGS, headers=auth_headers)
    assert read.json()["quarantine_threshold"] == pytest.approx(0.2)
    assert read.json()["quarantine_exit_passes"] == 5
    assert [row.test_id for row in await _quarantined()] == ["t::held"]

    history = ["passed"] * 19
    history[3] = "flipped"
    await _runs(history, test_id="t::point-one")
    await _record("t::point-one", check_history.FLIPPED)
    assert await _quarantined("t::point-one") == [], "0.1 is not above 0.2"
    assert [row.test_id for row in await _quarantined()] == ["t::held"]

    bad = await app.put(SETTINGS, json={"quarantine_threshold": 0}, headers=auth_headers)
    assert bad.status_code == 422


# --- FR-10: the fix task --------------------------------------------------------------------------


async def _flips_to_enter(test: str) -> None:
    history = ["passed"] * 19
    history[2] = "flipped"
    await _runs(history, test_id=test)
    await _record(test, check_history.FLIPPED)


async def test_entry_files_one_fix_task_unless_one_is_open_and_leaving_notes_it(app):
    """ac-fix-task: the first test entering with no fix task gets one naming its check, rate and
    flips; the second, with an open fix task naming it, gains none; the first leaving notes its
    task, which stays open."""
    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-oldfix",
                project_id=PROJECT,
                title="Fix flaky test t::second",
                description="",
                status="pending",
            )
        )
        await db.commit()
        await persist_event(
            db,
            PROJECT,
            FIX_TASK_EVENT,
            {"task_id": "task-oldfix", "tests": ["t::second"], "checks": [CHECK]},
        )
    await _set(quarantine_exit_passes=2)
    await _flips_to_enter("t::first")
    await _flips_to_enter("t::second")

    (first,) = await _quarantined("t::first")
    (second,) = await _quarantined("t::second")
    assert second.fix_task_id == "task-oldfix"
    (filed,) = await _fix_tasks()
    assert first.fix_task_id == filed.id
    assert "t::first" in filed.title
    assert f"Check: {CHECK}" in filed.description
    assert "Flake rate: 0.1000" in filed.description
    assert filed.description.count("check run chk-") >= 2, filed.description  # its flips
    assert filed.status == "pending"

    await _record("t::first", "passed")
    await _record("t::first", "passed")
    assert await _quarantined("t::first") == []
    async with async_session_factory() as db:
        task = await db.get(Task, filed.id)
    assert task.status == "pending", "leaving closed the fix task"
    assert "left quarantine" in str(task.notes)
    assert len(await _fix_tasks()) == 1


# --- FR-8: the never-quarantine mark, through the routes --------------------------------------------


async def test_a_mark_takes_a_test_out_at_once_and_keeps_it_out_until_removed(app, auth_headers):
    """ac-never-mark: marked, a quarantined test leaves at once; a flip past the threshold does
    not readmit it and its failure is judged; once the mark is removed, its next flip does."""
    await _flips_to_enter("t::guard")
    assert len(await _quarantined("t::guard")) == 1
    listed = await app.get(QUARANTINE, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    (entry,) = listed.json()["quarantined"]
    assert entry["test"] == "t::guard" and entry["check"] == CHECK
    assert entry["fix_task"]["id"]
    assert listed.json()["threshold"] == pytest.approx(0.05)

    marked = await app.put(MARKS, json={"check": CHECK, "test": "t::guard"}, headers=auth_headers)
    assert marked.status_code == 200, marked.text
    assert marked.json()["released"] is True
    assert marked.json()["quarantined"] == []
    assert [m["test"] for m in marked.json()["marks"]] == ["t::guard"]
    assert await _quarantined("t::guard") == []

    result = {"name": CHECK, "exit_code": 1, "timed_out": False, "failed_tests": ["t::guard"]}
    await quarantine.excuse(PROJECT, {"name": CHECK}, result, [])
    assert result["failed_tests"] == ["t::guard"] and quarantine.RESULT_KEY not in result
    await _record("t::guard", check_history.FLIPPED)
    assert await _quarantined("t::guard") == [], "a marked test re-entered"

    removed = await app.delete(
        MARKS, params={"check": CHECK, "test": "t::guard"}, headers=auth_headers
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["removed"] is True and removed.json()["marks"] == []
    assert await _quarantined("t::guard") == [], "removing the mark admitted it by itself"
    await _record("t::guard", check_history.FLIPPED)
    assert len(await _quarantined("t::guard")) == 1


# --- FR-2, FR-3, FR-4: the gates, with a real pytest report -------------------------------------

RUNNER = """
import os
import sys
from xml.sax.saxutils import quoteattr

TESTS = {{"suite::ok": None, "suite::quarantined": {flaky!r}, "suite::other": {steady!r}}}
asked = sys.argv[1:] or list(TESTS)
cases, failed = [], False
for test in asked:
    path = TESTS.get(test)
    classname, name = test.split("::")
    if path is not None and os.path.exists(path):
        failed = True
        body = '<failure message="it failed">it failed</failure>'
    else:
        body = ""
    cases.append(f"<testcase classname={{quoteattr(classname)}} name={{quoteattr(name)}}>{{body}}</testcase>")
with open("report.xml", "w", encoding="utf-8") as out:
    out.write("<testsuites><testsuite>" + "".join(cases) + "</testsuite></testsuites>")
sys.exit(1 if failed else 0)
"""

QUARANTINED, OTHER, OK = "suite::quarantined", "suite::other", "suite::ok"


def _check(tmp_path: Path, name: str = CHECK) -> Tuple[dict, Path, Path]:
    """A check with a re-run command over three tests, writing a JUnit report naming no file:
    `suite::quarantined` fails while its file exists, `suite::other` while its file does. The
    check, and those two files."""
    folder = _scripts(tmp_path) / f"{name}-runner"
    folder.mkdir(exist_ok=True)
    steady, flaky = folder / "other-fails", folder / "quarantined-fails"
    script = folder / "runner.py"
    script.write_text(RUNNER.format(steady=str(steady), flaky=str(flaky)), encoding="utf-8")
    check = {
        "name": name,
        "command": f'{PY} "{script}"',
        "rerun_command": f'{PY} "{script}" {{tests}}',
        "timeout_seconds": 120,
        "fast": False,
        "report_path": "report.xml",
    }
    return check, steady, flaky


@pytest.fixture
def rerun_commands(monkeypatch):
    """Every command `project_checks.run_one` is given, in order."""
    commands: List[str] = []
    real = project_checks.run_one

    def spy(check, cwd, owner=None):
        commands.append(str(check["command"]))
        return real(check, cwd, owner)

    monkeypatch.setattr(project_checks, "run_one", spy)
    return commands


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_pre_review_run_failing_only_a_quarantined_test_passes_and_names_it(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, rerun_commands
):
    """ac-excused-passes, ac-no-rerun (first run), FR-4: the run passes, the task goes on to
    review, the result names the test as quarantined, nothing is re-run, and its failure is in
    its history."""
    check, _steady, flaky = _check(tmp_path)
    await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [check],
    )
    await _quarantine(QUARANTINED)
    flaky.write_text("1", encoding="utf-8")
    rerun_commands.clear()
    run_id = await project_checks.request_run(PROJECT, "task-1")
    await project_checks.drain()
    async with async_session_factory() as db:
        run = await db.get(TaskCheckRun, run_id)
        task = await db.get(Task, "task-1")
        wait = await project_checks.review_wait(db, task)
    assert run.state == "passed", run.results
    (result,) = run.results
    assert [t["test"] for t in result[quarantine.RESULT_KEY]["tests"]] == [QUARANTINED]
    assert result[quarantine.RESULT_KEY]["first"]["exit_code"] != 0
    assert not project_checks.own_failure(run.results)
    assert wait is None, wait
    assert task.status == "completed"
    assert len(rerun_commands) == 1, f"a re-run was made: {rerun_commands}"

    rows = {row.test_id: row.outcome for row in await _history(run_id)}
    assert rows[QUARANTINED] == "failed"
    assert rows[OK] == "passed"


async def test_its_failure_and_its_pass_are_both_in_its_history(app, tmp_path):
    """ac-still-recorded: a quarantined test failing in one landing run and passing in the next:
    its history holds a failed row and a passed row for those runs."""
    check, _steady, flaky = _check(tmp_path, "pytest-landing")
    repo, sha, _ = await _landing_project(tmp_path, check)
    await _quarantine(QUARANTINED, check="pytest-landing")
    tip = git(repo, "rev-parse", "main").stdout.strip()
    landing = await _landing("task-2")
    flaky.write_text("1", encoding="utf-8")
    await _batch("lbat-q-still01", tip, [landing])
    first = await landing_queue.run_batch_checks(
        repo, PROJECT, "lbat-q-still01", tip, sha, [check], [landing]
    )
    flaky.unlink()
    async with async_session_factory() as db:
        row = await db.get(TaskCheckRun, first.run_id)
        row.results = []  # not reused: the next run executes the check again
        await db.commit()
    second = await landing_queue.run_batch_checks(
        repo, PROJECT, "lbat-q-still01", tip, sha, [check], [landing]
    )
    assert first.state == "passed" and second.state == "passed", (first.results, second.results)
    test = QUARANTINED
    assert [r.outcome for r in await _history(first.run_id) if r.test_id == test] == ["failed"]
    assert [r.outcome for r in await _history(second.run_id) if r.test_id == test] == ["passed"]


async def _landing_project(tmp_path: Path, check: dict):
    from .test_agent_trigger import _init_repo

    repo = _init_repo(tmp_path / "repo")
    git(repo, "checkout", "-q", "-b", "work")
    (repo / "ledger.py").write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", "ledger.py")
    git(repo, "commit", "-q", "-m", "work")
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "main")
    async with async_session_factory() as db:
        db.add(Task(id="task-1", project_id=PROJECT, title="t", description="", status="approved"))
        await db.commit()
    await _also_completed("task-2")
    return repo, sha, []


async def test_a_batch_fails_on_the_other_test_only_and_reruns_only_it(
    app, tmp_path, rerun_commands
):
    """ac-mixed-failure, ac-no-rerun (second run), ac-not-listed: a batch failing a quarantined
    test and an unlisted one that reproduces fails on the other only, names the quarantined one
    as excused, re-runs only the other, and once read as a run on main's tree lists the other
    alone."""
    check, steady, flaky = _check(tmp_path, "pytest-landing")
    repo, sha, _ = await _landing_project(tmp_path, check)
    await _quarantine(QUARANTINED, check="pytest-landing")
    tip = git(repo, "rev-parse", "main").stdout.strip()
    landing = await _landing("task-2")
    await _batch("lbat-q-mixed01", tip, [landing])
    steady.write_text("1", encoding="utf-8")
    flaky.write_text("1", encoding="utf-8")
    rerun_commands.clear()
    outcome = await landing_queue.run_batch_checks(
        repo, PROJECT, "lbat-q-mixed01", tip, sha, [check], [landing]
    )
    assert outcome.state == "failed", outcome.results
    (result,) = outcome.results
    assert result["own_tests"] == [OTHER], result
    assert project_checks.counts_against(result)
    assert [t["test"] for t in result[quarantine.RESULT_KEY]["tests"]] == [QUARANTINED]
    assert len(rerun_commands) == 2, rerun_commands
    assert OTHER in rerun_commands[1]
    assert QUARANTINED not in rerun_commands[1], rerun_commands[1]

    await known_failing.record_run(outcome.run_id, on_main=sha)
    async with async_session_factory() as db:
        listed = {row.test for row in (await db.execute(select(KnownFailingTest))).scalars()}
    assert listed == {OTHER}, listed


async def test_a_batch_failing_only_a_quarantined_test_adds_nothing_to_the_list(app, tmp_path):
    """ac-not-listed: the quarantined test fails in a landed batch's run on main's tree; the list
    records that run and adds no entry for it."""
    check, _steady, flaky = _check(tmp_path, "pytest-landing")
    repo, sha, _ = await _landing_project(tmp_path, check)
    await _quarantine(QUARANTINED, check="pytest-landing")
    tip = git(repo, "rev-parse", "main").stdout.strip()
    landing = await _landing("task-2")
    await _batch("lbat-q-alone01", tip, [landing])
    flaky.write_text("1", encoding="utf-8")
    outcome = await landing_queue.run_batch_checks(
        repo, PROJECT, "lbat-q-alone01", tip, sha, [check], [landing]
    )
    assert outcome.state == "passed", outcome.results
    await known_failing.record_run(outcome.run_id, on_main=sha)
    async with async_session_factory() as db:
        assert list((await db.execute(select(KnownFailingTest))).scalars()) == []


# --- FR-6: a changed file voids the excuse, where the report names it ---------------------------

REPORT = """<?xml version="1.0"?>
<testsuites><testsuite name="s" tests="2">
<testcase classname="suite" name="ok"{file_ok}/>
<testcase classname="suite" name="flaky"{file_flaky}><failure message="boom">boom</failure></testcase>
</testsuite></testsuites>
"""


def _report_check(tmp_path: Path, *, with_file: bool) -> dict:
    """A check that writes a fixed JUnit report failing `suite::flaky`, naming its file
    `tests/test_flaky.js` where *with_file*, and exits 1."""
    files = (' file="tests/test_ok.js"', ' file="tests/test_flaky.js"') if with_file else ("", "")
    text = REPORT.format(file_ok=files[0], file_flaky=files[1])
    source = _scripts(tmp_path) / f"report-{with_file}.xml"
    source.write_text(text, encoding="utf-8")
    script = _scripts(tmp_path) / f"write-{with_file}.py"
    script.write_text(
        "import shutil, sys\n" f"shutil.copy({str(source)!r}, 'report.xml')\n" "sys.exit(1)\n",
        encoding="utf-8",
    )
    return {
        "name": "js",
        "command": f'{PY} "{script}"',
        "timeout_seconds": 60,
        "report_path": "report.xml",
    }


@pytest.mark.parametrize(
    "with_file,changed,excused",
    [
        (True, ["tests/test_flaky.js"], False),
        (True, ["src/other.js"], True),
        (False, ["tests/test_flaky.js"], True),
    ],
)
async def test_a_changed_file_voids_the_excuse_only_where_the_report_names_it(
    app, tmp_path, with_file, changed, excused
):
    """ac-changed-file: a report naming the quarantined test's file, which the work edits: not
    excused, judged as without quarantine; the same failure with a report naming no file:
    excused."""
    check = _report_check(tmp_path, with_file=with_file)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    result = project_checks.run_one(check, cwd)
    assert result["failed_tests"] == ["suite::flaky"], result
    await _quarantine("suite::flaky", check="js")
    await quarantine.excuse(PROJECT, check, result, changed)
    if excused:
        assert not project_checks.failed(result)
        assert [t["test"] for t in result[quarantine.RESULT_KEY]["tests"]] == ["suite::flaky"]
    else:
        assert project_checks.failed(result)
        assert result["failed_tests"] == ["suite::flaky"]
        assert result[quarantine.RESULT_KEY] == {"changed_file": ["suite::flaky"]}


async def test_unreadable_quarantine_excuses_nothing(app, monkeypatch):
    """The Tier 2 hazard's safe side: quarantine state that cannot be read excuses nothing."""
    await _quarantine("t::x")

    async def broken(*args, **kwargs):
        raise RuntimeError("no such table: quarantined_tests")

    monkeypatch.setattr(quarantine, "_rows", broken)
    result = {"name": CHECK, "exit_code": 1, "timed_out": False, "failed_tests": ["t::x"]}
    await quarantine.excuse(PROJECT, {"name": CHECK}, result, [])
    assert project_checks.failed(result) and result["failed_tests"] == ["t::x"]
    assert quarantine.RESULT_KEY not in result


async def test_a_whole_check_rerun_failing_only_quarantined_tests_confirms_nothing(tmp_path):
    """FR-2 where a check has no re-run command: the whole check's re-run fails the quarantined
    test again but passes the other, so the other flipped and the check passes."""
    check, steady, flaky = _check(tmp_path)
    del check["rerun_command"]
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    flaky.write_text("1", encoding="utf-8")
    counter = steady
    counter.write_text("1", encoding="utf-8")
    result = project_checks.run_one(check, cwd)
    quarantine.apply_excuse(result, {QUARANTINED: {"test": QUARANTINED}}, [])
    assert result["failed_tests"] == [OTHER]
    counter.unlink()  # the other passes on the re-run; the quarantined one fails again
    project_checks.confirm_failure(check, cwd, result, None, [])
    assert not project_checks.failed(result), result
    assert result.get("flaky"), result


def test_excused_in_names_each_excused_test_once_for_the_landing_record():
    """FR-11: a landing names the quarantined tests its batch excused, once each, from the
    results' own record; results with none contribute nothing."""
    entry = {"id": "qt-1", "check": "tests", "test": "suite::flaky", "flake_rate": 0.1}
    results = [
        {"name": "lint", "exit_code": 0},
        {"name": "tests", "exit_code": 0, "quarantine": {"tests": [entry], "first": {}}},
        {"name": "tests", "exit_code": 0, "quarantine": {"tests": [dict(entry)]}},
    ]
    assert quarantine.excused_in(results) == [entry]
    assert quarantine.excused_in(None) == []
