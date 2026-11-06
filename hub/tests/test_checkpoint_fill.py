"""The one-time fill of checkpoints taken before titles existed
(`every-checkpoint-findable-and-readable`, FR-12).

The CLI is stubbed at `subprocess.run`, so each asking is a real `run_worker` call recorded as a
`WorkerInvocation`. Each checkpoint's body carries a marker, and the stub answers by the marker in
the prompt it was sent: which checkpoint was asked, and that it was sent its own body only, are
read from what the model would have read.
"""

import re
import subprocess
import time

import pytest
from sqlalchemy import select
from starlette.testclient import TestClient

from hub import checkpoint_fill
from hub.checkpoint_fill import FILL_KIND, fill_untitled_checkpoints, run_fill
from hub.checkpoint_generation import (
    MADE_BY_HUB_FROM_BODY,
    MADE_BY_HUB_FROM_FACTS,
    MADE_BY_MODEL,
    SUMMARY_MAX_CHARS,
    TITLE_MAX_CHARS,
    TITLE_MAX_WORDS,
)
from hub.db.engine import async_session_factory
from hub.db.models import Checkpoint, Conversation, Project, Runner, WorkerInvocation

from .test_checkpoint_generation import AGENT, PROJECT, _claude_stdout

RUNNER = "runner-cheap"
_MARK = re.compile(r"MARK-(\w+)")


def _body(mark: str) -> str:
    return (
        "## Objective\n\n"
        f"Move the importer onto the new schema for MARK-{mark}. It is the second attempt.\n\n"
        "## Current state\n\nHalf the tables are done.\n"
    )


async def _seed(db, marks, *, runner=True, bodies=None):
    """A project with (or without) a checkpoint runner, and one untitled checkpoint per mark,
    in *marks* order."""
    if runner:
        db.add(Runner(id=RUNNER, project_id=PROJECT, name="Cheap", cli="claude", model="haiku"))
        project = await db.get(Project, PROJECT)
        project.checkpoint_runner_id = RUNNER
    db.add(Conversation(id="conv-1", project_id=PROJECT, agent=AGENT, lifecycle="open"))
    await db.commit()
    for mark in marks:
        body = (bodies or {}).get(mark, _body(mark))
        db.add(
            Checkpoint(
                id=f"ckpt-{mark}",
                project_id=PROJECT,
                conversation_id="conv-1",
                agent=AGENT,
                trigger="task_completion",
                status="ready" if body else "unwritten",
                lineage_id=f"ckpt-{mark}",
                body=body,
            )
        )
        await db.commit()


def _stub(monkeypatch, answers):
    """Answer each spawn from *answers*[mark], in order, by the marker in its prompt. An answer is
    stdout or `(returncode, stdout)`. Returns the marks asked, one per spawn, and the prompts."""
    queues = {mark: list(queue) for mark, queue in answers.items()}
    asked, prompts = [], []

    def fake_run(cmd, **kwargs):
        prompt = " ".join(str(part) for part in cmd) + "\n" + (kwargs.get("input") or "")
        marks = set(_MARK.findall(prompt))
        assert len(marks) == 1, f"a prompt carried another checkpoint's body: {marks}"
        mark = marks.pop()
        asked.append(mark)
        prompts.append(prompt)
        queue = queues.get(mark) or []
        answer = queue.pop(0) if queue else (1, "")
        code, stdout = answer if isinstance(answer, tuple) else (0, answer)
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="it fell over")

    monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(subprocess, "run", fake_run)
    return asked, prompts


def _ok(title="Moved the importer schema", summary="Half the tables moved. The rest wait."):
    return _claude_stdout({"title": title, "summary": summary})


LONG_TITLE = "one two three four five six seven eight nine ten eleven twelve"
UNREACHABLE = (1, "")


async def _checkpoints(db):
    rows = await db.execute(select(Checkpoint).order_by(Checkpoint.sequence))
    return {row.id.removeprefix("ckpt-"): row for row in rows.scalars().all()}


async def _fill_kinds(db):
    rows = await db.execute(select(WorkerInvocation.kind))
    return list(rows.scalars().all())


def _within_limits(checkpoint):
    title, summary = checkpoint.title, checkpoint.summary
    assert title and len(title.split()) <= TITLE_MAX_WORDS and len(title) <= TITLE_MAX_CHARS
    assert summary and len(summary) <= SUMMARY_MAX_CHARS


# --------------------------------------------------------------------------- fill-every-existing


@pytest.mark.asyncio
async def test_the_fill_gives_every_untitled_checkpoint_a_title_from_its_own_body(app, monkeypatch):
    """fill-every-existing: accepted at once, accepted on the second asking, rejected twice, and
    unreadable twice -- every one ends with a title and summary within the limits."""
    async with async_session_factory() as db:
        await _seed(db, ["first", "second", "rejected", "prose"])
    asked, prompts = _stub(
        monkeypatch,
        {
            "first": [_ok()],
            "second": [_claude_stdout({"summary": "No title here."}), _ok("Second time right")],
            "rejected": [_ok(LONG_TITLE), _ok(LONG_TITLE)],
            "prose": [_claude_stdout("Sure, looks good."), _claude_stdout("Still fine.")],
        },
    )
    monkeypatch.setattr(checkpoint_fill, "FIRST_PASS_DELAY_SECONDS", 0)

    await run_fill()

    async with async_session_factory() as db:
        rows = await _checkpoints(db)
        kinds = await _fill_kinds(db)

    assert asked == ["first", "second", "second", "rejected", "rejected", "prose", "prose"]
    assert kinds == [FILL_KIND] * 7
    # Sent its own body, and only that: the stub refuses a prompt naming two markers.
    assert "Move the importer onto the new schema for MARK-first" in prompts[0]
    assert "previous answer was rejected: the title was missing" in prompts[2]
    for row in rows.values():
        _within_limits(row)

    assert rows["first"].title == "Moved the importer schema"
    assert rows["first"].title_made_by == MADE_BY_MODEL
    assert rows["second"].title == "Second time right"
    assert rows["second"].title_made_by == MADE_BY_MODEL
    for mark in ("rejected", "prose"):
        assert rows[mark].title_made_by == MADE_BY_HUB_FROM_BODY
        assert rows[mark].title.startswith("Move the importer onto the new schema")
        assert rows[mark].title_reason
    assert "12 words" in rows["rejected"].title_reason
    assert "could not be read" in rows["prose"].title_reason
    # The body was not touched: the fill writes only what tells checkpoints apart.
    assert rows["first"].body == _body("first")


@pytest.mark.asyncio
async def test_a_checkpoint_with_no_body_is_titled_from_the_hubs_facts_without_asking(
    app, monkeypatch
):
    async with async_session_factory() as db:
        await _seed(db, ["empty"], bodies={"empty": None})
    asked, _ = _stub(monkeypatch, {})

    await fill_untitled_checkpoints()

    async with async_session_factory() as db:
        row = (await _checkpoints(db))["empty"]
    assert asked == []
    assert row.title.startswith(f"{AGENT}: task finished, ")
    assert row.title_made_by == MADE_BY_HUB_FROM_FACTS
    _within_limits(row)


# --------------------------------------------------------------------------- fill-runs-once


@pytest.mark.asyncio
async def test_a_second_start_asks_only_for_what_no_model_was_reached_for(app, monkeypatch):
    """fill-runs-once: the unreachable one comes first and stops nothing; a crash in one stops
    nothing; at the next start only the unreachable one is sent again."""
    async with async_session_factory() as db:
        await _seed(db, ["unreachable", "crash", "accepted", "fallback"])
    asked, _ = _stub(
        monkeypatch,
        {
            "unreachable": [UNREACHABLE, UNREACHABLE],
            "accepted": [_ok()],
            "fallback": [_ok(LONG_TITLE), _ok(LONG_TITLE)],
        },
    )
    real_fill_one = checkpoint_fill.fill_one

    async def fill_one(checkpoint_id):
        if checkpoint_id == "ckpt-crash":
            raise RuntimeError("the database went away for this one")
        return await real_fill_one(checkpoint_id)

    monkeypatch.setattr(checkpoint_fill, "fill_one", fill_one)

    report = await fill_untitled_checkpoints()

    async with async_session_factory() as db:
        rows = await _checkpoints(db)
    assert (report.filled, report.awaiting, report.failed) == (2, 1, 1)
    assert asked == ["unreachable", "unreachable", "accepted", "fallback", "fallback"]
    assert rows["unreachable"].title is None and rows["unreachable"].title_made_by is None
    assert rows["crash"].title is None
    assert rows["accepted"].title_made_by == MADE_BY_MODEL
    assert rows["fallback"].title_made_by == MADE_BY_HUB_FROM_BODY

    # The next start: the model can be reached now, and nothing crashes.
    monkeypatch.setattr(checkpoint_fill, "fill_one", real_fill_one)
    asked_again, _ = _stub(monkeypatch, {"unreachable": [_ok("Reached at last")], "crash": [_ok()]})

    report = await fill_untitled_checkpoints()

    async with async_session_factory() as db:
        rows = await _checkpoints(db)
    assert sorted(asked_again) == ["crash", "unreachable"]
    assert (report.filled, report.awaiting, report.failed) == (2, 0, 0)
    assert rows["unreachable"].title == "Reached at last"
    assert rows["accepted"].title_made_by == MADE_BY_MODEL
    assert rows["fallback"].title_made_by == MADE_BY_HUB_FROM_BODY

    # And once all are filled, a start sends nothing.
    asked_third, _ = _stub(monkeypatch, {})
    report = await fill_untitled_checkpoints()
    assert asked_third == [] and report.filled == 0


@pytest.mark.asyncio
async def test_a_project_with_no_checkpoint_runner_waits_without_spending(app, monkeypatch):
    async with async_session_factory() as db:
        await _seed(db, ["norunner"], runner=False)
    asked, _ = _stub(monkeypatch, {})

    report = await fill_untitled_checkpoints()

    async with async_session_factory() as db:
        row = (await _checkpoints(db))["norunner"]
    assert asked == [] and report.awaiting == 1
    assert row.title is None


@pytest.mark.asyncio
async def test_a_checkpoint_given_a_title_while_its_answer_was_awaited_keeps_it(app, monkeypatch):
    """Generation or a concurrent pass wrote a title meanwhile: the fill does not overwrite it."""
    async with async_session_factory() as db:
        await _seed(db, ["raced"])
    _stub(monkeypatch, {"raced": [_ok("From the fill")]})
    real_ask = checkpoint_fill.ask_for_checkpoint

    async def ask_then_race(**kwargs):
        answer = await real_ask(**kwargs)
        async with async_session_factory() as db:
            row = (await _checkpoints(db))["raced"]
            row.title, row.summary, row.title_made_by = "Written first", "Already.", MADE_BY_MODEL
            await db.commit()
        return answer

    monkeypatch.setattr(checkpoint_fill, "ask_for_checkpoint", ask_then_race)

    await fill_untitled_checkpoints()

    async with async_session_factory() as db:
        row = (await _checkpoints(db))["raced"]
    assert row.title == "Written first"


# --------------------------------------------------------------------------- started by the Hub


def test_the_hub_starts_the_fill_with_its_other_background_work(monkeypatch):
    """Without anyone asking: `lifespan` starts it, and stopping the Hub cancels it cleanly."""
    started, cancelled = [], []

    async def spy():
        import asyncio

        started.append(True)
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    monkeypatch.setattr(checkpoint_fill, "run_fill", spy)
    from hub.main import create_app

    with TestClient(create_app()):
        for _ in range(100):
            if started:
                break
            time.sleep(0.05)

    assert started == [True]
    assert cancelled == [True]
