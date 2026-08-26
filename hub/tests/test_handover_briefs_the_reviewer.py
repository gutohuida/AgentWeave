"""Findings F43 and F44 — the reviewer's briefing is generated, and it is the author's.

**F43.** `_compose_loop_briefing` tells every agent in a flow to "record what a reviewer will need
(see `submit_checkpoint_notes`); somebody else reads it." Nobody could. `generate_checkpoint` had
two callers — a context-usage threshold and an operator button — and a flow firing is
`session_mode: new`, one small task, a conversation that never runs again. Its context never
approaches a threshold and no operator presses a button per handover, so the notes were never
consumed and `latest_checkpoint_for_loop` returned None on every firing the flow would ever have.

Measured on the live trial database when this was recorded: `checkpoint_notes` = 3, unconsumed = 3,
`checkpoints` = 6, of which **0** carried a `loop_id`. The agents had done their part — one note
named the task, the file, the line and the finding, written for somebody else to read.

**Why the suite was green.** `test_scheduler.py`'s
`test_loop_briefing_includes_a_prior_checkpoint_in_full_under_the_cap` builds its subject with
`_make_checkpoint(db, loop_id=loop.id, ...)` — a row inserted directly with the column already set
— and then asserts the briefing renders it. It never exercised anything that would *produce* such a
row, and in production nothing did. So the tests below **never insert a `Checkpoint` for the F43
assertions**; they drive `consider_handover` and assert on what it created. That distinction is the
entire lesson of F41 and F43, and writing these the convenient way would reproduce the defect.

**F44.** `latest_checkpoint_for_loop` filters on `loop_id` and takes the most recent, which is
whoever finished last. That was the author only while a loop ran one agent. With three agents
concurrent, the reviewer of task X gets an unrelated agent's account of task Y while being told it
is what a reviewer will need — on the live notes, two firings in three. `checkpoint_by_task_author`
resolves through the transition history instead, and the review turn uses it.
"""

import subprocess

import pytest
from sqlalchemy import select

from hub.checkpoint_handover import consider_handover
from hub.checkpoints import (
    checkpoint_by_task_author,
    get_checkpoint_by_id,
    latest_checkpoint_for_loop,
)
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    Checkpoint,
    CheckpointNote,
    Conversation,
    JobRun,
    Loop,
    Project,
    Run,
    Runner,
    Task,
)
from hub.scheduler import _briefing_checkpoint
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

AUTHOR = "handover-author"
OTHER = "handover-other"

#: A checkpoint body is markdown text, not the notes dict — the notes are an *input* to
#: generation, and `body` is what the model wrote. Used only for the rows these tests insert
#: directly, which stand in for another agent's finished handover rather than for the subject.
OTHER_AGENTS_BODY = "## Intent\n\nAn unrelated account of a different task entirely.\n"

GOOD_BODY = {
    "intent": "Refusing an entry with no postings; the guard was already correct.",
    "suspicions": ["Entry.balances() may already cover the empty case"],
    "warnings": ["Do not re-implement balances(); read book.py:20 first"],
}


def _claude_stdout(body):
    import json

    return json.dumps({"type": "result", "subtype": "success", "result": json.dumps(body)})


def _patch_cli(monkeypatch, responses):
    """Make the checkpoint worker's CLI spawn return canned output.

    Copied in shape from `test_checkpoint_generation._patch_cli` — generation is a real subprocess
    and these tests are about the trigger, not about the model.
    """
    calls = iter(responses)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=next(calls), stderr="")

    monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(subprocess, "run", fake_run)


async def _checkpoint_runner(db, *, cli="claude"):
    """Give the project a checkpoint runner. Without one, generation is skipped by design —
    `_resolve_runner` refuses to guess which CLI the operator wanted billed."""
    runner = Runner(
        id="runner-handover",
        project_id="proj-test",
        name="Handover checkpoints",
        cli=cli,
        model="claude-haiku-4-5-20251001",
    )
    db.add(runner)
    project = await db.get(Project, "proj-test")
    project.checkpoint_runner_id = runner.id
    await db.commit()
    return runner


async def _flow_handover(
    db,
    *,
    suffix,
    agent=AUTHOR,
    with_notes=True,
    complete=True,
    as_loop=True,
):
    """One flow agent finishing one task: job, loop, task, conversation, JobRun, Run, notes.

    Built through the same rows a real firing writes, because the `JobRun.conversation_id` ->
    `job_id` -> `Loop.job_id` join is exactly what `loop_for_conversation` walks, and a fixture
    that shortcut it would stop testing the thing that was broken.
    """
    job = AIJob(
        id=f"job-hand-{suffix}",
        project_id="proj-test",
        name=f"Handover {suffix}",
        agent=agent,
        message="carry on",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=False,
    )
    db.add(job)
    loop = Loop(
        id=f"loop-hand-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose="Close the defects; somebody else reviews.",
    )
    db.add(loop)
    task = Task(
        id=f"task-hand-{suffix}",
        project_id="proj-test",
        title=f"Handover task {suffix}",
        status="pending",
        loop_id=loop.id,
    )
    db.add(task)
    conversation = Conversation(
        id=f"conv-hand-{suffix}", project_id="proj-test", agent=agent, origin="job"
    )
    db.add(conversation)
    await db.commit()

    if as_loop:
        # The link that makes this a *loop firing* rather than a plain conversation.
        db.add(
            JobRun(
                id=f"jobrun-hand-{suffix}",
                job_id=job.id,
                project_id="proj-test",
                status="in_progress",
                trigger="scheduled",
                conversation_id=conversation.id,
            )
        )

    run = Run(
        id=f"run-hand-{suffix}",
        project_id="proj-test",
        agent=agent,
        conversation_id=conversation.id,
        # **Deliberately NULL**, matching production. Measured on the live database: of the ten runs
        # carrying a `completed` transition, six had `run.task_id = NULL`. An earlier draft of the
        # trigger gated on this column and would have declined most real handovers; setting it here
        # would have hidden that, which is the fixture-builds-what-production-does-not failure this
        # module's own docstring is about.
        task_id=None,
        status="completed",
    )
    db.add(run)
    await db.commit()

    if complete:
        actor = run_actor(agent=agent, run_id=run.id)
        await apply_transition(db, task, "assigned", actor)
        await apply_transition(db, task, "in_progress", actor)
        await apply_transition(db, task, "completed", actor)
        await db.commit()

    if with_notes:
        # **In an EARLIER firing's conversation, not the completing one.** A flow job is
        # `session_mode: new`, so every firing gets a fresh conversation, and a task needing more
        # than one firing records its notes in one and its completion in another. Measured live:
        # of four stranded notes, none shared a conversation with a run that completed a task —
        # `builder` wrote its note at 22:39:08 in one conversation and completed the task at
        # 22:40:00 in another. A same-conversation fixture passes against a trigger that can never
        # fire, which is exactly what the first draft of this module did.
        earlier = Conversation(
            id=f"conv-hand-{suffix}-prior", project_id="proj-test", agent=agent, origin="job"
        )
        db.add(earlier)
        await db.commit()
        db.add(
            JobRun(
                id=f"jobrun-hand-{suffix}-prior",
                job_id=job.id,
                project_id="proj-test",
                status="completed",
                trigger="scheduled",
                conversation_id=earlier.id,
            )
        )
        db.add(
            CheckpointNote(
                id=f"note-hand-{suffix}",
                project_id="proj-test",
                conversation_id=earlier.id,
                agent=agent,
                run_id=run.id,
                intent=GOOD_BODY["intent"],
                suspicions=GOOD_BODY["suspicions"],
                warnings=GOOD_BODY["warnings"],
            )
        )
        await db.commit()

    return job, loop, task, conversation, run


# ---------------------------------------------------------------------------
# F43 — the trigger exists, and it is the run boundary
# ---------------------------------------------------------------------------


async def test_a_flow_handover_with_notes_generates_the_authors_checkpoint(
    app, auth_headers, bind_runner, monkeypatch
):
    """The assertion that distinguishes this change from doing nothing.

    Nothing is inserted but the preconditions a real firing leaves. The `Checkpoint` is produced by
    the trigger, and it must carry `loop_id` — the column whose live count was 0 of 6.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        await _checkpoint_runner(db)
        _, loop, task, conversation, run = await _flow_handover(db, suffix="a")

    _patch_cli(monkeypatch, [_claude_stdout(GOOD_BODY), _claude_stdout(GOOD_BODY)])
    checkpoint_id = await consider_handover(run.id)

    assert checkpoint_id is not None, "the handover produced no checkpoint"
    async with async_session_factory() as db:
        checkpoint = await get_checkpoint_by_id(db, checkpoint_id)
        assert checkpoint.conversation_id == conversation.id
        assert checkpoint.loop_id == loop.id, "the checkpoint is not attributed to the flow"
        assert checkpoint.trigger == "task_completion"
        # And the notes the agent wrote for its reviewer are no longer stranded.
        #
        # Asserted **by note id**, not by the completing conversation. The fixture puts the note in
        # an earlier firing's conversation because that is where production puts it, so a query
        # scoped to `conversation.id` would find nothing and pass while proving nothing — which is
        # the vacuous-assertion twin of the dead fix this module exists to prevent.
        carried = await db.get(CheckpointNote, "note-hand-a")
        assert (
            carried.consumed_by_checkpoint_id == checkpoint_id
        ), "the note written in an earlier firing's conversation was not consumed"
        unconsumed = (
            (
                await db.execute(
                    select(CheckpointNote.id).where(
                        CheckpointNote.consumed_by_checkpoint_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert unconsumed == [], "the notes were not consumed by the checkpoint"


async def test_the_generated_checkpoint_is_what_the_next_firing_retrieves(
    app, auth_headers, bind_runner, monkeypatch
):
    """The whole chain, end to end: F43's trigger feeding the retrieval that already worked.

    `latest_checkpoint_for_loop` was never broken — it returned None because nothing upstream ever
    produced a row for it to find. This asserts the join now closes.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        await _checkpoint_runner(db)
        _, loop, _, _, run = await _flow_handover(db, suffix="chain")

    _patch_cli(monkeypatch, [_claude_stdout(GOOD_BODY), _claude_stdout(GOOD_BODY)])
    checkpoint_id = await consider_handover(run.id)

    async with async_session_factory() as db:
        found = await latest_checkpoint_for_loop(db, loop.id)
        assert found is not None, "the loop's next firing would still be briefed with nothing"
        assert found.id == checkpoint_id


async def test_a_handover_without_notes_spends_nothing(app, auth_headers, bind_runner, monkeypatch):
    """The operator's gate, 2026-08-25: generate only where the agent actually left something.

    Deliberately patches the CLI to raise. If the gate leaks, this fails loudly rather than
    silently billing a call the operator declined.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        await _checkpoint_runner(db)
        _, _, _, _, run = await _flow_handover(db, suffix="silent", with_notes=False)

    def explode(*args, **kwargs):
        raise AssertionError("generation was spawned for a handover with no notes")

    monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(subprocess, "run", explode)

    assert await consider_handover(run.id) is None


async def test_a_run_that_did_not_complete_its_task_is_not_a_handover(
    app, auth_headers, bind_runner, monkeypatch
):
    """A run that ended holding an unfinished task has handed nothing over. That case belongs to
    `evaluate_run_end`'s divergence check beside this one, not here."""
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        await _checkpoint_runner(db)
        _, _, _, _, run = await _flow_handover(db, suffix="unfinished", complete=False)

    assert await consider_handover(run.id) is None


async def test_an_ordinary_conversation_is_left_to_the_context_pressure_trigger(
    app, auth_headers, bind_runner, monkeypatch
):
    """Not every completed task is a flow handover. A conversation that is not a loop firing keeps
    running, so `checkpoint_trigger` still owns when it checkpoints and this must not pre-empt it.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        await _checkpoint_runner(db)
        _, _, _, _, run = await _flow_handover(db, suffix="plain", as_loop=False)

    assert await consider_handover(run.id) is None


async def test_a_project_with_no_checkpoint_runner_declines_rather_than_guessing(
    app, auth_headers, bind_runner, monkeypatch
):
    """`ledger-stress` had none set when F43 was recorded, which is why even the operator button
    returned 409. Spawning some other agent's runner because none was configured is a bill the
    operator did not agree to — so this declines, and says so in the log rather than crashing."""
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        _, _, _, _, run = await _flow_handover(db, suffix="norunner")

    assert await consider_handover(run.id) is None


async def test_the_same_boundary_evaluated_twice_generates_once(
    app, auth_headers, bind_runner, monkeypatch
):
    """A reconciliation pass or a retry can reach the same run again. The second visit must not buy
    a second summary of the same turn."""
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        await _checkpoint_runner(db)
        _, _, _, _, run = await _flow_handover(db, suffix="twice")

    _patch_cli(monkeypatch, [_claude_stdout(GOOD_BODY), _claude_stdout(GOOD_BODY)])
    first = await consider_handover(run.id)
    assert first is not None

    def explode(*args, **kwargs):
        raise AssertionError("the same run boundary generated a second checkpoint")

    monkeypatch.setattr(subprocess, "run", explode)
    assert await consider_handover(run.id) is None


# ---------------------------------------------------------------------------
# F44 — the reviewer is briefed by the author, not by whoever finished last
# ---------------------------------------------------------------------------


async def test_the_authors_checkpoint_is_found_by_task_not_by_recency(
    app, auth_headers, bind_runner, monkeypatch
):
    """Two agents, one loop, and the author is *not* the most recent.

    This is F44 exactly: `latest_checkpoint_for_loop` answers with the newest row, and for a review
    that is the wrong agent's account of a different task.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, OTHER)
    async with async_session_factory() as db:
        await _checkpoint_runner(db)
        _, loop, task, _, author_run = await _flow_handover(db, suffix="pair-a")

    _patch_cli(monkeypatch, [_claude_stdout(GOOD_BODY)] * 6)
    author_checkpoint = await consider_handover(author_run.id)
    assert author_checkpoint is not None

    # A second agent on the SAME loop finishes afterwards, so it owns the newest checkpoint.
    async with async_session_factory() as db:
        job = await db.get(AIJob, "job-hand-pair-a")
        other_conversation = Conversation(
            id="conv-hand-pair-b", project_id="proj-test", agent=OTHER, origin="job"
        )
        db.add(other_conversation)
        other_task = Task(
            id="task-hand-pair-b",
            project_id="proj-test",
            title="A different task entirely",
            status="pending",
            loop_id=loop.id,
        )
        db.add(other_task)
        await db.commit()
        db.add(
            JobRun(
                id="jobrun-hand-pair-b",
                job_id=job.id,
                project_id="proj-test",
                status="in_progress",
                trigger="scheduled",
                conversation_id=other_conversation.id,
            )
        )
        other_run = Run(
            id="run-hand-pair-b",
            project_id="proj-test",
            agent=OTHER,
            conversation_id=other_conversation.id,
            task_id=other_task.id,
            status="completed",
        )
        db.add(other_run)
        await db.commit()
        actor = run_actor(agent=OTHER, run_id=other_run.id)
        await apply_transition(db, other_task, "assigned", actor)
        await apply_transition(db, other_task, "in_progress", actor)
        await apply_transition(db, other_task, "completed", actor)
        db.add(
            CheckpointNote(
                id="note-hand-pair-b",
                project_id="proj-test",
                conversation_id=other_conversation.id,
                agent=OTHER,
                run_id=other_run.id,
                intent="An unrelated account of a different task.",
            )
        )
        await db.commit()

    newest = await consider_handover(other_run.id)
    assert newest is not None and newest != author_checkpoint

    async with async_session_factory() as db:
        # The defect, pinned: recency gives the wrong agent.
        by_recency = await latest_checkpoint_for_loop(db, loop.id)
        assert by_recency.id == newest

        # The fix: by task, it is the author's.
        by_author = await checkpoint_by_task_author(db, task.id, loop_id=loop.id)
        assert by_author is not None
        assert by_author.id == author_checkpoint, "the reviewer would read the wrong agent's work"


async def test_a_review_turn_is_briefed_from_the_author(
    app, auth_headers, bind_runner, monkeypatch
):
    """The selector wired where it matters. `_briefing_checkpoint` is what both firing paths call,
    and the `is_review` flag is the whole difference between the two questions."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, OTHER)
    async with async_session_factory() as db:
        await _checkpoint_runner(db)
        _, loop, task, _, author_run = await _flow_handover(db, suffix="brief")

    _patch_cli(monkeypatch, [_claude_stdout(GOOD_BODY)] * 4)
    author_checkpoint = await consider_handover(author_run.id)

    async with async_session_factory() as db:
        # A newer checkpoint on the same loop, from nobody relevant.
        db.add(
            Conversation(id="conv-hand-brief-x", project_id="proj-test", agent=OTHER, origin="job")
        )
        await db.commit()
        db.add(
            Checkpoint(
                id="ckpt-hand-brief-x",
                project_id="proj-test",
                conversation_id="conv-hand-brief-x",
                loop_id=loop.id,
                agent=OTHER,
                trigger="operator",
                status="ready",
                lineage_id="ckpt-hand-brief-x",
                body=OTHER_AGENTS_BODY,
            )
        )
        await db.commit()

        loop_row = await db.get(Loop, loop.id)
        task_row = await db.get(Task, task.id)

        as_review = await _briefing_checkpoint(db, loop_row, task_row, is_review=True)
        assert as_review.id == author_checkpoint

        # An ordinary continuation turn still asks "what did this loop last do", which is the
        # question `latest_checkpoint_for_loop` was written for and still answers correctly.
        as_work = await _briefing_checkpoint(db, loop_row, task_row, is_review=False)
        assert as_work.id == "ckpt-hand-brief-x"


async def test_a_review_falls_back_when_the_author_left_no_checkpoint(
    app, auth_headers, bind_runner, monkeypatch
):
    """F43's gate means a silent agent generates nothing. The reviewer is then no worse off than
    before either finding was fixed — the loop's own account, rather than an empty section."""
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        _, loop, task, _, _ = await _flow_handover(db, suffix="fallback", with_notes=False)
        db.add(Conversation(id="conv-hand-fb", project_id="proj-test", agent=OTHER, origin="job"))
        await db.commit()
        db.add(
            Checkpoint(
                id="ckpt-hand-fb",
                project_id="proj-test",
                conversation_id="conv-hand-fb",
                loop_id=loop.id,
                agent=OTHER,
                trigger="operator",
                status="ready",
                lineage_id="ckpt-hand-fb",
                body=OTHER_AGENTS_BODY,
            )
        )
        await db.commit()

        loop_row = await db.get(Loop, loop.id)
        task_row = await db.get(Task, task.id)
        found = await _briefing_checkpoint(db, loop_row, task_row, is_review=True)
        assert found is not None and found.id == "ckpt-hand-fb"
