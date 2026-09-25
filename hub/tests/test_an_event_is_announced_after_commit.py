"""an-event-is-announced-only-once-its-write-is-committed (F335).

A function that stages an event row with `persist_event(..., commit=False)` announces it through
`defer_broadcast`, which publishes from the session's `after_commit` listener. Every spy here is on
`SSEManager.publish`, the one funnel a deferred frame passes (design D2).
"""

import ast
from pathlib import Path

import pytest

from hub import sse as sse_module
from hub.db.engine import async_session_factory
from hub.db.models import Run, Task
from hub.run_divergence import evaluate_run_end
from hub.run_task_binding import bind_run_to_task
from hub.sse import defer_broadcast
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator

from .test_a_refused_review_leaves_nothing_behind import (
    _divergence,
    _divergence_leg,
    _events,
)

WORKER = "worker-ev"


@pytest.fixture
def published(monkeypatch):
    frames: list = []
    real = sse_module.sse_manager.publish

    def spy(project_id, event_type, payload):
        frames.append((event_type, payload))
        return real(project_id, event_type, payload)

    monkeypatch.setattr(sse_module.sse_manager, "publish", spy)
    return frames


async def _completed_with_open_divergence(task_id: str) -> str:
    async with async_session_factory() as db:
        task = Task(id=task_id, project_id="proj-test", title="div", status="pending")
        run = Run(id=f"run-{task_id}", project_id="proj-test", agent=WORKER, status="running")
        db.add_all([task, run])
        await db.flush()
        await bind_run_to_task(db, run, task)
        await db.commit()
        await apply_transition(db, task, "completed", operator())
        await db.commit()
        run.status = "completed"
        await db.commit()
    divergence_id = await evaluate_run_end(f"run-{task_id}")
    assert divergence_id is not None
    return divergence_id


# 1.1 (F335)


async def test_a_refused_review_announces_no_resolution(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    _task_id, _before, divergence_id, frames = await _divergence_leg(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    assert "run_divergence_resolved" not in frames
    async with async_session_factory() as db:
        assert (await _divergence(db, divergence_id)).resolved_at is None
    assert await _events("run_divergence_resolved") == 0


# 1.2 control: the same spy sees a true resolution


async def test_a_true_resolution_is_announced_once_after_its_commit(published):
    await _completed_with_open_divergence("task-ev-ctl")
    async with async_session_factory() as db:
        task = await db.get(Task, "task-ev-ctl")
        await apply_transition(db, task, "under_review", operator())
        assert [k for k, _ in published if k == "run_divergence_resolved"] == []
        await db.commit()
    resolved = [p for k, p in published if k == "run_divergence_resolved"]
    assert resolved == [{"task_id": "task-ev-ctl", "count": 1}]
    assert await _events("run_divergence_resolved") == 1


# 1.3 (D3) the operator route


async def test_the_route_announces_the_resolution_before_task_updated(app, auth_headers, published):
    await _completed_with_open_divergence("task-ev-route")
    resp = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-ev-route",
        json={"status": "under_review"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    kinds = [k for k, _ in published]
    assert "run_divergence_resolved" in kinds and "task_updated" in kinds
    assert kinds.index("run_divergence_resolved") < kinds.index("task_updated")


# 1.4 (D1)


async def test_a_deferred_announcement_waits_for_the_commit(published):
    async with async_session_factory() as db:
        defer_broadcast(db, "proj-test", "k1", {"a": 1})
        await db.rollback()
        assert published == []

    async with async_session_factory() as db:
        defer_broadcast(db, "proj-test", "k2", {"a": 2})
    assert published == []  # closed without commit

    session = async_session_factory()
    defer_broadcast(session, "proj-test", "k3", {"a": 3})
    await session.close()
    await session.commit()  # same instance, fresh transaction: the list must not have leaked
    assert published == []
    await session.close()

    async with async_session_factory() as db:
        defer_broadcast(db, "proj-test", "k4", {"a": 4})
        await db.commit()
        assert [k for k, _ in published] == ["k4"]
        await db.commit()
        assert [k for k, _ in published] == ["k4"]


# 1.5 (D2)


async def test_an_unserialisable_payload_does_not_fail_the_commit(published, caplog):
    async with async_session_factory() as db:
        db.add(Task(id="task-ev-nan", project_id="proj-test", title="t", status="pending"))
        defer_broadcast(db, "proj-test", "bad", {"x": float("nan")})
        defer_broadcast(db, "proj-test", "good", {"ok": True})
        await db.commit()
    assert [k for k, _ in published if k == "good"] == ["good"]
    assert "deferred SSE broadcast bad failed" in caplog.text
    async with async_session_factory() as db:
        assert await db.get(Task, "task-ev-nan") is not None


# 1.6 / 1.6b (D4) the AST guard

HUB = Path(__file__).resolve().parent.parent / "hub"


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _stages_without_commit(call: ast.Call) -> bool:
    return _call_name(call) == "persist_event" and any(
        kw.arg == "commit" and isinstance(kw.value, ast.Constant) and kw.value.value is False
        for kw in call.keywords
    )


def _functions(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield [n for n in ast.walk(node) if isinstance(n, ast.Call)]


def rule1(source: str, filename: str = "<snippet>") -> list[str]:
    out = []
    for calls in _functions(ast.parse(source)):
        if not any(_stages_without_commit(c) for c in calls):
            continue
        for c in calls:
            name = _call_name(c)
            if name != "defer_broadcast" and ("broadcast" in name or name == "publish"):
                out.append(
                    f"{filename}:{c.lineno} broadcasts in a function that stages an event row "
                    "with persist_event(commit=False). Replace it with defer_broadcast(session, "
                    "project_id, kind, payload) placed before this function's session.commit(), "
                    "in the order the frames go out today, and spy on SSEManager.publish in its "
                    "tests - a broadcast spy no longer sees it."
                )
    return out


def rule2(source: str, filename: str = "<snippet>") -> list[str]:
    out = []
    for calls in _functions(ast.parse(source)):
        defers = [c for c in calls if _call_name(c) == "defer_broadcast"]
        commits = [c for c in calls if _call_name(c) == "commit"]
        if not defers or not commits:
            continue
        last = max(c.lineno for c in commits)
        out += [
            f"{filename}:{d.lineno} defers an announcement after this function's last commit; "
            "nothing will publish it. Move it above the commit."
            for d in defers
            if d.lineno > last
        ]
    return out


def _scan(rule) -> list[str]:
    found = []
    for path in sorted(HUB.rglob("*.py")):
        found += rule(path.read_text(encoding="utf-8"), str(path.relative_to(HUB.parent)))
    return found


_STAGE = 'async def f(session):\n    persist_event(session, "k", {}, commit=False)\n    '


def test_no_staged_event_is_broadcast_before_commit():
    assert rule1(_STAGE + 'await _broadcast_run_lifecycle(session, "p", "x")')
    assert rule1(_STAGE + 'await sse_manager.broadcast("p", "k", {})')
    assert not rule1(_STAGE + 'defer_broadcast(session, "p", "k", {})')
    assert not rule1('async def f(session):\n    await sse_manager.broadcast("p", "k", {})')
    assert _scan(rule1) == []


def test_no_announcement_is_deferred_after_the_last_commit():
    call = 'defer_broadcast(session, "p", "k", {})'
    late = f"async def f(session):\n    await session.commit()\n    {call}"
    early = f"async def f(session):\n    {call}\n    await session.commit()"
    assert rule2(late)
    assert not rule2(early)
    assert _scan(rule2) == []
