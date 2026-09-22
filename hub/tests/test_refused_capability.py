"""A refused capability reaches the operator — F376, `openspec/changes/a-refused-capability-reaches-the-operator/`.

An agent refused `create_flow` because `projects.allow_agent_jobs` was off was told the call
*"requires operator approval or an enabled allowance"*. No approval was opened, the operator came
back to nothing, and the agent sent 20 hand-driven messages instead; 0 of 32 tasks reached
`approved`. The refusal now opens a question of record and says so, truthfully.

Every test here goes through the real route with real run attribution — the `X-AgentWeave-*`
headers the MCP adapter sends, or the run credential the CLI path sends — because the gate is what
decides whether a call is an agent's at all.
"""

from __future__ import annotations

import asyncio
import json
from typing import List
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

import hub.refused_capability as refused_capability
import hub.turn_scheduler as turn_scheduler
from hub.agent_auth import hash_run_token
from hub.conversations import conversation_attention
from hub.db.engine import async_session_factory
from hub.db.models import EventLog, InboundQueueEntry, PermissionRequest, Question, Run
from hub.mcp_server import HubAPIError, _readable_detail
from hub.permission_requests import expire_pending_for_run
from hub.refused_capability import AGENT_JOBS, REFUSAL_CODE

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"
KEY = AGENT_JOBS.subject_key
JOB = {
    "name": "nightly",
    "agent": "lead",
    "message": "run tests",
    "cron": "0 2 * * *",
    "session_mode": "new",
}


async def a_running_agent(
    agent: str = "lead", run_id: str = "run-refused", conversation_id: str | None = None
) -> dict[str, str]:
    """A live run, attributed the way the MCP adapter attributes its calls."""
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent=agent,
                status="running",
                turn_depth=0,
                conversation_id=conversation_id,
            )
        )
        await session.commit()
    return {"X-AgentWeave-Agent": agent, "X-AgentWeave-Run": run_id}


async def refuse(app, auth_headers, agent_headers) -> dict:
    refused = await app.post(
        f"/api/v1/projects/{PROJECT}/jobs", headers={**auth_headers, **agent_headers}, json=JOB
    )
    assert refused.status_code == 403, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == REFUSAL_CODE
    return detail


async def records() -> List[Question]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Question)
            .where(Question.project_id == PROJECT, Question.subject_key == KEY)
            .order_by(Question.created_at)
        )
        return list(result.scalars().all())


async def answer(app, auth_headers, question_id: str, text: str, labels: List[str] | None):
    body: dict = {"answer": text}
    if labels is not None:
        body["labels"] = labels
    answered = await app.patch(
        f"/api/v1/projects/{PROJECT}/questions/{question_id}", headers=auth_headers, json=body
    )
    assert answered.status_code == 200, answered.text


async def decline(app, auth_headers, question_id: str):
    declined = await app.post(
        f"/api/v1/projects/{PROJECT}/questions/{question_id}/decline", headers=auth_headers
    )
    assert declined.status_code == 200, declined.text


@pytest.fixture
def wakes(monkeypatch):
    """Every agent the Hub tries to wake. Recorded, not run: no turn is wanted here."""
    calls: list = []

    async def recording(project_id, agent):
        calls.append((project_id, agent))
        return None

    monkeypatch.setattr(turn_scheduler, "schedule_agent", recording)
    return calls


# ---------------------------------------------------------------------------
# The record (tasks 4.1, 4.2, 4.3, 4.9, 4.10)
# ---------------------------------------------------------------------------


async def test_the_first_refusal_opens_one_record_and_names_it(app, auth_headers):
    headers = await a_running_agent()

    detail = await refuse(app, auth_headers, headers)

    opened = await records()
    assert len(opened) == 1
    record = opened[0]
    assert detail["question_id"] == record.id
    assert detail["setting"] == "allow_agent_jobs"
    assert detail["current_value"] == "off"
    assert record.from_agent == "lead"
    assert record.blocking is False
    assert record.header == "Scheduled work"
    assert [option["label"] for option in record.options] == [
        "Enabled it — go ahead",
        "Leave it off",
    ]
    # One project-level question: it names the setting, never the caller or its arguments (D5).
    assert "`allow_agent_jobs`" in record.question
    assert "Environment › Settings" in record.question
    assert "lead" not in record.question and "nightly" not in record.question
    # The broadcast's durable twin: the operator's view learns of it without a reload.
    async with async_session_factory() as session:
        asked = (
            (
                await session.execute(
                    select(EventLog).where(
                        EventLog.project_id == PROJECT, EventLog.event_type == "question_asked"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert [json_id(event) for event in asked] == [record.id]


def json_id(event: EventLog) -> str:
    data = event.data if isinstance(event.data, dict) else json.loads(event.data)
    return data["id"]


async def test_the_sentence_is_honest_and_carries_the_record_id(app, auth_headers):
    headers = await a_running_agent()

    detail = await refuse(app, auth_headers, headers)

    message = detail["message"]
    assert message.startswith(
        "Agents cannot create or change scheduled work in this project: the project setting "
        "`allow_agent_jobs` is off."
    )
    assert f"`{detail['question_id']}`" in message
    assert "do not poll, and do not repeat this call" in message
    assert "reach you as a message" in message
    assert "approval" not in message.lower()


async def test_the_record_outlives_the_run_and_no_permission_request_exists(app, auth_headers):
    headers = await a_running_agent()
    detail = await refuse(app, auth_headers, headers)

    # The run ends by the path that sweeps turn-scoped operator decisions.
    async with async_session_factory() as session:
        run = await session.get(Run, "run-refused")
        run.status = "completed"
        await expire_pending_for_run(session, run.id)
        await session.commit()

    async with async_session_factory() as session:
        record = await session.get(Question, detail["question_id"])
        assert record.answered is False and record.declined is False
        permission_requests = await session.scalar(
            select(func.count()).select_from(PermissionRequest)
        )
    assert permission_requests == 0


async def test_an_answer_after_the_run_ended_is_queued_for_the_refused_agent_and_wakes_it(
    app, auth_headers, wakes
):
    headers = await a_running_agent()
    detail = await refuse(app, auth_headers, headers)
    async with async_session_factory() as session:
        run = await session.get(Run, "run-refused")
        run.status = "completed"
        await session.commit()

    await answer(app, auth_headers, detail["question_id"], "Enabled it — go ahead", None)

    async with async_session_factory() as session:
        queued = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(
                        InboundQueueEntry.project_id == PROJECT, InboundQueueEntry.agent == "lead"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(queued) == 1
    assert "Enabled it — go ahead" in queued[0].content
    assert (PROJECT, "lead") in wakes


async def test_the_record_does_not_say_anyone_is_waiting(app, auth_headers):
    headers = await a_running_agent(conversation_id="conv-refused")
    detail = await refuse(app, auth_headers, headers)

    async with async_session_factory() as session:
        record = await session.get(Question, detail["question_id"])
        # D10: carrying the run would stamp its conversation, and the rail would then report a run
        # that is still working as waiting on the operator. A check that the question merely
        # exists passes with the run stamped on it.
        assert record.created_by_run_id is None
        assert record.conversation_id is None
        attention = await conversation_attention(session, ["conv-refused"])
    assert attention["conv-refused"] == "running"


async def test_the_record_reports_asker_waiting_true_by_the_shipped_presumption(app, auth_headers):
    """D14, pinned rather than changed.

    `_with_asker_state` presumes a question with no recorded asking run has someone waiting,
    because it cannot know otherwise — which is how every operator-posted question already reads.
    The record has no run by design (D10), so it reports `true`. The Overview card no longer calls
    that "waiting" because it also reads `blocking` (F386); the tray's ordering still sees it.
    """
    headers = await a_running_agent()
    detail = await refuse(app, auth_headers, headers)

    listed = await app.get(
        f"/api/v1/projects/{PROJECT}/questions?answered=false", headers=auth_headers
    )
    assert listed.status_code == 200
    row = next(q for q in listed.json() if q["id"] == detail["question_id"])
    assert row["asker_waiting"] is True
    assert row["blocking"] is False
    # What keeps it out of the refused agent's tray and composer: no run asked it.
    assert row["created_by_run_id"] is None


# ---------------------------------------------------------------------------
# Dedupe and the bound (tasks 4.4, 4.4b, 4.5)
# ---------------------------------------------------------------------------


async def test_a_second_refusal_while_the_record_is_open_reuses_it(app, auth_headers):
    headers = await a_running_agent()

    first = await refuse(app, auth_headers, headers)
    second = await refuse(app, auth_headers, headers)

    assert len(await records()) == 1
    assert second["question_id"] == first["question_id"]
    assert "has not answered yet" in second["message"]


async def test_a_second_agent_refused_meanwhile_is_told_the_answer_goes_to_the_first(
    app, auth_headers
):
    """D5's known limit, stated in the sentence rather than hidden behind "reach you"."""
    first = await refuse(app, auth_headers, await a_running_agent())
    other = await refuse(app, auth_headers, await a_running_agent("other", "run-other"))

    assert other["question_id"] == first["question_id"]
    assert "reach you" not in other["message"]
    assert "goes to `lead`" in other["message"]


async def test_refusals_arriving_together_share_one_record(app, auth_headers):
    """4.4b, asserted on the integrity-error branch directly.

    Two requests racing through one in-process ASGI client do not interleave reliably, so this
    stages the losing side exactly: the record already exists, and the losing refusal's read is
    made to miss it — as it would if it had read before the winner committed. The partial unique
    index then refuses the insert, and the loser must report the winner's record.
    """
    headers = await a_running_agent()
    winner = await refuse(app, auth_headers, headers)

    original = refused_capability._records
    reads = {"n": 0}

    async def stale_first_read(session, project_id, subject_key):
        reads["n"] += 1
        if reads["n"] == 1:
            return []
        return await original(session, project_id, subject_key)

    with patch.object(refused_capability, "_records", stale_first_read):
        loser = await refuse(app, auth_headers, headers)

    assert reads["n"] == 2, "the insert should have been refused and the record re-read"
    assert len(await records()) == 1
    assert loser["question_id"] == winner["question_id"]


async def test_two_concurrent_refusals_leave_one_record(app, auth_headers):
    """The same property, attempted with real concurrency; the branch above is the guarantee."""
    headers = await a_running_agent()
    results = await asyncio.gather(
        refuse(app, auth_headers, headers), refuse(app, auth_headers, headers)
    )
    assert len(await records()) == 1
    assert results[0]["question_id"] == results[1]["question_id"]


@pytest.mark.parametrize(
    "resolve, said",
    [
        # (a) chose an offered answer: labels present.
        (
            lambda app, h, qid: answer(app, h, qid, "Leave it off", ["Leave it off"]),
            "answered: “Leave it off”",
        ),
        # (b) typed their own: no labels, which is what both UI surfaces send for typed text and
        # is the case R1's label rule read as agreement (D13).
        (
            lambda app, h, qid: answer(app, h, qid, "no, leave it off", None),
            "answered: “no, leave it off”",
        ),
        # (c) declined.
        (lambda app, h, qid: decline(app, h, qid), "declined to answer"),
    ],
    ids=["chosen", "typed", "declined"],
)
async def test_a_resolved_record_is_superseded_exactly_once(app, auth_headers, resolve, said):
    headers = await a_running_agent()
    first = await refuse(app, auth_headers, headers)
    await resolve(app, auth_headers, first["question_id"])

    second = await refuse(app, auth_headers, headers)

    opened = await records()
    assert len(opened) == 2
    assert second["question_id"] == opened[1].id != first["question_id"]
    assert f"The operator was asked and {said}." in second["message"]
    assert "this is the last time" in second["message"]
    assert "This is the last time the Hub will ask" in opened[1].question
    assert [option["label"] for option in opened[1].options] == [
        "I'll enable it now",
        "Leave it off — stop asking",
    ]

    await resolve(app, auth_headers, second["question_id"])
    third = await refuse(app, auth_headers, headers)

    assert len(await records()) == 2
    assert "question_id" not in third
    assert f"The operator was asked twice and {said}." in third["message"]
    assert "asked once more" not in third["message"]
    assert "raise it with them in a message" in third["message"]


# ---------------------------------------------------------------------------
# Who is gated, and what the agent reads (tasks 4.6, 4.8, 4.11)
# ---------------------------------------------------------------------------


async def test_an_operator_call_is_not_gated_and_opens_nothing(app, auth_headers):
    created = await app.post(f"/api/v1/projects/{PROJECT}/jobs", headers=auth_headers, json=JOB)
    assert created.status_code == 201, created.text
    assert await records() == []


async def test_the_cli_access_path_opens_the_same_record(app, auth_headers):
    """The spec's either-access-path scenario: the run credential instead of the MCP headers."""
    token = "aw_run_run-cli-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-cli",
                project_id=PROJECT,
                agent="lead",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()

    refused = await app.post(
        "/api/v1/agent-actions/jobs", headers={"Authorization": f"Bearer {token}"}, json=JOB
    )

    assert refused.status_code == 403, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == REFUSAL_CODE
    assert [record.id for record in await records()] == [detail["question_id"]]


async def test_an_mcp_caller_reads_the_whole_sentence_and_the_adapter_keeps_the_id(
    app, auth_headers
):
    detail = await refuse(app, auth_headers, await a_running_agent())

    error = HubAPIError(403, _readable_detail(detail), "POST", "/jobs", detail)

    assert str(error) == f"Hub rejected POST /jobs (403): {detail['message']}"
    assert detail["question_id"] in str(error)
    assert error.data["question_id"] == detail["question_id"]


async def test_the_refusal_survives_the_record_failing_to_open(app, auth_headers):
    """D16. `database is locked` at the record's commit must not turn the 403 into a 500."""
    headers = await a_running_agent()

    async def locked(*args, **kwargs):
        raise OperationalError("INSERT INTO questions", {}, Exception("database is locked"))

    with patch("hub.api.v1.questions.ask_question_for_actor", locked):
        detail = await refuse(app, auth_headers, headers)

    assert "question_id" not in detail
    assert detail["setting"] == "allow_agent_jobs"
    assert detail["current_value"] == "off"
    assert "could not be asked automatically" in detail["message"]
    assert "has been asked" not in detail["message"]
    assert "do not poll, and do not repeat this call" in detail["message"]
    assert await records() == []


# ---------------------------------------------------------------------------
# From the adversarial review of 229a708 (2026-09-22)
# ---------------------------------------------------------------------------


async def test_an_event_log_failure_after_the_commit_does_not_deny_the_record(app, auth_headers):
    """`ask_question_for_actor` commits the row, broadcasts, then `persist_event` commits again.

    If that second commit fails (`database is locked` — the concurrency D16 names), the record
    exists and the operator was broadcast to, yet the broad except turns the outcome into None and
    the sentence says the operator "could not be asked". D16/spec: the sentence must not name a
    record that does not exist — the converse (denying one that does) is the same class of error.
    """
    headers = await a_running_agent()

    async def locked(*args, **kwargs):
        raise OperationalError("INSERT INTO event_logs", {}, Exception("database is locked"))

    with patch("hub.api.v1.questions.persist_event", locked):
        detail = await refuse(app, auth_headers, headers)

    opened = await records()
    assert len(opened) == 1, "the record was committed before persist_event ran"
    assert "question_id" in detail, detail["message"]


async def test_a_second_agent_refused_meanwhile_is_not_woken_by_the_answer(
    app, auth_headers, wakes
):
    first = await refuse(app, auth_headers, await a_running_agent())
    await refuse(app, auth_headers, await a_running_agent("other", "run-other"))

    await answer(app, auth_headers, first["question_id"], "Enabled it", None)

    assert (PROJECT, "lead") in wakes
    assert (PROJECT, "other") not in wakes


async def test_a_refusal_while_the_second_record_is_open_names_it(app, auth_headers):
    """The newest-first order is load-bearing: with two rows, the open one is the newer.

    Mutating `_records` to oldest-first survives every other test in this file, and then this
    refusal says the operator "was asked twice" and that nothing further will be opened while the
    last record is sitting open and unanswered.
    """
    headers = await a_running_agent()
    first = await refuse(app, auth_headers, headers)
    await answer(app, auth_headers, first["question_id"], "Leave it off", ["Leave it off"])
    second = await refuse(app, auth_headers, headers)

    third = await refuse(app, auth_headers, headers)

    assert third.get("question_id") == second["question_id"], third["message"]
    assert "has not answered yet" in third["message"]
    assert len(await records()) == 2


async def test_a_question_a_run_asked_reports_that_run(app, auth_headers):
    """The contrast the tray reads: a run's own `ask_user` carries its run id on the wire."""
    token = "aw_run_run-asker-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-asker",
                project_id=PROJECT,
                agent="lead",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    asked = await app.post(
        "/api/v1/agent-actions/questions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "blocking": False,
            "question": "Which colour?",
            "header": "Colour",
            "options": [{"label": "blue"}, {"label": "green"}],
            "multi_select": False,
        },
    )
    assert asked.status_code in (200, 201), asked.text

    listed = await app.get(
        f"/api/v1/projects/{PROJECT}/questions?answered=false", headers=auth_headers
    )
    row = next(q for q in listed.json() if q["id"] == asked.json()["id"])
    assert row["created_by_run_id"] == "run-asker"
