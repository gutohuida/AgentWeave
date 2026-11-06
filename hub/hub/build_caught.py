"""What a build's checks caught, as its spec shows it (F1110): each failure, whether the build's
work caused it or the checks only found it, and how it was fixed.

Computed per read from the build's check runs and the project's known-failing list
(`known_failing`, `failures-already-known-are-on-a-list-not-re-argued`): a failure the list held is
`caught`, and its fix task is the list entry's owner. Nothing is stored, and nothing here adds a
requirement or holds the document from reading done.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import project_checks
from .db.models import Build, KnownFailingTest, Task, TaskCheckRun

INTRODUCED = "introduced"
CAUGHT = "caught"
_CLOSED = ("approved", "rejected")


def _entries(result: Any) -> List[Dict[str, Any]]:
    """The failures one check's result names, each with where it came from."""
    if not isinstance(result, dict) or result.get("skipped"):
        return []
    touched = set(result.get("touched_tests") or [])
    # The file the check's report gave for each failing test (FR-2): what `touched_tests` judged
    # "this build changed the file" by, shown beside the test.
    recorded = result.get("test_files")
    files: Dict[str, Any] = recorded if isinstance(recorded, dict) else {}
    found: List[Dict[str, Any]] = []
    for test in result.get("own_tests") or []:
        found.append({"test": test, "kind": "fails on this work", "origin": INTRODUCED})
    for entry in result.get("listed") or []:
        if isinstance(entry, dict) and entry.get("test"):
            found.append(
                {
                    "test": entry["test"],
                    "kind": entry.get("kind") or project_checks.FAILS_ON_MAIN,
                    "origin": CAUGHT,
                    "fix_task_id": entry.get("fix_task_id"),
                }
            )
    flaky = result.get("flaky") if isinstance(result.get("flaky"), dict) else {}
    for test in result.get("flaky_tests") or flaky.get("tests") or []:
        found.append({"test": test, "kind": project_checks.FLAKY, "origin": CAUGHT})
    if not found and project_checks.failed(result):
        # A failure named by no test: a timeout, a check without a report. An entry for the whole
        # check on the list makes it caught.
        origin = CAUGHT if project_checks.preexisting(result) else INTRODUCED
        entry = {"test": None, "kind": "check failed", "origin": origin}
        whole = [e for e in result.get("listed") or [] if isinstance(e, dict) and not e.get("test")]
        if whole:
            entry["fix_task_id"] = whole[0].get("fix_task_id")
        if result.get("whole_check"):
            # Why it names no test (`checks-report-which-tests-failed-in-any-language`, FR-4).
            entry["whole_check"] = str(result["whole_check"])
        found.append(entry)
    for entry in found:
        entry["check"] = str(result.get("name") or "check")
        entry["changed_by_build"] = entry["test"] in touched
        if entry["test"] and files.get(entry["test"]):
            entry["file"] = str(files[entry["test"]])
        if entry["changed_by_build"]:
            entry["origin"] = INTRODUCED
    return found


async def caught_during(session: AsyncSession, build: Build) -> List[Dict[str, Any]]:
    """Each failure *build*'s check runs found, oldest first, one row per check and test: the
    latest word on it, the task it was found on, and the fix task the Hub filed for it, if any."""
    tasks = {
        task.id: task
        for task in (await session.execute(select(Task).where(Task.build_id == build.id))).scalars()
    }
    if not tasks:
        return []
    runs = (
        await session.execute(
            select(TaskCheckRun)
            .where(TaskCheckRun.task_id.in_(tasks))
            .order_by(TaskCheckRun.started_at, TaskCheckRun.id)
        )
    ).scalars()
    rows: Dict[Tuple[str, Optional[str]], Dict[str, Any]] = {}
    for run in runs:
        for result in run.results or []:
            for entry in _entries(result):
                rows[(entry["check"], entry["test"])] = {
                    **entry,
                    "found_on": run.task_id,
                    "found_on_readable_id": tasks[run.task_id].display_id,
                    "found_on_status": tasks[run.task_id].status,
                }
    if not rows:
        return []
    # The owner fix task of each entry now on the list; an entry since removed keeps the one the
    # run recorded when it went past it.
    owners = {
        (check, test or None): fix_task_id
        for check, test, fix_task_id in (
            await session.execute(
                select(
                    KnownFailingTest.check_name,
                    KnownFailingTest.test,
                    KnownFailingTest.fix_task_id,
                ).where(KnownFailingTest.project_id == build.project_id)
            )
        ).all()
    }
    for row in rows.values():
        fix_id = owners.get((row["check"], row["test"])) or row.pop("fix_task_id", None)
        row.pop("fix_task_id", None)
        fix = await session.get(Task, fix_id) if fix_id else None
        row["fix_task"] = (
            {
                "id": fix.id,
                "readable_id": fix.display_id,
                "title": fix.title,
                "status": fix.status,
                "open": fix.status not in _CLOSED,
            }
            if fix is not None
            else None
        )
    return list(rows.values())
