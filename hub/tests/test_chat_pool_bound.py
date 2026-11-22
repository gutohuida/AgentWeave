"""A chat's choice of runner (`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool`,
FR-9, task chats-and-holds; its pool bound reversed by `a-profile-s-pool-and-a-new-chat-can-use-any-
model-of-any-provider`, FR-10, whose own criteria are in `test_chat_any_model`).

A new chat starts on the default and may choose any runner of the project or any catalog model;
once it has a turn, only one on the CLI it started on, and one on another CLI is refused saying a
new chat is needed. A choice on another runner than the default's launches on that runner.

Driven through `POST /agent/trigger`, the route the composer sends with, with the CLI stubbed.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Conversation, Run

from ._pool import add_pool_entry
from .test_agent_trigger import _await_background_run, _fake_pty

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/projects/proj-test"
_SESSIONS = iter(range(1, 1000))


def _claude_done() -> list:
    """A finished Claude turn on a session no other conversation holds."""
    result = {"type": "result", "subtype": "success", "is_error": False}
    return [json.dumps({**result, "session_id": f"chat-sess-{next(_SESSIONS)}"}) + "\n"]


def _codex_done() -> list:
    return [
        json.dumps({"type": "thread.started", "thread_id": f"thread-{next(_SESSIONS)}"}) + "\n",
        '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}\n',
    ]


async def _profile(app, auth_headers, bind_runner) -> dict:
    """A profile whose pool holds Claude Haiku (default) and Claude Sonnet, plus a runner on Opus
    the pool does not hold."""
    sync = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {"chatty": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    haiku = await bind_runner("chatty", cli="claude", model="haiku")
    sonnet = await add_pool_entry(app, auth_headers, "chatty", cli="claude", model="sonnet")
    opus = await app.post(
        f"{BASE}/runners",
        json={"name": "outside-opus", "cli": "claude", "model": "opus"},
        headers=auth_headers,
    )
    assert opus.status_code == 201, opus.text
    return {"haiku": haiku, "sonnet": sonnet, "opus": opus.json()["id"]}


async def _send(app, auth_headers, *, overrides=None, conversation_id=None, lines=None):
    body: dict = {"agent": "chatty", "message": "hi"}
    if conversation_id:
        body["conversation_id"] = conversation_id
    else:
        body["session_mode"] = "new"
    if overrides is not None:
        body["overrides"] = overrides
    spawn = _fake_pty(list(lines) if lines is not None else _claude_done())
    with (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn),
        patch("hub.api.v1.agent_trigger.PipeSession.spawn", spawn),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/cli"),
    ):
        response = await app.post(f"{BASE}/agent/trigger", json=body, headers=auth_headers)
        if response.status_code == 200:
            await _await_background_run()
    return response, spawn


def _model_flag(spawn) -> str:
    command = spawn.call_args.args[0]
    return command[command.index("--model") + 1]


async def test_a_chat_may_choose_a_runner_the_pool_does_not_hold_but_not_another_projects(
    app, auth_headers, bind_runner
):
    """Reversed by `a-profile-s-pool-and-a-new-chat-can-use-any-model-of-any-provider` (FR-10): a
    pool of Haiku and Sonnet no longer bounds a chat, so Opus, by its runner or by its model, and an
    effort no entry carries all run. A runner id this project does not have is refused naming it."""
    runners = await _profile(app, auth_headers, bind_runner)

    by_runner, spawn = await _send(app, auth_headers, overrides={"runner_id": runners["opus"]})
    assert by_runner.status_code == 200, by_runner.text
    assert _model_flag(spawn) == "opus"

    by_model, spawn = await _send(app, auth_headers, overrides={"model": "opus"})
    assert by_model.status_code == 200, by_model.text
    assert _model_flag(spawn) == "opus"

    effort, spawn = await _send(app, auth_headers, overrides={"effort": "high"})
    assert effort.status_code == 200, effort.text

    unknown, spawn = await _send(app, auth_headers, overrides={"runner_id": "runner-nope"})
    assert unknown.status_code == 400, unknown.text
    assert "runner-nope" in unknown.json()["detail"]
    spawn.assert_not_called()


async def test_a_new_chat_starts_on_the_default_and_may_choose_another_entry(
    app, auth_headers, bind_runner
):
    runners = await _profile(app, auth_headers, bind_runner)

    plain, spawn = await _send(app, auth_headers)
    assert plain.status_code == 200, plain.text
    assert _model_flag(spawn) == "haiku"

    chosen, spawn = await _send(app, auth_headers, overrides={"runner_id": runners["sonnet"]})
    assert chosen.status_code == 200, chosen.text
    assert _model_flag(spawn) == "sonnet"
    async with async_session_factory() as db:
        conversation = (
            await db.execute(
                select(Conversation).where(Conversation.id == chosen.json()["conversation_id"])
            )
        ).scalar_one()
        run = (
            await db.execute(select(Run).where(Run.conversation_id == conversation.id))
        ).scalar_one()
    # The choice is stored by the entry's runner, and the run launched on that runner.
    assert conversation.runtime_overrides == {"runner_id": runners["sonnet"]}
    assert run.runner_id == runners["sonnet"]

    # The composer sends the stored choice back with the next message: the same entry again.
    again, spawn = await _send(
        app,
        auth_headers,
        overrides={"runner_id": runners["sonnet"]},
        conversation_id=conversation.id,
    )
    assert again.status_code == 200, again.text
    assert _model_flag(spawn) == "sonnet"

    # By model, as the composer named it before pools: the entry on a runner of that model.
    by_model, spawn = await _send(app, auth_headers, overrides={"model": "sonnet"})
    assert by_model.status_code == 200, by_model.text
    assert _model_flag(spawn) == "sonnet"


async def test_a_started_chat_may_not_move_to_another_cli_and_a_new_chat_may(
    app, auth_headers, bind_runner
):
    runners = await _profile(app, auth_headers, bind_runner)
    codex = await add_pool_entry(
        app, auth_headers, "chatty", cli="codex", flags=["--no-app-server"]
    )
    started, _ = await _send(app, auth_headers)
    assert started.status_code == 200, started.text
    conversation_id = started.json()["conversation_id"]

    moved, spawn = await _send(
        app, auth_headers, overrides={"runner_id": codex}, conversation_id=conversation_id
    )
    assert moved.status_code == 400, moved.text
    detail = moved.json()["detail"]
    assert "Claude Code" in detail and "Codex" in detail and "new chat" in detail
    spawn.assert_not_called()

    # Within the CLI it started on, a started chat may switch entries.
    within, spawn = await _send(
        app,
        auth_headers,
        overrides={"runner_id": runners["sonnet"]},
        conversation_id=conversation_id,
    )
    assert within.status_code == 200, within.text
    assert _model_flag(spawn) == "sonnet"

    fresh, spawn = await _send(
        app, auth_headers, overrides={"runner_id": codex}, lines=_codex_done()
    )
    assert fresh.status_code == 200, fresh.text
    assert "codex" in spawn.call_args.args[0][0]
    async with async_session_factory() as db:
        run = (
            await db.execute(
                select(Run).where(Run.conversation_id == fresh.json()["conversation_id"])
            )
        ).scalar_one()
    assert run.runner_id == codex


async def test_the_conversation_list_says_which_cli_a_chat_started_on(
    app, auth_headers, bind_runner
):
    """The composer greys out other CLIs' entries from this field: null before a run recorded a
    runner, then the CLI of the conversation's latest run."""
    await _profile(app, auth_headers, bind_runner)
    codex = await add_pool_entry(
        app, auth_headers, "chatty", cli="codex", flags=["--no-app-server"]
    )
    on_claude, _ = await _send(app, auth_headers)
    on_codex, _ = await _send(
        app, auth_headers, overrides={"runner_id": codex}, lines=_codex_done()
    )
    assert on_claude.status_code == 200 and on_codex.status_code == 200

    listed = await app.get(f"{BASE}/agent/chatty/conversations", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    started = {c["id"]: c["started_cli"] for c in listed.json()}
    assert started[on_claude.json()["conversation_id"]] == "claude"
    assert started[on_codex.json()["conversation_id"]] == "codex"
