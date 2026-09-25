"""Morning drive: hold an agent 'busy' deterministically for the F373 MCP `run_job` probe (task
3.2, `pressing-run-names-the-reason-that-held`), without racing a real turn's own duration.

Two live Haiku turns racing each other (make bravo busy, then have another agent call run_job
before bravo's own turn ends) lost the race twice running on this machine -- bravo's turn finished
before the calling agent's tool call landed, so the call observed bravo already free and the flow
legitimately continued its own in-progress task rather than exercising the busy guard. The busy
check itself (`scheduler.py:287`) reads `Run.status == "running"` rows, not process state, so a
`Run` row is the same fact a live process would leave; this stages exactly that fact directly,
mirroring `hub/tests/test_loop_busy_guard.py`'s own `_running_turn` helper.

    py -3.11 scripts/drive/d8_0925_morning_hold_busy.py <db-path> add <run-id> <project-id> <agent>
    py -3.11 scripts/drive/d8_0925_morning_hold_busy.py <db-path> remove <run-id>
"""

import asyncio
import os
import sys
from pathlib import Path

DB = sys.argv[1]
CMD = sys.argv[2]
RUN_ID = sys.argv[3]

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB}"
os.environ.setdefault("AW_LOG_LEVEL", "WARNING")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hub"))
sys.stdout.reconfigure(encoding="utf-8")

from hub.db.engine import async_session_factory  # noqa: E402
from hub.db.models import Run  # noqa: E402


async def main():
    async with async_session_factory() as db:
        if CMD == "add":
            project_id, agent = sys.argv[4], sys.argv[5]
            db.add(Run(id=RUN_ID, project_id=project_id, agent=agent, status="running"))
            await db.commit()
            print(f"added Run {RUN_ID} status=running agent={agent}")
        elif CMD == "remove":
            run = await db.get(Run, RUN_ID)
            if run is not None:
                await db.delete(run)
                await db.commit()
                print(f"removed Run {RUN_ID}")
            else:
                print(f"Run {RUN_ID} not found (already gone)")
        else:
            raise SystemExit(f"unknown command {CMD!r}")


asyncio.run(main())
