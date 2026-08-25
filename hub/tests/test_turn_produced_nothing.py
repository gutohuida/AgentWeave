"""F38: a turn given a document to write, that wrote none and asked nothing.

Every fact these exercise is structured state. The retired backstop that read a run's final text
for something question-shaped is deliberately not reinstated — `test_prose_is_never_the_evidence`
is what holds that true.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import (
    EventLog,
    InboundQueueEntry,
    Question,
    Run,
    SpecDocument,
    SpecDocumentEvent,
)
from hub.run_divergence import evaluate_run_end

DOC = "spec/changes/teal-manticore/spec.html"


def _content_event(document_id: str, suffix: str) -> SpecDocumentEvent:
    return SpecDocumentEvent(
        id=f"spdocev-{document_id}-{suffix}",
        document_id=document_id,
        project_id="proj-test",
        kind="content",
        actor_kind="operator",
        actor="operator",
        origin="submission",
    )


async def _setup(
    run_id: str,
    *,
    document_path=DOC,
    written=False,
    named_document=True,
    asked=False,
    phase="exploring",
):
    """Build the document the way the product builds one, which is the whole point (F41).

    `create_document` is followed immediately by a scaffold `save_document` on both creation paths,
    so a real document always carries a `content_digest` **and** exactly one `content` event before
    any agent sees it. A fixture that left the digest null described a state nothing produces, and
    six tests passed against a check that could never fire in production.

    `written=True` adds the second `content` event — the first time anybody actually wrote
    something into the document.
    """
    document_id = f"spdoc-{run_id}"
    async with async_session_factory() as session:
        session.add(
            Run(id=run_id, project_id="proj-test", agent="author", status="completed"),
        )
        if document_path is not None:
            session.add(
                SpecDocument(
                    id=document_id,
                    project_id="proj-test",
                    path=document_path,
                    title="Spread fairness",
                    phase=phase,
                    # Populated exactly as the scaffold write populates it. Never null on a real row.
                    content_digest="0" * 64,
                )
            )
            await session.flush()
            session.add(_content_event(document_id, "scaffold"))
            if written:
                session.add(_content_event(document_id, "authored"))
        session.add(
            InboundQueueEntry(
                id=f"entry-{run_id}",
                project_id="proj-test",
                agent="author",
                origin_type="operator",
                content="Write the spec",
                hop_depth=0,
                state="delivered",
                delivered_in_run_id=run_id,
                spec_document=document_path if named_document else None,
            )
        )
        if asked:
            session.add(
                Question(
                    id=f"q-{run_id}",
                    project_id="proj-test",
                    from_agent="author",
                    question="How does spread() learn about all staff?",
                    created_by_run_id=run_id,
                    blocking=True,
                )
            )
        await session.commit()


async def _noted(run_id: str) -> bool:
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == "turn_produced_nothing")
                )
            )
            .scalars()
            .all()
        )
    return any((row.data or {}).get("run_id") == run_id for row in rows)


@pytest.mark.asyncio
async def test_a_turn_that_wrote_nothing_and_asked_nothing_is_recorded(app):
    """The F38 reproduction. The author diagnosed the bug correctly, asked four good questions as
    chat text, and ended the turn. The specification was never written."""
    await _setup("run-f38-silent")

    await evaluate_run_end("run-f38-silent")

    assert await _noted("run-f38-silent")


@pytest.mark.asyncio
async def test_a_turn_that_asked_is_not_recorded(app):
    """An agent that stopped to ask is not an agent that produced nothing — the same reasoning the
    divergence check already applies to a task."""
    await _setup("run-f38-asked", asked=True)

    await evaluate_run_end("run-f38-asked")

    assert not await _noted("run-f38-asked")


@pytest.mark.asyncio
async def test_a_turn_that_wrote_the_document_is_not_recorded(app):
    """A second `content` event is the first time anybody wrote anything into the document —
    the deliverable having advanced."""
    await _setup("run-f38-wrote", written=True)

    await evaluate_run_end("run-f38-wrote")

    assert not await _noted("run-f38-wrote")


@pytest.mark.asyncio
async def test_a_turn_with_no_document_is_not_a_candidate(app):
    """Most turns are conversation, and a reply that produces no row is the correct outcome for
    one. Recording a non-outcome for every chat turn would be noise."""
    await _setup("run-f38-chat", named_document=False)

    await evaluate_run_end("run-f38-chat")

    assert not await _noted("run-f38-chat")


@pytest.mark.asyncio
async def test_prose_is_never_the_evidence(app):
    """The constraint that matters most.

    A turn whose final text reads exactly like a question, but which wrote its document, records
    nothing — because the text is never read. The backstop that inspected prose was retired on
    2026-08-20 and migration 0082 dropped its table; this must not reintroduce it by another route.
    """
    await _setup("run-f38-prose", written=True)

    async with async_session_factory() as session:
        run = await session.get(Run, "run-f38-prose")
        run.error = "What I need to clarify before writing the spec: 1. Interface? 2. Scope?"
        await session.commit()

    await evaluate_run_end("run-f38-prose")

    assert not await _noted("run-f38-prose")


@pytest.mark.asyncio
async def test_the_record_names_what_was_not_written(app):
    """A note the operator cannot act on is not worth writing."""
    await _setup("run-f38-detail")

    await evaluate_run_end("run-f38-detail")

    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == "turn_produced_nothing")
                )
            )
            .scalars()
            .all()
        )
    payload = next(r.data for r in rows if (r.data or {}).get("run_id") == "run-f38-detail")
    assert payload["spec_document"] == DOC
    assert payload["agent"] == "author"
    assert payload["document_phase"] == "exploring"


@pytest.mark.asyncio
async def test_a_populated_digest_alone_does_not_mean_the_document_was_written(app):
    """F41, pinned directly: the check must not gate on `content_digest`.

    Both creation paths write a scaffold payload the instant the row exists, so every real document
    carries a digest before any agent sees it — measured on the live database, 50 documents, 0
    without one. Gating on it made the whole check unreachable, and the six tests above passed
    anyway because the fixture built a null-digest document the product never produces.

    The original subject is the proof: `spec/changes/teal-manticore/spec.html`, the document the
    author was given and never wrote, records `created` and `content` at the same microsecond.
    """
    await _setup("run-f41-digest")

    async with async_session_factory() as session:
        document = await session.get(SpecDocument, "spdoc-run-f41-digest")
        assert document.content_digest, "the fixture must build the shape the product builds"
        writes = (
            (
                await session.execute(
                    select(SpecDocumentEvent).where(
                        SpecDocumentEvent.document_id == "spdoc-run-f41-digest",
                        SpecDocumentEvent.kind == "content",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(writes) == 1, "a document nobody wrote into carries exactly the scaffold write"

    await evaluate_run_end("run-f41-digest")

    assert await _noted("run-f41-digest")
