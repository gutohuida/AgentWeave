"""A chat picks any catalog model; only its CLI is fixed (`a-profile-s-pool-and-a-new-chat-can-use-
any-model-of-any-provider`, task chat-any-model): FR-6, FR-7, FR-10, FR-11.

Builder's pool holds only Haiku 5.5. A chat names a model the way the composer does -- `provider`,
`model`, `effort` -- through `POST /agent/trigger`, with the CLIs replaced by the stubs
`test_launch_entry` uses, so what is asserted is the argv the CLI was handed, the `Run` row and the
profile's pool as the agents API returns it before and after.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Conversation, Runner
from hub.model_catalog import get_provider

from .test_launch_entry import (
    PROJECT,
    _copilot_installed,  # noqa: F401 -- autouse fixture
    _Drive,
    _flag,
    _run,
)

pytestmark = pytest.mark.asyncio

HAIKU = "claude-haiku-5-5"
HAIKU_4 = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5-5"


@pytest.fixture
def drive(app, auth_headers):
    return _Drive(app, auth_headers)


async def _builder(drive: _Drive) -> str:
    haiku = await drive.runner("Claude Haiku", HAIKU)
    await drive.agent("builder", [{"runner_id": haiku, "default": True}])
    return haiku


async def _pool(drive: _Drive) -> List[Dict[str, Any]]:
    listed = await drive.app.get(f"{PROJECT}/agents", headers=drive.headers)
    assert listed.status_code == 200, listed.text
    return next(a for a in listed.json() if a["name"] == "builder")["pool"]


async def _runner_ids() -> List[str]:
    async with async_session_factory() as db:
        return list((await db.execute(select(Runner.id))).scalars().all())


async def _refused(drive: _Drive, **body: Any):
    with drive._stubs():
        response = await drive.app.post(
            f"{PROJECT}/agent/trigger",
            json={"agent": "builder", "message": "go", **body},
            headers=drive.headers,
        )
    assert 400 <= response.status_code < 500, response.text
    return response.json()["detail"]


def _codex_model() -> str:
    codex = get_provider("codex")
    assert codex is not None and codex.models
    return codex.models[0].id


async def test_chat_off_pool_runs_that_model_and_leaves_the_pool_alone(drive):
    """Criterion ac-chat-off-pool: Haiku 4.5, outside a pool of Haiku 5.5, runs on Haiku 4.5."""
    await _builder(drive)
    before = await _pool(drive)

    started = await drive.send(
        "builder", session_mode="new", overrides={"provider": "claude", "model": HAIKU_4}
    )

    assert _flag(drive.claude.argvs[-1], "--model") == HAIKU_4
    run = await _run(started["run_id"])
    assert run.model == HAIKU_4
    assert await _pool(drive) == before
    async with async_session_factory() as db:
        conversation = (
            await db.execute(
                select(Conversation).where(Conversation.id == started["conversation_id"])
            )
        ).scalar_one()
        runner = await db.get(Runner, run.runner_id)
    # Stored by the runner it launched on; the provider is never stored.
    assert conversation.runtime_overrides == {"runner_id": run.runner_id}
    assert (runner.cli, runner.model) == ("claude", HAIKU_4)

    # A second chat on the same model reuses that runner rather than making another.
    count = len(await _runner_ids())
    again = await drive.send(
        "builder", session_mode="new", overrides={"provider": "claude", "model": HAIKU_4}
    )
    assert (await _run(again["run_id"])).runner_id == run.runner_id
    assert len(await _runner_ids()) == count


async def test_a_model_the_catalog_does_not_hold_is_refused_naming_it(drive):
    await _builder(drive)
    before = await _pool(drive)
    runners = await _runner_ids()

    detail = await _refused(
        drive, session_mode="new", overrides={"provider": "claude", "model": "not-a-model"}
    )

    assert "not-a-model" in detail
    assert drive.claude.argvs == []
    assert await _pool(drive) == before
    assert await _runner_ids() == runners


async def test_a_new_chat_may_start_on_another_provider(drive):
    """Criterion ac-chat-other-provider: a Codex catalog model for a profile whose pool is Claude's
    is not refused for being outside the pool, and the turn launches on Codex."""
    await _builder(drive)
    before = await _pool(drive)
    model = _codex_model()

    started = await drive.send(
        "builder", session_mode="new", overrides={"provider": "codex", "model": model}
    )

    run = await _run(started["run_id"])
    assert run.model == model
    async with async_session_factory() as db:
        assert (await db.get(Runner, run.runner_id)).cli == "codex"
    assert await _pool(drive) == before


async def test_a_started_chat_switches_model_within_its_cli_and_never_to_another(drive):
    """Criteria ac-switch-same-cli and ac-other-cli-refused."""
    await _builder(drive)
    before = await _pool(drive)
    first = await drive.send(
        "builder", session_mode="new", overrides={"provider": "claude", "model": HAIKU_4}
    )
    conversation_id = first["conversation_id"]

    second = await drive.send(
        "builder",
        conversation_id=conversation_id,
        overrides={"provider": "claude", "model": SONNET},
    )
    assert _flag(drive.claude.argvs[-1], "--model") == SONNET
    assert (await _run(second["run_id"])).model == SONNET
    assert await _pool(drive) == before

    for overrides in ({"provider": "codex", "model": _codex_model()}, {"model": _codex_model()}):
        detail = await _refused(drive, conversation_id=conversation_id, overrides=overrides)
        assert "runs on Claude Code" in detail and "new chat" in detail, detail
    assert len(drive.claude.argvs) == 2


async def test_effort_changes_after_the_first_turn(drive):
    """Criterion ac-effort-changes: a turn at the usual effort, then High, outside any entry."""
    await _builder(drive)
    first = await drive.send(
        "builder", session_mode="new", overrides={"provider": "claude", "model": HAIKU_4}
    )
    assert _flag(drive.claude.argvs[-1], "--effort") is None
    stored = dict(
        (await drive.app.get(f"{PROJECT}/runs/{first['run_id']}", headers=drive.headers)).json()
    )
    assert stored["effort"] is None

    second = await drive.send(
        "builder",
        conversation_id=first["conversation_id"],
        overrides={"provider": "claude", "model": HAIKU_4, "effort": "high"},
    )

    assert _flag(drive.claude.argvs[-1], "--effort") == "high"
    assert _flag(drive.claude.argvs[-1], "--model") == HAIKU_4
    body = (await drive.app.get(f"{PROJECT}/runs/{second['run_id']}", headers=drive.headers)).json()
    assert body["effort"] == "high"
    # The same runner as the first turn: the effort never moves the chat.
    assert body["runner_id"] == (await _run(first["run_id"])).runner_id


async def test_a_chat_pick_outside_the_pool_never_reaches_a_task_run(drive):
    """Criterion ac-no-leak: Builder chats on Haiku 4.5, outside its pool; its task's builder run,
    even in that same conversation, launches on the pool default."""
    haiku = await _builder(drive)
    chat = await drive.send(
        "builder", session_mode="new", overrides={"provider": "claude", "model": HAIKU_4}
    )
    await drive.task("t-leak")

    fresh = await drive.send("builder", task_id="t-leak")
    same = await drive.send("builder", task_id="t-leak", conversation_id=chat["conversation_id"])

    for started in (fresh, same):
        run = await _run(started["run_id"])
        assert (run.runner_id, run.model) == (haiku, HAIKU)
    assert [_flag(a, "--model") for a in drive.claude.argvs] == [HAIKU_4, HAIKU, HAIKU]
