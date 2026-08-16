"""A run that fails after the turn began hands its input back.

`test_delivery_attempts.py` covers `return_run_entries` itself — the counting, the session reset at
`RESUME_RETRY_LIMIT`, the abandonment at `DELIVERY_ATTEMPT_LIMIT`. All of that was correct and none
of it was reachable on the path failures actually take.

Loop 8 killed a Codex app-server mid-turn twice (`run-332ef259`, `run-68eca96d`). Each time the run
was marked `failed`, the agent returned to `idle`, and the queue entry stayed `state='delivered'`
with `delivery_attempts = 0` — never retried, never abandoned, nobody told. The cause: the two calls
to `return_run_entries` were both in *pre-spawn* `except` blocks, and a runtime that dies once
`run_turn` is under way comes back as a failed `TurnOutcome` through the **normal** completion path,
which had no notion of returning input at all. The limits were structurally unreachable on the death
mode most likely to occur, and the operator's message was consumed with no record it existed.

So these tests drive the endpoint and let the run fail on the normal path, which is the one the
finding was measured on. They also cover the second half of it: nothing drove the retry of a returned
entry, because both pre-spawn branches `return` before the `schedule_agent` the normal path runs at
its end, and no periodic drain exists.
"""

import json
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Run
from hub.inbound_queue import DELIVERY_ATTEMPT_LIMIT
from hub.sse import sse_manager


async def _await_background_run():
    while agent_trigger._background_runs:
        for task in list(agent_trigger._background_runs):
            await task


def _drain(queue):
    events = []
    while True:
        try:
            item = queue.get_nowait()
        except Exception:  # asyncio.QueueEmpty
            break
        events.append((item.event, json.loads(item.data)))
    return events


def _fresh_failing_pty(exit_code=1):
    """A `PtySession.spawn` replacement handing back a **new** session per call.

    `test_agent_trigger.py`'s `_fake_pty` reuses one MagicMock, whose `read.side_effect` list is
    exhausted by the second spawn. These tests deliberately provoke consecutive runs for the same
    agent, so each must get its own.
    """

    def _spawn(*args, **kwargs):
        session = MagicMock()
        session.pid = 4242
        session.read.side_effect = ['{"type":"result","is_error":true}\n', ""]
        session.wait.return_value = exit_code
        return session

    return MagicMock(side_effect=_spawn)


def _fake_run_turn(status="failed", thread_id="thread-returns-1"):
    from hub.codex_appserver import TurnOutcome

    async def _run(**kwargs):
        if kwargs.get("on_thread_started") is not None:
            await kwargs["on_thread_started"](thread_id)
        return TurnOutcome(thread_id=thread_id, status=status, error="app-server process ended")

    return AsyncMock(side_effect=_run)


async def _bind_app_server_codex(app, auth_headers, agent_name):
    created = await app.post(
        "/api/v1/projects/proj-test/runners",
        json={"name": f"{agent_name}-runner", "cli": "codex", "flags": ["--app-server"]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    bound = await app.patch(
        f"/api/v1/projects/proj-test/agents/{agent_name}",
        json={"runner_id": created.json()["id"]},
        headers=auth_headers,
    )
    assert bound.status_code == 200, bound.text


async def _register(app, auth_headers, agent_name, runner="claude"):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent_name: {"runner": runner}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200


async def _entries_for(agent_name):
    async with async_session_factory() as db:
        rows = await db.execute(
            select(InboundQueueEntry).where(InboundQueueEntry.agent == agent_name)
        )
        return list(rows.scalars().all())


async def _project_id(app, auth_headers):
    resp = await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)
    return resp.json()["project_id"]


def _schedule_after_the_first():
    """A `schedule_agent` spy that lets the **first** call through to the real thing.

    `POST /agent/trigger` starts its run by calling `schedule_agent` (`agent_trigger.py:819-821`)
    — the same function the completion path calls to drive a retry. Stubbing it outright means no
    run ever starts and the test passes without exercising anything, so the first call runs for
    real and every one after it is recorded and suppressed. `await_args_list[1:]` is therefore
    exactly the calls the failure paths made.
    """
    from hub.turn_scheduler import ScheduleResult
    from hub.turn_scheduler import schedule_agent as real

    seen = []

    async def _wrapped(project_id, agent):
        seen.append(agent)
        if len(seen) == 1:
            return await real(project_id, agent)
        return ScheduleResult(waiting_reason="suppressed for this test")

    return AsyncMock(side_effect=_wrapped)


def _requeued(events, agent):
    """The `queue_entry_queued` broadcasts a *failure* emitted.

    The trigger route emits one of its own when the input first arrives, carrying the entry's
    conversation and hop depth. A requeue carries only the entry, the agent and the run that was
    holding it, so the two are told apart by shape rather than by counting.
    """
    return [
        d
        for t, d in events
        if t == "queue_entry_queued" and d.get("agent") == agent and "hop_depth" not in d
    ]


@contextmanager
def _patched(*patchers):
    """Enter several patches as one context.

    `ruff` checks this repository at the CLI's 3.8 floor, where a parenthesized multi-item `with`
    is a syntax error, and nesting four `patch(...)` blocks buries the request under indentation.
    """
    with ExitStack() as stack:
        for patcher in patchers:
            stack.enter_context(patcher)
        yield


# ---------------------------------------------------------------------------
# The input comes back — both transports, on the normal completion path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_exec_run_returns_its_input_and_counts_the_attempt(
    app, auth_headers, bind_runner
):
    """Mutation guard for the exec path's `return_run_entries` call.

    `schedule_agent` is stubbed so exactly one attempt happens; the cascade is the subject of
    `test_three_failures_abandon_the_entry_with_a_reason` below.
    """
    await _register(app, auth_headers, "returns-exec")
    await bind_runner("returns-exec", cli="claude")

    with _patched(
        patch("hub.api.v1.agent_trigger.PtySession.spawn", _fresh_failing_pty()),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
        patch("hub.turn_scheduler.schedule_agent", _schedule_after_the_first()),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "returns-exec", "message": "do the thing", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        await _await_background_run()

    async with async_session_factory() as db:
        assert (await db.get(Run, run_id)).status == "failed"

    entries = await _entries_for("returns-exec")
    assert [(e.content, e.state, e.delivery_attempts) for e in entries] == [
        ("do the thing", "queued", 1)
    ]
    assert entries[0].delivered_in_run_id is None


@pytest.mark.asyncio
async def test_a_failed_app_server_run_returns_its_input_and_counts_the_attempt(app, auth_headers):
    """The path loop 8 actually measured: `run_turn` returns a failed outcome without raising,
    so the pre-spawn `except` never sees it."""
    await _register(app, auth_headers, "returns-appserver", runner="codex")
    await _bind_app_server_codex(app, auth_headers, "returns-appserver")

    with _patched(
        patch("hub.api.v1.agent_trigger.codex_run_turn", _fake_run_turn(status="failed")),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"),
        patch("hub.turn_scheduler.schedule_agent", _schedule_after_the_first()),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "returns-appserver", "message": "keep this", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        await _await_background_run()

    async with async_session_factory() as db:
        assert (await db.get(Run, run_id)).status == "failed"

    entries = await _entries_for("returns-appserver")
    assert [(e.content, e.state, e.delivery_attempts) for e in entries] == [
        ("keep this", "queued", 1)
    ]


@pytest.mark.asyncio
async def test_a_completed_run_does_not_return_its_input(app, auth_headers, bind_runner):
    await _register(app, auth_headers, "keeps-input")
    await bind_runner("keeps-input", cli="claude")

    session = MagicMock()
    session.pid = 4242
    session.read.side_effect = ['{"type":"result","is_error":false,"session_id":"s-1"}\n', ""]
    session.wait.return_value = 0

    with _patched(
        patch("hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=session)),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
        patch("hub.turn_scheduler.schedule_agent", _schedule_after_the_first()),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "keeps-input", "message": "consumed", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        await _await_background_run()

    entries = await _entries_for("keeps-input")
    assert [(e.state, e.delivery_attempts) for e in entries] == [("delivered", 0)]


@pytest.mark.asyncio
async def test_a_binding_conflict_does_not_return_its_input(app, auth_headers, bind_runner):
    """The one failure that must not requeue.

    A binding conflict is raised *after* the turn ran — the agent did the work and streamed its
    output — so the input was processed rather than lost, and re-delivering it makes the agent redo
    a completed turn. Requeueing it also defeats the check it comes from: at `RESUME_RETRY_LIMIT`
    the conversation gives up its provider session, so the third attempt binds the very session id
    the conflict refused. Caught by `test_conversation_contract.py` and `test_inbound_queue.py`
    independently before this test existed.
    """
    await _register(app, auth_headers, "conflicted")
    await bind_runner("conflicted", cli="claude")

    def _line(session_id):
        return (
            '{"type":"result","subtype":"success","is_error":false,'
            f'"session_id":"{session_id}"}}\n'
        )

    def _spawn_reporting(session_id):
        def _spawn(*args, **kwargs):
            session = MagicMock()
            session.pid = 4242
            session.read.side_effect = [_line(session_id), ""]
            session.wait.return_value = 0
            return session

        return MagicMock(side_effect=_spawn)

    with _patched(
        patch("hub.api.v1.agent_trigger.PtySession.spawn", _spawn_reporting("provider-1")),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
    ):
        first = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "conflicted", "message": "first", "session_mode": "new"},
            headers=auth_headers,
        )
        conversation_id = first.json()["conversation_id"]
        await _await_background_run()

    # The same conversation, a provider that now reports a different session id.
    with _patched(
        patch("hub.api.v1.agent_trigger.PtySession.spawn", _spawn_reporting("provider-2")),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
    ):
        second = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={
                "agent": "conflicted",
                "message": "second",
                "conversation_id": conversation_id,
            },
            headers=auth_headers,
        )
        run_id = second.json()["run_id"]
        await _await_background_run()

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "failed"
        assert "provider" in (run.error or "")
        # The binding the check exists to protect is untouched, and stays untouched — which it
        # would not be if the entry had been handed back and retried past `RESUME_RETRY_LIMIT`.
        conversation = await get_conversation_by_id(db, conversation_id)
        assert conversation.provider_session_id == "provider-1"

    entries = await _entries_for("conflicted")
    second_entry = [e for e in entries if e.content == "second"]
    assert [(e.state, e.delivery_attempts) for e in second_entry] == [("delivered", 0)]


@pytest.mark.asyncio
async def test_a_stopped_run_does_not_return_its_input(app, auth_headers):
    """A deliberate stop is `stopped`, not `failed`. The operator stopped the turn knowing what it
    was carrying, so requeueing it would restart work they just cancelled."""
    await _register(app, auth_headers, "stopped-keeps", runner="codex")
    await _bind_app_server_codex(app, auth_headers, "stopped-keeps")

    # A distinct thread id: a provider thread already bound to another conversation is a binding
    # conflict, which fails the run and would mask what this test is about.
    with _patched(
        patch(
            "hub.api.v1.agent_trigger.codex_run_turn",
            _fake_run_turn(status="interrupted", thread_id="thread-stopped-1"),
        ),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"),
        patch("hub.turn_scheduler.schedule_agent", _schedule_after_the_first()),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "stopped-keeps", "message": "cancelled", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        await _await_background_run()

    async with async_session_factory() as db:
        assert (await db.get(Run, run_id)).status == "stopped"

    entries = await _entries_for("stopped-keeps")
    assert [(e.state, e.delivery_attempts) for e in entries] == [("delivered", 0)]


# ---------------------------------------------------------------------------
# The retry is driven, and it stops
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_returned_entry_is_retried_without_anyone_asking(app, auth_headers, bind_runner):
    """Finding 2. `schedule_agent` is left real here, so the only thing that can start the second
    run is the failed run's own tail. Observed before this: an entry sat `queued` at one attempt
    until an unrelated `PUT /settings` happened to drain it."""
    await _register(app, auth_headers, "retried-alone")
    await bind_runner("retried-alone", cli="claude")

    spawn = _fresh_failing_pty()
    with _patched(
        patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "retried-alone", "message": "retry me", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        await _await_background_run()

    # One trigger, and the run kept failing — so every spawn after the first was driven by the
    # product rather than by a request.
    assert spawn.call_count == DELIVERY_ATTEMPT_LIMIT

    async with async_session_factory() as db:
        runs = await db.execute(
            select(Run).where(Run.agent == "retried-alone").order_by(Run.started_at)
        )
        assert [run.status for run in runs.scalars().all()] == ["failed"] * DELIVERY_ATTEMPT_LIMIT


@pytest.mark.asyncio
async def test_three_failures_abandon_the_entry_with_a_reason(app, auth_headers, bind_runner):
    project_id = await _project_id(app, auth_headers)
    await _register(app, auth_headers, "gives-up")
    await bind_runner("gives-up", cli="claude")
    queue = sse_manager.subscribe(project_id)

    with _patched(
        patch("hub.api.v1.agent_trigger.PtySession.spawn", _fresh_failing_pty()),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "gives-up", "message": "poisoned", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        await _await_background_run()

    entries = await _entries_for("gives-up")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.state == "withdrawn"
    assert entry.delivery_attempts == DELIVERY_ATTEMPT_LIMIT
    assert entry.abandoned_reason and "stopped retrying" in entry.abandoned_reason
    # The operator's breadcrumb from a dropped message to the run that ate it.
    assert entry.delivered_in_run_id is not None

    events = _drain(queue)
    abandoned = [d for t, d in events if t == "queue_entry_abandoned" and d["agent"] == "gives-up"]
    assert len(abandoned) == 1
    assert abandoned[0]["attempts"] == DELIVERY_ATTEMPT_LIMIT
    assert abandoned[0]["reason"] == entry.abandoned_reason
    # Two requeues then a give-up: the entry is announced back on the queue only while it is
    # still being retried.
    assert len(_requeued(events, "gives-up")) == DELIVERY_ATTEMPT_LIMIT - 1


@pytest.mark.asyncio
async def test_giving_up_lets_the_agent_accept_new_input(app, auth_headers, bind_runner):
    """The point of the cap. Once the Hub has given up, the agent is not wedged behind the entry
    that was killing it."""
    await _register(app, auth_headers, "unwedged")
    await bind_runner("unwedged", cli="claude")

    with _patched(
        patch("hub.api.v1.agent_trigger.PtySession.spawn", _fresh_failing_pty()),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
    ):
        first = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "unwedged", "message": "poisoned", "session_mode": "new"},
            headers=auth_headers,
        )
        assert first.status_code == 200
        await _await_background_run()

    session = MagicMock()
    session.pid = 4243
    session.read.side_effect = ['{"type":"result","is_error":false,"session_id":"s-ok"}\n', ""]
    session.wait.return_value = 0
    with _patched(
        patch("hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=session)),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
    ):
        second = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "unwedged", "message": "fine now", "session_mode": "new"},
            headers=auth_headers,
        )
        assert second.status_code == 200
        run_id = second.json()["run_id"]
        await _await_background_run()

    async with async_session_factory() as db:
        assert (await db.get(Run, run_id)).status == "completed"


# ---------------------------------------------------------------------------
# A pre-spawn failure schedules too
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pre_spawn_failure_schedules_the_agent(app, auth_headers, bind_runner):
    """Mutation guard for the exec pre-spawn branch's `schedule_agent`. That branch `return`s
    before the one at the end of the function, so without its own call the entry it just handed
    back waits for something unrelated to drain it."""
    await _register(app, auth_headers, "prespawn-exec")
    await bind_runner("prespawn-exec", cli="claude")

    scheduled = _schedule_after_the_first()
    with _patched(
        patch(
            "hub.api.v1.agent_trigger.PtySession.spawn",
            MagicMock(side_effect=FileNotFoundError("claude was not found in PATH")),
        ),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
        patch("hub.turn_scheduler.schedule_agent", scheduled),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "prespawn-exec", "message": "hi", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        await _await_background_run()

    # The first call is the route's own, which started the run. The second is the branch's, and
    # it is the whole point: without it the entry it just handed back waits for something
    # unrelated to drain it.
    assert [call.args[1] for call in scheduled.await_args_list[1:]] == ["prespawn-exec"]


@pytest.mark.asyncio
async def test_a_pre_spawn_app_server_failure_schedules_the_agent(app, auth_headers):
    from hub.codex_appserver import AppServerError

    await _register(app, auth_headers, "prespawn-appserver", runner="codex")
    await _bind_app_server_codex(app, auth_headers, "prespawn-appserver")

    scheduled = _schedule_after_the_first()
    with _patched(
        patch(
            "hub.api.v1.agent_trigger.codex_run_turn",
            AsyncMock(side_effect=AppServerError("app-server process ended", exit_code=-1)),
        ),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"),
        patch("hub.turn_scheduler.schedule_agent", scheduled),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "prespawn-appserver", "message": "hi", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        await _await_background_run()

    assert [call.args[1] for call in scheduled.await_args_list[1:]] == ["prespawn-appserver"]


# ---------------------------------------------------------------------------
# Divergence is not evaluated for a run whose work is being re-handed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_divergence_is_not_evaluated_when_the_input_went_back(app, auth_headers, bind_runner):
    """`run_reconciliation.py:53-60`'s rule, applied here for its reason: the work is about to be
    handed to a new run that will bind to the same task, so nothing has been dropped. Firing the
    check would tell the operator a task was abandoned moments before the retry picks it up."""
    await _register(app, auth_headers, "diverge-skip")
    await bind_runner("diverge-skip", cli="claude")

    evaluate = AsyncMock()
    with _patched(
        patch("hub.api.v1.agent_trigger.PtySession.spawn", _fresh_failing_pty()),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
        patch("hub.api.v1.agent_trigger.evaluate_run_end", evaluate),
        patch("hub.turn_scheduler.schedule_agent", _schedule_after_the_first()),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "diverge-skip", "message": "held", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        await _await_background_run()

    # Asserted first, so "the check did not fire" cannot be satisfied by a run that never
    # happened. The entry coming back at one attempt is what makes the skip meaningful.
    assert [(e.state, e.delivery_attempts) for e in await _entries_for("diverge-skip")] == [
        ("queued", 1)
    ]
    evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_divergence_is_still_evaluated_when_nothing_went_back(app, auth_headers, bind_runner):
    """The condition is on the returned set, not on `final_status`. A failed run that dropped its
    work — because the entry was abandoned on this very attempt — has genuinely left the task
    behind, and that is exactly what the divergence check exists to report."""
    await _register(app, auth_headers, "diverge-keep")
    await bind_runner("diverge-keep", cli="claude")

    evaluate = AsyncMock()
    with _patched(
        patch("hub.api.v1.agent_trigger.PtySession.spawn", _fresh_failing_pty()),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
        patch("hub.api.v1.agent_trigger.evaluate_run_end", evaluate),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "diverge-keep", "message": "dropped", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        await _await_background_run()

    # Three runs: the first two returned the entry and skipped the check, the third abandoned it
    # and so evaluated.
    assert evaluate.await_count == 1


# ---------------------------------------------------------------------------
# The re-delivered turn says the earlier attempt was cut off
# ---------------------------------------------------------------------------


def _entry(content, *, attempts=0, origin="operator", origin_agent=None):
    from hub.inbound_queue import new_entry

    entry = new_entry(
        project_id="proj-test",
        agent="prompt-note",
        origin_type=origin,
        origin_agent=origin_agent,
        content=content,
        hop_depth=0,
    )
    entry.delivery_attempts = attempts
    return entry


def test_a_first_delivery_says_nothing_about_earlier_attempts():
    from hub.inbound_queue import format_turn_prompt

    prompt = format_turn_prompt([_entry("fresh")])
    assert "Operator (hop 0):\nfresh" in prompt
    assert "attempt" not in prompt


def test_a_redelivered_entry_names_the_attempt():
    from hub.inbound_queue import format_turn_prompt

    prompt = format_turn_prompt([_entry("again", attempts=1)])
    # Attempt 1 failed, so this delivery is attempt 2 — the agent is told which one it is on,
    # not how many have failed.
    assert "delivery attempt 2" in prompt
    assert "cut off" in prompt
    assert "again" in prompt


def test_only_the_retried_entry_is_annotated():
    """Per entry, not in the preamble: one turn can carry a retried input alongside one never
    tried before, and a blanket sentence would misdescribe the second."""
    from hub.inbound_queue import format_turn_prompt

    prompt = format_turn_prompt([_entry("retried", attempts=2), _entry("brand new")])
    retried_block, fresh_block = prompt.split("\n\n")[1:3]
    assert "delivery attempt 3" in retried_block
    assert "attempt" not in fresh_block
    assert fresh_block.startswith("Operator (hop 0):")


def test_the_note_does_not_instruct_the_agent_what_to_do():
    """D5: what to do about half-finished work depends on what the work was, so an instruction
    would be wrong often enough to cost more than the bare fact saves."""
    from hub.inbound_queue import format_turn_prompt

    prompt = format_turn_prompt([_entry("again", attempts=1)]).lower()
    for instruction in ("check ", "review ", "redo", "start over", "worktree"):
        assert instruction not in prompt


# ---------------------------------------------------------------------------
# The provider session is given up on the way past, as it always was
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_second_failure_clears_the_conversations_provider_session(
    app, auth_headers, bind_runner
):
    """`RESUME_RETRY_LIMIT` was already implemented and already tested against
    `return_run_entries` directly. What is new is that a mid-turn death now reaches it."""
    await _register(app, auth_headers, "clears-thread")
    await bind_runner("clears-thread", cli="claude")

    with _patched(
        patch("hub.api.v1.agent_trigger.PtySession.spawn", _fresh_failing_pty()),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "clears-thread", "message": "unresumable", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        await _await_background_run()

    async with async_session_factory() as db:
        rows = await db.execute(select(Conversation).where(Conversation.agent == "clears-thread"))
        for conversation in rows.scalars().all():
            assert conversation.provider_session_id is None
