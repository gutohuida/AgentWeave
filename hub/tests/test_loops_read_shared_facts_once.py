"""`the-app-stays-responsive-while-agents-run` FR-6, FR-7 — the board reads the project once.

`GET /loops` and `GET /jobs` decide every loop's firing to label it (`_batch_loop_summaries`), and
each decision used to re-read the roster, the provider holds, the running turns, the attendance,
its documents and its agents' configs, several times over: 266 statements for four loops on the
operator's database. Design D6 reads each of those once per request (`scheduler.FiringFacts`).

Two halves, the requirement's two:

* **FR-6, cost.** A five-loop board over five agents stays within 25 statements on each route.
  Before the change this fixture cost well over a hundred.
* **FR-7, the same answers.** Cheaper must not mean different. `GET /loops` is pinned to the body
  the base revision (`72f7d5a`) answered for this fixture, `GET /jobs`'s loop blocks to the same
  summaries, and the batched hold read is checked against the per-agent `provider_hold` it
  replaces, including an agent whose newest row is uninformative.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from hub.db.engine import async_session_factory, engine
from hub.db.models import AIJob, Loop, Run, SpecDocument, Task, TaskTransition, TurnUsage
from hub.provider_allowance import agents_held, provider_hold

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/projects/proj-test"
AGENTS = ["ada", "bea", "cyd", "dov", "eli"]
#: Each loop's tasks, as `(suffix, status, assignee)`. Every status the board and the walk treat
#: differently appears somewhere: claimable, blocked, finished-and-reviewable, in review, decided.
LOOPS = {
    "one": [("a", "pending", None), ("b", "in_progress", "ada"), ("c", "approved", "ada")],
    "two": [("a", "blocked", "bea"), ("b", "pending", None)],
    "three": [("a", "completed", "cyd"), ("b", "pending", None)],
    "four": [("a", "under_review", "dov"), ("b", "rejected", "dov")],
    "five": [],
}


#: Fixed instants, so the hold sentences in the pinned bodies do not move with the clock.
FAR_FUTURE = int(datetime(2100, 1, 1, 9, 30, tzinfo=timezone.utc).timestamp())
LONG_AGO = int(datetime(2001, 1, 1, tzinfo=timezone.utc).timestamp())


def _refusal(epoch: int) -> dict:
    return {"status": "rejected", "resetsAt": epoch, "rateLimitType": "five_hour"}


async def _seed(app, auth_headers, add_agent, bind_runner):
    for name in AGENTS:
        await add_agent(name)
        await bind_runner(name)
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        for index, (suffix, tasks) in enumerate(LOOPS.items()):
            job = AIJob(
                id=f"job-once-{suffix}",
                project_id="proj-test",
                name=f"Once {suffix}",
                agent=AGENTS[index],
                message="work the queue",
                cron="0 9 * * *",
                session_mode="new",
                enabled=True,
            )
            db.add(job)
            document_id = None
            if index % 2 == 0:
                document_id = f"spdoc-once-{suffix}"
                db.add(
                    SpecDocument(
                        id=document_id,
                        project_id="proj-test",
                        path=f"spec/changes/once-{suffix}/spec.json",
                    )
                )
            await db.flush()
            db.add(
                Loop(
                    id=f"loop-once-{suffix}",
                    project_id="proj-test",
                    job_id=job.id,
                    purpose=suffix,
                    spec_document_id=document_id,
                )
            )
            await db.flush()
            for order, (task_suffix, status, assignee) in enumerate(tasks):
                task_id = f"task-once-{suffix}-{task_suffix}"
                db.add(
                    Task(
                        id=task_id,
                        project_id="proj-test",
                        title=task_id,
                        status=status,
                        assignee=assignee,
                        loop_id=f"loop-once-{suffix}",
                        spec_document_id=document_id,
                        created_at=now + timedelta(seconds=order),
                        **({"blocked_reason": "needs the API key"} if status == "blocked" else {}),
                    )
                )
                if status in ("completed", "under_review"):
                    await db.flush()
                    db.add(
                        TaskTransition(
                            id=f"tt-once-{suffix}-{task_suffix}",
                            project_id="proj-test",
                            task_id=task_id,
                            from_status="in_progress",
                            to_status="completed",
                            actor_kind="run",
                            actor_agent=assignee,
                            origin="actor",
                        )
                    )
        # ada is mid-turn on its task; bea's provider refused it until later; cyd's newest row says
        # nothing about the provider, so its hold comes from the refusal before it; dov's refusal
        # has already reset; eli has never run.
        db.add(
            Run(
                id="run-once-ada",
                project_id="proj-test",
                agent="ada",
                status="running",
                task_id="task-once-one-b",
            )
        )
        usage = [
            ("bea", "unavailable", _refusal(FAR_FUTURE)),
            ("cyd", "unavailable", _refusal(FAR_FUTURE + 3600)),
            ("cyd", "unavailable", None),
            ("dov", "unavailable", _refusal(LONG_AGO)),
            ("dov", "measured", None),
        ]
        for index, (agent, status, allowance) in enumerate(usage):
            db.add(
                Run(id=f"run-once-u{index}", project_id="proj-test", agent=agent, status="failed")
            )
            await db.flush()
            db.add(
                TurnUsage(
                    id=f"usage-once-{index}",
                    run_id=f"run-once-u{index}",
                    project_id="proj-test",
                    agent=agent,
                    status=status,
                    allowance=allowance,
                    **(
                        {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
                        if status == "measured"
                        else {}
                    ),
                )
            )
            await db.flush()
        await db.commit()


def _count_statements():
    statements: list = []

    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    return statements, _capture


async def test_the_board_stays_within_25_statements(app, auth_headers, add_agent, bind_runner):
    """FR-6: each route stays within 25 statements for five loops over five agents."""
    await _seed(app, auth_headers, add_agent, bind_runner)
    for route in ("loops", "jobs"):
        statements, capture = _count_statements()
        event.listen(engine.sync_engine, "before_cursor_execute", capture)
        try:
            response = await app.get(f"{BASE}/{route}", headers=auth_headers)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", capture)
        assert response.status_code == 200, response.text
        assert len(response.json()) == len(LOOPS)
        assert len(statements) <= 25, (route, len(statements))


async def test_the_batched_hold_read_answers_as_provider_hold_does(
    app, auth_headers, add_agent, bind_runner
):
    """FR-7: one statement for every agent's newest row, and the same holds as asking per agent --
    including cyd, whose newest row is uninformative and so falls back to the paged walk."""
    await _seed(app, auth_headers, add_agent, bind_runner)
    async with async_session_factory() as db:
        held = await agents_held(db, "proj-test")
        one_by_one = {
            agent for agent in AGENTS if await provider_hold(db, "proj-test", agent) is not None
        }
    assert held == one_by_one == {"bea", "cyd"}


#: `GET /loops` as the base revision (`72f7d5a`, before D6) answered it for this fixture, recorded
#: by running `_seed` against a checkout of that revision. Nothing in it states the current time:
#: the holds are fixed instants and the loops have not stopped.
BASE_LOOPS = [
    {
        "agent": "ada",
        "archived_at": None,
        "control": None,
        "current_tasks": [
            {
                "agent": "ada",
                "agent_capacity": "working",
                "id": "task-once-one-b",
                "status": "in_progress",
                "title": "task-once-one-b",
            },
            {
                "agent": "eli",
                "agent_capacity": "next",
                "id": "task-once-one-a",
                "status": "pending",
                "title": "task-once-one-a",
            },
        ],
        "ending_state": None,
        "firing_active": False,
        "id": "loop-once-one",
        "label": "Once one",
        "open_questions": 0,
        "pending_edit": None,
        "purpose": "one",
        "queue": {"approved": 1, "in_progress": 1, "pending": 1},
        "spec_document_id": "spdoc-once-one",
        "stall_reason": None,
        "stop_at": None,
        "stop_reason": None,
        "stop_when_queue_empties": False,
        "stopped_at": None,
        "work_needs_evidence": None,
    },
    {
        "agent": "bea",
        "archived_at": None,
        "control": None,
        "current_tasks": [
            {
                "agent": "bea",
                "agent_capacity": "assigned",
                "id": "task-once-two-a",
                "status": "blocked",
                "title": "task-once-two-a",
            }
        ],
        "ending_state": None,
        "firing_active": False,
        "id": "loop-once-two",
        "label": "Once two",
        "open_questions": 0,
        "pending_edit": None,
        "purpose": "two",
        "queue": {"blocked": 1, "pending": 1},
        "spec_document_id": None,
        "stall_reason": "bea is held until 09:30 UTC by its provider's usage limit",
        "stop_at": None,
        "stop_reason": None,
        "stop_when_queue_empties": False,
        "stopped_at": None,
        "work_needs_evidence": None,
    },
    {
        "agent": "cyd",
        "archived_at": None,
        "control": None,
        "current_tasks": [
            {
                "agent": "eli",
                "agent_capacity": "next",
                "id": "task-once-three-b",
                "status": "pending",
                "title": "task-once-three-b",
            }
        ],
        "ending_state": None,
        "firing_active": False,
        "id": "loop-once-three",
        "label": "Once three",
        "open_questions": 0,
        "pending_edit": None,
        "purpose": "three",
        "queue": {"completed": 1, "pending": 1},
        "spec_document_id": "spdoc-once-three",
        "stall_reason": None,
        "stop_at": None,
        "stop_reason": None,
        "stop_when_queue_empties": False,
        "stopped_at": None,
        "work_needs_evidence": None,
    },
    {
        "agent": "dov",
        "archived_at": None,
        "control": None,
        "current_tasks": [],
        "ending_state": None,
        "firing_active": False,
        "id": "loop-once-four",
        "label": "Once four",
        "open_questions": 0,
        "pending_edit": None,
        "purpose": "four",
        "queue": {"rejected": 1, "under_review": 1},
        "spec_document_id": None,
        "stall_reason": "task task-once-four-a has no branch to review. Its work was never committed "
        "to a task branch, so there is no commit for a reviewer to be given. Until "
        "the work that finished this task is recorded as evidence naming a commit, "
        "no reviewer can be given anything to look at.",
        "stop_at": None,
        "stop_reason": None,
        "stop_when_queue_empties": False,
        "stopped_at": None,
        "work_needs_evidence": None,
    },
    {
        "agent": "eli",
        "archived_at": None,
        "control": None,
        "current_tasks": [],
        "ending_state": None,
        "firing_active": False,
        "id": "loop-once-five",
        "label": "Once five",
        "open_questions": 0,
        "pending_edit": None,
        "purpose": "five",
        "queue": {},
        "spec_document_id": "spdoc-once-five",
        "stall_reason": None,
        "stop_at": None,
        "stop_reason": None,
        "stop_when_queue_empties": False,
        "stopped_at": None,
        "work_needs_evidence": None,
    },
]


async def test_the_board_answers_as_it_did_before(app, auth_headers, add_agent, bind_runner):
    """FR-7: `GET /loops` is the base revision's body, and each `GET /jobs` loop block is the same
    summary -- so both routes answer as they did before the reads were shared."""
    await _seed(app, auth_headers, add_agent, bind_runner)
    loops = await app.get(f"{BASE}/loops", headers=auth_headers)
    jobs = await app.get(f"{BASE}/jobs", headers=auth_headers)
    assert loops.status_code == 200 and jobs.status_code == 200
    assert loops.json() == BASE_LOOPS
    by_id = {summary["id"]: summary for summary in BASE_LOOPS}
    assert {job["loop"]["id"]: job["loop"] for job in jobs.json()} == by_id
