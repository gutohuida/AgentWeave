"""Which commit a review turn is about — `2026-08-23-a-reviewer-can-see-the-work`, task group 2.

Design D5: the most recent evidence wins, and where earlier evidence named a different commit the
reviewer is *told* rather than silently handed the newest. A reviewer that knows the work moved can
ask why; one that does not cannot.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub import requirement_evidence
from hub.db.engine import async_session_factory
from hub.db.models import (
    EvidenceFootprint,
    RequirementEvidence,
    SpecDocument,
    SpecRequirement,
    Task,
)

NOW = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
async def _schema(app):
    """These tests talk to the session factory directly; `app` is what builds the schema."""
    yield


def ago(minutes: int) -> datetime:
    return NOW - timedelta(minutes=minutes)


async def _scaffold(session, *, task_id="task-1"):
    """A document, a requirement and a task — the rows evidence needs to hang off."""
    session.add(
        SpecDocument(
            id="doc-1",
            project_id="proj-test",
            path="spec/ledger.md",
            title="Ledger",
            phase="current",
            kind="capability",
        )
    )
    session.add(
        SpecRequirement(
            id="req-1",
            project_id="proj-test",
            document_id="doc-1",
            identifier="FR-1",
            key="fr-1",
            digest="d" * 64,
        )
    )
    session.add(
        Task(
            id=task_id,
            project_id="proj-test",
            title="Balance the ledger",
            status="completed",
        )
    )


async def _evidence(
    session,
    *,
    evidence_id: str,
    task_id: str = "task-1",
    commit: str = None,
    branch: str = "agentweave/builder",
    produced_at: datetime,
):
    session.add(
        RequirementEvidence(
            id=evidence_id,
            project_id="proj-test",
            requirement_id="req-1",
            task_id=task_id,
            digest="d" * 64,
            kind="commit",
            actor_kind="agent",
            actor="builder",
            summary="done",
            produced_at=produced_at,
        )
    )
    session.add(
        EvidenceFootprint(
            id=f"fp-{evidence_id}",
            project_id="proj-test",
            evidence_id=evidence_id,
            kind="git" if commit else "paths",
            commit_sha=commit,
            branch=branch if commit else None,
            observed_at=produced_at,
        )
    )


# ---------------------------------------------------------------------------
# task 2.3 — single evidence
# ---------------------------------------------------------------------------


async def test_a_single_piece_of_evidence_names_the_commit():
    async with async_session_factory() as session:
        await _scaffold(session)
        await _evidence(session, evidence_id="ev-1", commit="cad5d74", produced_at=ago(10))
        await session.commit()

        target = await requirement_evidence.commit_for_task_review(session, "task-1")

    assert target.resolved is True
    assert target.commit_sha == "cad5d74"
    assert target.evidence_id == "ev-1"
    assert target.branch == "agentweave/builder"
    assert target.earlier_commits == []
    assert target.refusal is None


# ---------------------------------------------------------------------------
# task 2.3 — two evidence rows naming different commits
# ---------------------------------------------------------------------------


async def test_the_newer_evidence_wins_and_the_older_commit_is_reported():
    async with async_session_factory() as session:
        await _scaffold(session)
        await _evidence(session, evidence_id="ev-42cad5d2", commit="aaaaaaa", produced_at=ago(30))
        await _evidence(session, evidence_id="ev-5d0273ad", commit="bbbbbbb", produced_at=ago(5))
        await session.commit()

        target = await requirement_evidence.commit_for_task_review(session, "task-1")

    assert target.commit_sha == "bbbbbbb"
    assert target.evidence_id == "ev-5d0273ad"
    assert [c.commit_sha for c in target.earlier_commits] == ["aaaaaaa"]
    assert target.earlier_commits[0].evidence_id == "ev-42cad5d2"


async def test_evidence_naming_the_same_commit_twice_is_not_reported_as_a_move():
    async with async_session_factory() as session:
        await _scaffold(session)
        await _evidence(session, evidence_id="ev-1", commit="cad5d74", produced_at=ago(30))
        await _evidence(session, evidence_id="ev-2", commit="cad5d74", produced_at=ago(5))
        await session.commit()

        target = await requirement_evidence.commit_for_task_review(session, "task-1")

    assert target.commit_sha == "cad5d74"
    assert target.earlier_commits == []


async def test_three_commits_are_reported_oldest_first():
    async with async_session_factory() as session:
        await _scaffold(session)
        await _evidence(session, evidence_id="ev-1", commit="aaaaaaa", produced_at=ago(30))
        await _evidence(session, evidence_id="ev-2", commit="bbbbbbb", produced_at=ago(20))
        await _evidence(session, evidence_id="ev-3", commit="ccccccc", produced_at=ago(10))
        await session.commit()

        target = await requirement_evidence.commit_for_task_review(session, "task-1")

    assert target.commit_sha == "ccccccc"
    assert [c.commit_sha for c in target.earlier_commits] == ["aaaaaaa", "bbbbbbb"]


async def test_evidence_for_a_different_task_is_not_considered():
    async with async_session_factory() as session:
        await _scaffold(session)
        await _scaffold_second_task(session)
        await _evidence(session, evidence_id="ev-1", commit="aaaaaaa", produced_at=ago(30))
        await _evidence(
            session, evidence_id="ev-2", task_id="task-2", commit="bbbbbbb", produced_at=ago(5)
        )
        await session.commit()

        target = await requirement_evidence.commit_for_task_review(session, "task-1")

    assert target.commit_sha == "aaaaaaa"
    assert target.earlier_commits == []


async def _scaffold_second_task(session):
    session.add(Task(id="task-2", project_id="proj-test", title="Another", status="completed"))


# ---------------------------------------------------------------------------
# task 2.2 / 2.3 — a stated refusal, not an exception and not a guess
# ---------------------------------------------------------------------------


async def test_a_task_with_no_evidence_is_refused_with_a_reason():
    async with async_session_factory() as session:
        await _scaffold(session)
        await session.commit()

        target = await requirement_evidence.commit_for_task_review(session, "task-1")

    assert target.resolved is False
    assert target.commit_sha is None
    assert target.refusal is not None
    assert "no recorded evidence" in target.refusal
    assert "task-1" in target.refusal


async def test_evidence_that_names_no_commit_is_refused_differently():
    """A non-repository project is a supported case, and a distinguishable one."""
    async with async_session_factory() as session:
        await _scaffold(session)
        await _evidence(session, evidence_id="ev-1", commit=None, produced_at=ago(5))
        await session.commit()

        target = await requirement_evidence.commit_for_task_review(session, "task-1")

    assert target.resolved is False
    assert "none of it names a commit" in target.refusal
    assert "no recorded evidence" not in target.refusal


async def test_a_blank_commit_sha_counts_as_naming_no_commit():
    async with async_session_factory() as session:
        await _scaffold(session)
        await _evidence(session, evidence_id="ev-1", commit="   ", produced_at=ago(5))
        await session.commit()

        target = await requirement_evidence.commit_for_task_review(session, "task-1")

    assert target.resolved is False


async def test_evidence_naming_a_commit_wins_over_later_evidence_naming_none():
    """A run that recorded a path-only footprint after a git one must not erase the commit."""
    async with async_session_factory() as session:
        await _scaffold(session)
        await _evidence(session, evidence_id="ev-1", commit="cad5d74", produced_at=ago(30))
        await _evidence(session, evidence_id="ev-2", commit=None, produced_at=ago(5))
        await session.commit()

        target = await requirement_evidence.commit_for_task_review(session, "task-1")

    assert target.commit_sha == "cad5d74"
    assert target.refusal is None


async def test_the_refusal_is_returned_not_raised():
    """Task 2.2 states this: a refusal a generic handler can swallow is not a stated refusal."""
    async with async_session_factory() as session:
        await _scaffold(session)
        await session.commit()

        try:
            target = await requirement_evidence.commit_for_task_review(session, "task-1")
        except Exception as exc:  # pragma: no cover - the assertion is that this does not happen
            pytest.fail(f"commit_for_task_review raised {exc!r} instead of returning a refusal")

    assert target.refusal
