"""Per-conversation runtime overrides on POST /agent/trigger
(2026-08-04-hub-model-control-and-provisioning)."""

import asyncio
import json
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.sse import sse_manager
from tests import conftest
from tests.test_agent_trigger import (
    _await_background_run,
    _bind_codex_exec_runner,
    _fake_pty,
)


@pytest.mark.asyncio
async def test_an_invalid_override_refuses_the_turn_and_starts_no_process(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"override-invalid": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("override-invalid", cli="claude")

    fake_spawn = _fake_pty([])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={
                "agent": "override-invalid",
                "message": "hi",
                "session_mode": "new",
                "overrides": {"effort": "not-a-real-value"},
            },
            headers=auth_headers,
        )
    assert response.status_code == 400
    assert "not-a-real-value" in response.json()["detail"]
    fake_spawn.assert_not_called()


@pytest.mark.asyncio
async def test_an_effort_value_valid_for_the_other_provider_is_refused(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"override-cross": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("override-cross", cli="codex")

    fake_spawn = _fake_pty([])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={
                "agent": "override-cross",
                "message": "hi",
                "session_mode": "new",
                # "max" is a valid Claude effort value but not one Codex's catalog declares.
                "overrides": {"effort": "max"},
            },
            headers=auth_headers,
        )
    assert response.status_code == 400
    fake_spawn.assert_not_called()


@pytest.mark.asyncio
async def test_a_valid_override_is_applied_to_the_spawned_command(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"override-valid": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("override-valid", cli="claude", model="claude-sonnet-5")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={
                    "agent": "override-valid",
                    "message": "hi",
                    "session_mode": "new",
                    "overrides": {"model": "claude-opus-5", "effort": "high"},
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            await _await_background_run()

    command = fake_spawn.call_args.args[0]
    assert command[command.index("--model") + 1] == "claude-opus-5"
    assert command[command.index("--effort") + 1] == "high"


@pytest.mark.asyncio
async def test_an_override_persists_on_the_conversation_and_survives_reload(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"override-persist": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("override-persist", cli="claude")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={
                    "agent": "override-persist",
                    "message": "hi",
                    "session_mode": "new",
                    "overrides": {"effort": "high"},
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            await _await_background_run()

    conversations = await app.get(
        "/api/v1/projects/proj-test/agent/override-persist/conversations", headers=auth_headers
    )
    assert conversations.status_code == 200
    body = conversations.json()
    assert len(body) == 1
    assert body[0]["runtime_overrides"] == {"effort": "high"}


@pytest.mark.asyncio
async def test_a_new_conversation_does_not_inherit_a_previous_conversations_overrides(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"override-fresh": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("override-fresh", cli="claude")

    # Two separate PtySession.spawn mocks — each returns its own session object, so the
    # second call's read loop doesn't hit the first call's already-exhausted side_effect
    # iterator (a shared fake session across two real spawns hangs the second one).
    first_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", first_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            first = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={
                    "agent": "override-fresh",
                    "message": "hi",
                    "session_mode": "new",
                    "overrides": {"effort": "high"},
                },
                headers=auth_headers,
            )
            assert first.status_code == 200
            await _await_background_run()

    second_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s2"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", second_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            second = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "override-fresh", "message": "hi again", "session_mode": "new"},
                headers=auth_headers,
            )
            assert second.status_code == 200
            await _await_background_run()

    conversations = await app.get(
        "/api/v1/projects/proj-test/agent/override-fresh/conversations", headers=auth_headers
    )
    body = conversations.json()
    assert len(body) == 2
    overrides_by_id = {c["id"]: c["runtime_overrides"] for c in body}
    assert overrides_by_id[first.json()["conversation_id"]] == {"effort": "high"}
    assert overrides_by_id[second.json()["conversation_id"]] in (None, {})


async def _await_agent_idle(project_id, agent, timeout=10.0):
    """Wait until no run for *agent* is still `running`.

    `_await_background_run()` awaits the asyncio task, which is **not** the same thing as the `Run`
    row having reached a terminal status — the commit can trail the task on a busy machine.

    That difference is not cosmetic. `turn_scheduler.schedule_agent` refuses to start a turn while
    a run for the agent is still `running` (`turn_scheduler.py:37-43`), and `trigger_agent` then
    returns **200 with `status="queued"`** — the input is accepted, the turn never happens, and
    nothing is broadcast for it. A test that only checks the status code cannot tell that apart
    from a turn that ran, which is exactly how this cost four attempts to find.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        async with async_session_factory() as db:
            running = await db.execute(
                select(Run).where(
                    Run.project_id == project_id, Run.agent == agent, Run.status == "running"
                )
            )
            if running.scalars().first() is None:
                return
        await asyncio.sleep(0.05)
    # Diagnostic-only, added after three fix attempts each addressed a plausible but wrong
    # mechanism (see 2026-08-17-one-version-one-product-log.md, iteration 19): rather than guess
    # a fourth time, dump exactly what state the timeout found, so the next CI run answers
    # instead of another hypothesis. `_execute_run`'s own `finally` pops `_active_ptys[run_id]` —
    # if the run_id below is STILL in `_active_ptys`, `_execute_run` genuinely has not reached its
    # own end despite `_await_background_run()` having returned, which would mean the task this
    # test awaited was not the one it thinks it was.
    import hub.api.v1.agent_trigger as agent_trigger_module

    async with async_session_factory() as db:
        all_runs = await db.execute(
            select(Run).where(Run.project_id == project_id, Run.agent == agent)
        )
        rows = [
            # `pid` is set in the FIRST db block after the spawn succeeds, well before the finalize
            # block. A non-null pid therefore proves the row was visible to an *earlier* session in
            # this same task — so if the finalize session still cannot see it, the fault is
            # somewhere between the two, not "the row never existed for this task" (D6, option 1).
            f"run={r.id} status={r.status!r} error={r.error!r} exit_code={r.exit_code!r} "
            f"ended_at={r.ended_at!r} pid={r.pid!r}"
            for r in all_runs.scalars().all()
        ]
    # The breadcrumb trail `_execute_run` leaves per run_id. The previous dump established what
    # the end state was; it could not say which path produced it. A trail ending at `finally` with
    # no `finalize_committed` means the finalize never ran; one ending at `ROW_MISSING` means it
    # ran and could not see its own row; `finalize_committed run_seen=True` with the row still
    # `running` would mean the commit itself did not persist, which is a different problem again.
    traces = {
        run_id: steps
        for run_id, steps in agent_trigger_module._run_trace.items()
        if any(run_id == r.split()[0].removeprefix("run=") for r in rows)
    } or dict(agent_trigger_module._run_trace)

    raise AssertionError(
        f"{agent} still had a running run after {timeout}s\n"
        f"  Run rows for this project/agent: {rows}\n"
        f"  _background_runs (should be empty if _await_background_run already ran): "
        f"{len(agent_trigger_module._background_runs)} pending\n"
        f"  _active_ptys keys: {list(agent_trigger_module._active_ptys.keys())}\n"
        f"  _run_trace: {traces}\n"
        # Every COMMIT/ROLLBACK on the one shared connection, newest last. The finalize's own
        # COMMIT should appear; a ROLLBACK from another session sitting between the finalize's
        # flush and that COMMIT is the mechanism, and these frames name which session it was.
        f"  connection_events (oldest first):\n    " + "\n    ".join(conftest.connection_events)
    )


@pytest.mark.asyncio
async def test_a_conversation_whose_model_changed_attributes_usage_per_turn(
    app, auth_headers, bind_runner
):
    """agent-context-usage: 'Usage SHALL be attributed to the model that ran each turn.'"""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"model-switch": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    # Exercised through the `exec` transport (its spawn is what this test mocks), which codex
    # now reaches only by explicit opt-out.
    await _bind_codex_exec_runner(app, auth_headers)("model-switch")

    status = await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)
    project_id = status.json()["project_id"]
    queue = sse_manager.subscribe(project_id)

    async def await_model(timeout=5.0):
        """Wait for the next `context_warning` model, rather than assuming one has arrived.

        Two reasons this waits instead of draining once.

        The delivery is asynchronous and awaiting the run task does not guarantee it has landed,
        so an immediate drain is a race — and it is a race CI lost roughly half the time while
        this machine won it every time. A bounded wait removes the race without hiding anything:
        if a reading genuinely never arrives, this still fails, just with an accurate complaint.

        And it drains per turn, which matters independently: `sse_manager.subscribe` hands out an
        `asyncio.Queue(maxsize=256)` and `broadcast` does `put_nowait` inside
        `except asyncio.QueueFull: pass` — dropping rather than blocking a slow consumer. Letting
        two turns of streamed output pile up in one queue puts the tail at risk by design.
        """
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            while not queue.empty():
                event = queue.get_nowait()
                if event.event == "context_warning":
                    return json.loads(event.data)["model"]
            await asyncio.sleep(0.05)
        raise AssertionError("no context_warning was broadcast within the timeout")

    try:
        first_spawn = _fake_pty(
            [
                '{"type":"thread.started","thread_id":"thread-1"}\n',
                '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}\n',
            ]
        )
        with patch("hub.api.v1.agent_trigger.PipeSession.spawn", first_spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
                first = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={
                        "agent": "model-switch",
                        "message": "hi",
                        "session_mode": "new",
                        "overrides": {"model": "gpt-5.6-sol"},
                    },
                    headers=auth_headers,
                )
                assert first.status_code == 200
                # A trigger returns 200 with status="queued" when the agent is busy, and then no
                # run happens and nothing is broadcast. The test only ever checked the status code,
                # so a queued turn looked identical to a completed one until the assertion at the
                # end failed for a reason it could not name.
                assert first.json()["status"] != "queued", first.json()
                await _await_background_run()

        models_seen = [await await_model()]
        await _await_agent_idle(project_id, "model-switch")

        conversation_id = first.json()["conversation_id"]
        second_spawn = _fake_pty(
            [
                '{"type":"thread.started","thread_id":"thread-1"}\n',
                '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}\n',
            ]
        )
        with patch("hub.api.v1.agent_trigger.PipeSession.spawn", second_spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
                second = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={
                        "agent": "model-switch",
                        "message": "hi again",
                        "conversation_id": conversation_id,
                        "overrides": {"model": "gpt-5.4-mini"},
                    },
                    headers=auth_headers,
                )
                assert second.status_code == 200
                assert second.json()["status"] != "queued", second.json()
                await _await_background_run()

        models_seen.append(await await_model())
        assert models_seen == ["gpt-5.6-sol", "gpt-5.4-mini"]
    finally:
        sse_manager.unsubscribe(project_id, queue)
