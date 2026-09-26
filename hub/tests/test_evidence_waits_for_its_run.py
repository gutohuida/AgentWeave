"""`evidence-is-decided-after-the-run-that-recorded-it` (F358, F426): a decision waits for the run
that recorded the evidence, a same-turn re-record revises, and a held agent is told when it ends.

Liveness is staged the way `test_approval_waits_for_the_turn.py` stages it: a stand-in session in
`run_liveness.active_ptys`, popped in a finaliser.
"""

import asyncio
import inspect
import re

import pytest
from sqlalchemy import select

from hub import inbound_queue, run_liveness
from hub.agent_auth import hash_run_token
from hub.api.v1 import agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    Conversation,
    InboundQueueEntry,
    RequirementEvidence,
    Run,
)

from .test_conflict_refusal_names_what_clears_it import (
    AGENT_EVIDENCE,
    BASE,
    linked_task,
    make_document,
    make_repo,
    record_as_agent,
    set_main_branch,
)

RECORDING = "run-f358-rec"
TESTER_RUN = "run-f358-tester"
TESTER = {"Authorization": "Bearer aw_run_f358_tester-secret"}
BUILDER = {"Authorization": "Bearer aw_run_f358_rec-secret"}
AGENT_DECIDE = "/api/v1/agent-actions/spec/evidence/{}/decision"


class LiveTurn:
    pid = 424243

    def isalive(self) -> bool:
        return True


@pytest.fixture
async def world(app, auth_headers, request, tmp_path):
    """A repository, a document, a task, the recording run `builder` and a granted `tester`."""
    make_repo(tmp_path)
    await set_main_branch("main")
    async with async_session_factory() as session:
        session.add(Agent(id="ag-f358-b", project_id="proj-test", name="builder"))
        session.add(
            Agent(id="ag-f358-t", project_id="proj-test", name="tester", can_accept_evidence=True)
        )
        session.add(
            Conversation(
                id="conv-f358-tester",
                project_id="proj-test",
                agent="tester",
                origin="operator",
                lifecycle="open",
            )
        )
        session.add(
            Run(
                id=RECORDING,
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_f358_rec-secret"),
            )
        )
        session.add(
            Run(
                id=TESTER_RUN,
                project_id="proj-test",
                agent="tester",
                status="running",
                turn_depth=0,
                conversation_id="conv-f358-tester",
                capability_token_hash=hash_run_token("aw_run_f358_tester-secret"),
            )
        )
        await session.commit()
    await make_document(app, auth_headers, BUILDER)
    task = await linked_task(app, auth_headers)
    async with async_session_factory() as session:
        (await session.get(Run, RECORDING)).task_id = task
        await session.commit()

    def cleanup():
        run_liveness.active_ptys.pop(RECORDING, None)
        run_liveness.decision_waiters.clear()

    request.addfinalizer(cleanup)
    return task


def go_live() -> None:
    run_liveness.active_ptys[RECORDING] = LiveTurn()


def end_run() -> None:
    run_liveness.active_ptys.pop(RECORDING, None)


async def operator_decides(app, auth_headers, evidence_id, decision="accepted"):
    return await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": decision},
        headers=auth_headers,
    )


async def agent_decides(app, evidence_id, decision="accepted"):
    return await app.post(
        AGENT_DECIDE.format(evidence_id), json={"decision": decision}, headers=TESTER
    )


async def evidence_rows():
    async with async_session_factory() as session:
        return (await session.execute(select(RequirementEvidence))).scalars().all()


async def queued_entries():
    async with async_session_factory() as session:
        return (await session.execute(select(InboundQueueEntry))).scalars().all()


# ---- D1 ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operator_decision_is_held_while_the_recording_run_is_live(app, auth_headers, world):
    """1.1 and 1.3."""
    evidence_id = await record_as_agent(app, BUILDER)
    go_live()
    held = await operator_decides(app, auth_headers, evidence_id)
    assert held.status_code == 409, held.text
    detail = held.json()["detail"]
    assert detail["code"] == "recording_run_live"
    assert RECORDING in detail["message"]
    assert "stopping it" in detail["message"]
    assert (await evidence_rows())[0].review_state == "awaiting"

    end_run()
    decided = await operator_decides(app, auth_headers, evidence_id)
    assert decided.status_code == 200, decided.text
    assert decided.json()["review_state"] == "accepted"


@pytest.mark.asyncio
async def test_agent_decision_is_held_too_and_not_as_a_403(app, auth_headers, world):
    """1.2."""
    evidence_id = await record_as_agent(app, BUILDER)
    go_live()
    held = await agent_decides(app, evidence_id)
    assert held.status_code == 409, held.text
    assert held.json()["detail"]["code"] == "recording_run_live"
    assert "you will be sent a note" in held.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_a_run_recorded_running_but_not_registered_does_not_hold_a_decision(
    app, auth_headers, world
):
    """1.4: the registry, not the column — a crashed Hub leaves `running` behind."""
    evidence_id = await record_as_agent(app, BUILDER)
    async with async_session_factory() as session:
        assert (await session.get(Run, RECORDING)).status == "running"
    assert (await operator_decides(app, auth_headers, evidence_id)).status_code == 200


@pytest.mark.asyncio
async def test_the_refusals_that_do_not_clear_with_time_come_first(app, auth_headers, world):
    """1.5."""
    evidence_id = await record_as_agent(app, BUILDER)
    go_live()
    assert (await operator_decides(app, auth_headers, evidence_id, "maybe")).status_code == 422
    async with async_session_factory() as session:
        (await session.get(Agent, "ag-f358-t")).can_accept_evidence = False
        await session.commit()
    ungranted = await agent_decides(app, evidence_id)
    assert ungranted.status_code == 403
    assert ungranted.json()["detail"]["code"] == "acceptance_not_granted"


@pytest.mark.asyncio
async def test_the_view_says_the_row_is_still_being_recorded(app, auth_headers, world):
    """1.6."""
    evidence_id = await record_as_agent(app, BUILDER)
    go_live()
    held = await operator_decides(app, auth_headers, evidence_id)
    assert held.status_code == 409
    end_run()
    decided = await operator_decides(app, auth_headers, evidence_id)
    assert decided.json()["recording_run_live"] is False
    go_live()
    from hub.api.v1.spec import _evidence_view

    rows = await evidence_rows()
    assert _evidence_view(rows[0])["recording_run_live"] is True


# ---- D2 / D3 -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_same_run_re_record_revises_its_row(app, auth_headers, world):
    """1.7."""
    first = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "first"}, headers=BUILDER
    )
    assert first.status_code == 201, first.text
    before = (await evidence_rows())[0].produced_at
    second = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "second"}, headers=BUILDER
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["id"] == first.json()["id"] and body["revised"] is True
    rows = await evidence_rows()
    assert len(rows) == 1 and rows[0].summary == "second"
    assert rows[0].produced_at > before


@pytest.mark.asyncio
async def test_a_different_run_at_the_same_commit_is_still_a_duplicate(app, auth_headers, world):
    """1.8 and 1.10: the cross-run control, and the sentence no longer says to commit."""
    await record_as_agent(app, BUILDER)
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-f358-second",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                task_id=world,
                capability_token_hash=hash_run_token("aw_run_f358_second-secret"),
            )
        )
        await session.commit()
    again = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": "again"},
        headers={"Authorization": "Bearer aw_run_f358_second-secret"},
    )
    assert again.status_code == 409, again.text
    detail = again.json()["detail"]
    assert detail["code"] == "duplicate_evidence"
    assert "commit it first" not in detail["message"]
    assert "record again once it has" in detail["message"]


# ---- D6 ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_decision_answers_200_when_the_merge_after_it_raises(
    app, auth_headers, world, monkeypatch
):
    """1.14 (F426): the answer is built before integration rolls back."""
    from hub import task_integration
    from hub.db.models import Task

    async def loading(session, *args, **kwargs):
        await session.execute(select(Task))  # a transaction is open, as in production
        raise RuntimeError("merge failed")

    monkeypatch.setattr(task_integration, "tasks_awaiting_this_commit", loading, raising=False)

    evidence_id = await record_as_agent(app, BUILDER)
    decided = await operator_decides(app, auth_headers, evidence_id)
    assert decided.status_code == 200, decided.text
    assert decided.json()["review_state"] == "accepted"
    assert (await evidence_rows())[0].review_state == "accepted"


# ---- D7 ------------------------------------------------------------------------------------


async def drain_wake_tasks():
    while agent_trigger._decision_wake_tasks:
        await asyncio.gather(*list(agent_trigger._decision_wake_tasks))


@pytest.mark.asyncio
async def test_a_held_agent_is_told_when_the_run_ends(app, auth_headers, world, monkeypatch):
    """1.15: refused twice -> the run ends -> exactly one `evidence` entry, in its conversation."""
    from hub import turn_scheduler

    scheduled = []

    async def fake_schedule(project_id, agent):
        scheduled.append(agent)

    monkeypatch.setattr(turn_scheduler, "schedule_agent", fake_schedule)

    evidence_id = await record_as_agent(app, BUILDER)
    go_live()
    assert (await agent_decides(app, evidence_id)).status_code == 409
    assert (await agent_decides(app, evidence_id)).status_code == 409

    end_run()
    agent_trigger._wake_decision_waiters("proj-test", RECORDING)
    await drain_wake_tasks()

    entries = await queued_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.agent == "tester" and entry.state == "queued"
    assert entry.origin_type == "evidence" and entry.origin_agent is None
    assert entry.hop_depth == 0 and entry.conversation_id == "conv-f358-tester"
    assert evidence_id in entry.content and RECORDING in entry.content
    assert scheduled == ["tester"]
    prompt = inbound_queue.format_turn_prompt([entry])
    assert "AgentWeave" in prompt and 'Agent "None"' not in prompt


@pytest.mark.asyncio
async def test_the_wake_reaches_nobody_it_should_not(app, auth_headers, world, monkeypatch):
    """1.17 (a), (b), (d)."""
    from hub import turn_scheduler

    async def fake_schedule(project_id, agent):
        return None

    monkeypatch.setattr(turn_scheduler, "schedule_agent", fake_schedule)
    evidence_id = await record_as_agent(app, BUILDER)

    # (a) the operator is refused: nothing is remembered
    go_live()
    assert (await operator_decides(app, auth_headers, evidence_id)).status_code == 409
    assert run_liveness.decision_waiters == {}

    # (b) decided after the pop and before the wake task runs: nothing queued
    assert (await agent_decides(app, evidence_id)).status_code == 409
    end_run()
    assert (await operator_decides(app, auth_headers, evidence_id)).status_code == 200
    agent_trigger._wake_decision_waiters("proj-test", RECORDING)
    await drain_wake_tasks()
    assert await queued_entries() == []

    # (d) waiters cleared, as a restart does: nothing queued
    go_live()
    run_liveness.note_decision_waiter(
        RECORDING, agent="tester", refusing_run_id=TESTER_RUN, evidence_id=evidence_id
    )
    run_liveness.decision_waiters.clear()
    end_run()
    agent_trigger._wake_decision_waiters("proj-test", RECORDING)
    await drain_wake_tasks()
    assert await queued_entries() == []


def test_both_registry_releases_wake_the_waiters_before_their_first_await():
    """1.18."""
    source = inspect.getsource(agent_trigger)
    for release in (
        "run_liveness.active_ptys.pop(run_id",
        "run_liveness.active_app_server_runs.discard(run_id",
    ):
        at = source.index(release)
        block = source[at : at + 300]
        wake = block.index("_wake_decision_waiters(")
        assert "await " not in block[:wake], release
        assert re.search(r"finally:\s*\n\s*" + re.escape(release), source)


def test_the_evidence_origin_is_accepted_and_renders_as_the_hub():
    """1.19 (the CHECK constraints are covered by the migration head tests)."""
    entry = inbound_queue.new_entry(
        project_id="proj-test",
        agent="tester",
        origin_type="evidence",
        content="note",
        hop_depth=0,
        conversation_id="conv-x",
    )
    assert entry.origin_type == "evidence"
    assert "AgentWeave" in inbound_queue.format_turn_prompt([entry])
    with pytest.raises(ValueError):
        inbound_queue.new_entry(
            project_id="p", agent="a", origin_type="nope", content="", hop_depth=0
        )
