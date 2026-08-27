"""Give a completed task something a reviewer could actually be shown.

`decide_firing` refuses to staff a review for a task with no evidence naming a commit, because
`prepare_review_turn` cannot provision one and the firing used to discover that only after moving
the task to `under_review` — see `test_a_review_needs_something_to_review.py` for the live
reproduction.

Several tests predate that gate and build a completed task with nothing behind it, then assert what
the flow does with the review. Their subject is the *review*, not the evidence, so they call this
rather than each growing a copy of four rows.
"""

from datetime import datetime, timedelta, timezone

from hub.db.models import (
    EvidenceFootprint,
    RequirementEvidence,
    SpecDocument,
    SpecRequirement,
)


async def record_review_evidence(
    session,
    task_id: str,
    *,
    suffix: str,
    project_id: str = "proj-test",
    commit_sha: str = "c" * 40,
    actor: str = "author",
    commit: bool = True,
) -> None:
    """Attach one accepted-shaped evidence row naming *commit_sha* to *task_id*.

    `suffix` only keeps the generated ids distinct when a test seeds more than one task; nothing
    reads it. The document and requirement exist because `RequirementEvidence.requirement_id` is
    not nullable, not because any assertion involves them.
    """
    now = datetime.now(timezone.utc)
    session.add(
        SpecDocument(
            id=f"doc-rev-{suffix}",
            project_id=project_id,
            path=f"spec/rev-{suffix}.html",
            title=f"Reviewable {suffix}",
            phase="current",
            kind="capability",
        )
    )
    session.add(
        SpecRequirement(
            id=f"req-rev-{suffix}",
            project_id=project_id,
            document_id=f"doc-rev-{suffix}",
            identifier="FR-1",
            key="fr-1",
            digest="d" * 64,
        )
    )
    session.add(
        RequirementEvidence(
            id=f"ev-rev-{suffix}",
            project_id=project_id,
            requirement_id=f"req-rev-{suffix}",
            task_id=task_id,
            digest="d" * 64,
            kind="commit",
            actor_kind="agent",
            actor=actor,
            summary="the work",
            produced_at=now - timedelta(minutes=5),
        )
    )
    session.add(
        EvidenceFootprint(
            id=f"fp-rev-{suffix}",
            project_id=project_id,
            evidence_id=f"ev-rev-{suffix}",
            kind="git",
            commit_sha=commit_sha,
            branch="agentweave/author",
            observed_at=now - timedelta(minutes=5),
        )
    )
    if commit:
        await session.commit()
