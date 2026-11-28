"""Spec payloads are read once per request (`screens-stop-repeating-work-on-every-read`, FR-1, FR-2).

Red first: overview, next-slice offers and project builds each named the same documents from many
places and read each one's file again every time; the statements issued grew with the slices.
"""

# ruff: noqa: F811 -- fixtures are used by name
import contextvars
import pathlib

import pytest
from sqlalchemy import event

from hub import spec_documents
from hub.db.engine import async_session_factory, engine
from hub.db.models import Build, Task

from .test_next_slice_offer import DONE, OFFERS, _agents, _built_slice, land
from .test_spec_roadmaps import (  # noqa: F401 -- fixtures
    BASE,
    _approve,
    _move,
    _proposed_slice,
    _settle,
    planner,
    scheduled,
)

PROJECT = "/api/v1/projects/proj-test"
ROUTES = {
    "overview": f"{PROJECT}/overview",
    "offers": OFFERS,
    "builds": f"{BASE}/builds",
}


# Set only around the request under count: a statement from work another test or an earlier step
# left running (a stage push, a scheduled firing) shares the engine but not this context.
_COUNTING: contextvars.ContextVar[bool] = contextvars.ContextVar("_COUNTING", default=False)


class _Counted:
    def __init__(self, monkeypatch):
        self.reads: dict = {}
        self.statements = 0
        real = pathlib.Path.read_text
        counted = self

        def read_text(path, *args, **kwargs):
            if str(path).endswith("spec.json"):
                counted.reads[str(path)] = counted.reads.get(str(path), 0) + 1
            return real(path, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, "read_text", read_text)

        def count(*_):
            if _COUNTING.get():
                counted.statements += 1

        self._count = count
        event.listen(engine.sync_engine, "before_cursor_execute", count)

    def reset(self):
        self.reads.clear()
        self.statements = 0
        spec_documents._CONTENT_CACHE.clear()

    def close(self):
        event.remove(engine.sync_engine, "before_cursor_execute", self._count)


async def _answer(app, auth_headers, counted, name):
    counted.reset()
    token = _COUNTING.set(True)
    try:
        response = await app.get(ROUTES[name], headers=auth_headers)
    finally:
        _COUNTING.reset(token)
    assert response.status_code == 200, (name, response.text)
    if name == "builds":
        assert response.json()[
            "builds"
        ], "the builds route answered nothing: no build was exercised"
    return dict(counted.reads), counted.statements


async def _project_with_built_slice(app, auth_headers, planner, agents=True):  # noqa: F811
    if agents:
        await _agents("planner")
    roadmap_path, slice_path, task_id = await _built_slice(app, auth_headers, planner)
    await _move(app, auth_headers, task_id, *DONE)
    await land(task_id)
    await _settle()
    await _build_of(task_id)
    return roadmap_path


async def _build_of(task_id):
    """A running build of the task's document, the task attached: what pressing Build records."""
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        build_id = f"build-{task_id}"
        session.add(
            Build(
                id=build_id,
                project_id="proj-test",
                document_id=task.spec_document_id,
                state="running",
                driver="hand",
                level="reviewed",
                builders=[],
                reviewers=[],
            )
        )
        task.build_id = build_id
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(ROUTES))
async def test_spec_reads_counted(app, auth_headers, planner, scheduled, monkeypatch, name):
    """spec-reads-counted: no document's file is read more than once per request."""
    await _project_with_built_slice(app, auth_headers, planner)
    for _ in range(2):  # three approved roadmaps in all, each with a built slice and a build
        await _project_with_built_slice(app, auth_headers, planner, agents=False)
    counted = _Counted(monkeypatch)
    try:
        reads, _ = await _answer(app, auth_headers, counted, name)
    finally:
        counted.close()
    assert all(n == 1 for n in reads.values()), reads


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(ROUTES))
async def test_queries_flat_in_history(app, auth_headers, planner, scheduled, monkeypatch, name):
    """query-count-flat: a second roadmap with a built slice adds no statement to the route."""
    await _project_with_built_slice(app, auth_headers, planner)
    counted = _Counted(monkeypatch)
    try:
        _, before = await _answer(app, auth_headers, counted, name)
        await _project_with_built_slice(app, auth_headers, planner, agents=False)
        _, after = await _answer(app, auth_headers, counted, name)
    finally:
        counted.close()
    assert before > 0, "no statement was counted: the context did not reach the engine"
    assert after == before
