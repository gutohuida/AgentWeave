"""A folded name is closed and its chats are read-only (`fold-duplicate-agents-into-one-profile-with-
their-history-kept`, FR-5, FR-12, FR-13, task folded-name-closed).

DeveloperOpus is folded into Developer. Nothing launches under the folded name, anything newly
addressed to it is refused with the one `agent_folded` code naming the profile (design D4), the
pickers leave it out, its past conversation still reads but takes no turn, and the peer-checkpoint
grant is untouched by a fold: the profile reads the folded agent's checkpoints no more than before.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from hub import builds
from hub.agent_auth import hash_run_token
from hub.checkpoint_access import AccessDeniedError, may_read_checkpoint, read_checkpoint
from hub.checkpoints import compute_envelope, create_checkpoint
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Conversation, InboundQueueEntry, Message, Run, Task

P = "proj-test"
BASE = f"/api/v1/projects/{P}"
FOLDED, PROFILE = "DeveloperOpus", "Developer"
WORDS = f"{FOLDED} was folded into {PROFILE}; address {PROFILE} instead."


@pytest.fixture
async def folded(app, auth_headers, add_agent, bind_runner):
    for name in (PROFILE, FOLDED, "QA"):
        await add_agent(name)
        await bind_runner(name, cli="claude")
    async with async_session_factory() as db:
        db.add(Conversation(id="conv-old", project_id=P, agent=FOLDED, lifecycle="open"))
        await db.commit()
    resp = await app.post(
        f"{BASE}/agents/{FOLDED}/fold", json={"into": PROFILE}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text


def _refused(resp) -> None:
    assert resp.status_code in (409, 422), resp.text
    detail = resp.json()["detail"]
    text = detail["message"] if isinstance(detail, dict) else detail
    assert WORDS in text, text
    if isinstance(detail, dict):
        assert detail["code"] == "agent_folded"
        assert detail["folded_into"] == PROFILE


async def _count(model) -> int:
    async with async_session_factory() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


# ----------------------------------------------------------------- folded-never-launches


@pytest.mark.asyncio
async def test_a_trigger_under_a_folded_name_launches_nothing(app, auth_headers, folded):
    runs = await _count(Run)
    with patch("hub.api.v1.agent_trigger.PtySession.spawn") as spawn:
        for body in (
            {"agent": FOLDED, "message": "hi", "session_mode": "new"},
            {"agent": FOLDED, "message": "hi", "conversation_id": "conv-old"},
        ):
            resp = await app.post(f"{BASE}/agent/trigger", json=body, headers=auth_headers)
            _refused(resp)
        spawn.assert_not_called()
    assert await _count(Run) == runs


@pytest.mark.asyncio
async def test_the_direct_launch_path_refuses_a_folded_name(app, folded):
    """The one choke point every queued delivery, task turn, review and mend passes through."""
    from hub.api.v1.agent_trigger import TriggerAgentError, _trigger_agent_directly

    async with async_session_factory() as db:
        with pytest.raises(TriggerAgentError) as caught:
            await _trigger_agent_directly(
                project_id=P,
                agent=FOLDED,
                message="work",
                conversation_id="conv-old",
                session=db,
                review_claim=None,  # type: ignore[arg-type]
            )
    assert caught.value.status_code == 409
    assert WORDS in str(caught.value.detail)


@pytest.mark.asyncio
async def test_the_pickers_leave_a_folded_agent_out(app, auth_headers, folded):
    async with async_session_factory() as db:
        assert FOLDED not in await builds.open_agents(db, P)
        assert PROFILE in await builds.open_agents(db, P)
    listed = await app.get(f"{BASE}/agents", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    names = {a["name"] for a in listed.json()}
    assert FOLDED not in names
    assert PROFILE in names


# ----------------------------------------------------------------- addressing-refused


@pytest.mark.asyncio
async def test_a_task_created_or_reassigned_to_a_folded_name_is_refused(app, auth_headers, folded):
    before = await _count(Task)
    for extra in ({"assignee": FOLDED}, {"builder": FOLDED}, {"checker": FOLDED}):
        resp = await app.post(f"{BASE}/tasks", json={"title": "t", **extra}, headers=auth_headers)
        _refused(resp)
    assert await _count(Task) == before

    made = await app.post(
        f"{BASE}/tasks", json={"title": "t", "assignee": "QA"}, headers=auth_headers
    )
    assert made.status_code == 201, made.text
    task_id = made.json()["id"]
    patched = await app.patch(
        f"{BASE}/tasks/{task_id}", json={"assignee": FOLDED}, headers=auth_headers
    )
    _refused(patched)
    again = await app.get(f"{BASE}/tasks/{task_id}", headers=auth_headers)
    assert again.json()["assignee"] == "QA"


@pytest.mark.asyncio
async def test_a_job_for_a_folded_name_is_refused(app, auth_headers, folded):
    resp = await app.post(
        f"{BASE}/jobs",
        json={"name": "j", "agent": FOLDED, "message": "work", "cron": "*/5 * * * *"},
        headers=auth_headers,
    )
    _refused(resp)


@pytest.mark.asyncio
async def test_a_message_to_a_folded_name_is_refused_and_nothing_is_queued(app, folded):
    token = "aw_run_folded-sender-secret"
    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-sender",
                project_id=P,
                agent="QA",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    messages, queued = await _count(Message), await _count(InboundQueueEntry)
    resp = await app.post(
        "/api/v1/agent-actions/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"recipient": FOLDED, "subject": "Note", "content": "hello"},
    )
    _refused(resp)
    assert (await _count(Message), await _count(InboundQueueEntry)) == (messages, queued)


# ----------------------------------------------------------------- chat-read-only


@pytest.mark.asyncio
async def test_a_folded_agents_conversation_opens_but_takes_no_turn(app, auth_headers, folded):
    listed = await app.get(f"{BASE}/conversations?lifecycle=all", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert any(c["id"] == "conv-old" for c in listed.json()["conversations"])
    resp = await app.post(
        f"{BASE}/agent/trigger",
        json={"agent": FOLDED, "message": "continue", "conversation_id": "conv-old"},
        headers=auth_headers,
    )
    _refused(resp)


# ----------------------------------------------------------------- checkpoints-keep-grant


@pytest.mark.asyncio
async def test_a_fold_gives_the_profile_no_read_of_the_folded_agents_checkpoints(app, folded):
    async with async_session_factory() as db:
        conversation = (
            await db.execute(select(Conversation).where(Conversation.id == "conv-old"))
        ).scalar_one()
        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=await compute_envelope(db, conversation),
            body="## Objective\n\nsomething",
        )
        profile = (
            await db.execute(select(Agent).where(Agent.project_id == P, Agent.name == PROFILE))
        ).scalar_one()
        assert profile.can_read_checkpoints is False
        assert not may_read_checkpoint(profile, checkpoint)
        with pytest.raises(AccessDeniedError):
            await read_checkpoint(db, PROFILE, P, checkpoint.id)
