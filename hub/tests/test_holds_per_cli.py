"""A provider hold is the profile's on one CLI (`a-profile-runs-each-task-on-a-runner-and-model-
chosen-from-its-pool`, FR-11, task chats-and-holds).

Before this change a hold was keyed by agent alone (`provider_allowance`), so a Claude usage limit
also stopped that profile's Codex runs. Now every read is keyed by the agent and the CLI a reading
was written for (`TurnUsage.runner`): the flow offers, and the turn scheduler starts, a task whose
chosen entry is on another CLI, while the held CLI's task waits for the reset.

The acceptance check (criterion hold-is-per-cli) is driven through a real build over an approved
document with two tasks for one builder whose pool holds a Claude and a Codex entry, fired by the
scheduler with spawns that hang until released (the harness of `test_flow_offers_in_parallel`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pytest
from sqlalchemy import select

from hub import provider_allowance
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Run, Runner, Task, TurnUsage
from hub.provider_allowance import agent_holds, provider_hold
from hub.utils import short_id

from ._pool import add_pool_entry
from .test_a_held_agent_is_busy import _queue, _reading
from .test_a_lead_hands_out_the_work import _approved, _build, _tasks
from .test_agent_trigger import _await_background_run
from .test_flow_offers_in_parallel import _dev_entries, _fire
from .test_start_gate import _repo_project, _set_project, _Spawns

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"


async def _reading_row(
    agent: str,
    runner: Optional[str],
    *,
    refused: bool = True,
    resets_in: timedelta = timedelta(hours=1),
) -> None:
    """A recorded outcome on *runner*'s CLI: a refusal until *resets_in*, or a served turn."""
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        run_id = f"run-{short_id()}"
        db.add(Run(id=run_id, project_id=PROJECT, agent=agent, status="failed"))
        await db.flush()
        db.add(
            TurnUsage(
                id=f"usage-{short_id()}",
                run_id=run_id,
                project_id=PROJECT,
                agent=agent,
                runner=runner,
                status="unavailable" if refused else "measured",
                total_tokens=None if refused else 10,
                allowance=_reading(now + resets_in) if refused else None,
                observed_at=now - timedelta(minutes=1),
            )
        )
        await db.commit()


# ---------------------------------------------------------------------------
# The reads: keyed by agent and CLI
# ---------------------------------------------------------------------------


async def test_a_refusal_on_one_cli_holds_that_cli_only(app, auth_headers, bind_runner):
    """A Claude refusal holds Claude; Codex is not held, and a Codex served turn after it does not
    release Claude (before, the newest row of any CLI decided both)."""
    from hub.provider_allowance import agent_cli_holds, hold_on, last_refusals  # noqa: F401

    sync = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {"mixed": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("mixed", cli="claude")
    await _reading_row("mixed", "claude")
    await _reading_row("mixed", "codex", refused=False)

    async with async_session_factory() as db:
        assert await provider_hold(db, PROJECT, "mixed", cli="claude") is not None
        assert await provider_hold(db, PROJECT, "mixed", cli="codex") is None
        # No CLI named: the default entry's, Claude here.
        assert await provider_hold(db, PROJECT, "mixed") is not None
        readings = (await agent_cli_holds(db, PROJECT))["mixed"]
        assert hold_on(readings, "claude") is not None
        assert hold_on(readings, "codex") is None
        assert set(await last_refusals(db, PROJECT, "mixed")) == {"claude"}
        assert "mixed" in await agent_holds(db, PROJECT)


async def test_an_agent_held_only_on_another_cli_than_its_default_reads_free(
    app, auth_headers, bind_runner
):
    """A job firing or a chat starts on the default entry, so a hold on another CLI is not one
    they meet."""
    from hub.provider_allowance import agent_cli_holds, hold_on, last_refusals  # noqa: F401

    sync = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {"elsewhere": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("elsewhere", cli="claude")
    await _reading_row("elsewhere", "codex")

    async with async_session_factory() as db:
        assert await provider_hold(db, PROJECT, "elsewhere") is None
        assert "elsewhere" not in await agent_holds(db, PROJECT)
        assert hold_on((await agent_cli_holds(db, PROJECT))["elsewhere"], "codex") is not None


async def test_a_row_naming_no_cli_speaks_only_for_a_cli_with_no_reading_of_its_own(
    app, auth_headers, bind_runner
):
    from hub.provider_allowance import agent_cli_holds, hold_on, last_refusals  # noqa: F401

    sync = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {"legacy": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("legacy", cli="claude")
    await _reading_row("legacy", None)
    await _reading_row("legacy", "claude", refused=False)

    async with async_session_factory() as db:
        readings = (await agent_cli_holds(db, PROJECT))["legacy"]
        # Claude's own served turn is newer than the unnamed refusal: Claude is free.
        assert hold_on(readings, "claude") is None
        # Codex has no reading of its own, so the unnamed refusal is the word on it.
        assert hold_on(readings, "codex") is not None
        assert await provider_hold(db, PROJECT, "legacy", cli="claude") is None
        assert await provider_hold(db, PROJECT, "legacy", cli="codex") is not None


# ---------------------------------------------------------------------------
# hold-is-per-cli: the flow drive
# ---------------------------------------------------------------------------


async def _runs(agent: str, status: str = "running") -> List[Run]:
    async with async_session_factory() as db:
        return list(
            (await db.execute(select(Run).where(Run.agent == agent, Run.status == status)))
            .scalars()
            .all()
        )


def _patched_both(spawns: _Spawns):
    from unittest.mock import patch

    return (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", spawns),
        patch("hub.api.v1.agent_trigger.PipeSession.spawn", spawns),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/cli"),
    )


async def test_hold_is_per_cli_the_codex_task_starts_and_the_claude_task_waits(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Criterion hold-is-per-cli: a profile with a Claude entry and a Codex entry and a provider
    hold recorded on Claude; a flow fires with one task chosen on Claude and one on Codex. The
    Codex task starts, the Claude task waits, and it starts once the hold ends.

    Fails before the change at the first assertion: the hold was the agent's, so neither started.
    """
    await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, "dev", "qa"
    )
    await _approved(app, auth_headers)
    async with async_session_factory() as db:
        claude_runner = (
            await db.execute(select(Runner).where(Runner.name == "dev-runner"))
        ).scalar_one()
    codex_runner = await add_pool_entry(
        app, auth_headers, "dev", cli="codex", flags=["--no-app-server"]
    )
    await _set_project(profiles_run_in_parallel=True)
    await _build(
        app,
        auth_headers,
        driver="flow",
        builders=["dev"],
        level="reviewed",
        task_builder_entries={
            "t1": {"runner_id": claude_runner.id, "effort": None},
            "t2": {"runner_id": codex_runner, "effort": None},
        },
    )
    tasks = await _tasks()
    await _reading_row("dev", "claude", resets_in=timedelta(minutes=30))

    spawns = _Spawns()
    pty, pipe, which = _patched_both(spawns)
    with pty, pipe, which:
        try:
            await _fire()
            await spawns.wait_for(1)
            running = await _runs("dev")
            assert [(run.task_id, run.runner_id) for run in running] == [
                (tasks["t2"].id, codex_runner)
            ]
            # The Claude task was not briefed: it waits for the hold, offered to nobody else.
            assert [entry.task_id for entry in await _dev_entries()] == [tasks["t2"].id]

            # The hold ends at its reset; the next firing starts the Claude task on Claude.
            later = datetime.now(timezone.utc) + timedelta(hours=1)
            monkeypatch.setattr(provider_allowance, "_utcnow", lambda: later)
            await _fire()
            await spawns.wait_for(2)
            running = await _runs("dev")
            assert sorted((run.task_id, run.runner_id) for run in running) == sorted(
                [(tasks["t1"].id, claude_runner.id), (tasks["t2"].id, codex_runner)]
            )
        finally:
            spawns.release_all()
            await _await_background_run()


async def test_a_held_clis_queued_turn_waits_while_another_clis_turn_behind_it_starts(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """The turn scheduler's half of FR-11: input queued for both tasks, the Claude task's first,
    and a hold on Claude. The Codex turn behind the held head starts; the Claude input stays
    queued, uncounted. Before the change the pass returned at the agent's hold and started none."""
    await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, "dev", "qa"
    )
    await _approved(app, auth_headers)
    async with async_session_factory() as db:
        claude_runner = (
            await db.execute(select(Runner).where(Runner.name == "dev-runner"))
        ).scalar_one()
    codex_runner = await add_pool_entry(
        app, auth_headers, "dev", cli="codex", flags=["--no-app-server"]
    )
    await _set_project(profiles_run_in_parallel=True)
    await _build(
        app,
        auth_headers,
        driver="flow",
        builders=["dev"],
        level="reviewed",
        task_builder_entries={
            "t1": {"runner_id": claude_runner.id, "effort": None},
            "t2": {"runner_id": codex_runner, "effort": None},
        },
    )
    tasks = await _tasks()
    async with async_session_factory() as db:
        for key in ("t1", "t2"):
            task = await db.get(Task, tasks[key].id)
            task.assignee, task.status = "dev", "assigned"
        await db.commit()
    await _reading_row("dev", "claude", resets_in=timedelta(minutes=30))
    await _queue("dev", "conv-claude-task", task_id=tasks["t1"].id)
    await _queue("dev", "conv-codex-task", task_id=tasks["t2"].id)

    from hub.inbound_queue import queued_entries
    from hub.turn_scheduler import provider_held_conversations, schedule_agent

    async with async_session_factory() as db:
        held = await provider_held_conversations(
            db, PROJECT, "dev", await queued_entries(db, PROJECT, "dev")
        )
    assert list(held) == ["conv-claude-task"]

    spawns = _Spawns()
    pty, pipe, which = _patched_both(spawns)
    with pty, pipe, which:
        try:
            result = await schedule_agent(PROJECT, "dev")
            await spawns.wait_for(1)
            assert result.response is not None, result.waiting_reason
            assert [(run.task_id, run.runner_id) for run in await _runs("dev")] == [
                (tasks["t2"].id, codex_runner)
            ]
            async with async_session_factory() as db:
                (waiting,) = (
                    (
                        await db.execute(
                            select(InboundQueueEntry).where(
                                InboundQueueEntry.conversation_id == "conv-claude-task"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert waiting.state == "queued"
                # Not counted: it waits for the reset, it did not fail.
                assert waiting.delivery_attempts == 0
        finally:
            spawns.release_all()
            await _await_background_run()
