"""Closing loose tasks as done elsewhere or cancelled (`tasks-outside-a-flow-move-freely`, FR-7..FR-9)."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from hub import already_built, project_workspace
from hub.db.engine import async_session_factory
from hub.db.models import Project, Run, Task, TaskCheckRun, TaskLanding, TaskTransition

pytestmark = pytest.mark.asyncio

SHA = "a" * 40
READABLE = {"a": "TST-1", "b": "TST-2", "tf": "TST-3"}
HEADERS = {"Authorization": "Bearer aw_live_testkey_abcdefgh"}


@pytest.fixture(autouse=True)
def _git(monkeypatch):
    """No repository: a commit is on main when it is SHA, and the workspace is a stub."""

    def resolve(root, named, main_branch):
        ok = [ref for ref in named if ref in (SHA, "deadbeef")]
        return {
            "resolved": [SHA for ref in ok if ref == SHA],
            "unknown": [ref for ref in named if ref not in (SHA, "deadbeef")],
            "off_main": [ref for ref in named if ref == "deadbeef"],
            "newest": SHA,
        }

    async def workspace(session, project_id):
        return SimpleNamespace(root=".")

    monkeypatch.setattr(already_built, "_resolve_commits", resolve)
    monkeypatch.setattr(project_workspace, "resolve_project_workspace", workspace)


async def _setup(**tasks):
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.main_branch = "main"
        for task_id, (status, extra) in tasks.items():
            session.add(
                Task(
                    id=task_id,
                    readable_id=READABLE.get(task_id),
                    project_id="proj-test",
                    title=task_id,
                    status=status,
                    **extra,
                )
            )
        await session.commit()


async def _landing(task_id: str, state: str, sha=None):
    async with async_session_factory() as session:
        session.add(
            TaskLanding(
                id=f"land-{task_id}",
                project_id="proj-test",
                task_id=task_id,
                state=state,
                order_key=1.0,
                landed_sha=sha,
            )
        )
        await session.commit()


async def _close(app, tasks, outcome, **extra):
    return await app.post(
        "/api/v1/projects/proj-test/tasks/close",
        headers=HEADERS,
        json={"tasks": tasks, "outcome": outcome, **extra},
    )


async def _stage(app, task_id):
    return (await app.get(f"/api/v1/projects/proj-test/tasks/{task_id}", headers=HEADERS)).json()


async def test_done_elsewhere_by_a_landed_task_is_on_main_with_no_checks_or_review(app):
    """ac-done-elsewhere"""
    await _setup(a=("approved", {}), b=("pending", {}))
    await _landing("a", "landed", SHA)
    response = await _close(app, ["b"], "done_elsewhere", by_task="TST-1")
    assert response.status_code == 200, response.text
    assert [c["id"] for c in response.json()["closed"]] == ["b"]
    task = await _stage(app, "b")
    assert task["status"] == "approved"
    assert task["stage"] == "on_main"
    assert task["stage_detail"] == SHA[:7]
    async with async_session_factory() as session:
        assert (
            await session.execute(select(TaskCheckRun).where(TaskCheckRun.task_id == "b"))
        ).first() is None
        assert (await session.execute(select(Run).where(Run.task_id == "b"))).first() is None
        landings = (
            (await session.execute(select(TaskLanding).where(TaskLanding.task_id == "b")))
            .scalars()
            .all()
        )
        assert [(row.state, row.landed_sha) for row in landings] == [("landed", SHA)]
        moves = (
            (await session.execute(select(TaskTransition).where(TaskTransition.task_id == "b")))
            .scalars()
            .all()
        )
        assert [m.to_status for m in moves] == ["approved"]


async def test_done_elsewhere_by_a_commit_on_main(app):
    await _setup(b=("in_progress", {}))
    response = await _close(app, ["b"], "done_elsewhere", commit=SHA)
    assert response.status_code == 200, response.text
    assert (await _stage(app, "b"))["stage"] == "on_main"
    off = await _close(app, ["b"], "done_elsewhere", commit="deadbeef")
    assert off.status_code == 422
    assert off.json()["detail"]["code"] == "commit_not_on_main"


async def test_done_elsewhere_is_refused_while_the_named_task_is_not_on_main(app):
    """ac-done-elsewhere-refused"""
    await _setup(a=("approved", {}), b=("pending", {}))
    await _landing("a", "queued")
    response = await _close(app, ["b"], "done_elsewhere", by_task="TST-1")
    assert response.status_code == 409
    assert "TST-1 is not on main" in response.json()["detail"]["message"]
    assert (await _stage(app, "b"))["status"] == "pending"


async def test_cancel_closes_without_landing_and_shows_the_reason(app):
    """ac-cancel"""
    await _setup(c=("in_progress", {}))
    response = await _close(app, ["c"], "cancelled", reason="not needed")
    assert response.status_code == 200, response.text
    task = await _stage(app, "c")
    assert task["status"] == "rejected"
    assert task["stage"] == "closed"
    assert task["stage_detail"] == "not needed"
    async with async_session_factory() as session:
        assert (
            await session.execute(select(TaskLanding).where(TaskLanding.task_id == "c"))
        ).first() is None


async def test_cancel_withdraws_approved_work_that_has_not_landed(app):
    await _setup(c=("approved", {}))
    await _landing("c", "queued")
    response = await _close(app, ["c"], "cancelled")
    assert response.status_code == 200, response.text
    async with async_session_factory() as session:
        landing = await session.get(TaskLanding, "land-c")
        assert landing.state == "sent_back"
    assert (await _stage(app, "c"))["stage"] == "closed"


async def test_closing_several_names_the_flow_task_and_closes_the_rest(app):
    """ac-several"""
    await _setup(
        a=("approved", {}),
        t1=("pending", {}),
        t2=("completed", {}),
        t3=("in_progress", {}),
        tf=("pending", {"loop_id": "loop-x"}),
    )
    await _landing("a", "landed", SHA)
    response = await _close(app, ["t1", "t2", "tf", "t3"], "done_elsewhere", by_task="TST-1")
    body = response.json()
    assert response.status_code == 200, response.text
    assert sorted(c["id"] for c in body["closed"]) == ["t1", "t2", "t3"]
    assert [r["task"] for r in body["refused"]] == ["TST-3"]
    assert "flow" in body["refused"][0]["reason"]
    assert (await _stage(app, "tf"))["status"] == "pending"


async def test_the_moves_route_offers_a_loose_task_every_action_and_a_flow_task_its_own(app):
    """ac-offered: the answer the drawer is built from."""
    await _setup(loose=("completed", {}), flow=("completed", {"loop_id": "loop-x"}))
    base = "/api/v1/projects/proj-test/tasks"
    loose = (await app.get(f"{base}/loose/moves", headers=HEADERS)).json()
    flow = (await app.get(f"{base}/flow/moves", headers=HEADERS)).json()
    assert loose["loose"] is True
    assert {"approved", "revision_needed"} <= set(loose["moves"])
    assert loose["closes"] == ["done_elsewhere", "cancelled"]
    assert flow["loose"] is False
    assert flow["closes"] == []
