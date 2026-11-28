"""Every event-log lookup a project screen filters by a field of `data` is answered by an index on it.

`screens-stop-repeating-work-on-every-read`, task event-log-indexes (FR-5). The retrospective,
pre-mortem and task-stage reads filtered `event_logs` on `json_extract(data, ...)` with nothing
indexing those fields, so each one searched every row of its event type: about 60 ms apiece on the
operator's database, and overview issues dozens. Migration 0194 adds a partial expression index
per field, and the queries name the same expression and the same condition literally.

The statements are the ones the routes really issue: each is captured as the slice's routes are
answered, on a fixture with a built slice, its retrospective, a pre-mortem and staged tasks, and
put back to SQLite as `EXPLAIN QUERY PLAN`. A plan that visits `event_logs` through anything but
an index over the field it filters (a SCAN, or a search of the event type alone) fails.
"""

# ruff: noqa: F811

import re
from typing import List, Tuple

import pytest
from sqlalchemy import event, select

from hub import manager
from hub.db.engine import async_session_factory, engine
from hub.db.models import EventLog, SpecDocument
from hub.pre_mortem import ANSWER_EVENT
from hub.pre_mortem import JOB as PRE_MORTEM
from hub.review_on_completion import REVIEW_UNSTAFFED
from hub.utils import short_id

from .test_next_slice_offer import (  # noqa: F401 -- fixtures
    DONE,
    _built_slice,
    land,
)
from .test_spec_roadmaps import (  # noqa: F401 -- fixtures
    _move,
    _settle,
    planner,
    scheduled,
)

PROJECT = "proj-test"
ROOT = f"/api/v1/projects/{PROJECT}"

#: The slice's routes (FR-3's list), relative to the project; "{build}" is read first.
ROUTES = (
    "overview",
    "project/next-slice-offers",
    "project/builds",
    "project/builds/{build}/tasks",
    "project/documents",
    "project/specs",
    "project/spec/defects",
    "ledger",
    "project/spec/evidence?limit=50",
    "tasks",
    "loops",
    "jobs",
    "traces/settings",
)

_JSON = re.compile(r"json_extract\s*\(", re.IGNORECASE)


async def _history(slice_id: str, task_ids: List[str]) -> None:
    """A retrospective firing and its part, a pre-mortem firing and its answer, an unstaffed review
    and a held send-back per task, and a few unrelated rows of each type."""
    async with async_session_factory() as session:

        def add(event_type, data):
            session.add(
                EventLog(
                    id=f"evt-{short_id()}",
                    project_id=PROJECT,
                    event_type=event_type,
                    severity="info",
                    data=data,
                )
            )

        for document in (slice_id, "spdoc-other"):
            add(
                manager.FIRED_EVENT,
                {
                    "job": manager.BUILD_RETROSPECTIVE,
                    "trigger": "last_task_approved",
                    "subject": {"document": document},
                    "outcome": "written",
                },
            )
            add(
                manager.FIRED_EVENT,
                {"job": PRE_MORTEM, "subject": {"document": document}, "outcome": "written"},
            )
            add(ANSWER_EVENT, {"document": document, "firing": "evt-x", "finding": 1})
        for task_id in [*task_ids, "task-other"]:
            add(REVIEW_UNSTAFFED, {"task_id": task_id, "reason": "nobody free"})
            add("send_back_held", {"task_id": task_id, "reason": "cap"})
        await session.commit()


async def _captured(app, auth_headers) -> List[Tuple[str, tuple]]:
    statements: List[Tuple[str, tuple]] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            statements.append((statement, tuple(parameters or ())))

    builds = await app.get(f"{ROOT}/project/builds", headers=auth_headers)
    assert builds.status_code == 200, builds.text
    body = builds.json()
    rows = body if isinstance(body, list) else body.get("builds", [])
    build = rows[0]["id"] if rows else "build-none"

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        for route in ROUTES:
            response = await app.get(f"{ROOT}/{route.format(build=build)}", headers=auth_headers)
            assert response.status_code in (200, 404), (route, response.text)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    return statements


@pytest.mark.asyncio
async def test_every_event_log_json_lookup_plans_through_its_index(
    app, auth_headers, planner, scheduled
):
    _, slice_path, task_id = await _built_slice(app, auth_headers, planner)
    await _move(app, auth_headers, task_id, *DONE)
    await land(task_id)
    await _settle()
    async with async_session_factory() as session:
        slice_id = await session.scalar(
            select(SpecDocument.id).where(SpecDocument.path == slice_path)
        )
    await _history(slice_id, [task_id])

    statements = await _captured(app, auth_headers)
    lookups = [s for s in statements if "event_logs" in s[0] and _JSON.search(s[0])]
    assert lookups, "no route read event_logs by a field of data: nothing was checked"

    offending = []
    async with engine.connect() as conn:
        for statement, parameters in lookups:
            plan = (await conn.exec_driver_sql("EXPLAIN QUERY PLAN " + statement, parameters)).all()
            for step in plan:
                detail = step[-1]
                if " event_logs" not in detail:
                    continue
                if "ix_event_logs_data_" not in detail and "ix_event_logs_context_" not in detail:
                    offending.append((detail, " ".join(statement.split())[-200:]))
    assert not offending, offending
