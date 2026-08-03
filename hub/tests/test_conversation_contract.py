"""Dedicated contract suite for the stable Conversation identity (task 0.1 of the
archived `2026-08-02-agent-conversation-workspace` change).

`Conversation(id, project_id, agent, provider_session_id, lifecycle, created_at,
updated_at, archived_at)` — see design.md's "Conversation identity" and "Lifecycle,
retry, stop, and handoff" sections. Each behavior below is already incidentally
exercised elsewhere (test_conversations.py, test_agent_trigger.py,
test_migrations.py's `test_migration_0017_...`); this file asserts them explicitly,
as a standalone unit, so no future change can regress one without a dedicated,
named failure. Deterministic legacy backfill has its own dedicated test in
test_migrations.py, next to the rest of that file's per-migration coverage — not
duplicated here.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, EventLog, Run


async def _await_background_runs() -> None:
    while agent_trigger._background_runs:
        for task in list(agent_trigger._background_runs):
            await task


async def _wait_for_active_pty(run_id, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if run_id in agent_trigger._active_ptys:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} never registered an active pty")


def _fake_pty(lines, exit_code=0, pid=4242):
    session = MagicMock()
    session.pid = pid
    session.read.side_effect = [*lines, ""]
    session.wait.return_value = exit_code
    return MagicMock(return_value=session)


def _stoppable_pty(pid=5150, exit_code=15):
    """A PtySession whose `.read()` blocks until `.terminate()` releases it.

    Mirrors test_agent_trigger.py's `_stoppable_pty` — needed here to prove
    conversation allocation and retention hold even while a run is genuinely
    in flight, not just when the fake process happens to finish instantly.
    """
    released = threading.Event()

    def _blocking_read(size=4096):
        released.wait()
        return ""

    def _terminate(force=False):
        released.set()

    session = MagicMock()
    session.pid = pid
    session.read.side_effect = _blocking_read
    session.terminate.side_effect = _terminate
    session.wait.return_value = exit_code
    return session


# ---------------------------------------------------------------------------
# Model contract
# ---------------------------------------------------------------------------


def test_conversation_model_declares_full_contract_shape() -> None:
    """A column rename or a silently-dropped constraint must fail here, not
    surface downstream as a confusing 409 or a broken migration."""
    columns = Conversation.__table__.columns
    assert set(columns.keys()) >= {
        "id",
        "project_id",
        "agent",
        "provider_session_id",
        "lifecycle",
        "created_at",
        "updated_at",
        "archived_at",
    }
    assert columns["id"].primary_key
    assert not columns["project_id"].nullable
    assert not columns["agent"].nullable
    assert columns["provider_session_id"].nullable
    assert not columns["lifecycle"].nullable
    assert columns["lifecycle"].default.arg == "open"
    assert not columns["created_at"].nullable
    assert not columns["updated_at"].nullable
    assert columns["archived_at"].nullable

    check_constraints = {
        c.name for c in Conversation.__table__.constraints if isinstance(c, sa.CheckConstraint)
    }
    assert "ck_conversations_lifecycle" in check_constraints

    unique_index = next(
        idx
        for idx in Conversation.__table__.indexes
        if idx.name == "uq_conversations_project_agent_provider_session"
    )
    assert unique_index.unique
    assert [c.name for c in unique_index.columns] == [
        "project_id",
        "agent",
        "provider_session_id",
    ]


def test_new_conversation_helper_produces_contract_defaults() -> None:
    """`new_conversation()` is the only construction path outside migration
    backfill — its defaults must match the contract: open, unbound, freshly
    timestamped, never pre-archived."""
    conversation = new_conversation(project_id="proj-x", agent="agent-x")
    assert conversation.id.startswith("conv-")
    assert conversation.lifecycle == "open"
    assert conversation.provider_session_id is None
    assert conversation.archived_at is None
    assert conversation.created_at == conversation.updated_at


# ---------------------------------------------------------------------------
# Synchronous allocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_allocates_conversation_synchronously_before_provider_output(
    app, auth_headers
):
    """The conversation row must be durably committed before the HTTP response
    returns — not eventually, once the background provider process happens to
    produce output. `read()` blocks forever until released, so if allocation
    were deferred to background execution this test would find nothing instead
    of finding the row immediately after the response comes back."""
    await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    session = _stoppable_pty()
    try:
        with patch(  # noqa: SIM117
            "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=session)
        ):
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                response = await app.post(
                    "/api/v1/agent/trigger",
                    json={"agent": "claude", "message": "hi"},
                    headers=auth_headers,
                )
                assert response.status_code == 200
                conversation_id = response.json()["conversation_id"]

                async with async_session_factory() as db:
                    conversation = await db.get(Conversation, conversation_id)
                assert conversation is not None
                assert conversation.lifecycle == "open"
                assert conversation.provider_session_id is None
    finally:
        session.terminate()
        await _await_background_runs()


# ---------------------------------------------------------------------------
# Immutable scope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conversation_scope_is_immutable_across_binding_and_followups(app, auth_headers):
    """`project_id`, `agent`, and `created_at` must never change once a
    conversation exists — provider binding and follow-up turns only ever touch
    `provider_session_id`/`updated_at`."""
    await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"provider-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            first = await app.post(
                "/api/v1/agent/trigger",
                json={"agent": "claude", "message": "first"},
                headers=auth_headers,
            )
            conversation_id = first.json()["conversation_id"]
            await _await_background_runs()

    async with async_session_factory() as db:
        original = await db.get(Conversation, conversation_id)
        original_project_id = original.project_id
        original_agent = original.agent
        original_created_at = original.created_at

    fake_spawn_2 = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"provider-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn_2):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            await app.post(
                "/api/v1/agent/trigger",
                json={
                    "agent": "claude",
                    "message": "second",
                    "conversation_id": conversation_id,
                },
                headers=auth_headers,
            )
            await _await_background_runs()

    async with async_session_factory() as db:
        after = await db.get(Conversation, conversation_id)
        assert after.project_id == original_project_id
        assert after.agent == original_agent
        assert after.created_at == original_created_at


# ---------------------------------------------------------------------------
# Idempotent provider binding / binding conflict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_binding_is_idempotent_for_repeated_session_id(
    app, auth_headers, bind_runner
):
    """A provider re-announcing the same session id it was already bound to
    (a resumed CLI echoing its own session on every line) must not be treated
    as a conflict."""
    await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner("claude", cli="claude")
    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"provider-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            first = await app.post(
                "/api/v1/agent/trigger",
                json={"agent": "claude", "message": "first"},
                headers=auth_headers,
            )
            conversation_id = first.json()["conversation_id"]
            await _await_background_runs()

    fake_spawn_2 = _fake_pty(
        [
            '{"type":"result","subtype":"success","is_error":false,"session_id":"provider-1"}\n',
            '{"type":"result","subtype":"success","is_error":false,"session_id":"provider-1"}\n',
        ]
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn_2):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            second = await app.post(
                "/api/v1/agent/trigger",
                json={
                    "agent": "claude",
                    "message": "second",
                    "conversation_id": conversation_id,
                },
                headers=auth_headers,
            )
            run_id = second.json()["run_id"]
            await _await_background_runs()

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "completed"
        assert run.error is None

        conversation = await db.get(Conversation, conversation_id)
        assert conversation.provider_session_id == "provider-1"

        conflicts = (
            (
                await db.execute(
                    select(EventLog).where(EventLog.event_type == "conversation_binding_conflict")
                )
            )
            .scalars()
            .all()
        )
        assert conflicts == []


@pytest.mark.asyncio
async def test_provider_binding_conflict_leaves_conversation_untouched_and_fails_run(
    app, auth_headers, bind_runner
):
    """A provider reporting a *different* session id than the one already bound
    must fail that run without corrupting the conversation's existing binding —
    the whole point of binding conflict detection is that the Hub's own record
    of "which provider session this is" stays trustworthy even when a CLI
    misbehaves."""
    await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner("claude", cli="claude")
    fake_spawn_1 = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"provider-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn_1):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            first = await app.post(
                "/api/v1/agent/trigger",
                json={"agent": "claude", "message": "first"},
                headers=auth_headers,
            )
            conversation_id = first.json()["conversation_id"]
            await _await_background_runs()

    fake_spawn_2 = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"provider-2"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn_2):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            second = await app.post(
                "/api/v1/agent/trigger",
                json={
                    "agent": "claude",
                    "message": "second",
                    "conversation_id": conversation_id,
                },
                headers=auth_headers,
            )
            run_id = second.json()["run_id"]
            await _await_background_runs()

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "failed"
        assert "binding conflict" in run.error.lower()

        conversation = await db.get(Conversation, conversation_id)
        assert conversation.provider_session_id == "provider-1"
        assert conversation.lifecycle == "open"

        conflicts = (
            (
                await db.execute(
                    select(EventLog).where(EventLog.event_type == "conversation_binding_conflict")
                )
            )
            .scalars()
            .all()
        )
        assert len(conflicts) == 1
        assert conflicts[0].data["conversation_id"] == conversation_id


# ---------------------------------------------------------------------------
# Retry / stop retention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_and_retry_retain_conversation_and_resume_bound_session(
    app, auth_headers, bind_runner
):
    """design.md: 'A conversation remains open across run completion, failure,
    interruption, stop, and retry... Retry creates a new run under the same
    conversation. It resumes the bound provider session.' Exercises that whole
    chain: bind a session, stop a subsequent run mid-flight, then retry — the
    conversation identity and its provider binding must survive every step."""
    await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner("claude", cli="claude")

    fake_spawn_1 = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"provider-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn_1):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            first = await app.post(
                "/api/v1/agent/trigger",
                json={"agent": "claude", "message": "first"},
                headers=auth_headers,
            )
            conversation_id = first.json()["conversation_id"]
            await _await_background_runs()

    stoppable = _stoppable_pty()
    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=stoppable)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            second = await app.post(
                "/api/v1/agent/trigger",
                json={
                    "agent": "claude",
                    "message": "interrupted",
                    "conversation_id": conversation_id,
                },
                headers=auth_headers,
            )
            second_run_id = second.json()["run_id"]
            await _wait_for_active_pty(second_run_id)

            stop = await app.post("/api/v1/agent/claude/stop", headers=auth_headers)
            assert stop.status_code == 200
            await _await_background_runs()

    async with async_session_factory() as db:
        second_run = await db.get(Run, second_run_id)
        assert second_run.status == "stopped"

        conversation = await db.get(Conversation, conversation_id)
        assert conversation is not None, "stop must not delete the conversation row"
        assert conversation.lifecycle == "open"
        assert conversation.provider_session_id == "provider-1"

    fake_spawn_3 = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"provider-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn_3):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            retry = await app.post(
                "/api/v1/agent/trigger",
                json={
                    "agent": "claude",
                    "message": "retry",
                    "conversation_id": conversation_id,
                },
                headers=auth_headers,
            )
            assert retry.status_code == 200
            assert retry.json()["conversation_id"] == conversation_id
            retry_run_id = retry.json()["run_id"]
            await _await_background_runs()

    async with async_session_factory() as db:
        # session_id is stamped onto the Run synchronously (before background
        # execution starts) from conversation.provider_session_id — proving the
        # retry actually resumed rather than starting a fresh provider session.
        retry_run = await db.get(Run, retry_run_id)
        assert retry_run.session_id == "provider-1"

        conversation = await db.get(Conversation, conversation_id)
        assert conversation.provider_session_id == "provider-1"
        assert conversation.lifecycle == "open"


# ---------------------------------------------------------------------------
# Reset-only deletion
# ---------------------------------------------------------------------------


def test_no_code_path_deletes_conversations_outside_reset() -> None:
    """design.md: '`agentweave reset` may delete conversation/runtime data only
    under its existing explicit reset confirmation. Ordinary startup, migration,
    stop, archive, and project reopen never clear it.' No reset endpoint exists
    in the Hub yet, so today the invariant is absolute: zero code paths delete a
    Conversation row. This scan fails the day someone adds one outside an
    explicit, clearly-named reset gate — a signal to give it that gate rather
    than to relax this test."""
    hub_root = Path(__file__).resolve().parents[1] / "hub"
    offending = []
    for path in hub_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "Conversation" not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "delete(" in stripped and "Conversation" in stripped:
                offending.append(f"{path}:{lineno}: {stripped}")
    assert offending == [], f"found a code path deleting Conversation rows: {offending}"
