"""A reviewer verifies evidence on the task's current work; it does not author it.

`evidence-review-sends-work-back-only-for-what-is-wrong-with-it`, task `reviewer-verifies`. A piece
recorded at commit A, on a task branch that has since gained B (a master merge, a fix), used to cost
a full builder turn: the reviewer re-ran it on B, watched it pass, and still sent the task back,
because accepted evidence decides what lands. Now the reviewer accepts with its own reproduction at
B, the footprint is re-anchored there, and approval lands B (FR-1) -- only at a commit of the task's
own branch at or after A (FR-2), with the author's record kept beside the reviewer's (FR-3), never
over the operator's rejection (FR-4), and never to make a partial piece whole (FR-5).
"""

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import EvidenceFootprint, RequirementEvidence

from . import test_a_reviewer_does_not_record_evidence as f500
from .test_task_integration import (
    AGENT_EVIDENCE,
    BASE,
    approve,
    commits_on,
    coverage_for,
    files_on,
    git,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)

AGENT_DECIDE = "/api/v1/agent-actions/spec/evidence/{}/decision"
#: F500's two agents: the task's author, and a second agent whose run reviews the task.
author = f500.author
reviewing_run = f500.reviewing_run


def commit(root, filename, content):
    (root / filename).write_text(content, encoding="utf-8")
    git(root, "add", filename)
    git(root, "commit", "-q", "-m", f"work on {filename}")
    return git(root, "rev-parse", "HEAD").stdout.strip()


async def staged(app, auth_headers, author_headers, root, *, covers=""):
    """A task whose FR-1 evidence was recorded at A on its own branch, after which the branch
    merged main (M) and gained a fix: B. Returns (task, evidence id, A, B, M)."""
    make_repo(root)
    await make_document(app, auth_headers, author_headers)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)
    branch = worktrees.task_branch_name(task)
    git(root, "checkout", "-q", "-b", branch)
    a = commit(root, "feature.py", "print('hi')\n")
    body = {"identifier": "FR-1", "summary": "ran the tests", "task_id": task}
    if covers:
        body["covers"] = covers
    body.update(command="pytest -k feature", output="1 passed")
    recorded = await app.post(AGENT_EVIDENCE, json=body, headers=author_headers)
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["footprint"]["commit_sha"] == a
    git(root, "checkout", "-q", "main")
    m = commit(root, "main_moved.py", "elsewhere\n")
    git(root, "checkout", "-q", branch)
    git(root, "merge", "-q", "--no-ff", "-m", "merge main", "main")
    b = commit(root, "fix.py", "fixed\n")
    git(root, "checkout", "-q", "main")
    return task, recorded.json()["id"], a, b, m


async def footprint_commit(evidence_id):
    async with async_session_factory() as session:
        return await session.scalar(
            select(EvidenceFootprint.commit_sha).where(EvidenceFootprint.evidence_id == evidence_id)
        )


async def state_of(evidence_id):
    async with async_session_factory() as session:
        return (await session.get(RequirementEvidence, evidence_id)).review_state


def reproduce(**extra):
    return {
        "decision": "accepted",
        "reason": "re-ran it on the branch tip",
        "command": "pytest -k feature",
        "output": "2 passed",
        **extra,
    }


@pytest.mark.asyncio
async def test_a_reproduction_at_the_tip_re_anchors_and_approval_lands_it(
    app, auth_headers, author, tmp_path
):
    """ac-reanchor-lands: the footprint names B, and approving lands B's changes."""
    task, evidence, a, b, m = await staged(app, auth_headers, author, tmp_path)
    reviewer = await reviewing_run(task)

    accepted = await app.post(
        AGENT_DECIDE.format(evidence), json=reproduce(commit=b), headers=reviewer
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["review_state"] == "accepted"
    assert accepted.json()["footprint"]["commit_sha"] == b
    assert await footprint_commit(evidence) == b

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text
    landed = commits_on(tmp_path, "main")
    assert b in landed and a in landed
    assert {"feature.py", "fix.py", "main_moved.py"} <= files_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_without_a_reproduction_approval_is_refused_for_the_moved_branch(
    app, auth_headers, author, tmp_path
):
    """The control: the same staging, accepted plainly, names A, and approval is refused because
    the branch holds B, which nothing accepted names -- the send-back a moved branch used to cost.
    """
    task, evidence, _a, b, _m = await staged(app, auth_headers, author, tmp_path)
    accepted = await app.post(
        f"{BASE}/spec/evidence/{evidence}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 409, approved.text
    assert b in str(approved.json()["detail"]["unlanded"])
    assert "fix.py" not in files_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_commit_off_the_task_branch_or_before_the_evidence_is_refused(
    app, auth_headers, author, tmp_path
):
    """ac-foreign-commit-refused: each refusal names the commit; the evidence stays awaiting."""
    task, evidence, a, _b, m = await staged(app, auth_headers, author, tmp_path)
    git(tmp_path, "checkout", "-q", "-b", "elsewhere")
    foreign = commit(tmp_path, "other.py", "not this task\n")
    git(tmp_path, "checkout", "-q", "main")
    base = git(tmp_path, "rev-parse", f"{a}~1").stdout.strip()
    reviewer = await reviewing_run(task)

    for sha, code in (
        (foreign, "reproduction_commit_off_branch"),
        # On the branch through the merge, but not descended from A.
        (m, "reproduction_commit_before_evidence"),
        (base, "reproduction_commit_before_evidence"),
        ("0123456789abcdef0123456789abcdef01234567", "reproduction_commit_unknown"),
    ):
        refused = await app.post(
            AGENT_DECIDE.format(evidence), json=reproduce(commit=sha), headers=reviewer
        )
        assert refused.status_code == 409, refused.text
        detail = refused.json()["detail"]
        assert detail["code"] == code, (sha, detail)
        assert sha[:12] in detail["message"]
        assert await state_of(evidence) == "awaiting"
        assert await footprint_commit(evidence) == a


@pytest.mark.asyncio
async def test_both_records_are_returned_each_attributed(app, auth_headers, author, tmp_path):
    """ac-both-records-shown, over list_evidence and the operator's evidence view."""
    task, evidence, a, b, _m = await staged(app, auth_headers, author, tmp_path)
    reviewer = await reviewing_run(task)
    accepted = await app.post(
        AGENT_DECIDE.format(evidence),
        json=reproduce(commit=b, summary="feature passes with the fix on the merged tip"),
        headers=reviewer,
    )
    assert accepted.status_code == 200, accepted.text

    for url, headers in (
        (f"{AGENT_EVIDENCE}?identifier=FR-1", reviewer),
        (f"{BASE}/spec/evidence", auth_headers),
    ):
        listed = await app.get(url, headers=headers)
        assert listed.status_code == 200, listed.text
        rows = listed.json()
        rows = rows["evidence"] if isinstance(rows, dict) else rows
        [view] = [row for row in rows if row["id"] == evidence]
        assert view["author_record"] == {
            "actor_kind": "agent",
            "actor": "author",
            "run_id": "run-f500-author",
            "summary": "ran the tests",
            "command": "pytest -k feature",
            "output": "1 passed",
            "covers": None,
            "commit": a,
        }
        record = view["reviewer_record"]
        assert record["actor"] == "checker" and record["run_id"] == "run-f500-rev"
        assert record["command"] == "pytest -k feature"
        assert record["output"] == "2 passed"
        assert record["summary"] == "feature passes with the fix on the merged tip"
        assert record["commit"] == b and record["anchored_from_commit"] == a
        # The author's words are still the row's own.
        assert view["summary"] == "ran the tests"


@pytest.mark.asyncio
async def test_over_an_operator_rejection_both_routes_are_refused(
    app, auth_headers, author, tmp_path
):
    """ac-f500-refusals: the operator rejected FR-1's evidence on T. The reviewer can neither accept
    the author's later piece with a reproduction nor record its own, and with the rejected piece the
    only evidence the operator's rejection still blocks approval."""
    task, rejected_id, _a, b, _m = await staged(app, auth_headers, author, tmp_path)
    rejected = await app.post(
        f"{BASE}/spec/evidence/{rejected_id}/decision",
        json={"decision": "rejected", "reason": "does not show it"},
        headers=auth_headers,
    )
    assert rejected.status_code == 200, rejected.text
    reviewer = await reviewing_run(task)

    recorded = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": "I ran it", "task_id": task},
        headers=reviewer,
    )
    assert recorded.status_code == 409, recorded.text
    assert recorded.json()["detail"]["code"] == "reviewer_records_evidence"
    assert (await approve(app, auth_headers, task)).status_code != 200

    branch = worktrees.task_branch_name(task)
    git(tmp_path, "checkout", "-q", branch)
    again = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": "recorded again", "task_id": task},
        headers=author,
    )
    git(tmp_path, "checkout", "-q", "main")
    assert again.status_code == 201, again.text
    refused = await app.post(
        AGENT_DECIDE.format(again.json()["id"]), json=reproduce(commit=b), headers=reviewer
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "operator_rejected_requirement"
    assert await state_of(again.json()["id"]) == "awaiting"


@pytest.mark.asyncio
async def test_the_author_and_a_run_not_reviewing_cannot_reproduce(
    app, auth_headers, author, tmp_path
):
    task, evidence, _a, b, _m = await staged(app, auth_headers, author, tmp_path)
    own = await app.post(AGENT_DECIDE.format(evidence), json=reproduce(commit=b), headers=author)
    assert own.status_code == 403, own.text
    assert own.json()["detail"]["code"] == "reproduction_not_reviewing"

    worker = await reviewing_run(task, review=False)
    other = await app.post(AGENT_DECIDE.format(evidence), json=reproduce(commit=b), headers=worker)
    assert other.status_code == 403, other.text
    assert other.json()["detail"]["code"] == "reproduction_not_reviewing"
    assert await state_of(evidence) == "awaiting"


@pytest.mark.asyncio
async def test_a_partial_piece_is_not_made_whole_and_the_rest_is_not_recorded(
    app, auth_headers, author, tmp_path
):
    """ac-missing-piece: both refused, each telling the reviewer to send the task back."""
    task, evidence, _a, b, _m = await staged(app, auth_headers, author, tmp_path, covers="partial")
    reviewer = await reviewing_run(task)

    whole = await app.post(
        AGENT_DECIDE.format(evidence), json=reproduce(commit=b, covers="full"), headers=reviewer
    )
    assert whole.status_code == 409, whole.text
    assert whole.json()["detail"]["code"] == "missing_piece"
    assert "revision_needed" in whole.json()["detail"]["message"]
    assert "missing piece" in whole.json()["detail"]["message"]
    assert await state_of(evidence) == "awaiting"

    rest = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": "the rest", "covers": "partial", "task_id": task},
        headers=reviewer,
    )
    assert rest.status_code == 409, rest.text
    assert rest.json()["detail"]["code"] == "reviewer_records_evidence"
    assert "revision_needed" in rest.json()["detail"]["message"]
    assert "missing piece" in rest.json()["detail"]["message"]

    # Accepting it for what it is stays open, and coverage reads it as partial.
    accepted = await app.post(
        AGENT_DECIDE.format(evidence), json=reproduce(commit=b), headers=reviewer
    )
    assert accepted.status_code == 200, accepted.text
    assert (await coverage_for(app, auth_headers, "FR-1"))["state"] == "in_progress"


@pytest.mark.asyncio
async def test_a_covers_correction_down_to_partial_is_what_coverage_reads(
    app, auth_headers, author, tmp_path
):
    task, evidence, _a, b, _m = await staged(app, auth_headers, author, tmp_path, covers="full")
    reviewer = await reviewing_run(task)
    accepted = await app.post(
        AGENT_DECIDE.format(evidence), json=reproduce(commit=b, covers="partial"), headers=reviewer
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["covers"] == "full"
    assert accepted.json()["reviewer_record"]["covers"] == "partial"
    assert (await coverage_for(app, auth_headers, "FR-1"))["state"] == "in_progress"


@pytest.mark.asyncio
async def test_a_reproduction_rejects_nothing(app, auth_headers, author, tmp_path):
    task, evidence, _a, b, _m = await staged(app, auth_headers, author, tmp_path)
    reviewer = await reviewing_run(task)
    refused = await app.post(
        AGENT_DECIDE.format(evidence),
        json={"decision": "rejected", "reason": "no", "commit": b},
        headers=reviewer,
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "reproduction_needs_acceptance"


@pytest.mark.asyncio
async def test_the_review_briefing_names_the_moved_tip(app, auth_headers, author, tmp_path):
    """The review checkout is at A, the evidence's commit. A drive on this change found the
    reviewer reproducing there, with nothing to tell it where B is: the briefing names the tip."""
    from hub import review_turn
    from hub.db.models import Task

    task, evidence, a, b, _m = await staged(app, auth_headers, author, tmp_path)
    async with async_session_factory() as session:
        row = await session.get(Task, task)
        sentence = await review_turn.verdict_evidence_sentence(session, row, may_decide=False)
    assert f"moved past `{evidence}`" in sentence
    assert f"git checkout --detach {b}" in sentence
    assert f"commit='{b}'" in sentence

    # Nothing has moved: no tip sentence.
    git(tmp_path, "branch", "-f", worktrees.task_branch_name(task), a)
    async with async_session_factory() as session:
        row = await session.get(Task, task)
        sentence = await review_turn.verdict_evidence_sentence(session, row, may_decide=False)
    assert "branch has moved past `" not in sentence
