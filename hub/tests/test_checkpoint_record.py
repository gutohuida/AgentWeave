"""The checkpoint record: a computed envelope carrying a written body.

Section 5 of 2026-08-07-conversation-handoff-rework.

The failures being designed against were observed, not imagined. A model asked for a timestamp
it could not obtain invented one. A model asked for pending work reported none, from a worktree
that is *always* clean because the Hub commits everything at the end of every turn. Both runs
were reported "Handoff ready", because readiness meant the run had stopped.
"""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select

from hub.checkpoints import (
    LOOP_TASK_SCOPE_NOTE,
    TASK_SCOPE_NOTE,
    compute_envelope,
    create_checkpoint,
    latest_checkpoint,
    latest_checkpoint_for_loop,
    loop_for_conversation,
    runs_to_cover,
)
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    Checkpoint,
    Conversation,
    JobRun,
    Loop,
    PermissionRequest,
    Question,
    Run,
    Task,
)
from hub.worktrees import files_changed_in, snapshot_worktree

PROJECT = "proj-test"
AGENT = "claude-1"


async def _conversation(db, conversation_id="conv-1", overrides=None):
    conversation = Conversation(
        id=conversation_id,
        project_id=PROJECT,
        agent=AGENT,
        lifecycle="open",
        runtime_overrides=overrides,
    )
    db.add(conversation)
    await db.commit()
    return conversation


async def _run(db, run_id, conversation_id="conv-1", sha=None, started=None):
    from datetime import datetime, timedelta, timezone

    run = Run(
        id=run_id,
        project_id=PROJECT,
        agent=AGENT,
        conversation_id=conversation_id,
        status="completed",
        snapshot_commit_sha=sha,
        started_at=(
            started
            if started is not None
            else datetime.now(timezone.utc) + timedelta(seconds=len(run_id))
        ),
    )
    db.add(run)
    await db.commit()
    return run


async def _loop_firing(db, *, conversation_id, job_id="job-loop-1", loop_id="loop-1"):
    """A conversation that is a loop's firing: an `AIJob` with a `Loop`, and the `JobRun` that
    joins this conversation to it — the same join `loop_for_conversation` reads."""
    job = AIJob(
        id=job_id,
        project_id=PROJECT,
        name="Loop job",
        agent=AGENT,
        message="do the queue",
        cron="0 9 * * *",
    )
    db.add(job)
    loop = Loop(id=loop_id, project_id=PROJECT, job_id=job_id)
    db.add(loop)
    conversation = await _conversation(db, conversation_id)
    db.add(
        JobRun(
            id=f"run-{conversation_id}",
            job_id=job_id,
            project_id=PROJECT,
            conversation_id=conversation_id,
        )
    )
    await db.commit()
    return conversation, loop


# --------------------------------------------------------------------------- the computed half


@pytest.mark.asyncio
async def test_the_task_list_says_it_is_the_agents_whole_list(app):
    """Task 5.4. `tasks` has no `conversation_id`, so this list is identical across every
    conversation the agent is running. A reader who assumes otherwise is misled by a record that
    looks conversation-specific — so the record says so, in the payload."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        db.add(Task(id="t1", project_id=PROJECT, title="Wire it up", assignee=AGENT))
        db.add(Task(id="t2", project_id=PROJECT, title="Someone else's", assignee="codex-1"))
        db.add(
            Task(id="t3", project_id=PROJECT, title="Finished", assignee=AGENT, status="completed")
        )
        await db.commit()

        envelope = await compute_envelope(db, conversation)

    assert envelope.tasks["scope"] == "agent"
    assert envelope.tasks["note"] == TASK_SCOPE_NOTE
    assert "not specific to this one" in envelope.tasks["note"]
    titles = [item["title"] for item in envelope.tasks["items"]]
    assert titles == ["Wire it up"]  # not another agent's, not a finished one


@pytest.mark.asyncio
async def test_open_questions_and_permission_decisions_are_conversation_scoped(app):
    """Unlike tasks, both of these carry a `conversation_id` and can be carried exactly."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        await _conversation(db, "conv-other")
        db.add(
            Question(
                id="q1",
                project_id=PROJECT,
                from_agent=AGENT,
                question="Which database?",
                answered=False,
                conversation_id="conv-1",
            )
        )
        db.add(
            Question(
                id="q2",
                project_id=PROJECT,
                from_agent=AGENT,
                question="Already answered",
                answered=True,
                conversation_id="conv-1",
            )
        )
        db.add(
            Question(
                id="q3",
                project_id=PROJECT,
                from_agent=AGENT,
                question="Another thread's",
                answered=False,
                conversation_id="conv-other",
            )
        )
        db.add(
            PermissionRequest(
                id="p1",
                project_id=PROJECT,
                agent=AGENT,
                conversation_id="conv-1",
                tool_name="Bash",
                status="denied",
                decided_by="operator",
            )
        )
        db.add(
            PermissionRequest(
                id="p2",
                project_id=PROJECT,
                agent=AGENT,
                conversation_id="conv-other",
                tool_name="Write",
                status="allowed",
            )
        )
        await db.commit()

        envelope = await compute_envelope(db, conversation)

    assert [q["question"] for q in envelope.open_questions] == ["Which database?"]
    # Denials are the load-bearing half: an agent refused a tool call and working around it
    # leaves a successor that needs to know why the obvious route is closed.
    assert [(p["tool"], p["status"]) for p in envelope.permission_decisions] == [("Bash", "denied")]


@pytest.mark.asyncio
async def test_runtime_overrides_in_force_are_carried(app):
    """An inherited {"permission_mode": "manual"} is what failed run-9058966b. A checkpoint that
    omits the overrides hides the cause from the successor that inherits them."""
    async with async_session_factory() as db:
        conversation = await _conversation(db, overrides={"permission_mode": "manual"})
        envelope = await compute_envelope(db, conversation)

    assert envelope.runtime_overrides == {"permission_mode": "manual"}


@pytest.mark.asyncio
async def test_a_conversation_with_no_activity_yields_an_empty_but_valid_envelope(app):
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        envelope = await compute_envelope(db, conversation)

    assert envelope.files_changed == []
    assert envelope.tasks["items"] == []
    assert envelope.open_questions == []
    assert envelope.covers_from_run_id is None
    assert envelope.covers_through_run_id is None


# --------------------------------------------------------------------------- files changed, real git


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_files_changed_reads_a_real_commit_including_the_first_one(tmp_path):
    """`git show`, not a `sha^..sha` diff: the first commit on a fresh agent branch has no
    parent, and diffing against `sha^` fails outright on it. That is the exact commit a
    first-ever checkpoint needs to read."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")

    (repo / "alpha.txt").write_text("one")
    (repo / "beta.txt").write_text("two")
    first = snapshot_worktree(repo, AGENT)
    assert first is not None
    assert files_changed_in(repo, first) == ["alpha.txt", "beta.txt"]

    (repo / "gamma.txt").write_text("three")
    second = snapshot_worktree(repo, AGENT)
    assert files_changed_in(repo, second) == ["gamma.txt"]

    # A sha that is not there is empty, never an exception — a checkpoint that fails to exist
    # because a commit was garbage-collected is worse than one reporting no files.
    assert files_changed_in(repo, "0" * 40) == []


@pytest.mark.asyncio
async def test_files_changed_is_the_union_over_the_covered_turns(app, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")

    (repo / "one.txt").write_text("1")
    sha_a = snapshot_worktree(repo, AGENT)
    (repo / "two.txt").write_text("2")
    sha_b = snapshot_worktree(repo, AGENT)

    async with async_session_factory() as db:
        conversation = await _conversation(db)
        await _run(db, "run-a", sha=sha_a)
        await _run(db, "run-b", sha=sha_b)
        # A turn that changed nothing commits nothing, so it carries no sha.
        await _run(db, "run-c", sha=None)

        envelope = await compute_envelope(db, conversation, worktree=Path(repo))

    assert envelope.files_changed == ["one.txt", "two.txt"]
    assert envelope.covers_from_run_id == "run-a"
    assert envelope.covers_through_run_id == "run-c"


@pytest.mark.asyncio
async def test_turns_predating_the_snapshot_column_report_no_files_rather_than_a_guess(app):
    """Migration 0043 does not backfill: those SHAs were never captured and cannot be
    recovered. The same rule 0041 followed for peer bindings.

    This is also the shape of every run in a project that is not a git repository
    (`2026-08-12-run-without-a-git-repository`): no worktree, so no auto-snapshot, so no SHA.
    Those checkpoints carry no changed-file list for the same reason — there are no commits to
    read one from — and they degrade to `[]` here rather than raising.
    """
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        await _run(db, "run-old", sha=None)
        envelope = await compute_envelope(db, conversation, worktree=None)

    assert envelope.files_changed == []


# --------------------------------------------------------------------------- anchoring


@pytest.mark.asyncio
async def test_a_later_checkpoint_covers_only_the_turns_since_the_last_one(app):
    """Task 5.5. Regenerating from the whole transcript loses information gradually and costs
    the worker full price every time."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        await _run(db, "run-1")
        await _run(db, "run-2")

        envelope = await compute_envelope(db, conversation)
        first = await create_checkpoint(
            db, conversation, trigger="operator", envelope=envelope, body="the first"
        )
        assert first.covers_through_run_id == "run-2"

        await _run(db, "run-3")
        await _run(db, "run-4")

        anchor = await latest_checkpoint(db, conversation.id)
        assert anchor.id == first.id

        covered = await runs_to_cover(db, conversation.id, anchor)
        assert [run.id for run in covered] == ["run-3", "run-4"]

        second = await create_checkpoint(
            db,
            conversation,
            trigger="context_pressure",
            envelope=await compute_envelope(db, conversation, anchor=anchor),
            body="the second",
            anchor=anchor,
        )

    assert second.previous_checkpoint_id == first.id
    assert second.covers_from_run_id == "run-3"
    assert second.covers_through_run_id == "run-4"


@pytest.mark.asyncio
async def test_a_first_checkpoint_has_no_predecessor_and_founds_its_lineage(app):
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        await _run(db, "run-1")
        first = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=await compute_envelope(db, conversation),
            body="body",
        )

    assert first.previous_checkpoint_id is None
    # The chain is named after the checkpoint that founded it, so "show me this thread" is one
    # indexed read rather than a walk back through every predecessor.
    assert first.lineage_id == first.id


@pytest.mark.asyncio
async def test_the_lineage_id_is_carried_forward_not_regenerated(app):
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        await _run(db, "run-1")
        first = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=await compute_envelope(db, conversation),
            body="one",
        )
        await _run(db, "run-2")
        anchor = await latest_checkpoint(db, conversation.id)
        second = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=await compute_envelope(db, conversation, anchor=anchor),
            body="two",
            anchor=anchor,
        )
        await _run(db, "run-3")
        anchor = await latest_checkpoint(db, conversation.id)
        third = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=await compute_envelope(db, conversation, anchor=anchor),
            body="three",
            anchor=anchor,
        )

    assert second.lineage_id == first.id
    assert third.lineage_id == first.id
    assert third.previous_checkpoint_id == second.id


@pytest.mark.asyncio
async def test_an_anchor_naming_a_run_that_is_gone_covers_everything_rather_than_nothing(app):
    """Covering a turn twice is a redundancy; silently covering none is a hole."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        await _run(db, "run-1")
        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=await compute_envelope(db, conversation),
            body="body",
        )
        checkpoint.covers_through_run_id = "run-that-never-existed"
        await db.commit()

        covered = await runs_to_cover(db, conversation.id, checkpoint)

    assert [run.id for run in covered] == ["run-1"]


# --------------------------------------------------------------------------- generation failing


@pytest.mark.asyncio
async def test_the_envelope_survives_a_worker_that_returned_nothing(app):
    """Task 5.3, and the heart of the change. Generation failing must degrade the record, not
    prevent it — the computed half is the verifiable half and does not depend on a model."""
    async with async_session_factory() as db:
        conversation = await _conversation(db, overrides={"permission_mode": "manual"})
        db.add(Task(id="t1", project_id=PROJECT, title="Still open", assignee=AGENT))
        await db.commit()
        await _run(db, "run-1")

        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="run_failure",
            envelope=await compute_envelope(db, conversation),
            body=None,
        )

    assert checkpoint.status == "unwritten"
    assert checkpoint.body is None
    # Every computed field is still there.
    assert checkpoint.tasks["items"][0]["title"] == "Still open"
    assert checkpoint.runtime_overrides == {"permission_mode": "manual"}
    assert checkpoint.covers_through_run_id == "run-1"


@pytest.mark.asyncio
async def test_an_empty_body_is_the_same_state_as_no_body(app):
    """ "Cleared" and "never written" should not be two states with one meaning."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=await compute_envelope(db, conversation),
            body="   ",
        )

    assert checkpoint.status == "unwritten"


@pytest.mark.asyncio
async def test_a_body_less_checkpoint_cannot_be_stored_as_ready(app):
    """Enforced in the schema, not only in `create_checkpoint`. The defect this change removes
    is a readiness signal that meant "the run stopped"; making the state unrepresentable is what
    stops a future code path reintroducing it."""
    from sqlalchemy.exc import IntegrityError

    async with async_session_factory() as db:
        conversation = await _conversation(db)
        db.add(
            Checkpoint(
                id="ckpt-bad",
                project_id=PROJECT,
                conversation_id=conversation.id,
                agent=AGENT,
                trigger="operator",
                status="ready",
                visibility="private",
                lineage_id="ckpt-bad",
                body=None,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


# ------------------------------------------------------------------------- loop-scoped continuity


@pytest.mark.asyncio
async def test_a_loop_scoped_envelope_carries_the_whole_queue_regardless_of_status(app):
    """Task 7.3/7.4. `loop=` makes `tasks` the loop's whole queue — including a status
    `_LIVE_TASK_STATUSES` would have excluded, proving this is not just `_tasks_for` with a wider
    filter grafted on."""
    async with async_session_factory() as db:
        conversation, loop = await _loop_firing(db, conversation_id="conv-loop-1")
        db.add(Task(id="tl-1", project_id=PROJECT, title="Open item", loop_id=loop.id))
        db.add(
            Task(
                id="tl-2",
                project_id=PROJECT,
                title="Already approved",
                loop_id=loop.id,
                status="approved",
            )
        )
        db.add(Task(id="tl-3", project_id=PROJECT, title="Someone else's loop", loop_id="loop-x"))
        await db.commit()

        envelope = await compute_envelope(db, conversation, loop=loop)

    assert envelope.tasks["scope"] == "loop"
    assert envelope.tasks["note"] == LOOP_TASK_SCOPE_NOTE
    titles = {item["title"] for item in envelope.tasks["items"]}
    assert titles == {"Open item", "Already approved"}  # both statuses, not another loop's


@pytest.mark.asyncio
async def test_a_non_loop_conversations_envelope_is_unchanged(app):
    """Regression guard: a plain conversation (no `loop=` argument, matching every call site
    before this task) still gets the agent-wide task list, not an empty loop-scoped one."""
    async with async_session_factory() as db:
        conversation = await _conversation(db, "conv-plain")
        db.add(Task(id="t-plain", project_id=PROJECT, title="Ordinary task", assignee=AGENT))
        await db.commit()

        envelope = await compute_envelope(db, conversation)

    assert envelope.tasks["scope"] == "agent"
    assert envelope.tasks["note"] == TASK_SCOPE_NOTE
    assert [item["title"] for item in envelope.tasks["items"]] == ["Ordinary task"]


@pytest.mark.asyncio
async def test_create_checkpoint_stamps_loop_id_when_the_conversation_is_a_loop_firing(app):
    """Task 7.1."""
    async with async_session_factory() as db:
        conversation, loop = await _loop_firing(db, conversation_id="conv-loop-2")
        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="task_completion",
            envelope=await compute_envelope(db, conversation, loop=loop),
            body="body",
            loop=loop,
        )

    assert checkpoint.loop_id == loop.id


@pytest.mark.asyncio
async def test_create_checkpoint_leaves_loop_id_null_for_a_plain_conversation(app):
    async with async_session_factory() as db:
        conversation = await _conversation(db, "conv-plain-2")
        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="task_completion",
            envelope=await compute_envelope(db, conversation),
            body="body",
        )

    assert checkpoint.loop_id is None


@pytest.mark.asyncio
async def test_loop_for_conversation_finds_the_job_that_fired_it(app):
    async with async_session_factory() as db:
        conversation, loop = await _loop_firing(db, conversation_id="conv-loop-3")
        found = await loop_for_conversation(db, conversation.id)

    assert found is not None
    assert found.id == loop.id


@pytest.mark.asyncio
async def test_loop_for_conversation_is_none_for_a_conversation_no_job_ever_fired(app):
    async with async_session_factory() as db:
        conversation = await _conversation(db, "conv-plain-3")
        found = await loop_for_conversation(db, conversation.id)

    assert found is None


@pytest.mark.asyncio
async def test_latest_checkpoint_for_loop_crosses_conversations(app):
    """Task 7.2/7.4's load-bearing case: the loop's latest checkpoint is found from a DIFFERENT
    conversation than the one being asked about, because every firing makes a new conversation
    (design D4 item 1). A same-conversation-only test would not catch a regression to the old,
    narrower `conversation_id` join."""
    async with async_session_factory() as db:
        first_conversation, loop = await _loop_firing(
            db, conversation_id="conv-loop-4a", job_id="job-loop-4", loop_id="loop-4"
        )
        first = await create_checkpoint(
            db,
            first_conversation,
            trigger="task_completion",
            envelope=await compute_envelope(db, first_conversation, loop=loop),
            body="first firing's checkpoint",
            loop=loop,
        )

        second_conversation = await _conversation(db, "conv-loop-4b")
        db.add(
            JobRun(
                id="run-conv-loop-4b",
                job_id="job-loop-4",
                project_id=PROJECT,
                conversation_id="conv-loop-4b",
            )
        )
        await db.commit()

        found_loop = await loop_for_conversation(db, second_conversation.id)
        assert found_loop is not None and found_loop.id == loop.id

        latest = await latest_checkpoint_for_loop(db, loop.id)

    assert latest is not None
    assert latest.id == first.id
    assert latest.conversation_id == first_conversation.id
    assert latest.conversation_id != second_conversation.id


@pytest.mark.asyncio
async def test_the_trigger_is_recorded_on_every_checkpoint(app):
    """v1 generates uniformly for all five triggers and records which fired. Provisional — see
    `project_checkpoint_trigger_prompts_provisional`; the field is what makes revisiting it
    possible from real data rather than from memory."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        for index, trigger in enumerate(
            ("context_pressure", "operator", "delegation", "run_failure", "task_completion")
        ):
            await create_checkpoint(
                db,
                await _conversation(db, f"conv-{index + 10}"),
                trigger=trigger,
                envelope=await compute_envelope(db, conversation),
                body="body",
            )

        rows = (await db.execute(select(Checkpoint))).scalars().all()

    assert {row.trigger for row in rows} == {
        "context_pressure",
        "operator",
        "delegation",
        "run_failure",
        "task_completion",
    }


@pytest.mark.asyncio
async def test_an_unknown_trigger_is_refused_by_the_database(app):
    from sqlalchemy.exc import IntegrityError

    async with async_session_factory() as db:
        conversation = await _conversation(db)
        db.add(
            Checkpoint(
                id="ckpt-bad",
                project_id=PROJECT,
                conversation_id=conversation.id,
                agent=AGENT,
                trigger="whenever-i-feel-like-it",
                status="unwritten",
                visibility="private",
                lineage_id="ckpt-bad",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
