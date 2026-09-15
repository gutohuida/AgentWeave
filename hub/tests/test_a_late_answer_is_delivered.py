"""A late answer is delivered — F356, `openspec/changes/a-late-answer-is-delivered/`.

`ask_user` gives up at its deadline, returns to the model, and the run carries on working. An
operator who answered after that, while the run still lived, had the answer recorded and delivered to
nobody: the answer route read "the asking run is still running" as "the asker is still waiting", and
skipped the queue. Measured on `:8000` on 2026-09-13 (batch 14:38): two of four answers lost.

The Hub already knew the wait was over — the tool reports it (`wait_ended_at`). These tests pin the
three ways that fact now reaches delivery: the answer and decline routes read it (group 1), the
expiry report delivers an answer given between the tool's last poll and the report (group 2), and
the two writers decide after they commit, so a race costs a duplicate and never a loss (groups 2-3).

Several tests commit a second writer **inside** a route, between its load and its write, through a
patched `AsyncSession.get` that runs the real competing route right after returning the row. That is
the interleave the design's rounds argued about; a raw write from a second session would stage a
state the product cannot produce (Round 4, task 2.3).
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, List
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import hub.api.v1.agent_trigger as agent_trigger
import hub.turn_scheduler as turn_scheduler
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EventLog, InboundQueueEntry, Question, Run, Task

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"
AGENT = "asker"
REPORT = "/api/v1/agent-actions/questions/wait-ended"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


async def make_agent(name: str = AGENT) -> None:
    async with async_session_factory() as session:
        session.add(Agent(id=f"ag-{name}", project_id=PROJECT, name=name))
        await session.commit()


async def make_task(task_id: str = "task-late", *, status: str = "in_progress") -> str:
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id=PROJECT,
                title="Work a question was asked about",
                status=status,
                assignee=AGENT,
            )
        )
        await session.commit()
    return task_id


async def make_run(
    run_id: str = "run-asker", *, task_id: str | None = None, status: str = "running"
) -> dict[str, str]:
    """A run with a minted credential, in the shape the agent-facing router resolves."""
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent=AGENT,
                status=status,
                turn_depth=0,
                task_id=task_id,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def one(text: str, *, blocking: bool = True) -> dict:
    return {
        "blocking": blocking,
        "question": text,
        "header": "A decision only you can make",
        "options": [{"label": "blue"}, {"label": "green"}],
        "multi_select": False,
    }


async def ask(app, headers, *texts: str, blocking: bool = True) -> List[str]:
    """Ask through the agent's own routes, which is what stamps the Hub's deadline."""
    if len(texts) == 1:
        asked = await app.post(
            "/api/v1/agent-actions/questions",
            headers=headers,
            json=one(texts[0], blocking=blocking),
        )
        assert asked.status_code in (200, 201), asked.text
        return [asked.json()["id"]]
    asked = await app.post(
        "/api/v1/agent-actions/questions/batch",
        headers=headers,
        json={"questions": [one(text) for text in texts]},
    )
    assert asked.status_code == 201, asked.text
    return [row["id"] for row in asked.json()["questions"]]


async def expire(*question_ids: str) -> None:
    """Move the Hub's deadline into the past, which is the only thing time would have done."""
    async with async_session_factory() as session:
        for question_id in question_ids:
            question = await session.get(Question, question_id)
            question.wait_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()


async def report(app, headers, *question_ids: str) -> List[str]:
    """The tool's expiry report: exactly the ids it did not see resolved."""
    reported = await app.post(REPORT, headers=headers, json={"question_ids": list(question_ids)})
    assert reported.status_code == 200, reported.text
    return reported.json()["accepted"]


async def answer(app, auth_headers, question_id: str, text: str):
    answered = await app.patch(
        f"/api/v1/projects/{PROJECT}/questions/{question_id}",
        headers=auth_headers,
        json={"answer": text, "labels": [text]},
    )
    assert answered.status_code == 200, answered.text
    return answered.json()


async def decline(app, auth_headers, question_id: str):
    declined = await app.post(
        f"/api/v1/projects/{PROJECT}/questions/{question_id}/decline", headers=auth_headers
    )
    assert declined.status_code == 200, declined.text
    return declined.json()


async def entries(agent: str = AGENT) -> List[InboundQueueEntry]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(InboundQueueEntry)
            .where(InboundQueueEntry.project_id == PROJECT, InboundQueueEntry.agent == agent)
            .order_by(InboundQueueEntry.sequence)
        )
        return list(result.scalars().all())


async def queued_events() -> List[EventLog]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(EventLog).where(EventLog.event_type == "queue_entry_queued")
        )
        return list(result.scalars().all())


async def question_row(question_id: str) -> Question:
    async with async_session_factory() as session:
        return (
            await session.execute(select(Question).where(Question.id == question_id))
        ).scalar_one()


async def task_status(task_id: str) -> str:
    async with async_session_factory() as session:
        return (await session.execute(select(Task.status).where(Task.id == task_id))).scalar_one()


async def proceeded_reason(app, auth_headers, task_id: str):
    read = await app.get(f"/api/v1/projects/{PROJECT}/tasks/{task_id}", headers=auth_headers)
    assert read.status_code == 200, read.text
    return read.json()["proceeded_without_answer_reason"]


def after_loading(monkeypatch, question_id: str, action: Callable[[], Awaitable[None]]) -> dict:
    """Run *action* once, right after the next `session.get` of *question_id* returns its row.

    That is the moment between a route's load and its write. *action* runs a real competing route,
    which commits in its own session; the route under test then writes against a row it loaded
    before that commit. Its own `get`s of the same id pass through, so it cannot recurse.
    """
    original = AsyncSession.get
    fired = {"done": False}

    async def get(self, entity, ident, *args, **kwargs):
        row = await original(self, entity, ident, *args, **kwargs)
        if entity is Question and ident == question_id and not fired["done"]:
            fired["done"] = True
            await action()
        return row

    monkeypatch.setattr(AsyncSession, "get", get)
    return fired


@pytest.fixture
def wakes(monkeypatch):
    """Every `schedule_agent` call and what it answered, passed through to the real scheduler."""
    calls: list = []
    original = turn_scheduler.schedule_agent

    async def recording(project_id, agent):
        result = await original(project_id, agent)
        calls.append((project_id, agent, result))
        return result

    monkeypatch.setattr(turn_scheduler, "schedule_agent", recording)
    return calls


async def a_live_asker(app, *, task_id: str | None = None) -> dict[str, str]:
    await make_agent()
    return await make_run(task_id=task_id)


# ---------------------------------------------------------------------------
# 1. One predicate for "still waiting" (design D1, D2)
# ---------------------------------------------------------------------------


async def test_an_answer_after_the_wait_ended_is_queued_while_the_run_lives(
    app, auth_headers, wakes
):
    """1.2. The 14:38 batch on 09-13, one question at a time: the tool reported its wait over, the
    run worked on for another fourteen minutes, and the answer reached nobody."""
    headers = await a_live_asker(app)
    [question_id] = await ask(app, headers, "Which colour?")
    await expire(question_id)
    assert await report(app, headers, question_id) == [question_id]
    assert await entries() == [], "an unanswered expiry delivers nothing"

    body = await answer(app, auth_headers, question_id, "blue")

    [entry] = await entries()
    assert entry.content == "Question: Which colour?\n\nAnswer: blue"
    [event] = await queued_events()
    assert event.data["entry_id"] == entry.id
    assert event.data["question_id"] == question_id
    assert [(p, a) for p, a, _ in wakes] == [(PROJECT, AGENT)]
    assert body["asker_waiting"] is False


async def test_an_answer_in_the_tools_grace_window_is_not_duplicated(app, auth_headers, wakes):
    """1.3. The shortcut still holds. The Hub's deadline has passed but the tool has not reported:
    it polls on for a couple of seconds past the Hub's deadline and returns this answer as its tool
    result, so queuing it as well would tell the agent twice."""
    headers = await a_live_asker(app)
    [question_id] = await ask(app, headers, "Which colour?")
    await expire(question_id)

    body = await answer(app, auth_headers, question_id, "blue")

    assert await entries() == []
    assert wakes == []
    assert body["asker_waiting"] is True


async def test_a_decline_that_completes_a_batch_after_the_wait_ended_delivers_its_answers(
    app, auth_headers
):
    """1.4. The decline route reads the same predicate at the same point. A batch whose wait ended
    while its run lives on, finished by a decline, sends the answers already given."""
    headers = await a_live_asker(app)
    first, second = await ask(app, headers, "First?", "Second?")
    await expire(first, second)
    assert await report(app, headers, first, second) == [first, second]

    await answer(app, auth_headers, first, "blue")
    assert await entries() == [], "half a batch is still not a delivery"
    await decline(app, auth_headers, second)

    [entry] = await entries()
    assert "1. First?\n   Answer: blue" in entry.content
    assert "2. Second?\n   Declined" in entry.content


# ---------------------------------------------------------------------------
# 2. The expiry report delivers what the tool never received (design D3, D4)
# ---------------------------------------------------------------------------


async def test_late_answers_reported_together_are_delivered_once_with_the_whole_batch(
    app, auth_headers, wakes
):
    """2.2. Two answered in time, which the tool returned; two answered after its last poll, which
    it reports. One delivery, carrying all four in ask order, announced and woken."""
    headers = await a_live_asker(app)
    ids = await ask(app, headers, "One?", "Two?", "Three?", "Four?")
    await answer(app, auth_headers, ids[0], "a")
    await answer(app, auth_headers, ids[1], "b")
    await expire(*ids)
    await answer(app, auth_headers, ids[2], "c")
    await answer(app, auth_headers, ids[3], "d")
    assert await entries() == [], "the tool is presumed to be still polling until it reports"
    assert wakes == []

    assert await report(app, headers, ids[2], ids[3]) == [ids[2], ids[3]]

    [entry] = await entries()
    lines = entry.content.splitlines()
    assert lines[0] == "You asked 4 questions. The operator has now resolved all of them."
    assert [line for line in lines if line.strip().startswith("Answer:")] == [
        "   Answer: a",
        "   Answer: b",
        "   Answer: c",
        "   Answer: d",
    ]
    assert lines.index("1. One?") < lines.index("4. Four?")
    [event] = await queued_events()
    assert event.data["entry_id"] == entry.id
    assert [(p, a) for p, a, _ in wakes] == [(PROJECT, AGENT)]


async def test_a_sibling_declined_mid_report_does_not_strand_the_batchs_answer(
    app, auth_headers, monkeypatch
):
    """2.3 / 2.11, Round 4 F-A. Q1 was answered after the tool's last poll; the report stamps it.
    Then the operator declines Q2 — through the real route, after the report loaded Q2 and before
    its guarded write. The decline route reads Q2's wait as live (the stamp has not happened) and
    delivers nothing; the report's write on Q2 is refused. Unless the report judges the batch on
    fresh rows, it reads Q2 undeclined and delivers nothing either."""
    headers = await a_live_asker(app)
    first, second = await ask(app, headers, "First?", "Second?")
    await expire(first, second)
    await answer(app, auth_headers, first, "blue")

    async def the_operator_declines_the_sibling():
        await decline(app, auth_headers, second)

    fired = after_loading(monkeypatch, second, the_operator_declines_the_sibling)
    assert await report(app, headers, first, second) == [first, second]
    assert fired["done"]

    [entry] = await entries()
    assert "1. First?\n   Answer: blue" in entry.content
    assert "2. Second?\n   Declined" in entry.content
    assert (await question_row(second)).wait_ended_at is None


async def test_a_turn_queued_behind_a_live_run_waits_for_it_and_then_runs(
    app, auth_headers, bind_runner, wakes
):
    """2.5, and F-G's second half of the scenario. The late answer is queued for an agent whose run
    is still live. The scheduler refuses it without starting a second concurrent run; the run's own
    end — the real finalize, not a status write — re-drains the project and starts the turn that
    carries the answer."""
    sync = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {AGENT: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(AGENT, cli="claude")

    release = threading.Event()
    prompts: list = []

    def line(payload):
        return json.dumps(payload) + "\n"

    def turn(session_id):
        return [
            line({"type": "system", "subtype": "init", "session_id": session_id}),
            line(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Done."}]},
                    "session_id": session_id,
                }
            ),
            line({"type": "result", "subtype": "success", "is_error": False}),
        ]

    def spawn(cmd, *args, **kwargs):
        prompts.append(" ".join(str(part) for part in cmd))
        first = len(prompts) == 1
        remaining = iter([*turn(f"sess-{len(prompts)}"), ""])
        session = MagicMock()
        session.pid = 4000 + len(prompts)

        def read(*a, **k):
            # The asking run stays live until the test has answered and looked: its first read
            # blocks, in the executor thread `_execute_run` reads from, not on the event loop.
            if first:
                release.wait(timeout=20)
            return next(remaining, "")

        session.read.side_effect = read
        session.wait.return_value = 0
        return session

    async def runs():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Run).where(Run.agent == AGENT).order_by(Run.started_at)
            )
            return list(result.scalars().all())

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", side_effect=spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            started = await app.post(
                f"/api/v1/projects/{PROJECT}/agent/trigger",
                json={"agent": AGENT, "message": "please do it", "session_mode": "new"},
                headers=auth_headers,
            )
            assert started.status_code == 200, started.text
            asking_run = started.json()["run_id"]
            for _ in range(500):
                if prompts:
                    break
                await asyncio.sleep(0.01)
            assert prompts, "the asking run never spawned"

            # 1.2's fixture on a real run: its wait was reported over, and it works on.
            async with async_session_factory() as session:
                session.add(
                    Question(
                        id="q-late-live",
                        project_id=PROJECT,
                        from_agent=AGENT,
                        question="Which colour?",
                        blocking=True,
                        created_by_run_id=asking_run,
                        options=[{"label": "blue"}, {"label": "green"}],
                        wait_expires_at=datetime.now(timezone.utc) - timedelta(seconds=5),
                        wait_ended_at=datetime.now(timezone.utc) - timedelta(seconds=4),
                    )
                )
                await session.commit()

            # The operator's trigger went through the scheduler too; only the answer's wake counts.
            wakes.clear()
            await answer(app, auth_headers, "q-late-live", "blue")

            # The operator's own message is an entry too, delivered into the asking run.
            [entry] = [row for row in await entries() if "Answer: blue" in row.content]
            assert entry.state == "queued"
            assert [run.id for run in await runs()] == [asking_run], "no second concurrent run"
            [(_, _, refused)] = wakes
            assert refused.waiting_reason == "agent is already running"

            release.set()
            for _ in range(400):
                if agent_trigger._background_runs:
                    await asyncio.gather(
                        *list(agent_trigger._background_runs), return_exceptions=True
                    )
                if len(await runs()) > 1:
                    break
                await asyncio.sleep(0.01)
            while agent_trigger._background_runs:
                await asyncio.gather(*list(agent_trigger._background_runs), return_exceptions=True)

    all_runs = await runs()
    assert len(all_runs) == 2, "the asking run's end started no turn for the queued answer"
    [delivered] = [row for row in await entries() if row.id == entry.id]
    assert delivered.state == "delivered"
    assert delivered.delivered_in_run_id == all_runs[1].id
    assert "Answer: blue" in prompts[1]


async def test_a_second_report_of_the_same_ids_delivers_nothing_more(app, auth_headers):
    """2.6. Arriving second is the normal case for a report-plus-sweep pair. The first report
    recorded the wait's end and delivered; the second is accepted and changes nothing."""
    headers = await a_live_asker(app)
    [question_id] = await ask(app, headers, "Which colour?")
    await expire(question_id)
    await answer(app, auth_headers, question_id, "blue")

    assert await report(app, headers, question_id) == [question_id]
    assert len(await entries()) == 1
    recorded = (await question_row(question_id)).wait_ended_at

    assert await report(app, headers, question_id) == [question_id]
    assert len(await entries()) == 1
    assert (await question_row(question_id)).wait_ended_at == recorded


async def test_a_question_declined_before_the_report_is_accepted_and_not_called_an_absence(
    app, auth_headers
):
    """2.7. A decline is a decision handed back, not silence. Reported after the operator declined
    it: accepted, nothing queued, no wait's end recorded, and the task does not say it went ahead
    without the operator's answer."""
    task_id = await make_task()
    headers = await a_live_asker(app, task_id=task_id)
    [question_id] = await ask(app, headers, "Which colour?")
    await expire(question_id)
    await decline(app, auth_headers, question_id)

    assert await report(app, headers, question_id) == [question_id]

    assert await entries() == []
    assert (await question_row(question_id)).wait_ended_at is None
    assert await proceeded_reason(app, auth_headers, task_id) is None


async def test_a_decline_committed_mid_report_is_not_recorded_as_a_wait_that_ended(
    app, auth_headers, monkeypatch
):
    """2.8. The report loaded the question unresolved; the operator's decline commits before the
    report writes. The write is guarded against committed state, so the declined row is not stamped
    and the task does not say it proceeded without an answer."""
    task_id = await make_task()
    headers = await a_live_asker(app, task_id=task_id)
    [question_id] = await ask(app, headers, "Which colour?")
    await expire(question_id)

    async def the_operator_declines():
        await decline(app, auth_headers, question_id)

    fired = after_loading(monkeypatch, question_id, the_operator_declines)
    assert await report(app, headers, question_id) == [question_id]
    assert fired["done"]

    question = await question_row(question_id)
    assert question.declined is True
    assert question.wait_ended_at is None
    assert await proceeded_reason(app, auth_headers, task_id) is None


async def test_an_answer_committed_mid_report_is_delivered_by_the_report(
    app, auth_headers, monkeypatch
):
    """2.9. The report loaded the question unanswered; the operator's answer commits before the
    report writes, through the real answer route — which reads the wait as live and queues nothing.
    The report keys delivery from what it stamped, re-read after its commit, so it delivers."""
    headers = await a_live_asker(app)
    [question_id] = await ask(app, headers, "Which colour?")
    await expire(question_id)

    async def the_operator_answers():
        await answer(app, auth_headers, question_id, "blue")
        assert await entries() == [], "the answer route read the wait as still open"

    fired = after_loading(monkeypatch, question_id, the_operator_answers)
    assert await report(app, headers, question_id) == [question_id]
    assert fired["done"]

    [entry] = await entries()
    assert entry.content == "Question: Which colour?\n\nAnswer: blue"


async def test_a_decline_committed_mid_sweep_is_not_recorded_and_parks_nothing(
    app, auth_headers, monkeypatch
):
    """2.10, and Round 4 F-B. The run-end sweep is the second writer. It loads the unanswered
    question; the operator's decline commits before it writes. The declined row must not be stamped,
    and — whatever the write returned — the question is no longer a wait, so the task is not parked
    on it. The task was released by hand while the run waited, so it is `in_progress` here, which
    is the status a park would move."""
    from hub import run_divergence
    from hub.run_divergence import evaluate_run_end

    task_id = await make_task()
    headers = await a_live_asker(app, task_id=task_id)
    [question_id] = await ask(app, headers, "Which colour?")
    assert await task_status(task_id) == "blocked"
    released = await app.patch(
        f"/api/v1/projects/{PROJECT}/tasks/{task_id}",
        headers=auth_headers,
        json={"status": "in_progress"},
    )
    assert released.status_code == 200, released.text
    await expire(question_id)

    original = run_divergence.unanswered_blocking_question

    async def loaded_then_declined(session, run):
        row = await original(session, run)
        if row is not None:
            await decline(app, auth_headers, row.id)
        return row

    monkeypatch.setattr(run_divergence, "unanswered_blocking_question", loaded_then_declined)
    async with async_session_factory() as session:
        run = await session.get(Run, "run-asker")
        run.status = "completed"
        await session.commit()
    await evaluate_run_end("run-asker")

    question = await question_row(question_id)
    assert question.declined is True
    assert question.wait_ended_at is None
    assert await task_status(task_id) != "blocked"
    assert await proceeded_reason(app, auth_headers, task_id) is None


async def test_one_failed_release_in_a_report_does_not_fail_the_next(
    app, auth_headers, monkeypatch
):
    """Round 4 F-H. A release that raises is rolled back for its own question only — and the
    rollback expires the calling run, which the next question's release reads. Left expired, that
    read is a lazy load inside the async session: it raised, and took the next question down too.
    Reported in the order that puts the failure first and the real release second."""
    import hub.api.v1.agent_actions as agent_actions

    task_id = await make_task()
    headers = await a_live_asker(app, task_id=task_id)
    [parked] = await ask(app, headers, "Which colour?")
    [other] = await ask(app, headers, "Which size?")
    assert await task_status(task_id) == "blocked"
    assert (await question_row(parked)).blocked_task_id == task_id
    await expire(parked, other)

    real = agent_actions.release_block_for_expired_wait
    calls: List[str] = []

    async def first_one_fails(session, question, run):
        calls.append(question.id)
        if len(calls) == 1:
            raise RuntimeError("this question's release fails")
        return await real(session, question, run)

    monkeypatch.setattr(agent_actions, "release_block_for_expired_wait", first_one_fails)

    assert await report(app, headers, other, parked) == [parked]
    assert calls == [other, parked]
    assert (await question_row(other)).wait_ended_at is None, "the failed one is rolled back"
    assert (await question_row(parked)).wait_ended_at is not None
    assert await task_status(task_id) == "in_progress"


async def test_a_question_nobody_waited_on_cannot_be_reported_even_once_answered(app, auth_headers):
    """The answered branch skips the deadline check (design D3), but not the question of whether
    there was a wait at all. A non-blocking note has no `wait_expires_at`; its answer was already
    delivered by the answer route, so a report naming it would stamp a wait nobody had and deliver
    it a second time."""
    headers = await a_live_asker(app)
    [question_id] = await ask(app, headers, "A note", blocking=False)
    await answer(app, auth_headers, question_id, "blue")
    assert len(await entries()) == 1

    assert await report(app, headers, question_id) == []
    assert len(await entries()) == 1
    assert (await question_row(question_id)).wait_ended_at is None


# ---------------------------------------------------------------------------
# 3. Races (design D4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("order", ["answer-then-report", "report-then-answer"])
async def test_either_order_on_committed_state_delivers_exactly_once(app, auth_headers, order):
    """3.1. Whichever of the answer and the report comes second sees the other's write."""
    headers = await a_live_asker(app)
    [question_id] = await ask(app, headers, "Which colour?")
    await expire(question_id)

    if order == "answer-then-report":
        await answer(app, auth_headers, question_id, "blue")
        assert await report(app, headers, question_id) == [question_id]
    else:
        assert await report(app, headers, question_id) == [question_id]
        await answer(app, auth_headers, question_id, "blue")

    [entry] = await entries()
    assert entry.content == "Question: Which colour?\n\nAnswer: blue"


async def test_the_answer_decides_on_a_fresh_read_after_the_report_committed(
    app, auth_headers, monkeypatch
):
    """3.2. The answer route loaded the question before the report committed its wait's end. It
    must decide from the row as refreshed after its own commit, not as loaded — or it reads the
    wait as open, while the report (which found the question unanswered) keyed nothing."""
    headers = await a_live_asker(app)
    [question_id] = await ask(app, headers, "Which colour?")
    await expire(question_id)

    async def the_tool_reports():
        assert await report(app, headers, question_id) == [question_id]

    fired = after_loading(monkeypatch, question_id, the_tool_reports)
    await answer(app, auth_headers, question_id, "blue")
    assert fired["done"]

    [entry] = await entries()
    assert entry.content == "Question: Which colour?\n\nAnswer: blue"
    async with async_session_factory() as session:
        assert (
            await session.execute(select(func.count()).select_from(InboundQueueEntry))
        ).scalar_one() == 1
