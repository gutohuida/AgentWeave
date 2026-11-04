"""The project's checkpoints list: every checkpoint, newest first, narrowable, with the runs it
covers and where it was carried from and into (`every-checkpoint-findable-and-readable`, FR-1,
FR-4, FR-7, FR-10).
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.checkpoint_cutover import cut_over
from hub.checkpoint_generation import CheckpointBody, render_body
from hub.checkpoints import compute_envelope, create_checkpoint
from hub.conversations import archive
from hub.db.engine import async_session_factory
from hub.db.models import Run

from .test_checkpoint_cutover import GOOD_BODY, PROJECT, _conversation

BASE = f"/api/v1/projects/{PROJECT}"


async def _checkpoint(db, conversation, trigger="operator"):
    return await create_checkpoint(
        db,
        conversation,
        trigger=trigger,
        envelope=await compute_envelope(db, conversation),
        body=render_body(CheckpointBody(**GOOD_BODY), notes_incorporated=False),
    )


async def _runs(db, conversation, count):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(count):
        db.add(
            Run(
                id=f"{conversation.id}-run-{index}",
                project_id=PROJECT,
                agent=conversation.agent,
                conversation_id=conversation.id,
                status="completed",
                started_at=start + timedelta(minutes=index),
            )
        )
    await db.commit()


@pytest.mark.asyncio
async def test_lists_every_checkpoint_newest_first_including_archived_and_carried(
    app, auth_headers
):
    async with async_session_factory() as db:
        a = await _conversation(db, "conv-a", agent="alpha")
        b = await _conversation(db, "conv-b", agent="alpha")
        c = await _conversation(db, "conv-c", agent="beta")
        first = (await _checkpoint(db, a)).id
        second = (await _checkpoint(db, b)).id
        third = (await _checkpoint(db, c)).id
        archive(b)
        await db.commit()
        carried, _ = await cut_over(db, a, await _checkpoint_row(db, first))

    body = (await app.get(f"{BASE}/checkpoints", headers=auth_headers)).json()
    assert [row["id"] for row in body["checkpoints"]] == [third, second, first]
    assert body["lineage"] is None
    # The newest first is the route's order, so a reversed one fails this.
    assert carried.id


async def _checkpoint_row(db, checkpoint_id):
    from hub.checkpoints import get_checkpoint_by_id

    return await get_checkpoint_by_id(db, checkpoint_id)


@pytest.mark.asyncio
async def test_filters_narrow_and_combine(app, auth_headers):
    async with async_session_factory() as db:
        a1 = await _conversation(db, "conv-a1", agent="alpha")
        a2 = await _conversation(db, "conv-a2", agent="alpha")
        b1 = await _conversation(db, "conv-b1", agent="beta")
        op_a1 = (await _checkpoint(db, a1, "operator")).id
        op_a2 = (await _checkpoint(db, a2, "operator")).id
        await _checkpoint(db, a1, "task_completion")
        await _checkpoint(db, b1, "operator")
        await _checkpoint(db, b1, "task_completion")

    async def ids(**params):
        response = await app.get(f"{BASE}/checkpoints", params=params, headers=auth_headers)
        assert response.status_code == 200, response.text
        return {row["id"] for row in response.json()["checkpoints"]}

    assert len(await ids(agent="alpha")) == 3
    assert await ids(agent="alpha", trigger="operator") == {op_a1, op_a2}
    assert await ids(agent="alpha", trigger="operator", conversation_id="conv-a1") == {op_a1}
    assert len(await ids(trigger="task_completion")) == 2

    missing = await app.get(
        f"{BASE}/checkpoints", params={"conversation_id": "conv-nope"}, headers=auth_headers
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_a_checkpoint_names_every_run_it_covers_and_none_when_it_recorded_none(
    app, auth_headers
):
    async with async_session_factory() as db:
        covering = await _conversation(db, "conv-runs")
        await _runs(db, covering, 3)
        with_runs = (await _checkpoint(db, covering)).id
        bare = await _conversation(db, "conv-bare")
        without = (await _checkpoint(db, bare)).id

    rows = {
        row["id"]: row
        for row in (await app.get(f"{BASE}/checkpoints", headers=auth_headers)).json()[
            "checkpoints"
        ]
    }
    assert [run["run_id"] for run in rows[with_runs]["covered_runs"]] == [
        "conv-runs-run-0",
        "conv-runs-run-1",
        "conv-runs-run-2",
    ]
    assert rows[without]["covered_runs"] == []


@pytest.mark.asyncio
async def test_lineage_runs_both_ways_and_the_raw_text_only_on_request(app, auth_headers):
    async with async_session_factory() as db:
        predecessor = await _conversation(db, "conv-pre")
        made = await _checkpoint(db, predecessor)
        made_id = made.id
        made.unreadable_answer = "prose the model returned"
        await db.commit()
        successor, _ = await cut_over(db, predecessor, made)
        successor_id = successor.id

    successor_view = (
        await app.get(
            f"{BASE}/checkpoints", params={"conversation_id": successor_id}, headers=auth_headers
        )
    ).json()
    assert successor_view["checkpoints"] == []
    assert successor_view["lineage"]["started_from"]["checkpoint_id"] == made_id
    assert successor_view["lineage"]["started_from"]["conversation_id"] == "conv-pre"

    predecessor_view = (
        await app.get(
            f"{BASE}/checkpoints", params={"conversation_id": "conv-pre"}, headers=auth_headers
        )
    ).json()
    assert predecessor_view["lineage"]["carried_into"]["conversation_id"] == successor_id
    [row] = predecessor_view["checkpoints"]
    assert row["carried_into"] == {"conversation_id": successor_id}
    assert row["has_unreadable_answer"] is True
    assert row["unreadable_answer"] is None

    raw = (
        await app.get(
            f"{BASE}/checkpoints",
            params={"conversation_id": "conv-pre", "include_raw": "true"},
            headers=auth_headers,
        )
    ).json()
    assert raw["checkpoints"][0]["unreadable_answer"] == "prose the model returned"
