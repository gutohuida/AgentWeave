"""Starting a conversation from any checkpoint, with any agent.

`start-a-conversation-from-any-checkpoint-with-any-agent` (FR-1..FR-10), through the operator route
`POST /projects/{pid}/checkpoints/{id}/start`. The turn the route schedules is recorded rather than
run: what a start must leave behind is rows, and the scheduler's own behaviour is covered elsewhere.
"""

import pytest
from sqlalchemy import func, select

from hub import turn_scheduler
from hub.checkpoint_access import AccessDeniedError, read_checkpoint
from hub.checkpoint_cutover import delivery_content
from hub.checkpoints import get_checkpoint_by_id
from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import Checkpoint, Conversation, InboundQueueEntry, Project, Run
from hub.turn_scheduler import ScheduleResult

from .test_checkpoint_cutover import AGENT, PROJECT, _conversation, _ready_checkpoint

BASE = f"/api/v1/projects/{PROJECT}"
OTHER = "reviewer-b"


@pytest.fixture
def scheduled(monkeypatch):
    """Every `schedule_agent` call the route makes, answered as a turn that began nowhere."""
    calls: list = []

    async def recording(project_id, agent):
        calls.append((project_id, agent))
        return ScheduleResult(response=None, waiting_reason=None, terminal_failure=False)

    monkeypatch.setattr(turn_scheduler, "schedule_agent", recording)
    return calls


@pytest.fixture
async def agents(add_agent):
    await add_agent(AGENT)
    await add_agent(OTHER)


async def _checkpoint(**conversation_fields):
    async with async_session_factory() as db:
        conversation = await _conversation(db, **conversation_fields)
        return (await _ready_checkpoint(db, conversation)).id


async def _start(app, auth_headers, checkpoint_id, agent=AGENT, message=None):
    body = {"agent": agent}
    if message is not None:
        body["message"] = message
    return await app.post(
        f"{BASE}/checkpoints/{checkpoint_id}/start", json=body, headers=auth_headers
    )


async def _entries(conversation_id):
    async with async_session_factory() as db:
        return (
            (
                await db.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.conversation_id == conversation_id)
                    .order_by(InboundQueueEntry.sequence)
                )
            )
            .scalars()
            .all()
        )


async def _count(model):
    async with async_session_factory() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


# --------------------------------------------------------------------------- FR-1 ac-any


@pytest.mark.asyncio
async def test_any_written_checkpoint_starts_a_new_conversation_every_time(
    app, auth_headers, agents, scheduled
):
    """Offered, carried over, and already used to start one: each start makes a new one."""
    offered = await _checkpoint()
    carried = await _checkpoint(conversation_id="conv-2")
    cut = await app.post(f"{BASE}/checkpoints/{carried}/cutover", headers=auth_headers)
    assert cut.status_code == 200, cut.text

    started = []
    for checkpoint_id in (offered, carried, offered):
        response = await _start(app, auth_headers, checkpoint_id)
        assert response.status_code == 201, response.text
        started.append(response.json()["conversation_id"])

    assert len(set(started)) == 3
    async with async_session_factory() as db:
        for conversation_id in started:
            row = await get_conversation_by_id(db, conversation_id)
            assert row.lifecycle == "open" and row.agent == AGENT


# --------------------------------------------------------------------------- FR-2


@pytest.mark.asyncio
async def test_the_chosen_agent_owns_the_conversation_without_the_originals_overrides(
    app, auth_headers, agents, scheduled
):
    """ac-overrides: the original's model override is not carried, nor inherited from the agent's
    latest conversation, so the turn runs on the agent's own runner and model."""
    checkpoint_id = await _checkpoint(runtime_overrides={"model": "claude-opus-5-5"})

    own = (await _start(app, auth_headers, checkpoint_id)).json()
    other = (await _start(app, auth_headers, checkpoint_id, agent=OTHER)).json()

    async with async_session_factory() as db:
        mine = await get_conversation_by_id(db, own["conversation_id"])
        theirs = await get_conversation_by_id(db, other["conversation_id"])
    assert mine.agent == AGENT and mine.runtime_overrides is None
    assert theirs.agent == OTHER and theirs.runtime_overrides is None
    listed = await app.get(f"{BASE}/agent/{AGENT}/conversations", headers=auth_headers)
    [row] = [r for r in listed.json() if r["id"] == own["conversation_id"]]
    assert row["runtime_overrides"] is None


# --------------------------------------------------------------------------- FR-3, FR-4


@pytest.mark.asyncio
async def test_the_first_input_is_the_checkpoint_and_another_agent_is_told_whose_it_is(
    app, auth_headers, agents, scheduled
):
    """ac-input-own."""
    checkpoint_id = await _checkpoint()
    own = (await _start(app, auth_headers, checkpoint_id)).json()
    other = (await _start(app, auth_headers, checkpoint_id, agent=OTHER)).json()

    async with async_session_factory() as db:
        rendered = delivery_content(await get_checkpoint_by_id(db, checkpoint_id))
    [own_entry] = await _entries(own["conversation_id"])
    [other_entry] = await _entries(other["conversation_id"])

    assert own_entry.content == rendered
    assert own_entry.origin_type == "checkpoint" and own_entry.agent == AGENT
    assert other_entry.agent == OTHER
    note, _, rest = other_entry.content.partition(rendered)
    assert rest == "" and note, "the checkpoint follows the note, whole"
    assert note.startswith(f"The checkpoint below was written in {AGENT}'s conversation conv-1")
    assert f"the tasks it lists are {AGENT}'s, not yours" in note


@pytest.mark.asyncio
async def test_the_operators_message_follows_the_checkpoint_in_the_same_turn(
    app, auth_headers, agents, scheduled
):
    """ac-note: one queue entry, so one delivery: the checkpoint, then the message."""
    checkpoint_id = await _checkpoint()
    started = (
        await _start(app, auth_headers, checkpoint_id, message="Try the slower approach this time.")
    ).json()

    [entry] = await _entries(started["conversation_id"])
    async with async_session_factory() as db:
        rendered = delivery_content(await get_checkpoint_by_id(db, checkpoint_id))
    assert entry.content.startswith(rendered)
    assert entry.content.endswith("Try the slower approach this time.")
    assert entry.content.index(rendered) < entry.content.index("slower approach")


# --------------------------------------------------------------------------- FR-5


@pytest.mark.asyncio
async def test_the_turn_is_scheduled_at_once_even_where_carry_overs_wait_for_continue(
    app, auth_headers, agents, scheduled
):
    """ac-starts."""
    async with async_session_factory() as db:
        project = await db.get(Project, PROJECT)
        project.checkpoint_auto_continue = False
        await db.commit()
    checkpoint_id = await _checkpoint()

    started = (await _start(app, auth_headers, checkpoint_id, agent=OTHER)).json()

    [entry] = await _entries(started["conversation_id"])
    assert entry.awaits_continue is False and entry.state == "queued"
    assert scheduled == [(PROJECT, OTHER)]


# --------------------------------------------------------------------------- FR-6


@pytest.mark.asyncio
async def test_the_original_is_untouched_and_can_still_be_carried_over(
    app, auth_headers, agents, scheduled
):
    """ac-untouched."""
    checkpoint_id = await _checkpoint()
    entries_before = await _entries("conv-1")
    runs_before = await _count(Run)

    for agent in (AGENT, OTHER):
        assert (await _start(app, auth_headers, checkpoint_id, agent=agent)).status_code == 201

    async with async_session_factory() as db:
        original = await get_conversation_by_id(db, "conv-1")
        checkpoint = await get_checkpoint_by_id(db, checkpoint_id)
        assert original.lifecycle == "open" and original.archived_at is None
        assert checkpoint.cut_over_to_conversation_id is None
    assert await _entries("conv-1") == entries_before
    assert await _count(Run) == runs_before

    cut = await app.post(f"{BASE}/checkpoints/{checkpoint_id}/cutover", headers=auth_headers)
    assert cut.status_code == 200, cut.text


# --------------------------------------------------------------------------- FR-7


@pytest.mark.asyncio
async def test_the_checkpoint_lists_what_started_from_it_and_each_links_back(
    app, auth_headers, agents, scheduled
):
    """ac-lineage, at the routes the Checkpoints page reads."""
    checkpoint_id = await _checkpoint()
    cut = await app.post(f"{BASE}/checkpoints/{checkpoint_id}/cutover", headers=auth_headers)
    successor = cut.json()["successor_conversation_id"]
    first = (await _start(app, auth_headers, checkpoint_id, agent=OTHER)).json()
    second = (await _start(app, auth_headers, checkpoint_id)).json()

    listed = await app.get(f"{BASE}/checkpoints", headers=auth_headers)
    [row] = [r for r in listed.json()["checkpoints"] if r["id"] == checkpoint_id]
    assert row["carried_into"] == {"conversation_id": successor}
    started = row["started_conversations"]
    assert [(s["conversation_id"], s["agent"]) for s in started] == [
        (first["conversation_id"], OTHER),
        (second["conversation_id"], AGENT),
    ]
    assert all(s["created_at"] for s in started)
    assert successor not in {s["conversation_id"] for s in started}

    for conversation_id, agent in (
        (first["conversation_id"], OTHER),
        (second["conversation_id"], AGENT),
    ):
        lineage = (
            await app.get(
                f"{BASE}/checkpoints",
                params={"conversation_id": conversation_id},
                headers=auth_headers,
            )
        ).json()["lineage"]
        assert lineage["started_from_checkpoint"]["checkpoint_id"] == checkpoint_id
        assert lineage["started_from_checkpoint"]["agent"] == AGENT
        conversations = await app.get(f"{BASE}/agent/{agent}/conversations", headers=auth_headers)
        [conv] = [c for c in conversations.json() if c["id"] == conversation_id]
        assert conv["started_from_checkpoint_id"] == checkpoint_id

    # A conversation started from nothing says so.
    plain = (
        await app.get(
            f"{BASE}/checkpoints", params={"conversation_id": "conv-1"}, headers=auth_headers
        )
    ).json()["lineage"]
    assert plain["started_from_checkpoint"] is None


# --------------------------------------------------------------------------- FR-8


@pytest.mark.asyncio
async def test_the_title_names_the_checkpoint_and_can_be_renamed(
    app, auth_headers, agents, scheduled
):
    """ac-title."""
    checkpoint_id = await _checkpoint()
    async with async_session_factory() as db:
        checkpoint = await get_checkpoint_by_id(db, checkpoint_id)
        checkpoint.title = "Revised check slices 1, 3, 4"
        await db.commit()

    started = (await _start(app, auth_headers, checkpoint_id, agent=OTHER)).json()
    assert started["title"] == "From checkpoint: Revised check slices 1, 3, 4"

    renamed = await app.patch(
        f"{BASE}/agent/{OTHER}/conversations/{started['conversation_id']}",
        json={"title": "Second attempt"},
        headers=auth_headers,
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "Second attempt"


# --------------------------------------------------------------------------- FR-9


@pytest.mark.asyncio
async def test_no_grant_is_needed_and_the_grant_still_governs_reading(
    app, auth_headers, agents, scheduled
):
    """ac-no-grant: OTHER holds no checkpoint-reading grant (closed by default)."""
    checkpoint_id = await _checkpoint()

    assert (await _start(app, auth_headers, checkpoint_id, agent=OTHER)).status_code == 201

    async with async_session_factory() as db:
        with pytest.raises(AccessDeniedError):
            await read_checkpoint(db, OTHER, PROJECT, checkpoint_id)


# --------------------------------------------------------------------------- FR-10


@pytest.mark.asyncio
async def test_each_refusal_says_why_and_creates_nothing(
    app, auth_headers, agents, add_agent, scheduled
):
    """ac-refused: a failed checkpoint, an archived agent, an unknown agent, another project's."""
    checkpoint_id = await _checkpoint()
    async with async_session_factory() as db:
        failed = await _ready_checkpoint(db, await get_conversation_by_id(db, "conv-1"))
        failed.status = "failed"
        failed.body = None
        failed_id = failed.id
        db.add(Project(id="proj-elsewhere", name="Elsewhere"))
        await db.commit()
        foreign = await _conversation(db, "conv-x", project_id="proj-elsewhere")
        foreign_id = (await _ready_checkpoint(db, foreign)).id
    await add_agent("retired", lifecycle="archived")
    conversations_before = await _count(Conversation)
    entries_before = await _count(InboundQueueEntry)

    refused_failed = await _start(app, auth_headers, failed_id)
    refused_archived = await _start(app, auth_headers, checkpoint_id, agent="retired")
    refused_unknown = await _start(app, auth_headers, checkpoint_id, agent="nobody")
    refused_foreign = await _start(app, auth_headers, foreign_id)

    assert refused_failed.status_code == 409 and "never written" in refused_failed.json()["detail"]
    assert refused_archived.status_code == 409 and "archived" in refused_archived.json()["detail"]
    assert refused_unknown.status_code == 409 and "no agent" in refused_unknown.json()["detail"]
    assert refused_foreign.status_code == 404 and "not found" in refused_foreign.json()["detail"]
    assert await _count(Conversation) == conversations_before
    assert await _count(InboundQueueEntry) == entries_before
    assert scheduled == []
    async with async_session_factory() as db:
        rows = (await db.execute(select(Checkpoint.id))).scalars().all()
    assert failed_id in rows
