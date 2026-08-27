"""A turn is a review or work, never both (`every-run-knows-its-task`, F66, design D3).

Until this change, `schedule_agent`'s narrowing of `selected` filtered by conversation and hop
depth (finding F5, `test_hop_budget_bound.py`) but never by kind — so an agent whose queue held
both a review entry and a work entry on the same conversation was delivered a turn carrying both,
bound to neither correctly: the review checkout replaced the ordinary workspace, and the binding
(`run_task_binding.binding_from_entries`) picked whichever of the two entries arrived first,
which need not be the one the review checkout was prepared for.

These tests pin the fix: the controlling entry (the earliest admitted, same one that decides
`turn_depth`) decides the turn's kind, and an entry of the other kind is left queued rather than
delivered or refused — it rides the next turn instead.

That "next turn" usually follows within the same `_drain()` a test awaits, not a separate one a
test has to trigger by hand: a turn ending with queued entries self-continues unconditionally
(`agent_trigger.py`, "a turn ending with queued entries starts the next turn without waiting for
operator input"), so by the time a background run's task is fully awaited, a deferred entry has
almost always already been picked up as a turn of its own. What these tests pin is therefore never
"the other entry is still queued once the dust settles" — self-continuation makes that state too
transient to observe reliably — but that the two kinds were delivered as **separate, un-mixed
turns**: distinct `PtySession.spawn` calls, each carrying only its own kind's content.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Project, Task
from hub.inbound_queue import new_entry
from hub.review_turn import ReviewContext
from hub.turn_scheduler import schedule_agent


def _completed_session(pid, session_id):
    session = MagicMock()
    session.pid = pid
    session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,' f'"session_id":"{session_id}"}}\n',
        "",
    ]
    session.wait.return_value = 0
    return session


async def _register(app, auth_headers, bind_runner, agent):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner(agent, cli="claude")


async def _seed(agent, conversation_id, entries, tasks=()):
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        # Wide enough that hop depth never gates these tests — kind, not budget, is under test.
        project.hop_budget = 6
        db.add(
            Conversation(
                id=conversation_id,
                project_id="proj-test",
                agent=agent,
                lifecycle="open",
            )
        )
        for task_id, status in tasks:
            db.add(Task(id=task_id, project_id="proj-test", title=task_id, status=status))
        db.add_all(entries)
        await db.commit()


async def _drain():
    while agent_trigger._background_runs:
        for task in list(agent_trigger._background_runs):
            await task


async def _entries(agent):
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.agent == agent)
                    .order_by(InboundQueueEntry.sequence)
                )
            )
            .scalars()
            .all()
        )
        return [(row.content, row.state) for row in rows]


def _review_context(task_id, workspace):
    return ReviewContext(
        task_id=task_id,
        task_title=task_id,
        reviewer="reviewer-agent",
        commit_sha="d" * 40,
        evidence_id="ev-1",
        workspace=workspace,
    )


@pytest.mark.asyncio
async def test_a_turn_admits_only_the_controlling_entrys_kind_review_first(
    app, auth_headers, bind_runner, tmp_path
):
    """1.1 — the review entry is earliest admitted, so it alone controls the first turn; the
    work entry rides a separate, later turn rather than being batched into this one."""
    agent = "kind-review-first"
    await _register(app, auth_headers, bind_runner, agent)
    await _seed(
        agent,
        "conv-kind-1",
        [
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="operator",
                content="please review",
                hop_depth=0,
                conversation_id="conv-kind-1",
                review_task_id="task-review",
            ),
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="operator",
                content="please work",
                hop_depth=0,
                conversation_id="conv-kind-1",
                task_id="task-work",
            ),
        ],
        tasks=[("task-review", "completed"), ("task-work", "pending")],
    )

    spawn = MagicMock(side_effect=lambda *a, **k: _completed_session(9001, "kind-1"))
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "hub.api.v1.agent_trigger.review_turn.prepare_review_turn",
                AsyncMock(
                    return_value=_review_context("task-review", tmp_path / "review-workspace")
                ),
            ):
                result = await schedule_agent("proj-test", agent)
                assert result.response is not None
                await _drain()

    # Self-continuation (`agent_trigger.py`) picks up the deferred work entry the moment the
    # review turn ends, so both are delivered by the time `_drain()` returns — but as two turns,
    # never one. `spawn.call_count == 2` and each call's own content is the invariant that
    # matters; the queue's final resting state does not distinguish this fix from the bug it
    # replaces.
    assert await _entries(agent) == [
        ("please review", "delivered"),
        ("please work", "delivered"),
    ]
    assert spawn.call_count == 2
    first_prompt, second_prompt = (str(call) for call in spawn.call_args_list)
    assert "please review" in first_prompt and "please work" not in first_prompt
    assert "please work" in second_prompt and "please review" not in second_prompt


@pytest.mark.asyncio
async def test_a_turn_admits_only_the_controlling_entrys_kind_work_first(
    app, auth_headers, bind_runner
):
    """1.2 — the reverse arrival order gives the reverse outcome.

    Unlike 1.1, `review_turn.prepare_review_turn` is left unmocked here on purpose: once "please
    work" delivers, self-continuation immediately tries the deferred review, and the real
    resolver refuses it (no evidence-backed reviewable commit exists for `task-review` in this
    fixture) before ever reaching `PtySession.spawn` — so `spawn` genuinely is called once, and
    "please review" genuinely stays `queued`, not because self-continuation didn't try but
    because the attempt it made failed cleanly. Do not take this test's shape as evidence that
    self-continuation skips a deferred entry of the other kind — 1.1 pins the case where it
    succeeds.
    """
    agent = "kind-work-first"
    await _register(app, auth_headers, bind_runner, agent)
    await _seed(
        agent,
        "conv-kind-2",
        [
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="operator",
                content="please work",
                hop_depth=0,
                conversation_id="conv-kind-2",
                task_id="task-work",
            ),
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="operator",
                content="please review",
                hop_depth=0,
                conversation_id="conv-kind-2",
                review_task_id="task-review",
            ),
        ],
        tasks=[("task-review", "completed"), ("task-work", "pending")],
    )

    spawn = MagicMock(return_value=_completed_session(9002, "kind-2"))
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            result = await schedule_agent("proj-test", agent)
            assert result.response is not None
            await _drain()

    assert await _entries(agent) == [
        ("please work", "delivered"),
        ("please review", "queued"),
    ]
    assert "please review" not in str(spawn.call_args)


@pytest.mark.asyncio
async def test_a_deferred_entry_is_delivered_on_the_next_turn(
    app, auth_headers, bind_runner, tmp_path
):
    """1.3 — an entry left queued because a turn admitted only the other kind is not starved
    (design risk: "a review that keeps arriving first could starve the work entry").

    Two review entries arrive ahead of the work entry, both naming the same reviewed task (so
    they are not themselves a mixed batch — `_review_task_from_entries` admits several entries
    naming one review target together) and are delivered as the first turn. The work entry is
    deferred through that whole turn, not just past a single review — and self-continuation still
    reaches it afterwards rather than the queue getting stuck behind however many reviews
    happened to be ahead of it.
    """
    agent = "kind-deferred"
    await _register(app, auth_headers, bind_runner, agent)
    await _seed(
        agent,
        "conv-kind-3",
        [
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="operator",
                content="please review 1",
                hop_depth=0,
                conversation_id="conv-kind-3",
                review_task_id="task-review",
            ),
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="operator",
                content="please review 2",
                hop_depth=0,
                conversation_id="conv-kind-3",
                review_task_id="task-review",
            ),
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="operator",
                content="please work",
                hop_depth=0,
                conversation_id="conv-kind-3",
                task_id="task-work",
            ),
        ],
        tasks=[("task-review", "completed"), ("task-work", "pending")],
    )

    spawn = MagicMock(side_effect=lambda *a, **k: _completed_session(9003, "kind-3"))
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "hub.api.v1.agent_trigger.review_turn.prepare_review_turn",
                AsyncMock(
                    return_value=_review_context("task-review", tmp_path / "review-workspace")
                ),
            ):
                result = await schedule_agent("proj-test", agent)
                assert result.response is not None
                await _drain()

    assert await _entries(agent) == [
        ("please review 1", "delivered"),
        ("please review 2", "delivered"),
        ("please work", "delivered"),
    ]
    # Both reviews rode the first turn together; the work entry got a turn of its own once they
    # were drained, not before.
    assert spawn.call_count == 2
    first_prompt, second_prompt = (str(call) for call in spawn.call_args_list)
    assert "please work" not in first_prompt
    assert "please review 1" in first_prompt and "please review 2" in first_prompt
    assert "please work" in second_prompt


@pytest.mark.asyncio
async def test_several_work_entries_and_no_review_are_unchanged(app, auth_headers, bind_runner):
    """1.4 — a batch with no review present is delivered together, as before."""
    agent = "kind-all-work"
    await _register(app, auth_headers, bind_runner, agent)
    await _seed(
        agent,
        "conv-kind-4",
        [
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="operator",
                content="first",
                hop_depth=0,
                conversation_id="conv-kind-4",
                task_id="task-a",
            ),
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="agent",
                origin_agent="peer",
                content="second",
                hop_depth=0,
                conversation_id="conv-kind-4",
                task_id="task-b",
            ),
        ],
        tasks=[("task-a", "pending"), ("task-b", "pending")],
    )

    spawn = MagicMock(return_value=_completed_session(9005, "kind-4"))
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            result = await schedule_agent("proj-test", agent)
            assert result.response is not None
            await _drain()

    assert await _entries(agent) == [
        ("first", "delivered"),
        ("second", "delivered"),
    ]
    prompt = str(spawn.call_args)
    assert "first" in prompt and "second" in prompt
