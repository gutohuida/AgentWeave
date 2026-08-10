"""Generation and the blind-resume probe.

Section 6 of 2026-08-07-conversation-handoff-rework.

The probe is graded against the database, not by a judge. Factory needed an LLM judge because
they had nothing to compare against; the Hub has `files_changed`, `tasks` and `open_questions`
sitting in a table, so the dimension that benchmarks worst everywhere is the one that can be
settled deterministically.
"""

import json
import subprocess

import pytest
from sqlalchemy import select

from hub.checkpoint_generation import (
    CHECKPOINT_PROMPT_VERSION,
    PROBE_PROMPT_VERSION,
    CheckpointBody,
    ProbeAnswers,
    build_generation_prompt,
    generate_checkpoint,
    grade_probe,
    render_body,
    render_checkpoint,
)
from hub.checkpoints import CheckpointEnvelope, compute_envelope, create_checkpoint
from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput, Conversation, Question, Run, Task, WorkerInvocation

PROJECT = "proj-test"
AGENT = "claude-1"


async def _conversation(db, conversation_id="conv-1"):
    conversation = Conversation(
        id=conversation_id, project_id=PROJECT, agent=AGENT, lifecycle="open"
    )
    db.add(conversation)
    await db.commit()
    return conversation


def _claude_stdout(payload) -> str:
    """A real `claude --output-format json` envelope carrying *payload* as its result."""
    return json.dumps(
        {
            "is_error": False,
            "subtype": "success",
            "type": "result",
            "usage": {"input_tokens": 4, "output_tokens": 120, "cache_read_input_tokens": 0},
            "total_cost_usd": 0.002,
            "result": payload if isinstance(payload, str) else json.dumps(payload),
        }
    )


def _patch_cli(monkeypatch, responses):
    """Answer successive spawns from *responses* — generation first, then the probe."""
    queue = list(responses)

    def fake_run(cmd, **kwargs):
        stdout = queue.pop(0) if queue else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(subprocess, "run", fake_run)


GOOD_BODY = {
    "objective": "Add a column and its migration.",
    "state": "Both written; tests not yet run.",
    "decisions": ["Chose a nullable column over a default; rejected backfill as unrecoverable."],
    "dead_ends": ["Tried diffing sha^..sha; the first commit has no parent."],
    "next_actions": ["Run pytest hub/tests/."],
    "risks": ["Do not assume the worktree is dirty; the Hub commits every turn."],
}


# --------------------------------------------------------------------------- the prompt


def test_the_prompt_never_asks_for_a_field_the_hub_computes():
    """Spec: "the prompt does not ask the model for changed files, tasks, questions, or
    timestamps". The observed failure is why — a model asked for a timestamp it could not obtain
    invented one, and a model asked for pending work reported none from a worktree that is
    always clean."""
    prompt = build_generation_prompt(transcript="Received: do the thing")
    assert "Do NOT list changed files" in prompt
    # None of the computed fields appears as something requested in the reply schema.
    schema_part = prompt.split("Rules:")[0]
    for computed in ("files_changed", "tasks", "open_questions", "timestamp", "runner"):
        assert computed not in schema_part


def test_an_anchor_is_offered_for_carry_forward_not_restatement():
    prompt = build_generation_prompt(transcript="new turns", anchor_body="## Objective\n\nold")
    assert "previous checkpoint" in prompt
    assert "do not restate it wholesale" in prompt


def test_notes_are_marked_as_one_input_the_transcript_can_override():
    """Notes are an input, never the artifact — so the prompt says the transcript wins."""
    prompt = build_generation_prompt(transcript="turns", notes="I suspect the cache is stale.")
    assert "I suspect the cache is stale." in prompt
    assert "the transcript is authoritative where they disagree" in prompt


def test_a_checkpoint_generated_without_notes_says_so():
    """ "The agent had nothing to add" and "the agent was never asked" read identically
    otherwise."""
    body = render_body(CheckpointBody(**GOOD_BODY), notes_incorporated=False)
    assert "contributed no notes" in body
    with_notes = render_body(CheckpointBody(**GOOD_BODY), notes_incorporated=True)
    assert "contributed no notes" not in with_notes


# --------------------------------------------------------------------------- grading


def _envelope():
    return CheckpointEnvelope(
        files_changed=["hub/hub/worker.py", "hub/tests/test_worker.py"],
        tasks={"scope": "agent", "note": "n", "items": [{"id": "t1", "title": "x"}]},
        open_questions=[{"id": "q1", "question": "Which database?"}],
    )


def test_a_faithful_reading_passes():
    status, findings = grade_probe(
        ProbeAnswers(
            files_changed=["hub/hub/worker.py", "hub/tests/test_worker.py"],
            task_ids=["t1"],
            unanswered_question_ids=["q1"],
        ),
        _envelope(),
    )
    assert status == "passed"
    assert findings == []


def test_a_dropped_file_path_fails_the_checkpoint():
    """The single most-reported summarisation failure, and the Hub can settle it outright."""
    status, findings = grade_probe(
        ProbeAnswers(
            files_changed=["hub/hub/worker.py"], task_ids=["t1"], unanswered_question_ids=["q1"]
        ),
        _envelope(),
    )
    assert status == "failed"
    assert findings == [
        {"dimension": "files_changed", "missing": ["hub/tests/test_worker.py"], "invented": []}
    ]


def test_an_invented_file_path_is_reported_separately_from_a_missing_one():
    """The two directions mean different things: a missing path is information the checkpoint
    lost, an invented one is information it made up."""
    status, findings = grade_probe(
        ProbeAnswers(
            files_changed=["hub/hub/worker.py", "hub/hub/imaginary.py"],
            task_ids=["t1"],
            unanswered_question_ids=["q1"],
        ),
        _envelope(),
    )
    assert status == "failed"
    assert findings[0]["missing"] == ["hub/tests/test_worker.py"]
    assert findings[0]["invented"] == ["hub/hub/imaginary.py"]


def test_path_separators_and_leading_dots_are_not_disagreements():
    """A reader echoing `./hub/hub/worker.py` or a Windows separator has not lost anything."""
    status, _ = grade_probe(
        ProbeAnswers(
            files_changed=["./hub/hub/worker.py", "hub\\tests\\test_worker.py"],
            task_ids=["t1"],
            unanswered_question_ids=["q1"],
        ),
        _envelope(),
    )
    assert status == "passed"


def test_every_dimension_is_graded_not_just_files():
    status, findings = grade_probe(
        ProbeAnswers(files_changed=[], task_ids=[], unanswered_question_ids=[]),
        _envelope(),
    )
    assert status == "failed"
    assert {f["dimension"] for f in findings} == {
        "files_changed",
        "task_ids",
        "unanswered_question_ids",
    }


# --------------------------------------------------------------------------- the render


@pytest.mark.asyncio
async def test_the_render_carries_the_computed_half_a_successor_needs(app):
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        db.add(Task(id="t1", project_id=PROJECT, title="Wire it up", assignee=AGENT))
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
        await db.commit()
        envelope = await compute_envelope(db, conversation)
        envelope.files_changed = ["hub/hub/worker.py"]
        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=envelope,
            body=render_body(CheckpointBody(**GOOD_BODY), notes_incorporated=False),
        )
        rendered = render_checkpoint(checkpoint)

    assert "hub/hub/worker.py" in rendered
    assert "t1" in rendered and "Wire it up" in rendered
    assert "q1" in rendered and "Which database?" in rendered
    # The task-scope caveat travels with the artifact, not just the row.
    assert "not specific to this one" in rendered
    assert "Run pytest hub/tests/." in rendered


@pytest.mark.asyncio
async def test_an_unwritten_checkpoint_renders_saying_its_written_half_is_missing(app):
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="run_failure",
            envelope=await compute_envelope(db, conversation),
            body=None,
        )
        rendered = render_checkpoint(checkpoint)

    assert "generation produced nothing usable" in rendered


# --------------------------------------------------------------------------- end to end


@pytest.mark.asyncio
async def test_a_generated_checkpoint_that_reads_faithfully_is_ready(app, monkeypatch):
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        db.add(
            AgentOutput(
                id="o1",
                project_id=PROJECT,
                agent=AGENT,
                conversation_id="conv-1",
                content="I added the column.",
                kind="text",
            )
        )
        db.add(Run(id="run-1", project_id=PROJECT, agent=AGENT, conversation_id="conv-1"))
        await db.commit()

        _patch_cli(
            monkeypatch,
            [
                _claude_stdout(GOOD_BODY),
                _claude_stdout(
                    {"files_changed": [], "task_ids": [], "unanswered_question_ids": []}
                ),
            ],
        )
        checkpoint = await generate_checkpoint(
            db, conversation, trigger="operator", cli="claude", model="claude-haiku-4-5-20251001"
        )

    assert checkpoint.status == "ready"
    assert checkpoint.probe_status == "passed"
    assert checkpoint.probe_findings is None
    assert "Add a column and its migration." in checkpoint.body


@pytest.mark.asyncio
async def test_a_checkpoint_whose_reading_disagrees_with_the_database_is_failed(app, monkeypatch):
    """The rule that replaces "the run stopped". A record existing is not readiness."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        db.add(Task(id="t1", project_id=PROJECT, title="Wire it up", assignee=AGENT))
        await db.commit()

        _patch_cli(
            monkeypatch,
            [
                _claude_stdout(GOOD_BODY),
                # The reader saw no task, but the database has one assigned.
                _claude_stdout(
                    {"files_changed": [], "task_ids": [], "unanswered_question_ids": []}
                ),
            ],
        )
        checkpoint = await generate_checkpoint(
            db, conversation, trigger="operator", cli="claude", model="claude-haiku-4-5-20251001"
        )

    assert checkpoint.status == "failed"
    assert checkpoint.probe_status == "failed"
    assert checkpoint.probe_findings[0]["dimension"] == "task_ids"
    assert checkpoint.probe_findings[0]["missing"] == ["t1"]


@pytest.mark.asyncio
async def test_a_worker_that_returns_nothing_still_produces_a_record(app, monkeypatch):
    """Generation failing degrades the record; it does not prevent it. This inverts the previous
    design, in which the agent was authoritative and the Hub hoped."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        db.add(Task(id="t1", project_id=PROJECT, title="Still open", assignee=AGENT))
        await db.commit()

        _patch_cli(monkeypatch, ["not json at all"])
        checkpoint = await generate_checkpoint(
            db, conversation, trigger="context_pressure", cli="claude"
        )

    assert checkpoint.status == "unwritten"
    assert checkpoint.body is None
    # The computed half survived, which is the half that can be checked.
    assert checkpoint.tasks["items"][0]["title"] == "Still open"
    # No probe runs on a checkpoint with nothing to read.
    assert checkpoint.probe_status is None


@pytest.mark.asyncio
async def test_a_probe_that_cannot_run_leaves_the_checkpoint_ready(app, monkeypatch):
    """An unrunnable probe is the Hub's failure, not the checkpoint's. Failing a checkpoint
    because the grader was unavailable would recreate, in the other direction, a status that
    reports something other than what it names."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        _patch_cli(monkeypatch, [_claude_stdout(GOOD_BODY), "the probe CLI fell over"])
        checkpoint = await generate_checkpoint(db, conversation, trigger="operator", cli="claude")

    assert checkpoint.status == "ready"
    assert checkpoint.probe_status is None


@pytest.mark.asyncio
async def test_both_calls_are_accounted_for_under_their_own_prompt_versions(app, monkeypatch):
    """Generation and probing are separate invocations with separate prompts, so a change in
    either is attributable."""
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        _patch_cli(
            monkeypatch,
            [
                _claude_stdout(GOOD_BODY),
                _claude_stdout(
                    {"files_changed": [], "task_ids": [], "unanswered_question_ids": []}
                ),
            ],
        )
        checkpoint = await generate_checkpoint(db, conversation, trigger="operator", cli="claude")
        rows = (
            (await db.execute(select(WorkerInvocation).order_by(WorkerInvocation.created_at)))
            .scalars()
            .all()
        )

    versions = {(row.kind, row.prompt_version) for row in rows}
    assert versions == {
        ("checkpoint", CHECKPOINT_PROMPT_VERSION),
        ("checkpoint_probe", PROBE_PROMPT_VERSION),
    }
    assert checkpoint.worker_invocation_id in {row.id for row in rows}


@pytest.mark.asyncio
async def test_a_second_checkpoint_does_not_replay_what_the_first_already_covered(app, monkeypatch):
    """Anchoring, from the prompt's side. Both halves of the exchange are bounded by when the
    anchor was taken — filtering only the agent's outputs would replay every operator message on
    every subsequent checkpoint."""
    from datetime import datetime, timedelta, timezone

    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, stdout=_claude_stdout(GOOD_BODY), stderr="")

    # Timestamps are set explicitly rather than left to the wall clock. Letting them fall where
    # they may made this test pass alone and fail under a full sweep: the machine's tick is
    # coarse enough that "written after the checkpoint" and "written in the same instant as the
    # checkpoint" are not reliably distinguishable, which is a property of the clock and not the
    # behaviour under test.
    now = datetime.now(timezone.utc)

    async with async_session_factory() as db:
        conversation = await _conversation(db)
        db.add(
            AgentOutput(
                id="o1",
                project_id=PROJECT,
                agent=AGENT,
                conversation_id="conv-1",
                content="EARLY TURN, already summarised",
                kind="text",
                timestamp=now - timedelta(minutes=10),
            )
        )
        await db.commit()

        monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
        monkeypatch.setattr(subprocess, "run", fake_run)
        first = await generate_checkpoint(
            db, conversation, trigger="operator", cli="claude", probe=False
        )
        first.created_at = now - timedelta(minutes=5)
        await db.commit()

        db.add(
            AgentOutput(
                id="o2",
                project_id=PROJECT,
                agent=AGENT,
                conversation_id="conv-1",
                content="LATER TURN, new",
                kind="text",
                timestamp=now,
            )
        )
        await db.commit()
        await generate_checkpoint(db, conversation, trigger="operator", cli="claude", probe=False)

    first_prompt, second_prompt = captured[0], captured[1]
    assert "EARLY TURN" in first_prompt
    assert "LATER TURN" not in first_prompt
    assert "LATER TURN" in second_prompt
    assert "EARLY TURN" not in second_prompt
    # And the second is handed its predecessor to carry forward from.
    assert "previous checkpoint" in second_prompt


@pytest.mark.asyncio
async def test_a_turn_recorded_in_the_same_instant_as_the_checkpoint_is_not_lost(app, monkeypatch):
    """The boundary is inclusive, and it has to be.

    A turn whose timestamp compares equal to the anchor's would, under a strict `>`, be dropped
    from this checkpoint and from every later one too — it is only ever compared against a newer
    anchor, so it is never picked up again. Including it twice is a redundancy; losing it is a
    hole. This is not a hypothetical: leaving these timestamps to the wall clock made the
    anchoring test above pass alone and fail under a full sweep.
    """
    from datetime import datetime, timezone

    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, stdout=_claude_stdout(GOOD_BODY), stderr="")

    instant = datetime.now(timezone.utc)

    async with async_session_factory() as db:
        conversation = await _conversation(db)
        monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
        monkeypatch.setattr(subprocess, "run", fake_run)

        first = await generate_checkpoint(
            db, conversation, trigger="operator", cli="claude", probe=False
        )
        first.created_at = instant
        db.add(
            AgentOutput(
                id="o-boundary",
                project_id=PROJECT,
                agent=AGENT,
                conversation_id="conv-1",
                content="BOUNDARY TURN",
                kind="text",
                timestamp=instant,
            )
        )
        await db.commit()

        await generate_checkpoint(db, conversation, trigger="operator", cli="claude", probe=False)

    assert "BOUNDARY TURN" in captured[1]


# --------------------------------------------------------------------------- blind resume


@pytest.mark.asyncio
async def test_a_reader_given_only_the_checkpoint_can_answer_the_probe(app, monkeypatch):
    """Task 6.6, the acceptance test the control-plane literature calls a blind resume.

    The reader sees the rendered checkpoint and nothing else — no transcript, no database, no
    predecessor conversation. It must be able to answer the questions the Hub can already settle,
    because if it cannot, the artifact does not carry what a successor needs and "ready" would be
    a claim about a document nobody can use.
    """
    seen_by_probe = {}

    def fake_run(cmd, **kwargs):
        prompt = cmd[-1]
        if "You have not seen the conversation" in prompt:
            seen_by_probe["prompt"] = prompt
            # Answer strictly from what the prompt contains — which is the whole point.
            files = [line[2:] for line in prompt.splitlines() if line.startswith("- hub/")]
            tasks = [
                line.split(" — ")[0][2:]
                for line in prompt.splitlines()
                if line.startswith("- t") and " — " in line
            ]
            questions = [
                line.split(" — ")[0][2:]
                for line in prompt.splitlines()
                if line.startswith("- q") and " — " in line
            ]
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=_claude_stdout(
                    {
                        "files_changed": files,
                        "task_ids": tasks,
                        "unanswered_question_ids": questions,
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout=_claude_stdout(GOOD_BODY), stderr="")

    async with async_session_factory() as db:
        conversation = await _conversation(db)
        db.add(Task(id="t1", project_id=PROJECT, title="Finish the worker", assignee=AGENT))
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
        await db.commit()

        monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
        monkeypatch.setattr(subprocess, "run", fake_run)
        checkpoint = await generate_checkpoint(db, conversation, trigger="operator", cli="claude")

    assert checkpoint.status == "ready"
    assert checkpoint.probe_status == "passed"
    # The reader was genuinely blind: its prompt carried the checkpoint and no transcript.
    assert "I added the column" not in seen_by_probe["prompt"]
    # And the artifact carried an executable first step, which is what a successor starts from.
    assert "Run pytest hub/tests/." in checkpoint.body
