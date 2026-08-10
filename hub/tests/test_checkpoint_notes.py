"""Agent notes: an input to a checkpoint, never the checkpoint.

Tasks 6.1 and 6.2 of 2026-08-07-conversation-handoff-rework.

Hub-side generation cannot recover what never reached the record — what the agent was *about* to
do, what it suspects but did not verify, what it would warn a successor away from. It is asked
for those, and only those, through a tool call rather than prose, so the request, the answer and
the **absence** of an answer are all observable.

The inversion matters: the previous design made the agent authoritative and the Hub hopeful, and
it was observed producing nothing while reporting success. Here the agent contributes and the Hub
remains authoritative — timeout, refusal and garbage all still produce a checkpoint.
"""

import subprocess

import pytest
from sqlalchemy import select

from hub.checkpoint_generation import (
    format_notes,
    generate_checkpoint,
    pending_notes,
)
from hub.db.engine import async_session_factory
from hub.db.models import CheckpointNote, Conversation, Run

from .test_checkpoint_generation import GOOD_BODY, _claude_stdout

PROJECT = "proj-test"
AGENT = "claude-1"


async def _conversation_with_run(db, conversation_id="conv-1", run_id="run-1"):
    db.add(Conversation(id=conversation_id, project_id=PROJECT, agent=AGENT, lifecycle="open"))
    db.add(
        Run(
            id=run_id,
            project_id=PROJECT,
            agent=AGENT,
            conversation_id=conversation_id,
            status="running",
        )
    )
    await db.commit()


async def _note(db, conversation_id="conv-1", **overrides):
    fields = {
        "id": overrides.pop("id", "note-1"),
        "project_id": PROJECT,
        "conversation_id": conversation_id,
        "agent": AGENT,
        "intent": "About to run the migration against the live database.",
        "suspicions": ["The index may already exist; check before creating it."],
        "warnings": ["Do not re-run the backfill; it is not idempotent."],
    }
    fields.update(overrides)
    note = CheckpointNote(**fields)
    db.add(note)
    await db.commit()
    return note


# --------------------------------------------------------------------------- the tool surface


def test_the_tool_asks_only_for_what_the_transcript_cannot_hold():
    """The prompt an agent reads must not invite it to restate computed fields — the whole
    reason generation moved Hub-side."""
    from hub.mcp_server import submit_checkpoint_notes

    doc = submit_checkpoint_notes.__doc__ or ""
    assert "Do not restate any of that here." in doc
    for computed in ("files changed", "tasks are assigned", "unanswered"):
        assert computed in doc
    for asked in ("intent", "suspicions", "warnings"):
        assert asked in doc
    # It must be clear the checkpoint does not depend on this call.
    assert "whether or not you call this" in doc


@pytest.mark.asyncio
async def test_notes_are_recorded_against_the_runs_conversation(app, auth_headers, monkeypatch):
    async with async_session_factory() as db:
        await _conversation_with_run(db)

    from hub import agent_auth

    async def fake_actor():
        return agent_auth.AgentActor(project_id=PROJECT, agent=AGENT, run_id="run-1")

    from hub.api.v1 import agent_actions

    app_obj = app._transport.app
    app_obj.dependency_overrides[agent_actions.get_agent_actor] = fake_actor
    try:
        response = await app.post(
            "/api/v1/agent-actions/checkpoint-notes",
            json={
                "intent": "About to run the migration.",
                "suspicions": ["The index may already exist."],
                "warnings": ["Do not re-run the backfill."],
            },
            headers=auth_headers,
        )
    finally:
        app_obj.dependency_overrides.pop(agent_actions.get_agent_actor, None)

    assert response.status_code == 201, response.text
    assert response.json()["conversation_id"] == "conv-1"

    async with async_session_factory() as db:
        rows = (await db.execute(select(CheckpointNote))).scalars().all()

    assert len(rows) == 1
    assert rows[0].intent == "About to run the migration."
    assert rows[0].suspicions == ["The index may already exist."]
    assert rows[0].consumed_by_checkpoint_id is None


@pytest.mark.asyncio
async def test_notes_from_a_run_with_no_conversation_are_refused(app, auth_headers):
    """A note with nowhere to land is better refused loudly than stored where nothing reads it."""
    from hub import agent_auth
    from hub.api.v1 import agent_actions

    async def fake_actor():
        return agent_auth.AgentActor(project_id=PROJECT, agent=AGENT, run_id=None)

    app_obj = app._transport.app
    app_obj.dependency_overrides[agent_actions.get_agent_actor] = fake_actor
    try:
        response = await app.post(
            "/api/v1/agent-actions/checkpoint-notes",
            json={"intent": "something", "suspicions": [], "warnings": []},
            headers=auth_headers,
        )
    finally:
        app_obj.dependency_overrides.pop(agent_actions.get_agent_actor, None)

    assert response.status_code == 409
    assert "nowhere to land" in response.json()["detail"]


@pytest.mark.asyncio
async def test_an_essay_is_refused(app, auth_headers):
    """Capped near the 1-2k tokens recommended for distillation. An agent allowed to write at
    length here would be writing the checkpoint by the back door — the arrangement this change
    replaces."""
    from hub import agent_auth
    from hub.api.v1 import agent_actions

    async def fake_actor():
        return agent_auth.AgentActor(project_id=PROJECT, agent=AGENT, run_id="run-1")

    async with async_session_factory() as db:
        await _conversation_with_run(db)

    app_obj = app._transport.app
    app_obj.dependency_overrides[agent_actions.get_agent_actor] = fake_actor
    try:
        too_long = await app.post(
            "/api/v1/agent-actions/checkpoint-notes",
            json={"intent": "x" * 1501, "suspicions": [], "warnings": []},
            headers=auth_headers,
        )
        too_many = await app.post(
            "/api/v1/agent-actions/checkpoint-notes",
            json={"intent": "ok", "suspicions": [f"s{i}" for i in range(9)], "warnings": []},
            headers=auth_headers,
        )
        entry_too_long = await app.post(
            "/api/v1/agent-actions/checkpoint-notes",
            json={"intent": "ok", "suspicions": ["y" * 401], "warnings": []},
            headers=auth_headers,
        )
    finally:
        app_obj.dependency_overrides.pop(agent_actions.get_agent_actor, None)

    assert too_long.status_code == 422
    assert too_many.status_code == 422
    assert entry_too_long.status_code == 422


# --------------------------------------------------------------------------- as an input


def test_notes_render_with_their_three_parts_distinguished():
    note = CheckpointNote(
        id="note-1",
        project_id=PROJECT,
        conversation_id="conv-1",
        agent=AGENT,
        intent="Running the migration.",
        suspicions=["The index may exist."],
        warnings=["Backfill is not idempotent."],
    )
    rendered = format_notes(note)
    assert "In flight: Running the migration." in rendered
    assert "Unverified suspicions:" in rendered
    assert "Warnings for a successor:" in rendered


@pytest.mark.asyncio
async def test_notes_reach_the_generator_and_are_marked_as_one_input(app, monkeypatch):
    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, stdout=_claude_stdout(GOOD_BODY), stderr="")

    async with async_session_factory() as db:
        await _conversation_with_run(db)
        await _note(db)
        conversation = await db.get(Conversation, "conv-1")

        monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
        monkeypatch.setattr(subprocess, "run", fake_run)
        checkpoint = await generate_checkpoint(
            db, conversation, trigger="context_pressure", cli="claude", probe=False
        )

    assert "About to run the migration against the live database." in captured[0]
    assert "not idempotent" in captured[0]
    # The transcript wins where they disagree — notes are evidence, not instruction.
    assert "the transcript is authoritative where they disagree" in captured[0]
    # And the body does not carry the "no notes" disclaimer.
    assert "contributed no notes" not in checkpoint.body


@pytest.mark.asyncio
async def test_notes_are_consumed_once_and_not_reused_by_a_later_checkpoint(app, monkeypatch):
    """The agent wrote them about a moment that has passed. Presenting them as current on a
    later checkpoint is the same staleness as reporting a pre-compaction context percentage."""
    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, stdout=_claude_stdout(GOOD_BODY), stderr="")

    async with async_session_factory() as db:
        await _conversation_with_run(db)
        await _note(db)
        conversation = await db.get(Conversation, "conv-1")

        monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
        monkeypatch.setattr(subprocess, "run", fake_run)
        first = await generate_checkpoint(
            db, conversation, trigger="operator", cli="claude", probe=False
        )
        second = await generate_checkpoint(
            db, conversation, trigger="operator", cli="claude", probe=False
        )

        note = (await db.execute(select(CheckpointNote))).scalars().one()
        still_pending = await pending_notes(db, "conv-1")

    assert note.consumed_by_checkpoint_id == first.id
    assert still_pending is None
    assert "About to run the migration" in captured[0]
    assert "About to run the migration" not in captured[1]
    assert second.id != first.id


@pytest.mark.asyncio
async def test_notes_are_consumed_even_when_generation_produced_nothing(app, monkeypatch):
    """Otherwise a failed generation leaves stale intent to be picked up later as if current."""

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="not json", stderr="")

    async with async_session_factory() as db:
        await _conversation_with_run(db)
        await _note(db)
        conversation = await db.get(Conversation, "conv-1")

        monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
        monkeypatch.setattr(subprocess, "run", fake_run)
        checkpoint = await generate_checkpoint(
            db, conversation, trigger="run_failure", cli="claude", probe=False
        )
        note = (await db.execute(select(CheckpointNote))).scalars().one()

    assert checkpoint.status == "unwritten"
    assert note.consumed_by_checkpoint_id == checkpoint.id


@pytest.mark.asyncio
async def test_a_checkpoint_is_produced_when_the_agent_never_answered(app, monkeypatch):
    """Task 6.2. Timeout, refusal and silence are the same thing from here: no note row."""

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=_claude_stdout(GOOD_BODY), stderr="")

    async with async_session_factory() as db:
        await _conversation_with_run(db)
        conversation = await db.get(Conversation, "conv-1")

        monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
        monkeypatch.setattr(subprocess, "run", fake_run)
        checkpoint = await generate_checkpoint(
            db, conversation, trigger="operator", cli="claude", probe=False
        )

    assert checkpoint.status == "ready"
    # And it says so, rather than leaving "had nothing to add" and "was never asked" identical.
    assert "contributed no notes" in checkpoint.body
