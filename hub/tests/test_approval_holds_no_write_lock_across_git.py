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

from ._loop_lag import STALL_LIMIT, LagProbe
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


@dataclass
class Probe:
    writes: List[dict] = field(default_factory=list)

    @property
    def failed(self) -> List[dict]:
        """The writes a lock held across their git refused. Not how long a write took: with a
        100 ms busy timeout, a write that commits waited at most that long for anybody's lock, and
        any time beyond it is the machine's (1.756 s for one that waited for nobody, AW-40)."""
        return [w for w in self.writes if w["error"]]


async def database_file() -> str:
    async with engine.connect() as connection:
        rows = (await connection.exec_driver_sql("PRAGMA database_list")).all()
    return next(row[2] for row in rows if row[1] == "main")


def _write_until(path: str, window: float) -> str:
    """Insert and commit an event row from a second connection, retrying for *window* seconds;
    answer "" once one commits, else the last error."""
    deadline = time.perf_counter() + window
    while True:
        try:
            connection = sqlite3.connect(path, timeout=BUSY_TIMEOUT)
            try:
                connection.execute(
                    "INSERT INTO event_logs (id, project_id, event_type, severity,"
                    " timestamp) VALUES (?, 'proj-test', 'lock_probe', 'info', ?)",
                    (f"ev-probe-{uuid.uuid4().hex[:12]}", datetime.now(timezone.utc)),
                )
                connection.commit()
            finally:
                connection.close()
            return ""
        except sqlite3.OperationalError as exc:
            if time.perf_counter() >= deadline:
                return str(exc)


@contextlib.contextmanager
def a_write_during_every_git(path: str) -> Iterator[Probe]:
    probe = Probe()
    real = subprocess.run

    def _run(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        argv = args[0] if args else kwargs.get("args")
        if not (
            isinstance(argv, (list, tuple)) and argv and "git" in os.path.basename(str(argv[0]))
        ):
            return real(*args, **kwargs)
        started = time.perf_counter()
        # A lock held across this git is held before it starts and still held when it returns, so
        # a write fails both sides of it. A short transaction of the app's own, however far a busy
        # machine stretches it, cannot also span the slowed git between the two -- it is not what
        # this probes, so a write refused before the git is tried again after it.
        error = _write_until(path, GIT_DELAY * 2)
        time.sleep(GIT_DELAY)
        try:
            return real(*args, **kwargs)
        finally:
            if error:
                error = _write_until(path, GIT_DELAY * 2)
            probe.writes.append(
                {
                    "git": [str(a) for a in argv][1:9],
                    "error": error,
                    "seconds": round(time.perf_counter() - started, 3),
                    "thread": threading.current_thread().name,
                }
            )

    subprocess.run = _run
    try:
        yield probe
    finally:
        subprocess.run = real


def assert_no_write_waited(probe: Probe, lag: LagProbe) -> None:
    """No write waited for git, and the loop was never held meanwhile: git and its writes run on
    worker threads, so a 250 ms hold of the loop anywhere on the path counts too."""
    assert probe.writes, "nothing ran git, so this measured nothing"
    assert not probe.failed, probe.failed
    assert lag.worst < STALL_LIMIT, f"the loop stalled {lag.worst * 1000:.0f} ms: {lag.why}"


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
        async with LagProbe() as lag:
            approved = await app.patch(
                f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers
            )

    assert approved.status_code == 200, approved.text
    assert_no_write_waited(probe, lag)
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
        async with LagProbe() as lag:
            retried = await app.post(f"{TASKS}/{task}/integrations/retry", headers=auth_headers)

    assert retried.status_code == 200, retried.text
    assert_no_write_waited(probe, lag)
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
        async with LagProbe() as lag:
            rejected = await app.patch(
                f"{TASKS}/{task}", json={"status": "rejected"}, headers=auth_headers
            )

    assert rejected.status_code == 200, rejected.text
    assert_no_write_waited(probe, lag)
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
            async with LagProbe() as lag:
                await landing_queue.drain()
    finally:
        landing_queue.cancel_timers()

    assert_no_write_waited(probe, lag)
    for work in works:
        assert work in commits_on(tmp_path, "main")
    assert counter.exists()
