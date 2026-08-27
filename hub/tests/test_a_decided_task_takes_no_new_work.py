"""Finding F79 — a task the operator has decided about still takes new runs.

`release_conversations_bound_to` states the rule this file defends, and states it generally:
*"Work that has been approved or abandoned is finished being worked on, and a thread that kept
attributing turns to it would put stalled markers on a task the operator has already decided about
(design D7)."* It enforced that on **conversations**. Three things can name the task a turn works
on, and the other two bypassed it entirely.

Found live 2026-08-27 driving `proj-46b602c1f3cb`:

* A turn was queued for `builder` naming `task-a0409448ee8e`, and waited behind another turn. In
  the interval the operator took the task to `approved` and its work merged to `master`. The
  conversations released, as designed. The **queue entry kept its `task_id`**, and when it was
  delivered 29 minutes later it started a run bound to approved, merged work — and
  `bind_run_to_task` wrote `assignee = builder` back onto a card the operator had just deliberately
  cleared, which is F78's remedy being undone by the product.
* Reproduced on demand with no queue involved: `POST /agent/trigger` naming an **approved** task
  was accepted, and the board then reported `status: approved, assignee: author,
  assignee_status: running` — an agent shown working on work that is already merged.

The two remedies differ because the two situations do, and `resolve_bound_task` already draws
exactly this distinction for a task that has been *deleted* since the delegation was sent:

* An **explicit** `task_id` is a statement the caller is making right now, so it is refused while
  they are looking at the response — *"A refusal here is the right answer — nothing else in the
  request implies the work."*
* A **queued entry** is an instruction from earlier that has stopped being true. Refusing it would
  let approving a task cancel a message the agent was legitimately sent, so the binding is released
  at the moment of the decision, beside the conversations, and the turn still runs — unbound.

`review_task_id` is deliberately untouched throughout. Inspecting finished work is legitimate, and
binding review runs to their task was itself a fix (`every-run-knows-its-task`, D3): two
`under_review -> approved` transitions existed that no run recorded having caused.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Task
from hub.run_task_binding import (
    TERMINAL_FOR_BINDING,
    release_bindings_to,
    resolve_bound_task,
)

pytestmark = pytest.mark.asyncio


async def _task(session, task_id: str, *, status: str) -> Task:
    task = Task(id=task_id, project_id="proj-test", title=f"Task {task_id}", status=status)
    session.add(task)
    await session.flush()
    return task


async def _conversation(session, conv_id: str, *, task_id: str | None = None) -> Conversation:
    conversation = Conversation(
        id=conv_id,
        project_id="proj-test",
        agent="builder",
        lifecycle="open",
        origin="operator",
        task_id=task_id,
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def _entry(
    session,
    entry_id: str,
    *,
    state: str = "queued",
    task_id: str | None = None,
    review_task_id: str | None = None,
) -> InboundQueueEntry:
    entry = InboundQueueEntry(
        id=entry_id,
        project_id="proj-test",
        agent="builder",
        origin_type="operator",
        content="do the thing",
        hop_depth=0,
        state=state,
        task_id=task_id,
        review_task_id=review_task_id,
        conversation_id="conv-holder",
    )
    session.add(entry)
    await session.flush()
    return entry


async def _reload(session, entry_id: str) -> InboundQueueEntry:
    """By `id`, not `session.get`: this table's primary key is `sequence`."""
    result = await session.execute(
        select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id)
    )
    return result.scalars().one()


# ---------------------------------------------------------------------------
# The queued instruction that outlived the decision
# ---------------------------------------------------------------------------


async def test_approving_a_task_releases_the_turns_still_queued_against_it(app):
    """The live defect: the conversations released and the queue did not, so the rule held on one
    surface and the turn arrived on the other."""
    async with async_session_factory() as session:
        task = await _task(session, "task-f79", status="under_review")
        await _conversation(session, "conv-f79", task_id="task-f79")
        await _entry(session, "entry-f79-a", task_id="task-f79")
        await _entry(session, "entry-f79-b", task_id="task-f79")
        await _entry(session, "entry-f79-other", task_id="task-elsewhere")
        await session.commit()

        await release_bindings_to(session, task)
        await session.commit()

        rows = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.task_id.isnot(None))
                )
            )
            .scalars()
            .all()
        )
        assert {row.id for row in rows} == {"entry-f79-other"}, (
            "every queued turn still aimed at the decided task must be unbound; the message itself "
            "survives, only the claim that it is work on that task does not"
        )
        conversations = (
            (await session.execute(select(Conversation).where(Conversation.task_id.isnot(None))))
            .scalars()
            .all()
        )
        assert conversations == [], "and the conversation release it now covers still runs"


async def test_a_delivered_entry_keeps_the_task_it_was_delivered_for(app):
    """History is not rewritten. A delivered entry records a turn that already happened, and that
    run's own boundary check was decided against this binding."""
    async with async_session_factory() as session:
        task = await _task(session, "task-f79-hist", status="under_review")
        await _entry(session, "entry-f79-done", state="delivered", task_id="task-f79-hist")
        await session.commit()

        await release_bindings_to(session, task)
        await session.commit()

        entry = await _reload(session, "entry-f79-done")
        assert entry.task_id == "task-f79-hist"


async def test_a_queued_review_of_the_task_is_not_released(app):
    """Inspecting decided work is legitimate, and unbinding it would reopen the hole
    `every-run-knows-its-task` D3 closed: review runs with a NULL `task_id`, and approvals that no
    run records having caused."""
    async with async_session_factory() as session:
        task = await _task(session, "task-f79-rev", status="under_review")
        await _entry(session, "entry-f79-review", review_task_id="task-f79-rev")
        await session.commit()

        await release_bindings_to(session, task)
        await session.commit()

        entry = await _reload(session, "entry-f79-review")
        assert entry.review_task_id == "task-f79-rev"


# ---------------------------------------------------------------------------
# The explicit request, refused while the caller is looking
# ---------------------------------------------------------------------------


async def test_triggering_a_run_on_an_approved_task_is_refused_over_http(app, auth_headers):
    """The on-demand reproduction: the board read `approved` / `assignee: author` / `running`.

    **Over HTTP, deliberately.** The unit-level equivalent would pass against a guard that cannot
    fire: this route does not run the turn, it queues an entry, so the task reaches
    `resolve_bound_task` as a delegation and never through its explicit branch. Only the request
    proves the refusal is reachable.
    """
    async with async_session_factory() as session:
        await _task(session, "task-f79-approved", status="approved")
        await session.commit()

    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "builder", "message": "ACK", "task_id": "task-f79-approved"},
        headers=auth_headers,
    )

    assert response.status_code == 409, (
        "the task exists and the caller may see it, so this is a conflict with its state and not "
        "the 404 a task in another project gets: " + response.text
    )
    detail = response.json()["detail"]
    assert "approved" in detail, "the refusal names the status that caused it"
    assert "revision_needed" in detail, "and the move that would reopen the task"


async def test_triggering_a_run_on_a_rejected_task_is_refused_over_http(app, auth_headers):
    """The other half of the terminal band, so the check is the band and not one status."""
    async with async_session_factory() as session:
        await _task(session, "task-f79-rejected", status="rejected")
        await session.commit()

    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "builder", "message": "ACK", "task_id": "task-f79-rejected"},
        headers=auth_headers,
    )
    assert response.status_code == 409, response.text


async def test_triggering_a_run_on_a_task_under_review_is_not_refused(app, auth_headers):
    """The band boundary, and the mutation check for it. `completed` and `under_review` are
    deliberately outside `TERMINAL_FOR_BINDING` — work under review comes back often, and refusing
    there would refuse precisely the turn that does the revisions."""
    assert set(TERMINAL_FOR_BINDING) == {"approved", "rejected"}
    async with async_session_factory() as session:
        await _task(session, "task-f79-open", status="under_review")
        await session.commit()

    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "builder", "message": "ACK", "task_id": "task-f79-open"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def test_a_delegated_entry_naming_a_decided_task_runs_unbound_rather_than_refusing(app):
    """Belt to the release's braces, and the asymmetry stated in code.

    The release above is what normally stops this, but an entry can be written by a path that never
    passes through the operator's PATCH — and refusing at delivery would be the wrong answer even
    then. `turn_scheduler` treats a non-transient refusal as grounds to abandon the entry after
    three attempts, so a refusal here would silently discard a message the agent was legitimately
    sent, because of a decision taken about a different thing. The turn runs; only the binding is
    dropped.
    """
    async with async_session_factory() as session:
        await _task(session, "task-f79-delegated", status="approved")
        conversation = await _conversation(session, "conv-f79-delegated")
        entry = await _entry(session, "entry-f79-delegated", task_id="task-f79-delegated")
        await session.commit()

        bound = await resolve_bound_task(
            session,
            project_id="proj-test",
            conversation=conversation,
            queue_entry_ids=[entry.id],
        )
        assert bound.task is None, "no binding to decided work"
        assert bound.named is False, "and nothing for the conversation to be rebound to"
