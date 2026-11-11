"""An acceptance drive is approved only on a baseline showing each check reached and failing.

`evidence-review-sends-work-back-only-for-what-is-wrong-with-it`, task `baseline-gate`. A change's
first task is its acceptance drive; approval used to check only that it came first, so a drive
that stopped at a 404 before its assertion, or passed on no-op code, was found after the build.
Now the drive task is not approved without accepted `drive_baseline` evidence (FR-6), a baseline
naming a check that was not reached or passed before the build is not accepted by an agent, and
its reviewer is told to send the drive back naming each such check (FR-7). The model record and
the build retrospective count evidence-only send-backs and reviewer-verified acceptances per task
(FR-8).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from hub import build_retrospective, drive_baseline, review_turn, worktrees
from hub.db.engine import async_session_factory
from hub.db.models import RequirementEvidence, Run, SpecDocument, Task
from hub.model_record import model_record
from hub.spec_payload import SCHEMA_VERSION

from . import test_a_reviewer_does_not_record_evidence as f500
from . import test_a_reviewer_verifies_evidence as verifies
from .test_task_integration import (
    AGENT_EVIDENCE,
    ALPHA,
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
AGENT_DECIDE = "/api/v1/agent-actions/spec/evidence/{}/decision"
BASE = "/api/v1/projects/proj-test/project"
author = f500.author
reviewing_run = f500.reviewing_run

UNREACHED, VACUOUS = "c-unreached", "c-vacuous"
BAD_BASELINE = (
    "drive baseline on the pre-build code:\n"
    f"check {UNREACHED}: reached=no failed_at_assertion=no -- stopped at setup: POST answered 404\n"
    f"check {VACUOUS}: reached=yes failed_at_assertion=no -- passed on the pre-build code"
)
GOOD_BASELINE = (
    "check c-one: reached=yes failed_at_assertion=yes -- expected 201, got 404 at the assertion\n"
    "check c-two (ac-two): reached=yes failed_at_assertion=yes -- the greeting was empty"
)


async def drive_document(app, auth_headers, run_headers):
    """A change of two tasks whose first, `drive`, every other waits on: its acceptance drive."""
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Greeting"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Greeting",
                "requirements": [ALPHA],
                "tasks": [
                    {
                        "key": "drive",
                        "title": "Acceptance drive",
                        "description": "Write the drive and record its baseline.",
                        "requirements": ["alpha"],
                        "files": ["drive_check.py"],
                    },
                    {
                        "key": "build",
                        "title": "Build it",
                        "description": "Build the greeting.",
                        "requirements": ["alpha"],
                        "files": ["greet.py"],
                        "depends_on": ["drive"],
                    },
                ],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def spec_task(app, auth_headers, key, title, depends_on=None):
    """A task serving FR-1, bound to the document's task *key* the way decomposition binds it."""
    body = {"title": title, "requirement_ids": ["FR-1"]}
    if depends_on:
        body["depends_on"] = depends_on
    created = await app.post(TASKS, json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        task = await session.get(Task, task_id)
        task.spec_document_id = document.id
        task.spec_task_key = key
        await session.commit()
    return task_id


async def staged_drive(app, auth_headers, author, root, *, kind, output, key="drive"):
    """The drive task with one awaiting piece of *kind* at a commit on its branch, under review."""
    make_repo(root)
    await drive_document(app, auth_headers, author)
    await set_main_branch("main")
    task = await spec_task(app, auth_headers, key, "Acceptance drive")
    branch = worktrees.task_branch_name(task)
    commit_on_branch(root, branch, "drive_check.py", "print('drive')\n")
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={
            "identifier": "FR-1",
            "task_id": task,
            "kind": kind,
            "summary": "per-check baseline of the acceptance drive on the pre-build code",
            "command": "python drive_check.py",
            "output": output,
            "covers": "full",
        },
        headers=author,
    )
    assert recorded.status_code == 201, recorded.text
    git(root, "checkout", "-q", "main")
    walked = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review"
    )
    assert walked.status_code == 200, walked.text
    return task, recorded.json()["id"]


async def state_of(evidence_id):
    async with async_session_factory() as session:
        return (await session.get(RequirementEvidence, evidence_id)).review_state


async def status_of(task_id):
    async with async_session_factory() as session:
        return (await session.get(Task, task_id)).status


@pytest.mark.asyncio
async def test_a_drive_without_a_baseline_is_not_approved(app, auth_headers, author, tmp_path):
    """ac-no-baseline-no-approval: refused with a code naming the missing baseline, and the
    approval's acceptance of the evidence is rolled back with it."""
    task, evidence = await staged_drive(
        app, auth_headers, author, tmp_path, kind="test_result", output="1 passed"
    )
    refused = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == drive_baseline.MISSING == "drive_baseline_missing"
    assert "drive_baseline" in detail["message"]
    assert await status_of(task) == "under_review"
    assert await state_of(evidence) == "awaiting"


@pytest.mark.asyncio
async def test_a_drive_with_a_baseline_failing_at_each_check_is_approved(
    app, auth_headers, author, tmp_path
):
    task, evidence = await staged_drive(
        app, auth_headers, author, tmp_path, kind="drive_baseline", output=GOOD_BASELINE
    )
    approved = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)
    assert approved.status_code == 200, approved.text
    assert await state_of(evidence) == "accepted"


@pytest.mark.asyncio
async def test_an_agent_recorded_already_built_row_does_not_exempt_the_drive(
    app, auth_headers, author, tmp_path
):
    """Only the operator's close-as-already-built exempts a drive from its baseline: a row of kind
    `already_built` its builder recorded is ordinary evidence, and the reviewer's approval of it
    is still refused for the missing baseline."""
    task, evidence = await staged_drive(
        app, auth_headers, author, tmp_path, kind="already_built", output="nothing to baseline"
    )
    async with async_session_factory() as session:
        assert (await session.get(RequirementEvidence, evidence)).actor_kind != "operator"
    reviewer = await reviewing_run(task)
    refused = await app.patch(
        f"{AGENT_TASKS}/{task}", json={"status": "approved"}, headers=reviewer
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == drive_baseline.MISSING
    assert await status_of(task) == "under_review"
    assert await state_of(evidence) == "awaiting"


@pytest.mark.asyncio
async def test_a_task_that_is_not_the_drive_is_not_gated(app, auth_headers, author, tmp_path):
    """The control: the document's other task approves on ordinary evidence."""
    task, _evidence = await staged_drive(
        app, auth_headers, author, tmp_path, kind="test_result", output="1 passed", key="build"
    )
    approved = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)
    assert approved.status_code == 200, approved.text


@pytest.mark.asyncio
async def test_a_bad_baseline_sends_the_drive_back_naming_both_checks(
    app, auth_headers, author, tmp_path
):
    """ac-bad-baseline: one check stopped at a 404, one passed before the build. The reviewer's
    acceptance and its approval are both refused naming the two checks; it is told the per-check
    rule; its send-back names both, and the dependent task cannot start."""
    task, evidence = await staged_drive(
        app, auth_headers, author, tmp_path, kind="drive_baseline", output=BAD_BASELINE
    )
    dependent = await spec_task(app, auth_headers, "build", "Build it", depends_on=[task])
    reviewer = await reviewing_run(task)

    async with async_session_factory() as session:
        rule = await review_turn.verdict_evidence_sentence(
            session, await session.get(Task, task), may_decide=False
        )
    assert "acceptance drive" in rule and "reached" in rule and "revision_needed" in rule, rule

    # A reviewer accepts with its own reproduction (ERSWB-2); a bad baseline is refused even so.
    at = await verifies.footprint_commit(evidence)
    accepted = await app.post(
        AGENT_DECIDE.format(evidence),
        json=verifies.reproduce(commit=at, command="python drive_check.py", output=BAD_BASELINE),
        headers=reviewer,
    )
    assert accepted.status_code == 409, accepted.text
    detail = accepted.json()["detail"]
    assert detail["code"] == drive_baseline.NOT_FAILING
    assert UNREACHED in detail["message"] and VACUOUS in detail["message"]

    approving = await app.patch(
        f"{AGENT_TASKS}/{task}", json={"status": "approved"}, headers=reviewer
    )
    assert approving.status_code == 409, approving.text
    detail = approving.json()["detail"]
    assert detail["code"] == drive_baseline.NOT_FAILING
    assert {check["check"] for check in detail["checks"]} == {UNREACHED, VACUOUS}
    assert await status_of(task) == "under_review"
    assert await state_of(evidence) == "awaiting"

    named = f"{UNREACHED} stopped at a 404 before its assertion; {VACUOUS} passed pre-build"
    sent = await app.patch(
        f"{AGENT_TASKS}/{task}",
        json={
            "status": "revision_needed",
            "reason_class": "broken-check",
            "notes": named,
            "failing_pieces": [{"piece": evidence, "reason": named}],
        },
        headers=reviewer,
    )
    assert sent.status_code == 200, sent.text
    assert await status_of(task) == "revision_needed"
    assert await state_of(evidence) == "rejected"

    started = await drive_to(app, auth_headers, dependent, "assigned", "in_progress")
    assert started.status_code == 409, started.text
    assert await status_of(dependent) == "assigned"


@pytest.mark.asyncio
async def test_the_operator_is_held_only_to_a_baseline_existing(
    app, auth_headers, author, tmp_path
):
    """What the operator may do with evidence is unchanged: their approval of a baseline whose
    checks the Hub would refuse an agent goes through, since the judgement is theirs."""
    task, evidence = await staged_drive(
        app, auth_headers, author, tmp_path, kind="drive_baseline", output=BAD_BASELINE
    )
    approved = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)
    assert approved.status_code == 200, approved.text
    assert await state_of(evidence) == "accepted"


@pytest.mark.asyncio
async def test_evidence_only_send_backs_and_reviewer_verified_acceptances_are_reported(
    app, auth_headers, author, tmp_path
):
    """ac-reported: one reviewer-verified acceptance and one evidence-only send-back on a task
    appear per task in read_model_record and in the build retrospective."""
    task, evidence, _a, b, _m = await verifies.staged(app, auth_headers, author, tmp_path)
    reviewer = await reviewing_run(task)
    accepted = await app.post(
        AGENT_DECIDE.format(evidence), json=verifies.reproduce(commit=b), headers=reviewer
    )
    assert accepted.status_code == 200, accepted.text
    walked = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review"
    )
    assert walked.status_code == 200, walked.text
    sent = await app.patch(
        f"{TASKS}/{task}",
        json={
            "status": "revision_needed",
            "reason_class": "evidence-only",
            "notes": "Record FR-1 again with its command.",
        },
        headers=auth_headers,
    )
    assert sent.status_code == 200, sent.text

    async with async_session_factory() as session:
        # The author's run is the task's build turn, as the runtime would have bound it.
        (await session.get(Run, "run-f500-author")).task_id = task
        document = (await session.execute(select(SpecDocument))).scalars().first()
        (await session.get(Task, task)).spec_document_id = document.id
        await session.commit()

    async with async_session_factory() as session:
        record = await model_record(session, "proj-test")
        [row] = [
            entry
            for model in record["models"]
            for entry in model["tasks"]
            if entry["task_id"] == task
        ]
        assert row["evidence_only_send_backs"] == 1
        assert row["reviewer_verified_acceptances"] == 1
        [model] = [m for m in record["models"] if row in m["tasks"]]
        assert model["send_backs"]["evidence-only"] == 1
        assert model["reviewer_verified_acceptances"] == 1

        built = await build_retrospective.assemble(session, document)
        report, _ = build_retrospective.build_report(
            built, build_retrospective.RetrospectiveAnswer(), datetime.now(timezone.utc)
        )
    [per_task] = [r for r in report["evidence_review"]["per_task"] if r["task_id"] == task]
    assert per_task["evidence_only_send_backs"] == 1
    assert per_task["reviewer_verified_acceptances"] == 1
    assert report["evidence_review"]["totals"] == {
        "evidence_only_send_backs": 1,
        "reviewer_verified_acceptances": 1,
    }


def test_a_baseline_line_reads_its_check_and_a_bad_check_is_named():
    row = RequirementEvidence(id="ev-x", kind="drive_baseline", output=BAD_BASELINE, summary="")
    checks = {check.key: check for check in drive_baseline.checks_of(row)}
    assert set(checks) == {UNREACHED, VACUOUS}
    assert not checks[UNREACHED].reached
    assert checks[VACUOUS].reached and not checks[VACUOUS].failed_at_assertion
    good = RequirementEvidence(id="ev-y", kind="drive_baseline", output=GOOD_BASELINE, summary="")
    assert [c.key for c in drive_baseline.checks_of(good)] == ["c-one", "c-two"]
    assert drive_baseline.bad_checks(good) == []
