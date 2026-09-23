"""Round 4b: refusals that say what is true and what would work.

F175 + F182 (the model refusal named nothing it would accept, and called a published alias
undeclared), F191 (one sentence for every reason a conversation is unavailable), F200 (one sentence
for four queue-entry states, asserting a delivery that never happened), F180 (the archive refusal
offered only the destructive remedy), F208 (the arrange refusal named neither cause nor remedy).
Each leg drives the route and reads the sentence the caller gets.
"""

import pytest
from sqlalchemy import select

from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import Agent, InboundQueueEntry, Project
from hub.inbound_queue import new_entry
from hub.model_catalog import get_provider, validate_overrides

P = "/api/v1/projects/proj-test"
CLAUDE_MODELS = [m.id for m in get_provider("claude").models]
OPUS = next(m.id for m in get_provider("claude").models if "opus" in m.aliases)

pytestmark = pytest.mark.asyncio


# --- F175 + F182: the model refusal --------------------------------------------------------------


@pytest.mark.parametrize(
    ("route", "body"),
    [
        ("/runners", {"name": "r", "cli": "claude"}),
        ("/agents", {"name": "a-4b", "provider": "claude"}),
    ],
)
async def test_an_undeclared_model_is_refused_with_the_declared_ones(
    app, auth_headers, route, body
):
    refused = await app.post(
        P + route, json={**body, "model": "claude-opus-9"}, headers=auth_headers
    )

    assert refused.status_code == 400, refused.text
    detail = refused.json()["detail"]
    assert "'claude-opus-9' is not a model 'claude' declares" in detail
    assert all(model_id in detail for model_id in CLAUDE_MODELS)


@pytest.mark.parametrize(
    ("route", "body"),
    [
        ("/runners", {"name": "r", "cli": "claude"}),
        ("/agents", {"name": "a-4b", "provider": "claude"}),
    ],
)
async def test_a_published_alias_is_refused_naming_the_id_it_stands_for(
    app, auth_headers, route, body
):
    """`GET /model-catalog` publishes `opus` as an alias; calling it undeclared was untrue."""
    catalog = await app.get("/api/v1/model-catalog", headers=auth_headers)
    published = {
        alias: model["id"]
        for provider in catalog.json()["providers"]
        if provider["provider"] == "claude"
        for model in provider["models"]
        for alias in model["aliases"]
    }
    assert published["opus"] == OPUS

    refused = await app.post(P + route, json={**body, "model": "opus"}, headers=auth_headers)

    assert refused.status_code == 400, refused.text
    detail = refused.json()["detail"]
    assert "is not a model" not in detail
    assert f"use '{OPUS}'" in detail


async def test_the_override_refusal_uses_the_same_sentence():
    _, rejection = validate_overrides("claude", {"model": "nope"})
    assert rejection is not None
    assert "'nope' is not a model 'claude' declares" in rejection.reason
    assert all(model_id in rejection.reason for model_id in CLAUDE_MODELS)


# --- F191: why a conversation is unavailable ------------------------------------------------------


async def _conversation(agent, *, project_id="proj-test", lifecycle="open"):
    async with async_session_factory() as session:
        conversation = new_conversation(project_id=project_id, agent=agent, origin="operator")
        conversation.lifecycle = lifecycle
        session.add(conversation)
        await session.commit()
        return conversation.id


async def _trigger(app, auth_headers, conversation_id):
    return await app.post(
        f"{P}/agent/trigger",
        json={"agent": "vera", "message": "hello", "conversation_id": conversation_id},
        headers=auth_headers,
    )


async def test_each_reason_a_conversation_is_unavailable_is_named_with_its_repair(
    app, auth_headers
):
    async with async_session_factory() as session:
        session.add(Project(id="proj-other", name="Other"))
        session.add(Agent(id="agt-vera", project_id="proj-test", name="vera"))
        await session.commit()
    foreign = await _conversation("vera", project_id="proj-other")
    someone_elses = await _conversation("wren")
    archived = await _conversation("vera", lifecycle="archived")

    unknown_detail = (await _trigger(app, auth_headers, "conv-nope")).json()["detail"]
    foreign_resp = await _trigger(app, auth_headers, foreign)
    other_resp = await _trigger(app, auth_headers, someone_elses)
    archived_resp = await _trigger(app, auth_headers, archived)

    for resp in (foreign_resp, other_resp, archived_resp):
        assert resp.status_code == 409, resp.text
        assert "omit conversation_id to start a new conversation with vera" in resp.json()["detail"]
    assert unknown_detail.startswith("No conversation conv-nope in this project.")
    # Another project's conversation reads exactly as an unknown one: nothing leaks.
    assert foreign_resp.json()["detail"] == unknown_detail.replace("conv-nope", foreign)
    assert f"{someone_elses} is wren's, not vera's" in other_resp.json()["detail"]
    assert "Address it to wren" in other_resp.json()["detail"]
    assert f"{archived} is archived. Unarchive it" in archived_resp.json()["detail"]


# --- F200: why a queue entry cannot be withdrawn or released --------------------------------------


async def _entry(*, project_id="proj-test", state="queued", run=None, abandoned=None):
    async with async_session_factory() as session:
        entry = new_entry(
            project_id=project_id,
            agent="vera",
            origin_type="operator",
            content="a message",
            hop_depth=0,
        )
        entry.state = state
        entry.delivered_in_run_id = run
        entry.abandoned_reason = abandoned
        session.add(entry)
        await session.commit()
        return entry.id


@pytest.mark.parametrize(
    ("method", "suffix", "action"),
    [("DELETE", "", "withdraw"), ("POST", "/release", "release")],
)
async def test_each_state_an_entry_cannot_be_acted_on_in_is_named(
    app, auth_headers, method, suffix, action
):
    async with async_session_factory() as session:
        session.add(Project(id="proj-other", name="Other"))
        await session.commit()
    delivered = await _entry(state="delivered", run="run-abc")
    withdrawn = await _entry(state="withdrawn")
    abandoned = await _entry(state="withdrawn", abandoned="Delivery failed 3 times.")
    foreign = await _entry(project_id="proj-other")

    async def act(entry_id):
        return await app.request(
            method, f"{P}/queue/entries/{entry_id}{suffix}", headers=auth_headers
        )

    unknown = await act("entry-nope")
    assert unknown.status_code == 404, unknown.text
    assert unknown.json()["detail"] == "No queue entry entry-nope in this project."
    other = await act(foreign)
    assert other.status_code == 404, other.text
    assert other.json()["detail"] == f"No queue entry {foreign} in this project."
    # The foreign entry was not touched.
    async with async_session_factory() as session:
        state = await session.scalar(
            select(InboundQueueEntry.state).where(InboundQueueEntry.id == foreign)
        )
        assert state == "queued"

    resp = await act(delivered)
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == (
        f"Queue entry {delivered} was already delivered in run run-abc; there is nothing to "
        f"{action}."
    )
    resp = await act(withdrawn)
    assert resp.status_code == 409, resp.text
    assert "delivered" not in resp.json()["detail"]
    assert f"{withdrawn} was already withdrawn" in resp.json()["detail"]
    resp = await act(abandoned)
    assert resp.status_code == 409, resp.text
    assert "gave up delivering" in resp.json()["detail"]
    assert "Delivery failed 3 times" in resp.json()["detail"]


# --- F180: the archive refusal offers the non-destructive remedy ----------------------------------


@pytest.mark.parametrize("bound", [False, True])
async def test_the_archive_refusal_offers_delivery_before_discard(
    app, auth_headers, bind_runner, bound
):
    await app.post(
        f"{P}/session/sync",
        json={"data": {"agents": {"vera": {}}}},
        headers=auth_headers,
    )
    if bound:
        await bind_runner("vera")
    conversation_id = await _conversation("vera")
    async with async_session_factory() as session:
        entry = new_entry(
            project_id="proj-test",
            agent="vera",
            origin_type="operator",
            content="waiting",
            hop_depth=5000,  # above any hop budget, so a bound runner does not deliver it
            conversation_id=conversation_id,
        )
        session.add(entry)
        await session.commit()
        queued = [entry.id]

    refused = await app.post(f"{P}/agents/vera/archive", headers=auth_headers)

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["blocking_queue_entry_ids"] == queued
    message = detail["message"]
    assert "nothing delivers to an archived agent" in message
    assert "discard them to archive the agent now" in message
    if bound:
        assert "Let them be delivered first" in message
    else:
        assert "Bind a runner so it can deliver them" in message
    async with async_session_factory() as session:
        rows = (await session.execute(select(InboundQueueEntry.state))).scalars().all()
        assert rows == ["queued"]


# --- F208: the arrange refusal names the reindex ---------------------------------------------------


async def test_arranging_with_no_index_names_the_reindex_and_its_home(app, auth_headers):
    refused = await app.post(
        f"{P}/project/spec/documents/arrange",
        json={"path": "spec/area.html", "parent": None},
        headers=auth_headers,
    )

    assert refused.status_code == 409, refused.text
    message = refused.json()["detail"]["message"]
    assert message.startswith("no usable index to arrange (absent).")
    assert "POST /spec/reindex" in message
    assert '"home"' in message
