"""A checkpoint's title and summary: written in the same call, asked once more, made by the Hub
when they cannot be had (`every-checkpoint-findable-and-readable`, FR-9, FR-11, FR-13).

Every test stubs the CLI at `subprocess.run`, so each asking is a real `run_worker` call recorded
as a `WorkerInvocation`, and the prompts the model would have read are captured as sent.
"""

import subprocess

import pytest
from sqlalchemy import select

from hub.checkpoint_generation import (
    MADE_BY_HUB_FROM_BODY,
    MADE_BY_HUB_FROM_FACTS,
    MADE_BY_MODEL,
    SUMMARY_MAX_CHARS,
    TITLE_MAX_CHARS,
    TITLE_MAX_WORDS,
    generate_checkpoint,
    plain_text,
    render_checkpoint,
    summary_from_text,
    title_from_text,
    title_problem,
)
from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput, Run, Task, WorkerInvocation

from .test_checkpoint_generation import AGENT, GOOD_BODY, PROJECT, _claude_stdout, _conversation

PROBE_PASS = {"files_changed": [], "task_ids": [], "unanswered_question_ids": []}

SECTIONS = {key: value for key, value in GOOD_BODY.items() if key not in ("title", "summary")}


def _stub(monkeypatch, answers):
    """Answer successive spawns in order. Each answer is stdout, or `(returncode, stdout)`.
    Returns the list of prompts sent, one per spawn, in order."""
    queue = list(answers)
    prompts = []

    def fake_run(cmd, **kwargs):
        prompts.append(" ".join(str(part) for part in cmd) + "\n" + (kwargs.get("input") or ""))
        answer = queue.pop(0) if queue else ""
        code, stdout = answer if isinstance(answer, tuple) else (0, answer)
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="it fell over")

    monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(subprocess, "run", fake_run)
    return prompts


async def _generation_kinds(db):
    rows = (
        (await db.execute(select(WorkerInvocation).order_by(WorkerInvocation.created_at)))
        .scalars()
        .all()
    )
    return [row.kind for row in rows]


async def _with_runs(db):
    conversation = await _conversation(db)
    for index in (1, 2):
        db.add(Run(id=f"run-{index}", project_id=PROJECT, agent=AGENT, conversation_id="conv-1"))
        db.add(
            AgentOutput(
                id=f"o{index}",
                project_id=PROJECT,
                agent=AGENT,
                conversation_id="conv-1",
                run_id=f"run-{index}",
                content=f"Turn {index}: I worked on the column.",
                kind="text",
            )
        )
    await db.commit()
    return conversation


def _within_limits(title, summary):
    assert title and len(title.split()) <= TITLE_MAX_WORDS and len(title) <= TITLE_MAX_CHARS
    assert summary and len(summary) <= SUMMARY_MAX_CHARS


# --------------------------------------------------------------------------- the rules


@pytest.mark.parametrize(
    "title, summary, expected",
    [
        ("Added the column", "One sentence.", None),
        (None, "One sentence.", "the title was missing"),
        ("Added the column", "  ", "the summary was missing"),
        ("one two three four five six seven eight nine", "Fine.", "has 9 words"),
        ("x" * 61, "Fine.", "has 61 characters"),
        ("Fine", "One. Two. Three.", "has 3 sentences"),
        ("Fine", "y" * 301, "has 301 characters"),
    ],
)
def test_title_problem_names_what_is_wrong(title, summary, expected):
    problem = title_problem(title, summary)
    if expected is None:
        assert problem is None
    else:
        assert expected in problem


def test_first_words_stay_within_both_title_limits():
    text = plain_text(
        "## Objective\n\nRefactor the extraordinarily long-winded configuration loader"
    )
    title = title_from_text(text)
    assert title.startswith("Refactor the")
    assert len(title.split()) <= TITLE_MAX_WORDS and len(title) <= TITLE_MAX_CHARS
    assert "#" not in title
    summary = summary_from_text("First. Second. Third.")
    assert summary == "First. Second."


# --------------------------------------------------------------------------- FR-11


@pytest.mark.asyncio
async def test_an_accepted_first_answer_carries_title_and_summary_in_one_call(app, monkeypatch):
    """title-in-same-call: one generation invocation (plus the probe as before)."""
    async with async_session_factory() as db:
        conversation = await _with_runs(db)
        prompts = _stub(monkeypatch, [_claude_stdout(GOOD_BODY), _claude_stdout(PROBE_PASS)])
        checkpoint = await generate_checkpoint(db, conversation, trigger="operator", cli="claude")
        kinds = await _generation_kinds(db)

    assert kinds == ["checkpoint", "checkpoint_probe"]
    assert '"title": string' in prompts[0] and '"summary": string' in prompts[0]
    assert checkpoint.title == GOOD_BODY["title"]
    assert checkpoint.summary == GOOD_BODY["summary"]
    _within_limits(checkpoint.title, checkpoint.summary)
    assert checkpoint.title_made_by == MADE_BY_MODEL
    assert checkpoint.title_reason is None and checkpoint.unreadable_answer is None
    assert checkpoint.status == "ready" and checkpoint.probe_status == "passed"
    assert f"Title: {GOOD_BODY['title']}" in render_checkpoint(checkpoint)


# --------------------------------------------------------------------------- FR-13


@pytest.mark.asyncio
async def test_a_rejected_answer_is_asked_for_again_naming_what_was_wrong(app, monkeypatch):
    """rejected-answer-asked-again."""
    second = {**GOOD_BODY, "objective": "The second answer's objective."}
    async with async_session_factory() as db:
        conversation = await _with_runs(db)
        prompts = _stub(
            monkeypatch,
            [_claude_stdout(SECTIONS), _claude_stdout(second), _claude_stdout(PROBE_PASS)],
        )
        checkpoint = await generate_checkpoint(db, conversation, trigger="operator", cli="claude")
        kinds = await _generation_kinds(db)

    assert kinds == ["checkpoint", "checkpoint", "checkpoint_probe"]
    assert "previous answer was rejected" not in prompts[0]
    assert "previous answer was rejected: the title was missing" in prompts[1]
    assert "The second answer's objective." in checkpoint.body
    assert checkpoint.title == GOOD_BODY["title"]
    assert checkpoint.summary == GOOD_BODY["summary"]
    assert checkpoint.title_made_by == MADE_BY_MODEL
    assert checkpoint.title_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad, reason",
    [
        (SECTIONS, "the title was missing"),
        ({**GOOD_BODY, "summary": ""}, "the summary was missing"),
        (
            {
                **GOOD_BODY,
                "title": "one two three four five six seven eight nine ten eleven twelve",
            },
            "the title has 12 words",
        ),
    ],
    ids=["no-title", "empty-summary", "twelve-word-title"],
)
async def test_two_rejected_answers_fall_back_to_the_bodys_first_words(
    app, monkeypatch, bad, reason
):
    """rejected-twice-falls-back."""
    async with async_session_factory() as db:
        conversation = await _with_runs(db)
        _stub(
            monkeypatch,
            [_claude_stdout(bad), _claude_stdout(bad), _claude_stdout(PROBE_PASS)],
        )
        checkpoint = await generate_checkpoint(db, conversation, trigger="operator", cli="claude")
        kinds = await _generation_kinds(db)

    assert kinds.count("checkpoint") == 2
    # Its readable body is kept, and probed as before.
    assert checkpoint.status == "ready"
    assert GOOD_BODY["objective"] in checkpoint.body
    assert checkpoint.title == "Add a column and its migration"
    assert checkpoint.summary.startswith("Add a column and its migration.")
    _within_limits(checkpoint.title, checkpoint.summary)
    assert checkpoint.title_made_by == MADE_BY_HUB_FROM_BODY
    assert reason in checkpoint.title_reason
    assert checkpoint.title_reason.startswith("first answer:")
    assert "second answer:" in checkpoint.title_reason
    assert checkpoint.unreadable_answer is None
    assert "(made by the Hub)" in render_checkpoint(checkpoint)


@pytest.mark.asyncio
async def test_two_unreadable_answers_are_titled_from_the_hubs_facts(app, monkeypatch):
    """unreadable-titled-from-facts, the prose pair: raw text kept aside, never the body."""
    prose = "Sure! I looked at the conversation and it seems fine overall."
    async with async_session_factory() as db:
        conversation = await _with_runs(db)
        db.add(Task(id="t1", project_id=PROJECT, title="Still open", assignee=AGENT))
        await db.commit()
        prompts = _stub(monkeypatch, [_claude_stdout(prose), _claude_stdout(prose)])
        checkpoint = await generate_checkpoint(
            db, conversation, trigger="task_completion", cli="claude"
        )
        kinds = await _generation_kinds(db)

    assert kinds == ["checkpoint", "checkpoint"]  # nothing to probe
    assert "previous answer was rejected: the answer could not be read" in prompts[1]
    assert checkpoint.status == "unwritten" and checkpoint.body is None
    date = checkpoint.created_at.date().isoformat()
    assert checkpoint.title == f"{AGENT}: task finished, {date}"
    _within_limits(checkpoint.title, checkpoint.summary)
    assert checkpoint.title_made_by == MADE_BY_HUB_FROM_FACTS
    assert "could not be read" in checkpoint.title_reason
    assert checkpoint.unreadable_answer == prose
    # The Hub's own record is kept, and the summary counts it.
    assert checkpoint.tasks["items"][0]["title"] == "Still open"
    assert checkpoint.citations
    assert "1 task(s)" in checkpoint.summary
    assert prose not in render_checkpoint(checkpoint)


@pytest.mark.asyncio
async def test_a_worker_never_reached_is_asked_twice_and_keeps_no_raw_text(app, monkeypatch):
    """unreadable-titled-from-facts, the unreachable pair."""
    async with async_session_factory() as db:
        conversation = await _with_runs(db)
        prompts = _stub(monkeypatch, [(1, ""), (1, "")])
        checkpoint = await generate_checkpoint(db, conversation, trigger="operator", cli="claude")
        kinds = await _generation_kinds(db)

    assert kinds == ["checkpoint", "checkpoint"]
    # A model never reached has nothing to be told it got wrong.
    assert "previous answer was rejected" not in prompts[1]
    assert checkpoint.status == "unwritten"
    assert checkpoint.title.startswith(f"{AGENT}: operator asked, ")
    assert checkpoint.title_made_by == MADE_BY_HUB_FROM_FACTS
    assert "no answer was returned (nonzero_exit" in checkpoint.title_reason
    assert checkpoint.unreadable_answer is None


@pytest.mark.asyncio
async def test_a_readable_answer_then_an_unreadable_one_keeps_the_readable_body(app, monkeypatch):
    """Every part of the answer that could be read is kept, whichever asking it came from."""
    async with async_session_factory() as db:
        conversation = await _with_runs(db)
        _stub(
            monkeypatch,
            [_claude_stdout(SECTIONS), _claude_stdout("not json"), _claude_stdout(PROBE_PASS)],
        )
        checkpoint = await generate_checkpoint(db, conversation, trigger="operator", cli="claude")

    assert checkpoint.status == "ready"
    assert GOOD_BODY["objective"] in checkpoint.body
    assert checkpoint.title_made_by == MADE_BY_HUB_FROM_BODY
    assert "first answer: the title was missing" in checkpoint.title_reason
    assert "second answer: the answer could not be read" in checkpoint.title_reason
    assert checkpoint.unreadable_answer is None


# --------------------------------------------------------------------------- FR-9 (storage half)


@pytest.mark.asyncio
async def test_a_probe_failure_keeps_its_findings_beside_a_title(app, monkeypatch):
    """failure-reason-shown, the third case: a checkpoint whose probe found something missing
    keeps the model's title and the findings that name what was missing."""
    async with async_session_factory() as db:
        conversation = await _with_runs(db)
        db.add(Task(id="t1", project_id=PROJECT, title="Wire it up", assignee=AGENT))
        await db.commit()
        _stub(monkeypatch, [_claude_stdout(GOOD_BODY), _claude_stdout(PROBE_PASS)])
        checkpoint = await generate_checkpoint(db, conversation, trigger="operator", cli="claude")

    assert checkpoint.status == "failed"
    assert checkpoint.title == GOOD_BODY["title"]
    assert checkpoint.probe_findings == [
        {"dimension": "task_ids", "missing": ["t1"], "invented": []}
    ]
