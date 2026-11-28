"""The Hub halves of `every-overview-control-lands-where-you-can-act-on-it` (task hub-closable-needs):
each need says whether it can be dismissed (FR-7, closable-per-kind), the operator ends a stall and
it stays ended until its task changes (FR-2, stall-ended-by-operator), and a stall with no task opens
its thread, or nothing (FR-4, stall-opens-with-remedies)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

from hub import builds, slice_drafting, stalls
from hub.db.engine import async_session_factory
from hub.db.models import (
    MainNotice,
    PermissionRequest,
    Question,
    Run,
    Stall,
    TaskTransition,
)

from .conftest import TEST_PROJECT_ID
from .test_overview_route import _add, _could_not_run, _read, _task

P = TEST_PROJECT_ID
NOW = datetime.now(timezone.utc)
STALLS = f"/api/v1/projects/{P}/stalls"

# FR-7's list, every kind the Overview counts.
FR7 = {
    "question": True,
    "permission": True,
    "stall": True,
    "main_moved": True,
    "offer": True,
    "reopening": True,
    "review": False,
    "merge": False,
    "check": False,
    "main": False,
}


def ago(**delta: float) -> datetime:
    return NOW - timedelta(**delta)


# --- closable-per-kind ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_need_says_whether_it_can_be_dismissed_per_fr7(app, auth_headers, monkeypatch):
    await _add(
        _task("t-checked", status="approved"),
        _task("t-merge", status="approved", builder="dev"),
        _task("t-stalled", status="in_progress", assignee="dev"),
        _task("t-review", status="under_review", assignee="user", builder="dev"),
        Stall(
            id="stall-merge",
            project_id=P,
            key="integration_failed:t-merge",
            cause="integration_failed",
            reason="Approved work failed to merge",
            task_id="t-merge",
        ),
        Stall(
            id="stall-1",
            project_id=P,
            key="stuck_task:t-stalled",
            cause="stuck_task",
            reason="Nobody could take the task",
            task_id="t-stalled",
        ),
        Question(id="q-1", project_id=P, from_agent="arch", question="Which tab first?"),
        TaskTransition(
            id="ttr-review",
            project_id=P,
            task_id="t-review",
            from_status="completed",
            to_status="under_review",
            actor_kind="operator",
        ),
        PermissionRequest(id="perm-1", project_id=P, agent="dev", tool_name="Bash"),
        _could_not_run("hub-ui", ago(minutes=10)),
        MainNotice(
            id="mn-1", project_id=P, branch="master", old_tip="a" * 40, new_tip="c" * 40, commits=[]
        ),
    )

    async def offers(session, workspace, project_id):
        return [
            {
                "roadmap": "spec/changes/roadmap/spec.json",
                "document_id": "spdoc-roadmap",
                "next_slice": {"key": "s3", "title": "Manager indicators"},
                "agent": "arch",
                "conversation_id": None,
            }
        ]

    async def warnings(session, project_id):
        return [{"build_id": "build-1", "path": "spec/changes/x/spec.json", "title": "X",
                 "reopened_at": ago(minutes=3).isoformat()}]  # fmt: skip

    monkeypatch.setattr(slice_drafting, "list_offers", offers)
    monkeypatch.setattr(builds, "reopening_warnings", warnings)

    needs = (await _read(app, auth_headers))["needs"]

    assert sorted({n["kind"] for n in needs}) == sorted(FR7), "one need of every kind"
    assert {n["kind"]: n["dismissable"] for n in needs} == FR7
    assert all(isinstance(n["dismissable"], bool) for n in needs)


# --- stall-ended-by-operator ---------------------------------------------------------------------


async def _detect(task_id: str, text: str = "Nobody could check it") -> "tuple[Stall, bool]":
    """What the stall detector does when it sees the cause on *task_id*."""
    async with async_session_factory() as db:
        return await stalls.record(
            db, P, cause="review_unstaffed", subject=task_id, text=text, task_id=task_id
        )


async def _open_for(key: str):
    async with async_session_factory() as db:
        return await stalls.open_stall(db, P, key)


@pytest.mark.asyncio
async def test_a_stall_the_operator_ends_stays_ended_until_its_task_changes(app, auth_headers):
    await _add(_task("t-1", status="completed", builder="dev"))
    stall, created = await _detect("t-1")
    assert created

    response = await app.post(f"{STALLS}/{stall.id}/end", headers=auth_headers, json={})
    assert response.status_code == 200, response.text
    ended = response.json()
    assert ended["ended_at"] is not None
    assert ended["ended_by"] == "operator"
    listed = (await app.get(STALLS, headers=auth_headers)).json()["stalls"]
    assert [s["ended_by"] for s in listed if s["id"] == stall.id] == ["operator"]

    # The cause persists: the detector sees it again, with the same words or new ones.
    again, created = await _detect("t-1")
    assert not created and again.id == stall.id
    _, created = await _detect("t-1", text="Nobody could check it, still")
    assert not created
    assert await _open_for("review_unstaffed:t-1") is None
    needs = (await _read(app, auth_headers))["needs"]
    assert not [n for n in needs if n["kind"] == "stall"]

    # The task moves: the same cause may be raised again.
    await _add(
        TaskTransition(
            id="ttr-moved",
            project_id=P,
            task_id="t-1",
            from_status="completed",
            to_status="in_progress",
            actor_kind="operator",
            created_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        )
    )
    raised, created = await _detect("t-1")
    assert created and raised.id != stall.id
    assert (await _open_for("review_unstaffed:t-1")).id == raised.id


@pytest.mark.asyncio
async def test_a_new_run_on_the_task_also_lets_the_stall_be_raised_again(app, auth_headers):
    await _add(_task("t-2", status="completed", builder="dev"))
    stall, _ = await _detect("t-2")
    assert (await app.post(f"{STALLS}/{stall.id}/end", headers=auth_headers, json={})).is_success
    assert not (await _detect("t-2"))[1]

    await _add(
        Run(
            id="run-later",
            project_id=P,
            agent="dev",
            task_id="t-2",
            status="completed",
            started_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        )
    )
    assert (await _detect("t-2"))[1]


@pytest.mark.asyncio
async def test_a_stall_the_hub_ended_is_raised_again_as_before(app, auth_headers):
    """Only the operator's end holds the cause back; the Hub's own (its cause went away) does not."""
    await _add(_task("t-3", status="completed", builder="dev"))
    stall, _ = await _detect("t-3")
    async with async_session_factory() as db:
        row = await db.get(Stall, stall.id)
        await stalls.end(db, row, "resolved", "The task moved to approved.")
        assert stalls.view(row)["ended_by"] == "hub"
    assert (await _detect("t-3"))[1]


@pytest.mark.asyncio
async def test_a_taskless_stall_the_operator_ended_returns_only_with_a_new_reason(
    app, auth_headers
):
    async def detect(text: str) -> bool:
        async with async_session_factory() as db:
            return (await stalls.record(db, P, cause="loop_stalled", subject="loop-1", text=text))[
                1
            ]

    assert await detect("The loop found nothing to start")
    stall = await _open_for("loop_stalled:loop-1")
    assert (await app.post(f"{STALLS}/{stall.id}/end", headers=auth_headers, json={})).is_success
    assert not await detect("The loop found nothing to start")
    assert await detect("The loop's agents are all held")


@pytest.mark.asyncio
async def test_the_operators_detail_follows_the_mark(app, auth_headers):
    await _add(_task("t-4", status="completed", builder="dev"))
    stall, _ = await _detect("t-4")
    body: Dict[str, Any] = {"outcome": "gave_up", "detail": "Not worth it."}
    ended = (await app.post(f"{STALLS}/{stall.id}/end", headers=auth_headers, json=body)).json()
    assert ended["outcome"] == "gave_up"
    assert ended["outcome_detail"] == "Ended by the operator. Not worth it."
    assert ended["ended_by"] == "operator"


# --- stall-opens-with-remedies (the Hub half) ----------------------------------------------------


@pytest.mark.asyncio
async def test_a_stall_without_a_task_opens_its_thread_or_nothing(app, auth_headers):
    await _add(
        Stall(
            id="stall-thread",
            project_id=P,
            key="loop_stalled:loop-a",
            cause="loop_stalled",
            reason="The loop found nothing to start",
            conversation_id="conv-mend",
            first_seen_at=ago(minutes=20),
        ),
        Stall(
            id="stall-lone",
            project_id=P,
            key="loop_stalled:loop-b",
            cause="loop_stalled",
            reason="The other loop found nothing to start",
            first_seen_at=ago(minutes=10),
        ),
    )
    needs = {n["id"]: n for n in (await _read(app, auth_headers))["needs"]}

    threaded = needs["stall-stall-thread"]
    assert threaded["target"]["type"] == "thread"
    assert threaded["target"]["conversation_id"] == "conv-mend"
    assert threaded["agent"] == stalls.MENDER

    lone = needs["stall-stall-lone"]
    assert lone["target"] == {"type": "none", "id": None, "conversation_id": None, "path": None}
    assert lone["title"] == "The other loop found nothing to start"
    assert lone["dismissable"] is True
