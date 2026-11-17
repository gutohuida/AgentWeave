"""Landing check runs go first, the Hub's check concurrency is a setting, and every test's outcome
is recorded with its flake rate (`landing-time-and-test-flakiness-are-measured`, FR-3, FR-5,
FR-6, FR-10).

The seams: `project_checks.check_slot`, taken by a task's pre-review run (`_execute`, through
`request_run`) and by a landing batch's (`landing_queue.run_batch_checks`); the settings route
`/api/v1/hub-settings`; and a real pytest run writing its default xunit2 report, which names no
file per test, read through the same runs into `test_history`.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import pytest
from sqlalchemy import select

from hub import check_history, landing_queue, project_checks
from hub.dashboard_query import run_query
from hub.db.engine import async_session_factory
from hub.db.models import CheckTestOutcome, HubSettings, LandingBatch, TaskCheckRun

from .test_a_check_run_records_its_slot import _also_completed, _landing, _wait_for
from .test_a_landing_timeout_is_unjudged import _batch
from .test_checks_run_before_review import PY, _flow_task_completed, _scripts, _slow
from .test_task_integration import git

pytestmark = pytest.mark.asyncio


# --- FR-3: a landing run gets the freed slot first -------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_landing_run_gets_the_freed_slot_before_a_pre_review_run_that_waited_first(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """ac-landing-jumps-queue: concurrency 1 with the slot held, a pre-review run waiting and then
    a landing run waiting; when the slot frees, the landing run's `slot_at` is the earlier."""
    repo, sha, _, _ = await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [_slow(tmp_path)],
    )
    await _also_completed("task-2")
    tip = git(repo, "rev-parse", "main").stdout.strip()
    landing = await _landing("task-2")
    await _batch("lbat-first0001", tip, [landing])
    project_checks.set_check_concurrency(1)

    slots = project_checks._semaphore()
    await slots.acquire()  # another run holds the one slot
    held = True
    try:
        review = await project_checks.request_run("proj-test", "task-1")
        assert review is not None

        async def review_waits() -> bool:
            return review in project_checks._waiting_for_slot

        await _wait_for(review_waits)
        batch = asyncio.get_running_loop().create_task(
            landing_queue.run_batch_checks(
                repo, "proj-test", "lbat-first0001", tip, sha, [_slow(tmp_path)], [landing]
            )
        )

        async def both_wait() -> bool:
            return sum(1 for w in slots._waiters if not w.future.done()) == 2

        await _wait_for(both_wait)
        await asyncio.sleep(0.05)
        slots.release()
        held = False
        outcome = await batch
        await project_checks.drain()
    finally:
        if held:
            slots.release()
    assert outcome.state == "passed"

    async with async_session_factory() as db:
        landing_run_id = (await db.get(LandingBatch, "lbat-first0001")).check_run_id
        landing_run = await db.get(TaskCheckRun, landing_run_id)
        review_run = await db.get(TaskCheckRun, review)
    assert review_run.started_at < landing_run.started_at, "premise: pre-review waited first"
    assert landing_run.slot_at is not None and review_run.slot_at is not None
    assert landing_run.slot_at < review_run.slot_at


async def test_landing_waiters_are_served_by_rank_then_arrival():
    """The pool itself: landing waiters before the rest, each kind in the order it came, and a
    run waiting for every slot is not passed by the runs behind it."""
    project_checks.set_check_concurrency(1)
    slots = project_checks._semaphore()
    await slots.acquire()
    order: List[str] = []

    async def take(name: str, landing: bool) -> None:
        async with project_checks.check_slot(landing=landing):
            order.append(name)
            await asyncio.sleep(0)

    loop = asyncio.get_running_loop()
    jobs = []
    for name, landing in (("review-1", False), ("landing-1", True), ("review-2", False)):
        jobs.append(loop.create_task(take(name, landing)))
        await asyncio.sleep(0)
    jobs.append(loop.create_task(take("landing-2", True)))
    await asyncio.sleep(0.01)
    slots.release()
    await asyncio.wait_for(asyncio.gather(*jobs), timeout=5)
    assert order == ["landing-1", "landing-2", "review-1", "review-2"]
    assert slots.held == 0 and not slots.whole


async def test_a_cancelled_waiter_gives_its_turn_to_the_next():
    project_checks.set_check_concurrency(1)
    slots = project_checks._semaphore()
    await slots.acquire()
    loop = asyncio.get_running_loop()
    gone = loop.create_task(slots.acquire(landing=True))
    after = loop.create_task(slots.acquire())
    await asyncio.sleep(0.01)
    gone.cancel()
    await asyncio.gather(gone, return_exceptions=True)
    slots.release()
    await asyncio.wait_for(after, timeout=5)
    assert slots.held == 1
    slots.release()
    assert slots.held == 0


# --- FR-10: the concurrency is a Hub setting, applied without a restart -----------------------


async def _three_runs_at_most_at_once() -> int:
    """Three runs taking a slot each; the most that held one at the same time."""
    now, most = 0, 0

    async def run() -> None:
        nonlocal now, most
        async with project_checks.check_slot():
            now += 1
            most = max(most, now)
            await asyncio.sleep(0.05)
            now -= 1

    await asyncio.wait_for(asyncio.gather(run(), run(), run()), timeout=10)
    return most


async def test_the_setting_changed_from_2_to_1_applies_to_the_runs_after_it(app, auth_headers):
    """ac-setting-applies: the default is 2; set to 1 through the route on a running Hub, three
    checks started afterwards never hold a slot at the same time."""
    got = await app.get("/api/v1/hub-settings", headers=auth_headers)
    assert got.status_code == 200, got.text
    assert got.json() == {
        "check_concurrency": None,
        "check_concurrency_in_force": 2,
        "check_concurrency_default": 2,
    }
    assert await _three_runs_at_most_at_once() == 2

    put = await app.put("/api/v1/hub-settings", headers=auth_headers, json={"check_concurrency": 1})
    assert put.status_code == 200, put.text
    assert put.json()["check_concurrency_in_force"] == 1
    assert await _three_runs_at_most_at_once() == 1

    # It is kept: a restart reads it back.
    project_checks.set_check_concurrency(None)
    assert await project_checks.load_check_concurrency() == 1
    async with async_session_factory() as db:
        assert (await db.get(HubSettings, 1)).check_concurrency == 1

    # Null puts the default back.
    put = await app.put(
        "/api/v1/hub-settings", headers=auth_headers, json={"check_concurrency": None}
    )
    assert put.json()["check_concurrency_in_force"] == 2


async def test_the_setting_refuses_a_count_out_of_range(app, auth_headers):
    for value in (0, project_checks.MAX_CHECK_CONCURRENCY + 1):
        put = await app.put(
            "/api/v1/hub-settings", headers=auth_headers, json={"check_concurrency": value}
        )
        assert put.status_code == 422, put.text


async def test_a_lower_setting_holds_new_runs_until_enough_have_ended():
    slots = project_checks._semaphore()
    await slots.acquire()
    await slots.acquire()  # two run under the default 2
    project_checks.set_check_concurrency(1)
    waiting = asyncio.get_running_loop().create_task(slots.acquire())
    await asyncio.sleep(0.01)
    slots.release()
    await asyncio.sleep(0.01)
    assert not waiting.done(), "a third started while two ran under a limit of 1"
    slots.release()
    await asyncio.wait_for(waiting, timeout=5)
    slots.release()


# --- FR-5: every test of every run, from a real xunit2 report ----------------------------------

FOUR_TESTS = """
def test_a():
    assert True


def test_b():
    assert True


def test_c():
    assert True


def test_d():
    assert 2 == 3
"""


def _pytest_check(tmp_path: Path, name: str, files: dict) -> dict:
    """A pytest check over tests kept beside the repository, writing pytest's default (xunit2)
    report into the checkout."""
    tests = _scripts(tmp_path) / f"{name}-tests"
    tests.mkdir(exist_ok=True)
    for file, body in files.items():
        (tests / file).write_text(body, encoding="utf-8")
    return {
        "name": name,
        "command": f'{PY} -m pytest "{tests}" -q -p no:cacheprovider --junitxml=report.xml',
        "timeout_seconds": 120,
        "fast": False,
        "report_path": "report.xml",
    }


def _report_cases(tmp_path: Path, check: dict) -> dict:
    """The ids and outcomes pytest's own report gives for *check*'s tests, run from inside
    *tmp_path* as the check is from its checkout (pytest's ids depend on where it starts)."""
    import subprocess

    out = _scripts(tmp_path) / f"{check['name']}-report.xml"
    command = check["command"].replace("--junitxml=report.xml", f'--junitxml="{out}"')
    subprocess.run(command, shell=True, capture_output=True, check=False, cwd=tmp_path)
    root = ElementTree.parse(out).getroot()
    assert root.find("testsuite").get("name") == "pytest"
    cases = {}
    for case in root.iter("testcase"):
        assert case.get("file") is None, "premise: xunit2 names no file"
        failed = case.find("failure") is not None or case.find("error") is not None
        cases[f"{case.get('classname')}::{case.get('name')}"] = "failed" if failed else "passed"
    return cases


async def _history(run_id: str) -> List[CheckTestOutcome]:
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(CheckTestOutcome)
                    .where(CheckTestOutcome.check_run_id == run_id)
                    .order_by(CheckTestOutcome.id)
                )
            ).scalars()
        )


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_pre_review_run_records_every_test_of_its_xunit2_report(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """ac-history-xunit2: 3 passes and 1 failure in pytest's default report give 4 rows, with the
    report's ids and outcomes, and no file."""
    check = _pytest_check(tmp_path, "pytest", {"test_four.py": FOUR_TESTS})
    expected = _report_cases(tmp_path, check)
    assert sorted(expected.values()) == ["failed", "passed", "passed", "passed"]
    await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [check],
    )
    run_id = await project_checks.request_run("proj-test", "task-1")
    await project_checks.drain()
    async with async_session_factory() as db:
        run = await db.get(TaskCheckRun, run_id)
    assert run.state == "failed", run.results

    rows = await _history(run_id)
    assert {row.test_id: row.outcome for row in rows} == expected
    assert len(rows) == 4
    assert all(row.file == "" for row in rows)
    assert all(
        row.check_name == "pytest"
        and row.phase == "review"
        and row.commit_sha == run.merged_sha
        and row.project_id == "proj-test"
        and row.recorded_at is not None
        for row in rows
    )
    # The outcomes are history's, not the run's record: nothing of them is stored on the result.
    assert all(check_history.OUTCOMES_KEY not in r for r in run.results)


FLAKY_TESTS = """
import os

COUNTER = {counter!r}


def test_steady():
    assert True


def test_flaky():
    if os.path.exists(COUNTER):
        os.remove(COUNTER)
        assert False, "first run"
"""


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_failure_the_confirmation_passes_is_recorded_flipped(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """ac-flip-recorded: a test that fails on its first run and passes on its confirmation re-run,
    in a landing batch's run, is `flipped` there; the test beside it is `passed`."""
    counter = _scripts(tmp_path) / "flaky-counter"
    counter.write_text("1", encoding="utf-8")
    check = _pytest_check(
        tmp_path, "pytest-landing", {"test_flaky.py": FLAKY_TESTS.format(counter=str(counter))}
    )
    repo, sha, _, _ = await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [check],
    )
    await _also_completed("task-2")
    tip = git(repo, "rev-parse", "main").stdout.strip()
    landing = await _landing("task-2")
    await _batch("lbat-flip0001", tip, [landing])
    outcome = await landing_queue.run_batch_checks(
        repo, "proj-test", "lbat-flip0001", tip, sha, [check], [landing]
    )
    assert outcome.state == "passed", outcome.results
    assert not counter.exists(), "premise: the first run failed test_flaky"
    assert outcome.results[0].get("flaky"), outcome.results

    rows = await _history(outcome.run_id)
    got = {row.test_id.rsplit("::", 1)[-1]: row for row in rows}
    assert set(got) == {"test_steady", "test_flaky"}, [r.test_id for r in rows]
    assert got["test_flaky"].outcome == "flipped"
    assert got["test_steady"].outcome == "passed"
    assert all(r.phase == "landing" and r.check_name == "pytest-landing" for r in rows)
    assert all(r.commit_sha == sha for r in rows)


async def test_a_failure_the_rerun_fails_again_is_not_a_flip(tmp_path):
    """FR-6: a test that failed on every run of a check, re-runs included, stays `failed`."""
    check = _pytest_check(tmp_path, "pytest", {"test_four.py": FOUR_TESTS})
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    result = project_checks.run_one(check_history.recording(check), cwd)
    taken = check_history.take(result)
    project_checks.confirm_failure(check, cwd, result, None, [])
    assert result.get("confirmed"), result
    rows = check_history.rows_for(taken, result)
    assert sorted(outcome for _, _, outcome in rows) == ["failed", "passed", "passed", "passed"]


# --- FR-6: the flake rate ----------------------------------------------------------------------

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


async def _runs(
    outcomes: List[str], test_id: str = "t::x", check: str = "pytest"
) -> List[datetime]:
    """One history row per outcome, oldest first, a minute apart; their times."""
    times = [T0 + timedelta(minutes=k) for k in range(len(outcomes))]
    async with async_session_factory() as db:
        for k, (outcome, at) in enumerate(zip(outcomes, times, strict=True)):
            db.add(
                CheckTestOutcome(
                    project_id="proj-test",
                    check_name=check,
                    test_id=test_id,
                    file="",
                    outcome=outcome,
                    check_run_id=f"chk-{test_id}-{k}",
                    phase="review",
                    commit_sha="c" * 40,
                    recorded_at=at,
                )
            )
        await db.commit()
    return times


async def _rate(test_id: str = "t::x") -> dict:
    async with async_session_factory() as db:
        (row,) = await check_history.flake_rates(db, "proj-test", test_id=test_id)
    return row


def _at(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def test_the_flake_rate_is_the_flipped_runs_over_the_runs(app):
    """ac-flake-rate: 20 runs, 2 flipped, 1 failed throughout, 17 passed: 0.1, and the last
    flip is the later one."""
    outcomes = ["passed"] * 20
    outcomes[4], outcomes[11], outcomes[15] = "flipped", "flipped", "failed"
    times = await _runs(outcomes)
    rate = await _rate()
    assert rate["runs"] == 20 and rate["flips"] == 2
    assert rate["flake_rate"] == pytest.approx(0.1)
    assert _at(rate["last_flipped_at"]) == times[11]


async def test_the_rate_counts_only_the_last_100_runs_and_the_last_flip_is_kept(app):
    """ac-flake-rate-window: 120 runs whose only 3 flips are in the oldest 20: the rate is 0, the
    last-flipped time still the third flip's."""
    outcomes = ["passed"] * 120
    outcomes[2], outcomes[9], outcomes[17] = "flipped", "flipped", "flipped"
    times = await _runs(outcomes)
    rate = await _rate()
    assert rate["runs"] == 120 and rate["window_runs"] == 100 and rate["flips"] == 3
    assert rate["flake_rate"] == 0
    assert _at(rate["last_flipped_at"]) == times[17]


async def test_below_20_runs_there_is_no_rate_and_it_is_not_among_the_flakiest(app):
    """ac-flake-rate-minimum: 5 runs, 1 flipped: no rate, its flip count 1 with its time, and
    the dashboard's ten flakiest leave it out -- while a test with a rate is listed."""
    times = await _runs(["passed", "flipped", "passed", "passed", "passed"], test_id="t::young")
    old = ["passed"] * 20
    old[3] = "flipped"
    await _runs(old, test_id="t::old")
    rate = await _rate("t::young")
    assert rate["runs"] == 5
    assert rate["flake_rate"] is None
    assert rate["flips"] == 1
    assert _at(rate["last_flipped_at"]) == times[1]

    flakiest = await run_query("proj-test", check_history.TEN_FLAKIEST_SQL)
    listed = [row[flakiest["columns"].index("test_id")] for row in flakiest["rows"]]
    assert listed == ["t::old"]


async def test_the_flakiest_are_ten_highest_rates_first(app):
    for k in range(12):
        outcomes = ["passed"] * 20
        for j in range(k + 1):
            outcomes[j] = "flipped"
        await _runs(outcomes, test_id=f"t::{k:02d}")
    flakiest = await run_query("proj-test", check_history.TEN_FLAKIEST_SQL)
    column = flakiest["columns"].index("test_id")
    assert [row[column] for row in flakiest["rows"]] == [f"t::{k:02d}" for k in range(11, 1, -1)]
