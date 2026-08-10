"""A turn ending on a question nobody was asked is detected, surfaced, and actionable.

The measured failure: Codex, told to ask which package manager to use, wrote the question into its
final message and ended the turn. No question row, no card, no operator. These tests pin the
detection and the two things the operator can then do about it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub.api.v1.agent_trigger import _flag_unasked_question
from hub.db.engine import async_session_factory
from hub.db.models import (
    AgentOutput,
    Conversation,
    EventLog,
    InboundQueueEntry,
    Question,
    UnaskedQuestion,
)

PROJECT = "proj-test"


async def _seed_run_output(
    *,
    run_id: str,
    agent: str = "codex-1",
    content: str = "Which package manager should I use?",
    kind: str = "text",
    sequence: int = 1,
    conversation_id: str | None = None,
) -> None:
    async with async_session_factory() as db:
        db.add(
            AgentOutput(
                id=f"out-{run_id}-{sequence}",
                project_id=PROJECT,
                agent=agent,
                content=content,
                kind=kind,
                run_id=run_id,
                sequence=sequence,
                conversation_id=conversation_id,
            )
        )
        await db.commit()


async def _pending(agent: str = "codex-1") -> list[UnaskedQuestion]:
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(UnaskedQuestion).where(
                        UnaskedQuestion.project_id == PROJECT,
                        UnaskedQuestion.agent == agent,
                    )
                )
            )
            .scalars()
            .all()
        )


async def _flag(run_id: str, *, agent: str = "codex-1", final_status: str = "completed") -> None:
    await _flag_unasked_question(
        project_id=PROJECT,
        agent=agent,
        run_id=run_id,
        conversation_id=None,
        final_status=final_status,
    )


@pytest.mark.asyncio
async def test_a_completed_turn_ending_in_a_question_is_flagged(app, auth_headers):
    await _seed_run_output(run_id="run-1")
    await _flag("run-1")

    rows = await _pending()
    assert len(rows) == 1
    assert rows[0].question == "Which package manager should I use?"
    assert rows[0].status == "pending"
    assert rows[0].run_id == "run-1"


@pytest.mark.asyncio
async def test_the_flag_is_recorded_as_a_warn_event_the_activity_view_can_filter(app, auth_headers):
    """severity="warning" is a value nothing in the UI reads — it renders unmarked and is hidden
    by the filter meant to reveal it."""
    await _seed_run_output(run_id="run-1")
    await _flag("run-1")

    async with async_session_factory() as db:
        events = list(
            (await db.execute(select(EventLog).where(EventLog.event_type == "question_not_asked")))
            .scalars()
            .all()
        )
    assert len(events) == 1
    assert events[0].severity == "warn"
    assert events[0].data["question"] == "Which package manager should I use?"


@pytest.mark.asyncio
async def test_a_run_that_asked_properly_is_not_flagged(app, auth_headers):
    """An agent that used the tool and then signed off with a question mark did nothing wrong."""
    await _seed_run_output(run_id="run-1", content="Done. Anything else you want changed?")
    async with async_session_factory() as db:
        db.add(
            Question(
                id="q-1",
                project_id=PROJECT,
                from_agent="codex-1",
                question="Which package manager?",
                created_by_run_id="run-1",
            )
        )
        await db.commit()

    await _flag("run-1")
    assert await _pending() == []


@pytest.mark.asyncio
async def test_a_turn_that_did_not_end_in_a_question_is_not_flagged(app, auth_headers):
    await _seed_run_output(run_id="run-1", content="I ran the tests and they pass.")
    await _flag("run-1")
    assert await _pending() == []


@pytest.mark.asyncio
async def test_a_turn_about_to_continue_is_not_flagged(app, auth_headers):
    """Queued input means `schedule_agent` starts the next turn immediately — the question is
    answered by that turn's input rather than stranded."""
    await _seed_run_output(run_id="run-1")
    async with async_session_factory() as db:
        db.add(Conversation(id="conv-q", project_id=PROJECT, agent="codex-1", lifecycle="open"))
        db.add(
            InboundQueueEntry(
                id="qe-1",
                project_id=PROJECT,
                agent="codex-1",
                conversation_id="conv-q",
                content="here is the answer",
                state="queued",
                origin_type="operator",
                hop_depth=0,
            )
        )
        await db.commit()

    await _flag("run-1")
    assert await _pending() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "stopped"])
async def test_a_run_that_did_not_complete_is_not_flagged(app, auth_headers, status):
    """A killed run's trailing text is often cut mid-sentence; a "?" there is truncation."""
    await _seed_run_output(run_id="run-1")
    await _flag("run-1", final_status=status)
    assert await _pending() == []


@pytest.mark.asyncio
async def test_only_the_final_text_output_is_considered(app, auth_headers):
    """A question asked mid-turn and then worked past is not a turn that stopped and waited."""
    await _seed_run_output(run_id="run-1", content="Should I use npm?", sequence=1)
    await _seed_run_output(
        run_id="run-1", content="The lockfile is pnpm's, so I used pnpm.", sequence=2
    )
    await _flag("run-1")
    assert await _pending() == []


@pytest.mark.asyncio
async def test_tool_output_does_not_stand_in_for_the_agents_own_words(app, auth_headers):
    """Only `kind="text"` is the agent talking; a tool result ending in "?" is not."""
    await _seed_run_output(run_id="run-1", content="grep: no match for 'why?'", kind="tool_result")
    await _flag("run-1")
    assert await _pending() == []


@pytest.mark.asyncio
async def test_a_failure_in_the_backstop_never_changes_the_runs_outcome(
    app, auth_headers, monkeypatch
):
    """The run is already recorded as finished. A backstop that could fail it would be worse than
    the gap it closes."""
    import hub.api.v1.agent_trigger as trigger

    def boom(_text):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(trigger, "trailing_question", boom)
    await _seed_run_output(run_id="run-1")
    await _flag("run-1")  # must not raise
    assert await _pending() == []


# --- the operator's two actions -------------------------------------------------------------


async def _seed_pending(record_id: str = "unasked-1", agent: str = "codex-1") -> None:
    async with async_session_factory() as db:
        db.add(
            UnaskedQuestion(
                id=record_id,
                project_id=PROJECT,
                agent=agent,
                run_id="run-1",
                conversation_id=None,
                question="Which package manager should I use?",
                status="pending",
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_pending_records_are_listed_for_the_operator(app, auth_headers):
    await _seed_pending()
    resp = await app.get(f"/api/v1/projects/{PROJECT}/unasked-questions", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["question"] == "Which package manager should I use?"
    assert body[0]["agent"] == "codex-1"


@pytest.mark.asyncio
async def test_dismissing_removes_it_from_the_operators_list(app, auth_headers):
    await _seed_pending()
    resp = await app.post(
        f"/api/v1/projects/{PROJECT}/unasked-questions/unasked-1/dismiss", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "dismissed"

    listed = await app.get(f"/api/v1/projects/{PROJECT}/unasked-questions", headers=auth_headers)
    assert listed.json() == []


@pytest.mark.asyncio
async def test_acting_twice_is_refused_rather_than_silently_repeated(app, auth_headers):
    """Two presses would start two turns racing on one question."""
    await _seed_pending()
    first = await app.post(
        f"/api/v1/projects/{PROJECT}/unasked-questions/unasked-1/dismiss", headers=auth_headers
    )
    assert first.status_code == 200
    second = await app.post(
        f"/api/v1/projects/{PROJECT}/unasked-questions/unasked-1/dismiss", headers=auth_headers
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_an_unknown_record_is_a_404(app, auth_headers):
    resp = await app.post(
        f"/api/v1/projects/{PROJECT}/unasked-questions/unasked-nope/dismiss", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_asking_properly_re_prompts_the_agent_with_the_question(
    app, auth_headers, monkeypatch
):
    """The re-prompt's wording is the mechanism — it is what converts prose into a tool call — so
    it is asserted here rather than left to a click handler."""
    import hub.api.v1.agent_trigger as trigger

    sent = {}

    async def fake_trigger(**kwargs):
        sent.update(kwargs)
        return None

    # The endpoint imports this inside the function body, so the name is looked up on the
    # trigger module at call time — patching it there is what takes effect.
    monkeypatch.setattr(trigger, "trigger_agent_directly", fake_trigger)

    async with async_session_factory() as db:
        db.add(Conversation(id="conv-1", project_id=PROJECT, agent="codex-1", lifecycle="open"))
        await db.commit()
    await _seed_pending()

    resp = await app.post(
        f"/api/v1/projects/{PROJECT}/unasked-questions/unasked-1/ask", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "asked"

    assert sent["agent"] == "codex-1"
    assert sent["conversation_id"] == "conv-1"
    assert "Which package manager should I use?" in sent["message"]
    assert "ask_user" in sent["message"]


@pytest.mark.asyncio
async def test_asking_with_no_open_conversation_is_refused(app, auth_headers):
    await _seed_pending()
    resp = await app.post(
        f"/api/v1/projects/{PROJECT}/unasked-questions/unasked-1/ask", headers=auth_headers
    )
    assert resp.status_code == 409
