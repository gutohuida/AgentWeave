"""Each piece of evidence is judged on its own (`each-piece-of-evidence-is-judged-on-its-own`, K).

Operator, 2026-10-26: "when we reject or an agent rejects an evidence, all evidences are rejected on
the same value ... that is confusing." Until K a send-back rejected every awaiting piece of the task
with the one verdict reason (`requirement_evidence.decide_with_verdict`), so QA's "FR-4 held, but is
rejected with this verdict" was the record, and slice 2's 30 of 54 rejections counted send-backs
times requirements. The verdict stays one action (F672); inside it a send-back rejects only the
pieces the reviewer names as failing, each with its own reason, and holds the rest at that commit.

The acceptance drive: a real repository, real routes, the reviewer an agent with no
`can_accept_evidence` grant, as `test_the_reviewers_verdict_decides_the_tasks_evidence.py` is.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EvidenceReview, RequirementEvidence, Run, Task
from hub.spec_payload import SCHEMA_VERSION

from .test_approval_refuses_unaccepted_evidence import record_evidence_for
from .test_task_integration import (
    AGENT_BRANCH,
    BASE,
    PATH,
    SUBMIT,
    TASKS,
    commit_on_branch,
    drive_to,
    git,
    make_repo,
    set_main_branch,
)

AGENT_TASKS = "/api/v1/agent-actions/tasks"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
FOUR = ["FR-1", "FR-2", "FR-3", "FR-4"]
S = "the overdue list is not sorted; see FR-3"
R3 = "the test asserts the count, not the order FR-3 requires"


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-piece-b", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-piece-b",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_pieceb-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_pieceb-secret"}


@pytest.fixture
async def reviewer():
    """No `can_accept_evidence` grant: the verdict alone decides."""
    async with async_session_factory() as session:
        session.add(Agent(id="ag-piece-r", project_id="proj-test", name="reviewer"))
        session.add(
            Run(
                id="run-piece-r",
                project_id="proj-test",
                agent="reviewer",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_piecer-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_piecer-secret"}


async def a_document(app, auth_headers, builder, count):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Pieces demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Pieces demo",
                "requirements": [
                    {"key": f"req-{n}", "statement": f"It does thing {n}", "modal": "MUST"}
                    for n in range(1, count + 1)
                ],
            },
        },
        headers=builder,
    )
    assert saved.status_code == 200, saved.text


async def a_completed_task(app, auth_headers, builder, tmp_path, identifiers):
    """A task serving *identifiers*, one awaiting piece each at one real commit, under review.

    Returns `(task_id, {identifier: evidence_id})`; the checkout is left on `main`.
    """
    make_repo(tmp_path)
    await set_main_branch("main")
    await a_document(app, auth_headers, builder, len(identifiers))
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": identifiers}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    task = created.json()["id"]
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('due')\n")
    pieces = {
        identifier: await record_evidence_for(
            app, builder, identifier, task_id=task, summary=f"ran the test for {identifier}"
        )
        for identifier in identifiers
    }
    git(tmp_path, "checkout", "-q", "main")
    walked = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review"
    )
    assert walked.status_code == 200, walked.text
    return task, pieces


async def send_back(
    app,
    reviewer,
    task,
    *,
    notes=None,
    failing=None,
    status="revision_needed",
    reason_class="defect",
):
    body = {"status": status}
    if status == "revision_needed" and reason_class is not None:
        # A reviewer's send-back names why (FR-9 of `a-task-s-checks-and-merges-use-its-own-work-
        # and-a-live-run-is-never-reset`); what these tests judge is the evidence, not the class.
        body["reason_class"] = reason_class
    if notes is not None:
        body["notes"] = notes
    if failing is not None:
        body["failing_pieces"] = failing
    return await app.patch(f"{AGENT_TASKS}/{task}", json=body, headers=reviewer)


async def outcome(evidence_id):
    """`(review_state, latest decision, its reason, who decided)` read from the rows."""
    async with async_session_factory() as session:
        evidence = await session.get(RequirementEvidence, evidence_id)
        review = (
            (
                await session.execute(
                    select(EvidenceReview)
                    .where(EvidenceReview.evidence_id == evidence_id)
                    .order_by(EvidenceReview.sequence.desc())
                )
            )
            .scalars()
            .first()
        )
        if review is None:
            return (evidence.review_state, None, None, None)
        return (evidence.review_state, review.decision, review.reason, review.actor)


async def listed(app, headers, task, review_state=None, *, agent=False):
    """The list_evidence route (the agent's or the operator's), narrowed to *task*'s pieces."""
    url = AGENT_EVIDENCE if agent else f"{BASE}/spec/evidence"
    params = {"review_state": review_state} if review_state else None
    response = await app.get(url, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return [row for row in response.json()["evidence"] if row["task_id"] == task]


async def status_of(task_id):
    async with async_session_factory() as session:
        return (await session.get(Task, task_id)).status


@pytest.mark.asyncio
async def test_one_of_four_rejects_only_the_named_piece(
    app, auth_headers, builder, reviewer, tmp_path
):
    """one-of-four (FR-1). FAILS before K: the send-back rejected all four with S."""
    task, pieces = await a_completed_task(app, auth_headers, builder, tmp_path, FOUR)

    sent = await send_back(app, reviewer, task, notes=S, failing=[{"piece": "FR-3", "reason": R3}])

    assert sent.status_code == 200, sent.text
    assert await outcome(pieces["FR-3"]) == ("rejected", "rejected", R3, "reviewer")
    for identifier in ("FR-1", "FR-2", "FR-4"):
        state = (await outcome(pieces[identifier]))[0]
        assert state != "rejected", (identifier, state)


@pytest.mark.asyncio
async def test_the_pieces_not_named_are_held_with_the_send_backs_reason(
    app, auth_headers, builder, reviewer, tmp_path
):
    """three-held (FR-2), read through both list_evidence routes."""
    task, pieces = await a_completed_task(app, auth_headers, builder, tmp_path, FOUR)

    sent = await send_back(app, reviewer, task, notes=S, failing=[{"piece": "FR-3", "reason": R3}])
    assert sent.status_code == 200, sent.text

    for agent, headers in ((False, auth_headers), (True, reviewer)):
        rows = {row["id"]: row for row in await listed(app, headers, task, agent=agent)}
        for identifier in ("FR-1", "FR-2", "FR-4"):
            row = rows[pieces[identifier]]
            assert row["review_state"] == "held", (agent, identifier, row["review_state"])
            assert row["latest_review"]["decision"] == "held", row["latest_review"]
            assert row["latest_review"]["reason"] == S, row["latest_review"]
            assert row["latest_review"]["actor"] == "reviewer", row["latest_review"]
        assert rows[pieces["FR-3"]]["review_state"] == "rejected"
        assert rows[pieces["FR-3"]]["latest_review"]["reason"] == R3


@pytest.mark.asyncio
async def test_a_send_back_naming_none_holds_every_piece_and_needs_a_reason(
    app, auth_headers, builder, reviewer, tmp_path
):
    """general-send-back (FR-3): naming none and giving no reason is refused, and changes nothing;
    naming none with a reason holds both pieces with it."""
    task, pieces = await a_completed_task(app, auth_headers, builder, tmp_path, ["FR-1", "FR-2"])

    refused = await send_back(app, reviewer, task)

    assert refused.status_code == 422, refused.text
    text = str(refused.json()["detail"])
    assert "failing_pieces" in text and "notes" in text, text
    assert await status_of(task) == "under_review"
    for evidence_id in pieces.values():
        assert await outcome(evidence_id) == ("awaiting", None, None, None)

    sent = await send_back(app, reviewer, task, notes="lint fails")

    assert sent.status_code == 200, sent.text
    for evidence_id in pieces.values():
        assert await outcome(evidence_id) == ("held", "held", "lint fails", "reviewer")


@pytest.mark.asyncio
async def test_held_pieces_are_recorded_again_at_the_next_commit(
    app, auth_headers, builder, reviewer, tmp_path
):
    """re-record (FR-4): a held piece never counts as accepted; approval is refused for the
    requirements whose only pieces are held, and accepts the new pieces once they are recorded."""
    task, old = await a_completed_task(app, auth_headers, builder, tmp_path, FOUR)
    sent = await send_back(app, reviewer, task, notes=S, failing=[{"piece": "FR-3", "reason": R3}])
    assert sent.status_code == 200, sent.text

    # The builder's fix, at a new commit, and evidence for the requirement that failed.
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('due, sorted')\n", create=False)
    new = {"FR-3": await record_evidence_for(app, builder, "FR-3", task_id=task)}
    git(tmp_path, "checkout", "-q", "main")
    walked = await drive_to(app, auth_headers, task, "in_progress", "completed")
    assert walked.status_code == 200, walked.text
    # The send-back returned the task to its author; the review is someone else's.
    reviewing = await app.patch(
        f"{TASKS}/{task}", json={"status": "under_review", "assignee": None}, headers=auth_headers
    )
    assert reviewing.status_code == 200, reviewing.text

    refused = await app.patch(
        f"{AGENT_TASKS}/{task}", json={"status": "approved"}, headers=reviewer
    )

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    blocking = sorted(entry["identifier"] for entry in detail["blocking"])
    assert blocking == ["FR-1", "FR-2", "FR-4"], detail
    assert "held" in detail["message"], detail["message"]
    assert await outcome(new["FR-3"]) == ("awaiting", None, None, None)

    git(tmp_path, "checkout", "-q", AGENT_BRANCH)
    for identifier in ("FR-1", "FR-2", "FR-4"):
        new[identifier] = await record_evidence_for(app, builder, identifier, task_id=task)
    git(tmp_path, "checkout", "-q", "main")

    approved = await app.patch(
        f"{AGENT_TASKS}/{task}",
        json={"status": "approved", "notes": "all four checked at the fix"},
        headers=reviewer,
    )

    assert approved.status_code == 200, approved.text
    for identifier in FOUR:
        assert (await outcome(new[identifier]))[0] == "accepted", identifier
    for identifier in ("FR-1", "FR-2", "FR-4"):
        assert (await outcome(old[identifier]))[0] == "held", identifier
    assert (await outcome(old["FR-3"]))[0] == "rejected"


@pytest.mark.asyncio
async def test_after_a_send_back_nothing_awaits_a_second_decision(
    app, auth_headers, builder, reviewer, tmp_path
):
    """no-second-decision (FR-5)."""
    task, _pieces = await a_completed_task(app, auth_headers, builder, tmp_path, FOUR)

    sent = await send_back(app, reviewer, task, notes=S, failing=[{"piece": "FR-3", "reason": R3}])

    assert sent.status_code == 200, sent.text
    assert await listed(app, builder, task, "awaiting", agent=True) == []
    assert await listed(app, auth_headers, task, "awaiting") == []


@pytest.mark.asyncio
async def test_approving_while_naming_a_failing_piece_is_refused(
    app, auth_headers, builder, reviewer, tmp_path
):
    """approve-with-failure-refused (FR-6): refused naming the contradiction, nothing changes."""
    task, pieces = await a_completed_task(app, auth_headers, builder, tmp_path, FOUR)

    refused = await send_back(
        app, reviewer, task, status="approved", failing=[{"piece": "FR-3", "reason": R3}]
    )

    assert refused.status_code == 422, refused.text
    text = str(refused.json()["detail"])
    assert "contradict" in text and "FR-3" in text, text
    assert await status_of(task) == "under_review"
    for evidence_id in pieces.values():
        assert await outcome(evidence_id) == ("awaiting", None, None, None)


@pytest.mark.asyncio
async def test_a_piece_the_task_does_not_hold_cannot_be_named(
    app, auth_headers, builder, reviewer, tmp_path
):
    """A named piece that is not one of the task's awaiting pieces is refused, not ignored: the
    reviewer would otherwise believe it had rejected something."""
    task, pieces = await a_completed_task(app, auth_headers, builder, tmp_path, ["FR-1", "FR-2"])

    refused = await send_back(
        app, reviewer, task, notes=S, failing=[{"piece": "FR-9", "reason": "nope"}]
    )

    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "unknown_failing_piece", detail
    assert "FR-9" in detail["message"] and "FR-1, FR-2" in detail["message"], detail
    for evidence_id in pieces.values():
        assert await outcome(evidence_id) == ("awaiting", None, None, None)


@pytest.mark.asyncio
async def test_the_outcome_is_traceable(app, auth_headers, builder, reviewer, tmp_path):
    """trace-visible (FR-7): the history names FR-3 rejected with R3 and three held; the two
    review-state filters return three and one."""
    task, pieces = await a_completed_task(app, auth_headers, builder, tmp_path, FOUR)
    sent = await send_back(app, reviewer, task, notes=S, failing=[{"piece": "FR-3", "reason": R3}])
    assert sent.status_code == 200, sent.text

    for url, headers in (
        (f"{TASKS}/{task}/transitions", auth_headers),
        (f"{AGENT_TASKS}/{task}/transitions", builder),
    ):
        history = await app.get(url, headers=headers)
        assert history.status_code == 200, history.text
        last = history.json()["transitions"][-1]
        assert last["to_status"] == "revision_needed", last
        note = last["note"] or ""
        assert f"FR-3 rejected: {R3}" in note, note
        assert "FR-1, FR-2, FR-4 held" in note, note

    for agent, headers in ((False, auth_headers), (True, builder)):
        held = await listed(app, headers, task, "held", agent=agent)
        rejected = await listed(app, headers, task, "rejected", agent=agent)
        assert sorted(row["id"] for row in held) == sorted(
            pieces[i] for i in ("FR-1", "FR-2", "FR-4")
        )
        assert [row["id"] for row in rejected] == [pieces["FR-3"]]


@pytest.mark.asyncio
async def test_the_reviewer_is_told_how(app, auth_headers, builder, reviewer, tmp_path):
    """brief-says-so (FR-8): the review brief and the update_task tool both name the argument and
    say that unnamed pieces are held."""
    from hub import mcp_server, review_turn

    task, _pieces = await a_completed_task(app, auth_headers, builder, tmp_path, FOUR)
    async with async_session_factory() as session:
        sentence = await review_turn.verdict_evidence_sentence(
            session, await session.get(Task, task), may_decide=False
        )

    assert sentence is not None
    assert "failing_pieces" in sentence and "held" in sentence, sentence
    described = mcp_server.update_task.__doc__ or ""
    assert "failing_pieces" in described and "held" in described, described


# ---------------------------------------------------------------------------------------------
# Review of K (2026-10-27): what regressed, each red before its fix.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_brief_names_requirements_whose_evidence_is_only_held(
    app, auth_headers, builder, reviewer, tmp_path
):
    """The reviewer's probe: a send-back names only FR-3; the builder re-records FR-3 and
    completes. Approval is refused for FR-1 and FR-2 (held only), so the brief must say so, as it
    said "only rejected evidence" before K. FAILED before: the brief named only FR-3's piece."""
    from hub import review_turn

    three = ["FR-1", "FR-2", "FR-3"]
    task, _old = await a_completed_task(app, auth_headers, builder, tmp_path, three)
    sent = await send_back(app, reviewer, task, notes=S, failing=[{"piece": "FR-3", "reason": R3}])
    assert sent.status_code == 200, sent.text
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('due, sorted')\n", create=False)
    await record_evidence_for(app, builder, "FR-3", task_id=task)
    git(tmp_path, "checkout", "-q", "main")
    walked = await drive_to(app, auth_headers, task, "in_progress", "completed")
    assert walked.status_code == 200, walked.text
    reviewing = await app.patch(
        f"{TASKS}/{task}", json={"status": "under_review", "assignee": None}, headers=auth_headers
    )
    assert reviewing.status_code == 200, reviewing.text

    async with async_session_factory() as session:
        sentence = await review_turn.verdict_evidence_sentence(
            session, await session.get(Task, task), may_decide=False
        )

    assert sentence is not None
    assert "`FR-1`, `FR-2`" in sentence and "only held evidence" in sentence, sentence
    assert "next commit" in sentence, sentence


@pytest.mark.asyncio
async def test_the_operator_accepts_or_rejects_a_held_piece(
    app, auth_headers, builder, reviewer, tmp_path
):
    """The operator acts on a held piece as on an awaiting one: accept with no reason, reject
    with one. FAILED before: accepting needed a reason, refused as 'overturning a decision'."""
    task, pieces = await a_completed_task(app, auth_headers, builder, tmp_path, ["FR-1", "FR-2"])
    sent = await send_back(app, reviewer, task, notes="lint fails")
    assert sent.status_code == 200, sent.text

    overturn = await app.post(
        f"{BASE}/spec/evidence/{pieces['FR-1']}/overturn",
        json={"reason": "it was right"},
        headers=auth_headers,
    )
    assert overturn.status_code == 409, overturn.text
    said = overturn.json()["detail"]["message"]
    assert "held" in said and "accept it" in said and "overturn" not in said.lower(), said

    # Even an agent granted acceptance leaves a held piece to its next commit.
    async with async_session_factory() as session:
        (await session.get(Agent, "ag-piece-r")).can_accept_evidence = True
        await session.commit()
    agent = await app.post(
        f"{AGENT_EVIDENCE}/{pieces['FR-1']}/decision",
        json={"decision": "accepted", "reason": ""},
        headers=reviewer,
    )
    assert agent.status_code in (403, 409), agent.text
    assert "held" in str(agent.json()["detail"]), agent.text

    accepted = await app.post(
        f"{BASE}/spec/evidence/{pieces['FR-1']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text
    assert (await outcome(pieces["FR-1"]))[:2] == ("accepted", "accepted")

    blank = await app.post(
        f"{BASE}/spec/evidence/{pieces['FR-2']}/decision",
        json={"decision": "rejected", "reason": ""},
        headers=auth_headers,
    )
    assert blank.status_code == 422, blank.text
    assert "overturn" not in str(blank.json()["detail"]).lower(), blank.text
    rejected = await app.post(
        f"{BASE}/spec/evidence/{pieces['FR-2']}/decision",
        json={"decision": "rejected", "reason": "it never ran"},
        headers=auth_headers,
    )
    assert rejected.status_code == 200, rejected.text
    assert await outcome(pieces["FR-2"]) == ("rejected", "rejected", "it never ran", "operator")


@pytest.mark.asyncio
async def test_an_author_naming_failing_pieces_is_refused_as_the_author_first(
    app, auth_headers, builder, reviewer, tmp_path
):
    """K introduced this: failing_pieces was resolved before the author-is-not-the-reviewer
    refusal, so the author was told its piece was unknown (its own pieces are not the verdict's
    to decide). FAILED before: 422 unknown_failing_piece."""
    task, pieces = await a_completed_task(app, auth_headers, builder, tmp_path, ["FR-1"])

    refused = await send_back(
        app, builder, task, notes=S, failing=[{"piece": "FR-1", "reason": "mine is wrong"}]
    )

    assert refused.status_code == 403, refused.text
    assert "different actor" in refused.text, refused.text
    assert await outcome(pieces["FR-1"]) == ("awaiting", None, None, None)


@pytest.mark.asyncio
async def test_the_evidence_note_follows_a_note_as_its_own_sentence(
    app, auth_headers, builder, reviewer, tmp_path
):
    """L's return writes a note with no full stop, and the evidence account followed it as
    "...check run chk-1 Evidence: ...". FAILED before."""
    from hub.task_transition_service import apply_transition
    from hub.task_transitions import operator

    task, _pieces = await a_completed_task(app, auth_headers, builder, tmp_path, ["FR-1"])
    async with async_session_factory() as session:
        row = await session.get(Task, task)
        transition = await apply_transition(
            session,
            row,
            "revision_needed",
            operator(),
            verdict_reason="the checks failed",
            note="the project's checks failed on check run chk-1",
        )
        note = transition.note
        await session.commit()

    assert note.startswith("the project's checks failed on check run chk-1. Evidence: "), note
