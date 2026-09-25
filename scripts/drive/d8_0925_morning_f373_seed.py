"""Morning drive: seed the F373 staging (design Context table, `pressing-run-names-the-reason-
that-held`) directly against a running trial Hub's database.

Stages: a flow (job declares a spec document), its only task `in_progress` and assigned to the
job's own agent, and an hour-old `skipped` JobRun row reading the stale prerequisite-approval
stall text, with `requested_by_run_id="run-sentinel"` seeded (per task 1.7's identity note: an
operator's press sends no run identity, so an unseeded row would compare None with None).

The job and its first task are created over real HTTP first (`aw.py`), matching how the product
makes them; only the two facts a live turn cannot cheaply stage -- the task's status/assignee and
the hour-old stale row -- are written directly, through the Hub's own SQLAlchemy models, against
the same database file the running Hub serves.

    py -3.11 scripts/drive/d8_0925_morning_f373_seed.py <db-path> <job-id> <task-id> <owner-agent>
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = sys.argv[1]
JOB_ID = sys.argv[2]
TASK_ID = sys.argv[3]
OWNER = sys.argv[4]

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB}"
os.environ.setdefault("AW_LOG_LEVEL", "WARNING")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hub"))
sys.stdout.reconfigure(encoding="utf-8")

from hub.db.engine import async_session_factory  # noqa: E402
from hub.db.models import JobRun, Task  # noqa: E402


async def main():
    async with async_session_factory() as db:
        task = await db.get(Task, TASK_ID)
        task.status = "in_progress"
        task.assignee = OWNER
        run = JobRun(
            id="run-f373-stale-sentinel",
            job_id=JOB_ID,
            project_id=task.project_id,
            fired_at=datetime.now(timezone.utc) - timedelta(hours=1),
            status="skipped",
            trigger="scheduled",
            error_summary="loop queue is stalled: 1 still awaiting a prerequisite's approval",
            requested_by_run_id="run-sentinel",
            tick_count=1,
        )
        db.add(run)
        await db.commit()
        print(f"task {TASK_ID}: status={task.status} assignee={task.assignee}")
        print(f"seeded JobRun {run.id}: fired_at={run.fired_at} status={run.status}")


asyncio.run(main())
