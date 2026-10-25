"""Acceptance drive for `turn-starts-approvals-and-evidence-never-freeze-the-hub` (Tier 2).

A loop-lag probe (a 10 ms `asyncio.sleep` sampler) inside a scratch Hub, in this process, on a
COPY of a Hub database whose project is rebound to a scratch clone of this repository. Each
scenario drives the Hub's own code path and reports the longest loop stall it saw; a stall is the
overshoot of one 10 ms sample, and the limit is 100 ms (the spec's requirements).

Safety, by construction rather than by care:

- The source database is opened read-only and copied with SQLite's backup API; the Hub only ever
  opens the copy. The operator's live database (`~/.agentweave/hub/data/agentweave.db`) is refused
  as a source outright, and so is any copy path outside the scratch directory.
- Every project in the copy is unbound except the one rebound to the scratch clone, so no git runs
  against a real checkout. `HOME`/`USERPROFILE` point into scratch, so a Copilot home is written there.
- No socket is opened: requests go through `httpx.ASGITransport`. Nothing contacts :8000 or :8010.
- The lifespan is off by default (no scheduler, no loops, no sweeps). `--lifespan` turns it on, and
  is refused unless the copy's jobs, manager jobs, loops, queued input and running runs are all
  disabled (`unsafe_for_lifespan`); the drive disables them in its own copy before checking.
- Runner processes are never spawned: `_execute_run` is replaced by a stub that marks the spawn
  point; the line scenarios replace only the process (`PtySession.spawn`/`PipeSession.spawn`, and
  the RPC transports' `run_turn`) and run the Hub's real executors around it.

    py -3.11 scripts/drive/perf_loop_lag.py                # every scenario
    py -3.11 scripts/drive/perf_loop_lag.py --only turn,approve
    py -3.11 scripts/drive/perf_loop_lag.py --check-guard  # show the guard refusing a raw copy

Exit status 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
LIVE_DB = (Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db").resolve()
DEFAULT_SOURCE = Path(r"C:\Users\huida\aw-perf\real-C.db")
PROJECT = "proj-d85a82bf4216"
OPERATOR_KEY = "aw_live_" + "perfloop" * 4
STALL_LIMIT = 0.100
SAMPLE = 0.010

# ---------------------------------------------------------------------------------------------
# Scratch setup (before any `hub` import: the engine binds DATABASE_URL at import time)
# ---------------------------------------------------------------------------------------------


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def copy_database(source: Path, target: Path) -> None:
    if source.resolve() == LIVE_DB:
        raise SystemExit(f"refusing to use the live operator database {LIVE_DB} as a source")
    if target.exists():
        target.unlink()
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


_MIGRATE = """
import asyncio, sqlite3, sys
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
import hub.db.engine as e
asyncio.run(e._run_alembic_upgrade())
head = ScriptDirectory.from_config(
    Config(str(Path(e.__file__).parent.parent / "alembic.ini"))
).get_current_head()
have = sqlite3.connect(sys.argv[1]).execute("select version_num from alembic_version").fetchone()[0]
print("MIGRATED", have, head)
sys.exit(0 if have == head else 1)
"""


def migrate_to_head(db: Path) -> None:
    """Upgrade the copy to this checkout's head, as a Hub does when it starts (in a child process,
    so this one's engine is not bound before DATABASE_URL names the copy)."""
    env = dict(os.environ, DATABASE_URL="sqlite+aiosqlite:///" + db.resolve().as_posix())
    result = subprocess.run(
        [sys.executable, "-c", _MIGRATE, str(db)],
        cwd=str(REPO / "hub"),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit(
            "could not migrate the copy:\n" + result.stdout[-600:] + result.stderr[-600:]
        )
    print("  " + [ln for ln in result.stdout.splitlines() if ln.startswith("MIGRATED")][-1])


def unsafe_for_lifespan(db_path: Path) -> List[str]:
    """Why a Hub with its lifespan on must not start against *db_path* (empty: it may)."""
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    reasons = []
    try:
        checks = {
            "enabled jobs": "select count(*) from ai_jobs where enabled = 1 and archived_at is null",
            "enabled manager jobs": "select count(*) from manager_jobs where enabled = 1",
            # A loop fires only through its job, so a loop is disabled when its job is.
            "loops that can fire": "select count(*) from loops l join ai_jobs j "
            "on j.id = l.job_id where j.enabled = 1 and l.stopped_at is null "
            "and l.archived_at is null",
            "queued input": "select count(*) from inbound_queue_entries where state = 'queued'",
            "running runs": "select count(*) from runs where status in ('running', 'pending')",
            "scheduled jobs": "select count(*) from apscheduler_jobs",
        }
        for label, sql in checks.items():
            count = connection.execute(sql).fetchone()[0]
            if count:
                reasons.append(f"{count} {label}")
    finally:
        connection.close()
    return reasons


def disable_background_work(db_path: Path, clone: Path) -> None:
    sys.path.insert(0, str(REPO / "hub"))
    from hub.project_workspace import canonical_path_key  # pure; no engine import

    now = datetime.now(timezone.utc).isoformat(sep=" ")
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("update ai_jobs set enabled = 0")
        connection.execute("update manager_jobs set enabled = 0")
        connection.execute(
            "update inbound_queue_entries set state = 'withdrawn', withdrawn_at = ? "
            "where state = 'queued'",
            (now,),
        )
        connection.execute(
            "update runs set status = 'failed' where status in ('running', 'pending')"
        )
        connection.execute("delete from apscheduler_jobs")
        resolved = clone.resolve()
        connection.execute(
            "update projects set working_directory = null, path_key = null, "
            "directory_state = 'unbound' where id != ?",
            (PROJECT,),
        )
        connection.execute(
            # `checks = null`: the project's own checks are a full test suite, which a drive on a
            # shared machine must never start as a side effect of completing a task.
            "update projects set working_directory = ?, path_key = ?, checks = null, "
            "directory_state = 'available' where id = ?",
            (str(resolved), canonical_path_key(resolved), PROJECT),
        )
        connection.execute(
            "insert or ignore into operator_credentials (id, label, revoked, created_at) "
            "values (?, 'perf drive', 0, ?)",
            (OPERATOR_KEY, now),
        )
        connection.commit()
    finally:
        connection.close()


def make_clone(source_repo: Path, clone: Path) -> None:
    if clone.exists():
        shutil.rmtree(clone, onerror=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--depth",
            "300",
            "--branch",
            "master",
            source_repo.resolve().as_uri(),
            str(clone),
        ],
        check=True,
    )
    _git(clone, "config", "user.email", "perf@example.invalid")
    _git(clone, "config", "user.name", "perf drive")
    marker = clone / ".agentweave" / "project.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"version": 1, "project_id": PROJECT}), encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------------------------

MAIN_THREAD = threading.main_thread()
GIT_CALLS: List[Dict[str, Any]] = []
_real_run = subprocess.run


def _counted_run(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
    argv = args[0] if args else kwargs.get("args")
    started = time.perf_counter()
    try:
        return _real_run(*args, **kwargs)
    finally:
        if isinstance(argv, (list, tuple)) and argv and "git" in os.path.basename(str(argv[0])):
            GIT_CALLS.append(
                {
                    "argv": [str(a) for a in argv[:4]],
                    "start": started,
                    "seconds": time.perf_counter() - started,
                    "on_loop": threading.current_thread() is MAIN_THREAD,
                }
            )


class Probe:
    """Samples the loop every 10 ms; a stall is how late a sample woke."""

    def __init__(self) -> None:
        self.worst = 0.0
        self.samples = 0
        self._on = True
        self._task: Optional[asyncio.Task] = None

    async def _run(self) -> None:
        while self._on:
            started = time.perf_counter()
            await asyncio.sleep(SAMPLE)
            late = time.perf_counter() - started - SAMPLE
            self.samples += 1
            self.worst = max(self.worst, late)

    async def __aenter__(self) -> "Probe":
        self._task = asyncio.create_task(self._run())
        await asyncio.sleep(0.03)
        self.worst = 0.0
        GIT_CALLS.clear()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await asyncio.sleep(0.03)
        self._on = False
        if self._task is not None:
            await self._task


RESULTS: List[Dict[str, Any]] = []


def check(
    requirement: str, name: str, value: float, limit: float, unit: str, note: str = ""
) -> None:
    ok = value <= limit
    RESULTS.append(
        {"requirement": requirement, "check": name, "value": value, "limit": limit, "ok": ok}
    )
    loop_git = sum(1 for call in GIT_CALLS if call["on_loop"])
    print(
        f"  [{'PASS' if ok else 'FAIL'}] {requirement:26s} {name:34s} "
        f"{value:9.1f}{unit} (limit {limit:g}{unit})  git on loop: {loop_git} {note}",
        flush=True,
    )


def fail(requirement: str, name: str, why: str) -> None:
    RESULTS.append(
        {"requirement": requirement, "check": name, "value": None, "limit": None, "ok": False}
    )
    print(f"  [FAIL] {requirement:26s} {name:34s} could not run: {why}", flush=True)


async def stalled(requirement: str, name: str, work: Callable[[], Any], note: str = "") -> Any:
    async with Probe() as probe:
        started = time.perf_counter()
        result = await work()
        elapsed = time.perf_counter() - started
    check(
        requirement,
        name,
        probe.worst * 1000,
        STALL_LIMIT * 1000,
        "ms",
        f"({elapsed * 1000:.0f}ms wall) {note}",
    )
    return result


# ---------------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------------


class Drive:
    def __init__(self, clone: Path) -> None:
        self.clone = clone
        from hub.api.v1 import agent_trigger
        from hub.db.engine import async_session_factory
        from hub.main import app

        self.app = app
        self.trigger = agent_trigger
        self.sessions = async_session_factory
        self.spawned: Dict[str, float] = {}
        self.spawn_kwargs: Dict[str, Dict[str, Any]] = {}
        self.real_execute_run = agent_trigger._execute_run
        self.tasks: Dict[str, str] = {}
        self.agents: Dict[str, str] = {}

        async def _stub_execute_run(**kwargs: Any) -> None:
            run_id = kwargs["run_id"]
            self.spawned[run_id] = time.perf_counter()
            self.spawn_kwargs[run_id] = kwargs
            from hub.db.models import Run

            async with self.sessions() as db:
                run = await db.get(Run, run_id)
                if run is not None:
                    run.status = "completed"
                    run.ended_at = datetime.now(timezone.utc)
                    await db.commit()

        agent_trigger._execute_run = _stub_execute_run

    def client(self):
        import httpx

        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://perf.invalid",
            headers={"Authorization": f"Bearer {OPERATOR_KEY}"},
            timeout=300,
        )

    async def setup_agents(self) -> None:
        from sqlalchemy import select

        from hub.db.models import Agent, Runner

        async with self.sessions() as db:
            runners = (
                (await db.execute(select(Runner).where(Runner.project_id == PROJECT)))
                .scalars()
                .all()
            )
            by_cli: Dict[str, str] = {}
            for runner in runners:
                if runner.cli not in by_cli or runner.model:
                    by_cli.setdefault(runner.cli, runner.id)
            for kind in ("claude", "copilot", "codex"):
                name = f"perf-{kind}"
                self.agents[kind] = name
                existing = (
                    await db.execute(
                        select(Agent).where(Agent.project_id == PROJECT, Agent.name == name)
                    )
                ).scalar_one_or_none()
                if existing is None:
                    db.add(
                        Agent(
                            id=f"agent-{uuid.uuid4().hex[:12]}",
                            project_id=PROJECT,
                            name=name,
                            config={},
                            runner_id=by_cli[kind],
                            lifecycle="open",
                        )
                    )
            await db.commit()

    async def new_task(self, agent: str, title: str) -> str:
        from hub.db.models import Task

        task_id = f"task-{uuid.uuid4().hex[:12]}"
        async with self.sessions() as db:
            db.add(
                Task(
                    id=task_id,
                    project_id=PROJECT,
                    title=title,
                    description="perf drive",
                    status="assigned",
                    assignee=agent,
                    assigner="operator",
                    workspace_scheme="task",
                )
            )
            await db.commit()
        return task_id

    async def start_turn(self, agent: str, task_id: Optional[str]) -> str:
        from hub.conversations import new_conversation

        async with self.sessions() as db:
            conversation = new_conversation(project_id=PROJECT, agent=agent, origin="operator")
            db.add(conversation)
            await db.commit()
            response = await self.trigger.trigger_agent_directly(
                project_id=PROJECT,
                agent=agent,
                message="perf drive turn",
                conversation_id=conversation.id,
                session=db,
                task_id=task_id,
            )
            await db.commit()
        return response.run_id

    # -- FR-1 -----------------------------------------------------------------------------
    async def turn_starts(self) -> None:
        print("turn-start-no-stall", flush=True)
        for kind in ("claude", "copilot", "codex"):
            agent = self.agents[kind]
            task_id = await self.new_task(agent, f"perf turn {kind}")
            self.tasks[kind] = task_id
            try:
                run_id = await stalled(
                    "turn-start-no-stall",
                    f"{kind} turn start to spawn",
                    lambda: self.start_turn(agent, task_id),
                )
                if run_id not in self.spawned:
                    fail("turn-start-no-stall", f"{kind} spawned", "the stub was never reached")
            except Exception as exc:  # noqa: BLE001
                fail("turn-start-no-stall", f"{kind} turn start to spawn", repr(exc)[:300])

    # -- FR-6 -----------------------------------------------------------------------------
    async def starvation(self) -> None:
        """Eight streaming runs each hold a blocking read on the default executor, which is
        sized as a 4-CPU VDI's (`min(32, cpu + 4)` = 8). A turn start's git must still begin
        within 100 ms."""
        print("blocking-work-not-starved", flush=True)
        loop = asyncio.get_running_loop()
        small = ThreadPoolExecutor(max_workers=8, thread_name_prefix="vdi-default")
        loop.set_default_executor(small)
        release = threading.Event()
        readers = [loop.run_in_executor(None, release.wait, 60) for _ in range(8)]
        await asyncio.sleep(0.05)
        agent = self.agents["claude"]
        task_id = await self.new_task(agent, "perf starvation")
        try:
            GIT_CALLS.clear()
            asked = time.perf_counter()
            try:
                await asyncio.wait_for(self.start_turn(agent, task_id), timeout=20)
            except asyncio.TimeoutError:
                pass
            offloaded = [call for call in GIT_CALLS if not call["on_loop"]]
            if not offloaded:
                fail(
                    "blocking-work-not-starved",
                    "first off-loop git begins",
                    f"no git ran off the loop ({len(GIT_CALLS)} on it)",
                )
            else:
                first = min(call["start"] for call in offloaded) - asked
                check(
                    "blocking-work-not-starved",
                    "first off-loop git begins",
                    first * 1000,
                    100,
                    "ms",
                )
        finally:
            release.set()
            await asyncio.gather(*readers, return_exceptions=True)
            loop.set_default_executor(ThreadPoolExecutor())

    # -- FR-2 -----------------------------------------------------------------------------
    async def approval(self) -> None:
        print("approval-no-stall (and evidence/review staffing on the same task)", flush=True)
        task_id = self.tasks.get("claude")
        if task_id is None:
            fail("approval-no-stall", "approve", "no task from the turn-start scenario")
            return
        from hub import worktrees

        checkout = worktrees.task_worktree_path(self.clone, task_id)
        if not checkout.exists():
            fail("approval-no-stall", "approve", f"no checkout at {checkout}")
            return
        (checkout / "perf-drive.txt").write_text(f"{task_id}\n", encoding="utf-8")
        _git(checkout, "add", "perf-drive.txt")
        _git(checkout, "commit", "-q", "-m", f"perf drive work for {task_id}")
        work_sha = _git(checkout, "rev-parse", "HEAD")
        async with self.client() as c:
            base = f"/api/v1/projects/{PROJECT}/tasks/{task_id}"
            for status in ("in_progress", "completed"):
                r = await c.patch(base, json={"status": status})
                if r.status_code >= 400:
                    fail(
                        "approval-no-stall", "approve", f"{status}: {r.status_code} {r.text[:300]}"
                    )
                    return
        # A flow's task with accepted evidence naming its commit: what approval merges, and what
        # GET /loops asks git about while the task is under review.
        try:
            await self._flow_evidence(task_id, work_sha)
        except Exception as exc:  # noqa: BLE001
            fail("approval-no-stall", "accepted evidence", repr(exc)[:300])
            return
        await self.review_staffing(task_id)
        async with self.client() as c:
            base = f"/api/v1/projects/{PROJECT}/tasks/{task_id}"
            r = await c.patch(base, json={"status": "under_review"})
            if r.status_code >= 400:
                fail(
                    "approval-no-stall", "approve", f"under_review: {r.status_code} {r.text[:300]}"
                )
                return
        # Under review by a reviewer with no turn running: the flow's board asks whether its
        # approval is held for the operator.
        from hub.db.models import Task

        async with self.sessions() as db:
            (await db.get(Task, task_id)).assignee = "QA"
            await db.commit()
        await self.loops()
        async with self.client() as c:
            base = f"/api/v1/projects/{PROJECT}/tasks/{task_id}"

            async def approve():
                return await c.patch(base, json={"status": "approved"})

            r = await stalled("approval-no-stall", "approve (release + merge)", approve)
            if r.status_code >= 400:
                fail("approval-no-stall", "approve outcome", f"{r.status_code} {r.text[:300]}")
                return
        merged = _git(self.clone, "log", "-1", "--format=%s", "master")
        released = not checkout.exists()
        print(f"    outcome: checkout released={released}, master tip={merged!r}", flush=True)
        if not released:
            fail("approval-no-stall", "checkout released", "the checkout is still on disk")
        landed = (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", work_sha, "master"],
                cwd=str(self.clone),
                capture_output=True,
            ).returncode
            == 0
        )
        if not landed:
            fail("approval-no-stall", "work merged", f"{work_sha[:12]} is not on master")

    async def _flow_evidence(self, task_id: str, sha: str) -> None:
        from sqlalchemy import select

        from hub.db.models import Loop, SpecDocument, SpecRequirement, Task, TaskRequirementLink

        async with self.sessions() as db:
            loops = (
                (
                    await db.execute(
                        select(Loop)
                        .where(
                            Loop.project_id == PROJECT,
                            Loop.archived_at.is_(None),
                            Loop.spec_document_id.is_not(None),
                        )
                        .order_by(Loop.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            chosen = None
            for loop in loops:
                requirement = (
                    await db.execute(
                        select(SpecRequirement.identifier, SpecDocument.path, SpecRequirement.id)
                        .join(SpecDocument, SpecDocument.id == SpecRequirement.document_id)
                        .where(
                            SpecRequirement.document_id == loop.spec_document_id,
                            SpecRequirement.state == "active",
                        )
                        .limit(1)
                    )
                ).first()
                if requirement is not None:
                    chosen = (loop, requirement)
                    break
            if chosen is None:
                raise RuntimeError("no flow with an active requirement in the copy")
            loop, requirement = chosen
            loop.stopped_at = None  # its job stays disabled, so it never fires
            task = await db.get(Task, task_id)
            task.loop_id = loop.id
            db.add(
                TaskRequirementLink(
                    id=f"trl-{uuid.uuid4().hex[:12]}",
                    project_id=PROJECT,
                    task_id=task_id,
                    requirement_id=requirement[2],
                    actor_kind="operator",
                    actor="operator",
                )
            )
            await db.commit()
        async with self.client() as c:
            r = await c.post(
                f"/api/v1/projects/{PROJECT}/project/spec/evidence",
                json={
                    "identifier": requirement[0],
                    "document": requirement[1],
                    "locator": "perf-drive.txt",
                    "summary": "perf drive work",
                    "task_id": task_id,
                    "commit": sha,
                },
            )
            if r.status_code >= 400:
                raise RuntimeError(f"{r.status_code} {r.text[:300]}")
        # As an agent's piece lands: awaiting the reviewer's verdict, which approval gives. While
        # it waits, the flow's board asks whether approval is held (git, every GET /loops).
        from hub.db.models import RequirementEvidence

        async with self.sessions() as db:
            piece = await db.get(RequirementEvidence, r.json()["id"])
            piece.review_state = "awaiting"
            await db.commit()

    async def review_staffing(self, task_id: str) -> None:
        from hub import review_turn, worktrees

        async def staff():
            async with self.sessions() as db:
                try:
                    return await review_turn.prepare_review_turn(
                        db,
                        project_id=PROJECT,
                        reviewer="QA",
                        task_id=task_id,
                        repo_root=self.clone,
                    )
                finally:
                    await db.rollback()

        try:
            await stalled("evidence-no-stall", "review staffing", staff)
        except Exception as exc:  # noqa: BLE001
            fail("evidence-no-stall", "review staffing", repr(exc)[:300])
        finally:
            await asyncio.to_thread(worktrees.release_review_checkout, self.clone, "QA")

    # -- FR-3 -----------------------------------------------------------------------------
    async def evidence(self) -> None:
        print("evidence-no-stall", flush=True)
        from sqlalchemy import func, select

        from hub import stalls
        from hub.db.models import RequirementEvidence, SpecDocument, SpecRequirement, Stall

        async with self.sessions() as db:
            row = (
                await db.execute(
                    select(SpecRequirement.identifier, SpecDocument.path)
                    .join(SpecDocument, SpecDocument.id == SpecRequirement.document_id)
                    .where(SpecRequirement.project_id == PROJECT, SpecRequirement.state == "active")
                    .limit(1)
                )
            ).first()
            run_row = (
                await db.execute(
                    select(RequirementEvidence.run_id, func.count())
                    .where(
                        RequirementEvidence.project_id == PROJECT,
                        RequirementEvidence.actor_kind == "agent",
                        RequirementEvidence.run_id.is_not(None),
                    )
                    .group_by(RequirementEvidence.run_id)
                    .order_by(func.count().desc())
                    .limit(1)
                )
            ).first()
            stall = (
                (await db.execute(select(Stall).where(Stall.project_id == PROJECT).limit(1)))
                .scalars()
                .first()
            )
        async with self.client() as c:
            if row is None:
                fail("evidence-no-stall", "record evidence", "no active requirement in the copy")
            else:

                async def record():
                    r = await c.post(
                        f"/api/v1/projects/{PROJECT}/project/spec/evidence",
                        json={
                            "identifier": row[0],
                            "document": row[1],
                            "locator": "hub/hub/main.py",
                            "summary": f"perf drive {uuid.uuid4().hex[:6]}",
                        },
                    )
                    if r.status_code >= 400:
                        raise RuntimeError(f"{r.status_code} {r.text[:300]}")

                try:
                    await stalled("evidence-no-stall", "record evidence", record)
                except Exception as exc:  # noqa: BLE001
                    fail("evidence-no-stall", "record evidence", repr(exc)[:300])

            async def drift():
                r = await c.post(f"/api/v1/projects/{PROJECT}/project/spec/drift/detect")
                if r.status_code >= 400:
                    raise RuntimeError(f"{r.status_code} {r.text[:300]}")

            try:
                await stalled("evidence-no-stall", "drift detection", drift)
            except Exception as exc:  # noqa: BLE001
                fail("evidence-no-stall", "drift detection", repr(exc)[:300])

        if run_row is None:
            fail("evidence-no-stall", "run-end restamp", "no agent evidence in the copy")
        else:

            async def restamp():
                async with self.sessions() as db:
                    await self.trigger._restamp_evidence_footprints(
                        db,
                        project_id=PROJECT,
                        run_id=run_row[0],
                        worktree=self.clone,
                        snapshot_sha=None,
                    )
                    await db.rollback()

            await stalled("evidence-no-stall", "run-end restamp", restamp, f"({run_row[1]} rows)")

        if stall is None:
            fail("evidence-no-stall", "mender brief", "no stall in the copy")
        else:

            async def brief():
                async with self.sessions() as db:
                    held = await db.get(Stall, stall.id)
                    return await stalls.brief(db, held)

            await stalled("evidence-no-stall", "mender brief", brief)

    # -- FR-7 -----------------------------------------------------------------------------
    async def spec_lists(self) -> None:
        print("spec-list-cost", flush=True)
        async with self.client() as c:
            base = f"/api/v1/projects/{PROJECT}/project"
            for route in ("specs", "documents"):
                r = await c.get(f"{base}/{route}")  # warm
                if r.status_code >= 400:
                    fail("spec-list-cost", f"GET {route}", f"{r.status_code} {r.text[:200]}")
                    continue
                walls: List[float] = []

                async def five():
                    for _ in range(5):
                        started = time.perf_counter()
                        await c.get(f"{base}/{route}")
                        walls.append(time.perf_counter() - started)

                await stalled("spec-list-cost", f"GET {route} x5 (stall)", five)
                check(
                    "spec-list-cost",
                    f"GET {route} median",
                    statistics.median(walls) * 1000,
                    100,
                    "ms",
                )
            # Freshness: one document's file changes on disk.
            documents = (await c.get(f"{base}/documents")).json()["documents"]
            target = next(
                (
                    d
                    for d in documents
                    if not d.get("diverged") and (self.clone / d["path"]).is_file()
                ),
                None,
            )
            if target is None:
                fail("spec-list-cost", "fresh after a change", "no undiverged document on disk")
                return
            path = self.clone / target["path"]
            before = {s["path"]: s for s in (await c.get(f"{base}/specs")).json()["specs"]}
            text = path.read_text(encoding="utf-8")
            payload = json.loads(text)
            payload["title"] = f"{payload.get('title', '')} (perf drive edit)"
            time.sleep(0.02)
            path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
            after_specs = {s["path"]: s for s in (await c.get(f"{base}/specs")).json()["specs"]}
            after_docs = {
                d["path"]: d for d in (await c.get(f"{base}/documents")).json()["documents"]
            }
            moved = after_specs.get(target["path"], {}).get("updated_at") != before.get(
                target["path"], {}
            ).get("updated_at")
            diverged = bool(after_docs.get(target["path"], {}).get("diverged"))
            path.write_text(text, encoding="utf-8")
            check(
                "spec-list-cost",
                "fresh after a change (0 = fresh)",
                0 if (moved and diverged) else 1,
                0,
                "",
                f"updated_at moved={moved} diverged={diverged}",
            )

    # -- integrator's addition: GET /loops git calls -----------------------------------------
    async def loops(self, task_id: Optional[str] = None) -> None:
        """GET /loops with a live loop holding an under_review task with a branch: its
        availability path asks git about ancestry and mergeability on every request."""
        print("loops-git (D4: unchanged facts are not recomputed)", flush=True)
        from sqlalchemy import select

        from hub.db.models import Loop, Task

        if task_id is not None:
            async with self.sessions() as db:
                loop = (
                    (
                        await db.execute(
                            select(Loop)
                            .where(Loop.project_id == PROJECT, Loop.archived_at.is_(None))
                            .order_by(Loop.created_at.desc())
                        )
                    )
                    .scalars()
                    .first()
                )
                task = await db.get(Task, task_id)
                if loop is not None and task is not None:
                    loop.stopped_at = None  # its job stays disabled, so it never fires
                    task.loop_id = loop.id
                    await db.commit()
        async with self.client() as c:
            url = f"/api/v1/projects/{PROJECT}/loops"
            r = await c.get(url)
            if r.status_code >= 400:
                fail("spec-list-cost", "GET loops", f"{r.status_code} {r.text[:200]}")
                return

            async def again():
                return await c.get(url)

            await stalled("evidence-no-stall", "GET loops (stall)", again)
            GIT_CALLS.clear()
            started = time.perf_counter()
            await c.get(url)
            wall = time.perf_counter() - started
            check(
                "loops-steady-state",
                "GET loops steady-state git calls",
                len(GIT_CALLS),
                3,
                "",
                f"({wall * 1000:.0f}ms wall)",
            )

    # -- FR-4 / FR-5 ----------------------------------------------------------------------
    def _claude_lines(self, count: int, session: str) -> List[str]:
        lines = [
            json.dumps(
                {"type": "system", "subtype": "init", "session_id": session, "model": "haiku"}
            )
        ]
        for i in range(count - 1):
            if i % 4 == 2:
                block = {
                    "type": "tool_use",
                    "id": f"toolu_perf_{i}",
                    "name": "Read",
                    "input": {"file_path": "README.md"},
                }
                lines.append(
                    json.dumps(
                        {
                            "type": "assistant",
                            "session_id": session,
                            "message": {"content": [block]},
                        }
                    )
                )
            elif i % 4 == 3:
                lines.append(
                    json.dumps(
                        {
                            "type": "user",
                            "session_id": session,
                            "message": {
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": f"toolu_perf_{i - 1}",
                                        "content": "y" * 2000,
                                    }
                                ]
                            },
                        }
                    )
                )
            else:
                kind = "thinking" if i % 4 == 0 else "text"
                block = {"type": kind, kind: f"line {i} " + "x" * 400}
                lines.append(
                    json.dumps(
                        {
                            "type": "assistant",
                            "session_id": session,
                            "message": {"content": [block]},
                        }
                    )
                )
        return lines

    def _rpc_events(self, count: int) -> List[Any]:
        from hub.runner_events import RunEvent

        events = []
        for i in range(count):
            if i % 4 == 2:
                events.append(
                    RunEvent(
                        kind="tool_use",
                        content="Called Read",
                        payload={
                            "version": 1,
                            "call_id": f"call-{i}",
                            "tool": "Read",
                            "category": "read",
                            "input": '{"path": "README.md"}',
                            "summary": "Called Read",
                        },
                        call_id=f"call-{i}",
                    )
                )
            elif i % 4 == 3:
                events.append(
                    RunEvent(
                        kind="tool_result",
                        content="tool completed",
                        payload={
                            "version": 1,
                            "call_id": f"call-{i - 1}",
                            "tool": "Read",
                            "output": "y" * 2000,
                            "summary": "tool completed",
                            "is_error": False,
                        },
                        call_id=f"call-{i - 1}",
                    )
                )
            else:
                kind = "thinking" if i % 4 == 0 else "text"
                events.append(
                    RunEvent(
                        kind=kind,
                        content=f"line {i} " + "x" * 400,
                        payload={"version": 1, "text": f"line {i} " + "x" * 400},
                    )
                )
        return events

    async def _replay(
        self,
        kind: str,
        count: int,
        interval: float,
        on_line: Optional[Callable] = None,
        run_id: Optional[str] = None,
    ) -> str:
        """Start a turn (spawn stubbed) unless *run_id* names one, then run the Hub's real
        executor for it with only the process replaced: *count* lines, one every *interval*."""
        from unittest.mock import MagicMock, patch

        agent = self.agents[kind]
        if run_id is None:
            run_id = await self.start_turn(agent, None)
        kwargs = dict(self.spawn_kwargs[run_id])
        from hub.db.models import Run

        async with self.sessions() as db:
            run = await db.get(Run, run_id)
            run.status = "running"
            run.ended_at = None
            await db.commit()
        session_id = f"sess-perf-{uuid.uuid4().hex[:8]}"
        patches = []
        if kind == "claude":
            lines = self._claude_lines(count, session_id)
            state = {"i": 0}

            def _spawn(*_a, **_k):
                fake = MagicMock()
                fake.pid = 4242

                def _read(*_x, **_y):
                    i = state["i"]
                    state["i"] += 1
                    if i >= len(lines):
                        return ""
                    if interval:
                        time.sleep(interval)
                    if on_line is not None:
                        on_line(i)
                    return lines[i] + "\n"

                fake.read.side_effect = _read
                fake.wait.return_value = 0
                return fake

            patches = [
                patch.object(self.trigger.PtySession, "spawn", side_effect=_spawn),
                patch.object(self.trigger.PipeSession, "spawn", side_effect=_spawn),
            ]
        else:
            events = self._rpc_events(count)
            if kind == "codex":
                from hub.codex_appserver import TurnOutcome
                from hub.runner_adapters.codex import CodexAppServerTransport as T

                outcome = TurnOutcome(thread_id=session_id, status="completed")
            else:
                from hub.copilot_acp import TurnOutcome
                from hub.runner_adapters.copilot import CopilotAcpTransport as T

                outcome = TurnOutcome(session_id=session_id, status="completed")

            async def _run_turn(_self, _req, cb):  # noqa: ANN001, ANN202
                await cb.on_session(session_id)
                for i, event in enumerate(events):
                    if interval:
                        await asyncio.sleep(interval)
                    if on_line is not None:
                        on_line(i)
                    await cb.on_event(event)
                return outcome

            patches = [patch.object(T, "run_turn", _run_turn)]
        for p in patches:
            p.start()
        try:
            await self.real_execute_run(**kwargs)
        finally:
            for p in patches:
                p.stop()
        return run_id

    async def line_cost(self) -> None:
        print("line-cost (90 lines a minute, each runner, concurrently)", flush=True)
        # Idle baseline: the loop thread's CPU with nothing running, over the same window.
        window = 60.0
        idle0 = time.thread_time()
        await asyncio.sleep(2.0)
        idle_rate = (time.thread_time() - idle0) / 2.0
        count = 90
        kinds = ("claude", "copilot", "codex")
        # The turns start first, outside the measured window: only the recording is measured.
        started = [await self.start_turn(self.agents[kind], None) for kind in kinds]
        cpu0 = time.thread_time()
        wall0 = time.perf_counter()
        results = await asyncio.gather(
            *(
                self._replay(kind, count, window / count, run_id=run_id)
                for kind, run_id in zip(kinds, started)
            ),
            return_exceptions=True,
        )
        wall = time.perf_counter() - wall0
        cpu = time.thread_time() - cpu0 - idle_rate * wall
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            fail("line-cost", "loop CPU per line", repr(errors[0])[:300])
            return
        lines = await self._count_lines(results)
        check(
            "line-cost",
            "loop CPU per line",
            cpu / max(1, sum(lines)) * 1000,
            1.5,
            "ms",
            f"({sum(lines)} lines in {wall:.0f}s)",
        )

    async def _count_lines(self, run_ids: List[str]) -> List[int]:
        from sqlalchemy import func, select

        from hub.db.models import AgentOutput

        counts = []
        async with self.sessions() as db:
            for run_id in run_ids:
                counts.append(
                    (
                        await db.execute(select(func.count()).where(AgentOutput.run_id == run_id))
                    ).scalar_one()
                )
        return counts

    async def line_visible_and_durable(self) -> None:
        print("line-visible-and-durable", flush=True)
        from hub.sse import sse_manager

        received: Dict[int, float] = {}
        shown: Dict[int, float] = {}
        finished_counts: Dict[str, List[int]] = {}
        original = sse_manager.publish
        from sqlalchemy import select

        from hub.db.models import AgentOutput

        def _publish(project_id, event_type, data):  # noqa: ANN001, ANN202
            if event_type == "agent_output" and isinstance(data, dict):
                content = str(data.get("content") or "")
                if content.startswith("line "):
                    try:
                        shown.setdefault(int(content.split()[1]), time.perf_counter())
                    except ValueError:
                        pass
            if event_type in ("run_completed", "run_failed") and isinstance(data, dict):
                run_id = data.get("run_id")
                if run_id:
                    pending.append(asyncio.ensure_future(_count_at_finish(run_id)))
            return original(project_id, event_type, data)

        pending: List[asyncio.Future] = []

        async def _count_at_finish(run_id: str) -> None:
            async with self.sessions() as db:
                rows = (
                    (
                        await db.execute(
                            select(AgentOutput.sequence)
                            .where(AgentOutput.run_id == run_id)
                            .order_by(AgentOutput.timestamp, AgentOutput.id)
                        )
                    )
                    .scalars()
                    .all()
                )
            finished_counts[run_id] = list(rows)

        sse_manager.publish = _publish
        try:
            for kind in ("claude", "copilot", "codex"):
                received.clear()
                shown.clear()

                def _got(i: int) -> None:
                    received[i] = time.perf_counter()

                await self._replay(kind, 6, 0.3, on_line=_got)
                lags = [
                    shown[i] - received[i] for i in received if i in shown and kind != "claude"
                ] + [
                    # Claude's line i is stream line i; the init line carries no content.
                    shown[i - 1] - received[i]
                    for i in received
                    if kind == "claude" and (i - 1) in shown
                ]
                if not lags:
                    fail("line-visible-and-durable", f"{kind} line on screen", "nothing broadcast")
                else:
                    check(
                        "line-visible-and-durable",
                        f"{kind} line reaches the stream",
                        max(lags) * 1000,
                        250,
                        "ms",
                    )
                run_id = await self._replay(kind, 200, 0.0)
                await asyncio.gather(*pending)
                pending.clear()
                expected = await self._count_lines([run_id])
                at_finish = finished_counts.get(run_id)
                if at_finish is None:
                    fail("line-visible-and-durable", f"{kind} 200 lines durable", "no finish event")
                    continue
                in_order = at_finish == sorted(at_finish)
                stored = len(at_finish)
                # Claude's first stream line is `init`, which maps to no output row.
                emitted = 199 if kind == "claude" else 200
                check(
                    "line-visible-and-durable",
                    f"{kind} lines missing at finish",
                    max(0, emitted - stored) + (0 if in_order else 1000),
                    0,
                    "",
                    f"(stored {stored} at finish, {expected[0]} after; in order={in_order})",
                )
        finally:
            sse_manager.publish = original


async def main(args: argparse.Namespace, clone: Path, db_copy: Path) -> int:
    subprocess.run = _counted_run  # counts every git, and which thread ran it
    drive = Drive(clone)
    if args.lifespan:
        context = drive.app.router.lifespan_context(drive.app)
        await context.__aenter__()
    await drive.setup_agents()
    wanted = set(args.only.split(",")) if args.only else None

    def on(name: str) -> bool:
        return wanted is None or name in wanted

    if on("turn") or on("approve"):
        await drive.turn_starts()
    if on("starve"):
        await drive.starvation()
    if on("approve"):
        await drive.approval()
    if on("evidence"):
        await drive.evidence()
    if on("specs"):
        await drive.spec_lists()
    if on("loops") and not on("approve"):
        await drive.loops()
    if on("lines"):
        await drive.line_visible_and_durable()
    if on("cost"):
        await drive.line_cost()
    if args.lifespan:
        await context.__aexit__(None, None, None)
    from hub.db.engine import engine

    await asyncio.sleep(0.2)
    await engine.dispose()
    failed = [r for r in RESULTS if not r["ok"]]
    print()
    print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    for r in failed:
        print(f"  FAIL {r['requirement']}: {r['check']} = {r['value']} (limit {r['limit']})")
    return 1 if failed else 0


def entry() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--scratch", type=Path, default=Path(tempfile.gettempdir()) / "aw-perf-loop-lag"
    )
    parser.add_argument("--repo", type=Path, default=REPO, help="the repository to clone")
    parser.add_argument(
        "--only", default="", help="turn,starve,approve,evidence,specs,loops,lines,cost"
    )
    parser.add_argument("--lifespan", action="store_true", help="run the app's lifespan too")
    parser.add_argument("--check-guard", action="store_true")
    args = parser.parse_args()

    scratch = args.scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    db_copy = scratch / "perf.db"
    if args.check_guard:
        raw = scratch / "guard-check.db"
        copy_database(args.source_db, raw)
        reasons = unsafe_for_lifespan(raw)
        print("a raw copy is refused:" if reasons else "a raw copy was NOT refused:", reasons)
        return 0 if reasons else 1

    t0 = time.perf_counter()
    copy_database(args.source_db, db_copy)
    migrate_to_head(db_copy)
    clone = scratch / "repo"
    make_clone(args.repo, clone)
    print(f"scratch prepared in {time.perf_counter() - t0:.0f}s")
    disable_background_work(db_copy, clone)
    reasons = unsafe_for_lifespan(db_copy)
    if args.lifespan and reasons:
        print(f"refusing to start a Hub with its lifespan on: the copy has {', '.join(reasons)}")
        return 2

    home = scratch / "home"
    home.mkdir(exist_ok=True)
    for name in ("HOME", "USERPROFILE"):
        os.environ[name] = str(home)
    for name in list(os.environ):
        if name.startswith("AW_RUN") or name in ("AW_BOOTSTRAP_API_KEY", "AW_HUB_URL"):
            os.environ.pop(name)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_copy.as_posix()}"
    # The address a run would be told to call back on. Port 9 (discard) is never 8000/8010, and
    # nothing calls it: every runner process is stubbed.
    os.environ["HUB_URL"] = "http://127.0.0.1:9"
    sys.path.insert(0, str(REPO / "hub"))
    import logging

    logging.basicConfig(level=logging.ERROR)
    print(f"scratch Hub on {db_copy} (lifespan {'on' if args.lifespan else 'off'}), clone {clone}")
    return asyncio.run(main(args, clone, db_copy))


if __name__ == "__main__":
    sys.exit(entry())
