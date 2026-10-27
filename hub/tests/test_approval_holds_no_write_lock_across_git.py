"""No approval, landing, integration retry or checkout release holds the database's write lock while
git runs (`approved-work-merges-in-batches`, FR no-write-lock-across-git).

Before this change approval accepted the evidence, merged and released the checkout inside one
transaction, so every other writer waited for git -- the merge up to 2.1 s, the release 10 s at p95 --
and with SQLite's busy timeout behind it a concurrent request answered 500 "database is locked" (F349
is the same shape on another route).

The probe: every git process is slowed by 250 ms, and as each one starts a second connection to the
same database file, with a 100 ms busy timeout, inserts an event row and commits. A write lock held
across that git makes the insert fail with "database is locked"; none held lets it commit at once.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import sqlite3
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, List

import pytest

from hub import worktrees
from hub.db.engine import engine

from .test_approvals_and_evidence_never_freeze_the_hub import (
    _REAL_ENSURE_TASK_WORKTREE,
    _completed_task_with_accepted_work,
)
from .test_approved_work_merges_in_batches import (
    approve,
    counting_check,
    set_checks,
    tasks_under_review,
)
from .test_task_integration import (  # noqa: F401 -- `builder` is a fixture
    TASKS,
    builder,
    commits_on,
    drive_to,
    git,
    integrations,
)

GIT_DELAY = 0.25
BUSY_TIMEOUT = 0.1
#: A write that waits for nobody commits in milliseconds; one that waits for git fails at 0.1 s.
WRITE_BOUND = 1.0


@dataclass
class Probe:
    writes: List[dict] = field(default_factory=list)

    @property
    def failed(self) -> List[dict]:
        return [w for w in self.writes if w["error"] or w["seconds"] > WRITE_BOUND]


async def database_file() -> str:
    async with engine.connect() as connection:
        rows = (await connection.exec_driver_sql("PRAGMA database_list")).all()
    return next(row[2] for row in rows if row[1] == "main")


@contextlib.contextmanager
def a_write_during_every_git(path: str) -> Iterator[Probe]:
    probe = Probe()
    real = subprocess.run

    def _run(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        argv = args[0] if args else kwargs.get("args")
        if isinstance(argv, (list, tuple)) and argv and "git" in os.path.basename(str(argv[0])):
            started = time.perf_counter()
            error = ""
            try:
                connection = sqlite3.connect(path, timeout=BUSY_TIMEOUT)
                try:
                    connection.execute(
                        "INSERT INTO event_logs (id, project_id, event_type, severity, timestamp)"
                        " VALUES (?, 'proj-test', 'lock_probe', 'info', ?)",
                        (f"ev-probe-{uuid.uuid4().hex[:12]}", datetime.now(timezone.utc)),
                    )
                    connection.commit()
                finally:
                    connection.close()
            except sqlite3.OperationalError as exc:
                error = str(exc)
            probe.writes.append(
                {
                    "git": [str(a) for a in argv][1:9],
                    "error": error,
                    "seconds": round(time.perf_counter() - started, 3),
                    "thread": threading.current_thread().name,
                }
            )
            time.sleep(GIT_DELAY)
        return real(*args, **kwargs)

    subprocess.run = _run
    try:
        yield probe
    finally:
        subprocess.run = real


def assert_no_write_waited(probe: Probe) -> None:
    assert probe.writes, "nothing ran git, so this measured nothing"
    assert not probe.failed, probe.failed


@pytest.mark.asyncio
async def test_approving_holds_no_write_lock_while_it_merges_and_releases(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, work = await _completed_task_with_accepted_work(app, auth_headers, builder, tmp_path)
    checkout = _REAL_ENSURE_TASK_WORKTREE(tmp_path, task, "main")
    moved = await drive_to(app, auth_headers, task, "under_review")
    assert moved.status_code == 200, moved.text
    path = await database_file()

    with a_write_during_every_git(path) as probe:
        approved = await app.patch(
            f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers
        )

    assert approved.status_code == 200, approved.text
    assert_no_write_waited(probe)
    assert any("merge" in w["git"] for w in probe.writes), "the merge ran no git"
    # The same outcome as before: merged, recorded, released.
    assert work in commits_on(tmp_path, "main")
    assert [row["outcome"] for row in await integrations(app, auth_headers, task)] == ["merged"]
    assert not checkout.exists()


@pytest.mark.asyncio
async def test_retrying_an_integration_holds_no_write_lock_while_it_merges(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, work = await _completed_task_with_accepted_work(app, auth_headers, builder, tmp_path)
    moved = await drive_to(app, auth_headers, task, "under_review")
    assert moved.status_code == 200, moved.text
    (tmp_path / "README.md").write_text("an operator's edit\n", encoding="utf-8")
    approved = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)
    assert approved.status_code == 200, approved.text
    assert [row["outcome"] for row in await integrations(app, auth_headers, task)] == ["skipped"]
    git(tmp_path, "checkout", "--", "README.md")
    path = await database_file()

    with a_write_during_every_git(path) as probe:
        retried = await app.post(f"{TASKS}/{task}/integrations/retry", headers=auth_headers)

    assert retried.status_code == 200, retried.text
    assert_no_write_waited(probe)
    assert work in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_releasing_a_rejected_tasks_checkout_holds_no_write_lock(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task, _ = await _completed_task_with_accepted_work(app, auth_headers, builder, tmp_path)
    checkout = _REAL_ENSURE_TASK_WORKTREE(tmp_path, task, "main")
    assert checkout.exists()
    moved = await drive_to(app, auth_headers, task, "under_review")
    assert moved.status_code == 200, moved.text
    path = await database_file()

    with a_write_during_every_git(path) as probe:
        rejected = await app.patch(
            f"{TASKS}/{task}", json={"status": "rejected"}, headers=auth_headers
        )

    assert rejected.status_code == 200, rejected.text
    assert_no_write_waited(probe)
    assert not checkout.exists()
    assert git(tmp_path, "rev-parse", "--verify", worktrees.task_branch_name(task)).returncode == 0


@pytest.mark.asyncio
async def test_landing_a_batch_holds_no_write_lock_while_git_or_a_check_runs(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    landing_queue = importlib.import_module("hub.landing_queue")
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    check, counter = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 2)
    await set_checks([check])
    for task_id in ids:
        assert (await approve(app, auth_headers, task_id)).status_code == 200
    path = await database_file()

    try:
        with a_write_during_every_git(path) as probe:
            await landing_queue.drain()
    finally:
        landing_queue.cancel_timers()

    assert_no_write_waited(probe)
    for work in works:
        assert work in commits_on(tmp_path, "main")
    assert counter.exists()
