"""Every route a task surface reads carries the same stage and check state
(`task-stages-in-the-build-view-and-dependency-map` FR-11, criterion every-route-carries-stage;
task map-and-other-surfaces).

One project database holds a task in Landing checks (approved, its batch's run deciding) and one
in Pre-review checks (completed, its checks configured and not yet run on this work), the first a
prerequisite of a third. At the moment the landing run is decided, every route the board, the map,
the drawer, the spec page, the build view, the Running panel, the Loop tab and the Overview read is
fetched, and each must say what the task list says. The runs are made by `landing_queue` with real
git and a real check subprocess, as `test_task_stages_and_check_state` does.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from hub import landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import Build, Run, Task, TaskDependency
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator

from .test_a_failing_batch_is_narrowed import _approve, _project, _repo, _tasks

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/projects/proj-test"
TASKS = f"{BASE}/tasks"
BUILD = "build-everyroute1"
DOCUMENT = "spdoc-everyroute"
#: The UI tests feed each surface the response its route really gave here
#: (`hub/ui/src/__tests__/everyRouteStages.test.tsx`). Set `AW_RECORD_STAGE_ROUTES=1` to rewrite it
#: from this test's own fetches.
RECORDED = (
    Path(__file__).resolve().parents[1]
    / "ui"
    / "src"
    / "__tests__"
    / "fixtures"
    / "everyRouteStages.json"
)


@pytest.fixture(autouse=True)
def _no_reviewer_is_staffed(monkeypatch):
    from hub import review_on_completion

    monkeypatch.setattr(review_on_completion, "staff_review", AsyncMock(return_value=None))


@pytest.fixture(autouse=True)
def _a_long_gather_window(monkeypatch):
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    yield
    landing_queue.cancel_timers()


async def _setting(ids: List[str]) -> None:
    """ids[0] lands; ids[1] is completed and held for its checks; ids[2] waits on ids[0]. Each has
    a running turn, so the Overview's running rows name all three."""
    async with async_session_factory() as db:
        db.add(
            Build(
                id=BUILD,
                project_id="proj-test",
                document_id=DOCUMENT,
                driver="flow",
                level="reviewed",
                loop_id="loop-narrow",
            )
        )
        for task_id in ids:
            task = await db.get(Task, task_id)
            task.build_id = BUILD
            task.spec_document_id = DOCUMENT
        db.add(
            TaskDependency(
                id="dep-everyroute",
                project_id="proj-test",
                task_id=ids[2],
                depends_on_task_id=ids[0],
            )
        )
        for status in ("revision_needed", "in_progress", "completed"):
            await apply_transition(db, await db.get(Task, ids[1]), status, operator())
        for n, task_id in enumerate(ids):
            db.add(
                Run(
                    id=f"run-everyroute-{n}",
                    project_id="proj-test",
                    agent="builder",
                    task_id=task_id,
                    status="running",
                )
            )
        await db.commit()


def _read(row: Dict[str, Any]) -> tuple:
    return (row.get("stage"), row.get("check_state"))


async def _every_route(
    app, auth_headers, ids: List[str], bodies: Dict[str, Any]
) -> Dict[str, Dict[str, tuple]]:
    """Each route's `(stage, check_state)` for each task it names, by route; each body fetched is
    kept in *bodies* by path."""

    async def get(path: str, **params) -> Any:
        response = await app.get(path, params=params or None, headers=auth_headers)
        assert response.status_code == 200, (path, response.text)
        key = path + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")
        bodies[key] = response.json()
        return response.json()

    seen: Dict[str, Dict[str, tuple]] = {}
    listed = await get(TASKS, limit=1000)
    seen["task list (board, map, drawer)"] = {t["id"]: _read(t) for t in listed["tasks"]}
    in_document = await get(TASKS, spec_document_id=DOCUMENT)
    seen["document's tasks (spec page builds and outline)"] = {
        t["id"]: _read(t) for t in in_document["tasks"]
    }
    seen["one task (drawer)"] = {t: _read(await get(f"{TASKS}/{t}")) for t in ids}
    seen["prerequisites (map, drawer)"] = {
        p["id"]: _read(p) for t in listed["tasks"] for p in t.get("prerequisites") or []
    }
    seen["dependents (drawer)"] = {
        d["id"]: _read(d) for t in listed["tasks"] for d in t.get("dependents") or []
    }
    built = await get(f"{BASE}/project/builds/{BUILD}/tasks")
    seen["build read (build view)"] = {t["id"]: _read(t) for t in built["tasks"]}
    rows = (await get(f"{BASE}/project/builds"))["builds"]
    seen["builds listing (Running panel)"] = {
        landing["task_id"]: _read(landing)
        for row in rows
        if row["id"] == BUILD
        for landing in row.get("landings") or []
    }
    loop = await get(f"{BASE}/loops/loop-narrow")
    seen["loop (Loop tab, Running panel)"] = {
        t["id"]: _read(t) for t in loop.get("current_tasks") or []
    }
    loops = await get(f"{BASE}/loops", stages="true")
    seen["loops list (Running panel)"] = {
        t["id"]: _read(t) for one in loops for t in one.get("current_tasks") or []
    }
    overview = await get(f"{BASE}/overview")
    seen["overview (Overview)"] = {
        r["task_id"]: _read(r) for r in overview["running"] if r.get("task_id")
    }
    return seen


async def test_every_route_a_surface_reads_carries_the_same_stage_and_check_state(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    _repo(tmp_path, tmp_path_factory.mktemp("ledger") / "runs.txt")
    await _project()
    # No pre-review run is started, so the completed task stays held for checks not yet run on its
    # work: Pre-review checks, waiting.
    monkeypatch.setattr(project_checks, "request_run", AsyncMock(return_value=None))
    ids, _tips = await _tasks(
        tmp_path,
        [
            ({"one.py": "x = 1\n"}, None),
            ({"two.py": "x = 2\n"}, None),
            ({"three.py": "x = 3\n"}, 1),
        ],
    )
    await _setting(ids)
    await _approve(app, auth_headers, ids[0])

    at_the_verdict: List[Dict[str, Dict[str, tuple]]] = []
    bodies: Dict[str, Any] = {}
    decide = landing_queue._decide

    async def read_then_decide(*args, **kwargs):
        if not at_the_verdict:
            at_the_verdict.append(await _every_route(app, auth_headers, ids, bodies))
        return await decide(*args, **kwargs)

    monkeypatch.setattr(landing_queue, "_decide", read_then_decide)
    await landing_queue.drain()
    [seen] = at_the_verdict

    truth = seen["task list (board, map, drawer)"]
    landing: Optional[tuple] = truth[ids[0]]
    assert landing[0] == "checking", truth
    assert landing[1] is not None and landing[1]["kind"] == "landing", truth
    pre_review = truth[ids[1]]
    assert pre_review == ("pre_review_checks", {"kind": "pre_review", "state": "waiting"}), truth

    # Each route names the tasks its surface shows, and says of each what the task list says.
    expected_tasks = {
        "document's tasks (spec page builds and outline)": set(ids),
        "one task (drawer)": set(ids),
        "prerequisites (map, drawer)": {ids[0]},
        "dependents (drawer)": {ids[2]},
        "build read (build view)": set(ids),
        "builds listing (Running panel)": {ids[0]},
        "overview (Overview)": set(ids),
    }
    for route, wanted in expected_tasks.items():
        assert wanted <= set(seen[route]), (route, seen[route])
    for route, reads in seen.items():
        for task_id, read in reads.items():
            assert read == truth[task_id], f"{route} disagrees with the task list on {task_id}"
    loop_reads = {**seen["loop (Loop tab, Running panel)"], **seen["loops list (Running panel)"]}
    for task_id, read in loop_reads.items():
        assert read == truth[task_id], task_id

    if os.environ.get("AW_RECORD_STAGE_ROUTES") == "1":
        recorded = {"ids": ids, "routes": {k.replace(BASE, ""): v for k, v in bodies.items()}}
        RECORDED.write_text(json.dumps(recorded, indent=2, sort_keys=True) + "\n", encoding="utf-8")
