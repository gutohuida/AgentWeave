"""The manager's build retrospective: its triggers, what it reads, what it keeps, where it lands.

`a-finished-spec-gets-a-build-retrospective`. As in `test_chapters_job.py` the worker is faked: a
test hands `build_retrospective.run_worker` what the model would answer, so what is checked is what
the Hub does with it. The real spawn is the acceptance drive's
(`scripts/drive/d1029_build_retrospective.py`).
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from hub import build_retrospective as br
from hub import distillation, manager, vault
from hub.db.engine import async_session_factory
from hub.db.models import (
    AgentOutput,
    Build,
    Checkpoint,
    Conversation,
    EvidenceReview,
    Question,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecDocumentEvent,
    SpecRequirement,
    Stall,
    Task,
    TaskCheckRun,
    TaskTransition,
    TurnUsage,
)
from hub.worker import WorkerResult, WorkerUsage

from .test_spec_archive import PATH as ARCHIVE_PATH
from .test_spec_archive import _approved_document, run_headers  # noqa: F401

P = "proj-test"
BASE = f"/api/v1/projects/{P}"
HAIKU = "claude-haiku-4-5-20251001"
DOC, PATH = "spdoc-retro", "spec/changes/retro/spec.json"
JOB = "build-retrospective"
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def finding(text, *cites):
    return br.Finding(text=text, cites=list(cites))


class _Worker:
    """Stands in for `run_worker`: every call answers *answer*, or fails with a spawn failure."""

    def __init__(self, answer=None, *, fail=False, hold=None) -> None:
        self.answer = answer or br.RetrospectiveAnswer()
        self.fail = fail
        self.hold = hold
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.hold is not None:
            await self.hold.wait()
        if self.fail:
            return WorkerResult("spawn_failed", error="the CLI is not installed")
        return WorkerResult(
            "ok",
            parsed=self.answer,
            usage=WorkerUsage(input_tokens=11, output_tokens=7, cost_usd_micros=900),
            duration_ms=5,
        )


@pytest.fixture
def worker(monkeypatch):
    def install(answer=None, **kwargs):
        fake = _Worker(answer, **kwargs)
        monkeypatch.setattr(br, "run_worker", fake)
        return fake

    return install


async def _runner(app, auth_headers):
    created = await app.post(
        f"{BASE}/runners",
        json={"name": "reviewer", "cli": "claude", "model": HAIKU},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _configure(app, auth_headers, **fields):
    patched = await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"enabled": True, "runner_id": await _runner(app, auth_headers), **fields},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    return patched.json()


async def _seed(*rows):
    async with async_session_factory() as session:
        session.add_all(rows)
        await session.commit()


def _document(document_id=DOC, path=PATH, title="Retro demo"):
    return SpecDocument(
        id=document_id, project_id=P, path=path, title=title, kind="change-spec", phase="approved"
    )


def _task(task_id, status="under_review", document=DOC, created=0, **columns):
    return Task(
        id=task_id,
        project_id=P,
        title=f"Task {task_id}",
        status=status,
        spec_document_id=document,
        spec_task_key=task_id,
        created_at=at(created),
        **columns,
    )


def _run(run_id, task="t1", agent="dev", start=0, minutes=10, status="completed", **columns):
    return Run(
        id=run_id,
        project_id=P,
        agent=agent,
        task_id=task,
        status=status,
        started_at=at(start),
        ended_at=at(start + minutes),
        **columns,
    )


def _move(move_id, task, a, b, minutes, **columns):
    columns.setdefault("actor_kind", "operator")
    return TaskTransition(
        id=move_id,
        project_id=P,
        task_id=task,
        from_status=a,
        to_status=b,
        created_at=at(minutes),
        **columns,
    )


async def _approve(app, auth_headers, task_id):
    moved = await app.patch(
        f"{BASE}/tasks/{task_id}", json={"status": "approved"}, headers=auth_headers
    )
    assert moved.status_code == 200, moved.text


async def _firings():
    await br.settled()
    async with async_session_factory() as session:
        return await manager.list_firings(session, P, job=JOB)


async def _record():
    async with async_session_factory() as session:
        return await br.assemble(session, await session.get(SpecDocument, DOC))


async def _fire(trigger=br.REQUESTED):
    async with async_session_factory() as session:
        document = await session.get(SpecDocument, DOC)
        job, runner = await br.gate(session, P, br.REQUESTED)
        plan = br._plan(document, job, runner)
    return await br.review(plan, trigger=trigger, subject=br.subject_of(plan))


async def _listed(app, auth_headers, path=PATH):
    await br.settled()
    answer = await app.get(
        f"{BASE}/manager/jobs/{JOB}/retrospectives", params={"path": path}, headers=auth_headers
    )
    assert answer.status_code == 200, answer.text
    return answer.json()["retrospectives"]


async def _press(app, auth_headers, path=PATH):
    return await app.post(
        f"{BASE}/manager/jobs/{JOB}/run", params={"path": path}, headers=auth_headers
    )


# ---------------------------------------------------------------------------
# FR-1, FR-2: the job, and when it fires
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_listed_and_off_by_default(app, auth_headers, worker):
    fake = worker()
    await _seed(_document(), _task("t1"))

    jobs = (await app.get(f"{BASE}/manager/jobs", headers=auth_headers)).json()["jobs"]
    job = next(j for j in jobs if j["key"] == JOB)
    assert job["title"] == "Build retrospective"
    assert job["enabled"] is False and job["runner_id"] is None and job["needs_runner"] is True

    await _approve(app, auth_headers, "t1")

    assert await _firings() == [] and fake.calls == []


@pytest.mark.asyncio
async def test_turned_off_with_a_runner_it_does_not_fire_automatically(app, auth_headers, worker):
    fake = worker()
    await _configure(app, auth_headers)
    await app.patch(f"{BASE}/manager/jobs/{JOB}", json={"enabled": False}, headers=auth_headers)
    await _seed(_document(), _task("t1"))
    await _approve(app, auth_headers, "t1")
    assert await _firings() == [] and fake.calls == []


@pytest.mark.asyncio
async def test_fires_exactly_once_after_the_third_of_three(app, auth_headers, worker):
    fake = worker()
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1"), _task("t2"), _task("t3"))

    await _approve(app, auth_headers, "t1")
    await _approve(app, auth_headers, "t2")
    assert await _firings() == [] and fake.calls == []

    await _approve(app, auth_headers, "t3")
    (firing,) = await _firings()
    assert firing["trigger"] == br.LAST_TASK_APPROVED
    assert firing["subject"]["document"] == DOC and firing["subject"]["task"] == "t3"
    assert len(fake.calls) == 1 and fake.calls[0]["initiator"] == "autonomous"


async def _back_to_review(task_id):
    async with async_session_factory() as session:
        (await session.get(Task, task_id)).status = "under_review"
        await session.commit()


@pytest.mark.asyncio
async def test_a_last_task_approved_again_does_not_fire_a_second_time(app, auth_headers, worker):
    """F1144: a landing's merge-needed send-back, then re-approval of the same last task, wrote a
    second retrospective of the same build. A task added afterwards reopens it and fires again;
    Review this build always runs."""
    fake = worker()
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1"))
    await _approve(app, auth_headers, "t1")
    assert len(await _firings()) == 1

    await _back_to_review("t1")
    await _approve(app, auth_headers, "t1")
    assert len(await _firings()) == 1 and len(fake.calls) == 1

    pressed = await _press(app, auth_headers)
    assert pressed.status_code == 202, pressed.text
    assert [f["trigger"] for f in await _firings()] == [br.REQUESTED, br.LAST_TASK_APPROVED]

    reopened = _task("t2")
    reopened.created_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    await _seed(reopened)
    await _approve(app, auth_headers, "t2")
    firings = await _firings()
    assert [f["trigger"] for f in firings][0] == br.LAST_TASK_APPROVED and len(firings) == 3
    assert firings[0]["subject"]["task"] == "t2"


@pytest.mark.asyncio
async def test_on_with_no_runner_says_so_on_the_activity(app, auth_headers, worker):
    fake = worker()
    await app.patch(f"{BASE}/manager/jobs/{JOB}", json={"enabled": True}, headers=auth_headers)
    await _seed(_document(), _task("t1"))
    await _approve(app, auth_headers, "t1")
    (firing,) = await _firings()
    assert firing["outcome"] == "failed" and "no runner" in firing["detail"]
    assert fake.calls == []


# ---------------------------------------------------------------------------
# FR-3: Review this build
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_on_unfinished_build_and_a_second_press(app, auth_headers, worker):
    release = asyncio.Event()
    fake = worker(hold=release)
    await _configure(app, auth_headers, mode="button")
    await _seed(_document(), _task("t1", status="approved"), _task("t2", status="revision_needed"))

    first = await _press(app, auth_headers)
    assert first.status_code == 202, first.text
    for _ in range(100):
        if fake.calls:
            break
        await asyncio.sleep(0.01)
    assert len(fake.calls) == 1

    second = await _press(app, auth_headers)
    assert second.status_code == 409
    assert "in progress" in second.json()["detail"]

    release.set()
    (firing,) = await _firings()
    assert firing["trigger"] == br.REQUESTED
    assert len(fake.calls) == 1 and fake.calls[0]["initiator"] == "operator"
    prompt = fake.calls[0]["prompt"]
    assert '"id": "t1"' in prompt and '"id": "t2"' in prompt

    # The claim is released with the firing.
    third = await _press(app, auth_headers)
    assert third.status_code == 202, third.text
    await br.settled()


@pytest.mark.asyncio
async def test_request_needs_a_runner_a_document_and_tasks(app, auth_headers, worker):
    worker()
    await _seed(_document(), _task("t1", status="in_progress"))
    assert (await _press(app, auth_headers)).status_code == 409  # no runner
    # A runner is enough, with the job turned off.
    await _configure(app, auth_headers)
    await app.patch(f"{BASE}/manager/jobs/{JOB}", json={"enabled": False}, headers=auth_headers)
    assert (await _press(app, auth_headers, "spec/changes/none/spec.json")).status_code == 404
    await _seed(_document("spdoc-empty", "spec/changes/empty/spec.json"))
    assert (await _press(app, auth_headers, "spec/changes/empty/spec.json")).status_code == 409
    assert (await _press(app, auth_headers)).status_code == 202
    await br.settled()


# ---------------------------------------------------------------------------
# FR-4, FR-13: what it reads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_input_holds_every_record_under_its_id(app):
    conversation = Conversation(id="conv-1", project_id=P, agent="dev")
    requirement = SpecRequirement(
        id="spreq-1", project_id=P, document_id=DOC, identifier="FR-1", key="k", digest="d"
    )
    await _seed(
        _document(),
        conversation,
        requirement,
        _task("t1", notes="the-seeded-note"),
    )
    await _seed(
        _run("run-a", conversation_id="conv-1"),
        _move("ttr-1", "t1", "assigned", "in_progress", 1, reason="moved"),
        RequirementEvidence(
            id="evd-1",
            project_id=P,
            requirement_id="spreq-1",
            digest="d",
            kind="test_result",
            actor_kind="agent",
            task_id="t1",
        ),
        TaskCheckRun(
            id="chk-1",
            project_id=P,
            task_id="t1",
            main_sha="a",
            target_shas=[],
            state="failed",
            results=[{"name": "pytest", "exit_code": 1}],
            started_at=at(2),
            ended_at=at(3),
        ),
        Stall(
            id="stall-1",
            project_id=P,
            key="stuck_task:t1",
            cause="stuck_task",
            reason="stuck",
            task_id="t1",
            mender_turns=1,
            outcome="fixed",
            outcome_detail="the-mender-fixed-it",
        ),
        Checkpoint(
            id="ckpt-1",
            project_id=P,
            conversation_id="conv-1",
            agent="dev",
            trigger="operator",
            status="ready",
            lineage_id="ckpt-1",
            body="the-checkpoint-summary",
        ),
        SpecDocumentEvent(
            id="ev-amend",
            document_id=DOC,
            project_id=P,
            kind="amendment",
            actor_kind="agent",
            origin="control",
            detail={"id": "amd-1", "op": "add_criterion", "target": "c9"},
        ),
        SpecDocumentEvent(
            id="ev-rec",
            document_id=DOC,
            project_id=P,
            kind="reconcile",
            actor_kind="agent",
            origin="control",
            detail={"summary": "s", "gaps": [{"class": "missing", "summary": "the-gap"}]},
        ),
        Question(
            id="q-1",
            project_id=P,
            from_agent="dev",
            question="which one?",
            answered=True,
            answer="that",
            created_by_run_id="run-a",
            created_at=at(4),
            answered_at=at(9),
        ),
    )
    await _seed(
        EvidenceReview(
            id="evr-1",
            project_id=P,
            evidence_id="evd-1",
            decision="rejected",
            actor_kind="agent",
            actor="qa",
            reason="the-rejection",
        )
    )

    record = await _record()
    built = br.build_input(record, at(100))
    (task,) = built["tasks"]
    assert task["notes"] == "the-seeded-note"
    assert task["transitions"][0]["id"] == "ttr-1" and task["transitions"][0]["at"]
    assert task["transitions"][0]["who"] == "operator"
    assert task["runs"][0]["id"] == "run-a" and task["runs"][0]["duration_seconds"] == 600
    assert task["evidence"][0]["id"] == "evd-1"
    assert task["evidence"][0]["decisions"][0]["id"] == "evr-1"
    assert task["check_runs"][0]["id"] == "chk-1"
    assert task["stalls"][0]["id"] == "stall-1" and task["stalls"][0]["mender_turns"] == 1
    assert task["checkpoints"][0] == {
        "id": "ckpt-1",
        "agent": "dev",
        "summary": "the-checkpoint-summary",
    }
    assert task["questions"][0]["id"] == "q-1" and task["questions"][0]["waited_seconds"] == 300
    assert {row["id"] for row in built["amendments_and_reconciles"]} == {"ev-amend", "ev-rec"}

    # And the prompt carries it all, as the model reads it.
    prompt = br.prompt_for(record, at(100))
    body = prompt[
        prompt.index(br.RECORD_START) + len(br.RECORD_START) : prompt.index(br.RECORD_END)
    ]
    assert json.loads(body)["tasks"][0]["id"] == "t1"
    for needle in (
        "ttr-1", "run-a", "the-seeded-note", "evr-1", "the-rejection", "chk-1", "stall-1",
        "the-mender-fixed-it", "ckpt-1", "the-checkpoint-summary", "ev-amend", "the-gap", "q-1",
    ):  # fmt: skip
        assert needle in prompt, needle


@pytest.mark.asyncio
async def test_only_and_all_flagged_transcripts(app, auth_headers, worker):
    """One run per flag, three ordinary: the model reads five transcripts and the report lists the
    five. Each ordinary run takes ten minutes, so the median is ten and the long one is flagged."""
    fake = worker(br.RetrospectiveAnswer(what_worked=[finding("fine", "t1")]))
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1"), _task("t2", created=1))
    await _seed(
        _run("run-ordinary-1", start=0),
        # The send-back's: the operator sends t2 back at 40, and this is the last run before it.
        _run("run-ordinary-2", task="t2", start=10),
        _run("run-sent-back", task="t2", start=20),
        _move("ttr-back", "t2", "completed", "revision_needed", 40, reason_class="defect"),
        _run("run-ordinary-3", task="t2", start=45),
        _run("run-stalled", start=60),
        Stall(
            id="stall-1",
            project_id=P,
            key="dead_run:run-stalled",
            cause="dead_run",
            reason="its process ended",
            task_id="t1",
            conversation_id="conv-mender",
        ),
        _run("run-failed", start=70, status="failed"),
        _run("run-long", start=80, minutes=100),
        Conversation(id="conv-mender", project_id=P, agent="mender"),
    )
    await _seed(
        _run("run-mender", task=None, agent="mender", start=190, conversation_id="conv-mender")
    )
    flagged = {"run-sent-back", "run-stalled", "run-failed", "run-long", "run-mender"}
    ordinary = {"run-ordinary-1", "run-ordinary-2", "run-ordinary-3"}
    await _seed(
        *[
            AgentOutput(
                id=f"out-{run_id}",
                project_id=P,
                agent="dev",
                run_id=run_id,
                sequence=1,
                kind="text",
                content=f"transcript-of-{run_id}",
            )
            for run_id in flagged | ordinary
        ]
    )

    record = await _record()
    assert set(record.transcripts) == flagged
    assert set(record.flags) == flagged

    assert await _fire() == "written"
    prompt = fake.calls[0]["prompt"]
    for run_id in flagged:
        assert f"transcript-of-{run_id}" in prompt
    for run_id in ordinary:
        assert f"transcript-of-{run_id}" not in prompt
    (listed,) = await _listed(app, auth_headers)
    read = {row["run_id"]: row["flags"] for row in listed["report"]["transcripts_read"]}
    assert set(read) == flagged
    assert read["run-sent-back"] == ["send_back"] and read["run-long"] == ["over_twice_the_median"]
    assert read["run-mender"] == ["mender"] and read["run-stalled"] == ["stall"]


@pytest.mark.asyncio
async def test_a_reviewers_send_back_flags_its_run_and_the_work_it_sent_back(app):
    await _seed(_document(), _task("t1"))
    await _seed(
        _run("run-work", start=0),
        _run("run-review", agent="qa", start=11),
        _move(
            "ttr-back",
            "t1",
            "under_review",
            "revision_needed",
            20,
            actor_kind="run",
            run_id="run-review",
            actor_agent="qa",
        ),
    )
    assert set((await _record()).flags) == {"run-work", "run-review"}


# ---------------------------------------------------------------------------
# FR-6: figures
# ---------------------------------------------------------------------------


def _usage(run_id, agent, micros, tokens):
    return TurnUsage(
        id=f"use-{run_id}",
        run_id=run_id,
        project_id=P,
        agent=agent,
        status="measured",
        total_tokens=tokens,
        input_tokens=tokens - 1,
        output_tokens=1,
        api_equivalent_usd_micros=micros,
    )


@pytest.mark.asyncio
async def test_figures_equal_records_whatever_the_answer_says(app, auth_headers, worker):
    """t1: created at 0, assigned until 5, building until 25, waiting for review until 40 (of which
    the gate ran 5), back to revision until 50, building until 60, approved at 70."""
    answer = br.RetrospectiveAnswer.model_validate(
        {
            "where_time_went": [
                {"text": "It took 999999 hours and cost a million dollars.", "cites": ["t1"]}
            ],
            "totals": {"cost_usd_micros": 7},
            "cost_usd_micros": 7,
        }
    )
    worker(answer)
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1", status="approved"), _task("t2", status="approved"))
    await _seed(
        _move("m1", "t1", "assigned", "in_progress", 5),
        _move("m2", "t1", "in_progress", "completed", 25),
        _move("m3", "t1", "completed", "revision_needed", 40, reason_class="defect"),
        _move("m4", "t1", "revision_needed", "in_progress", 50),
        _move("m5", "t1", "in_progress", "completed", 60),
        _move("m6", "t1", "completed", "approved", 70),
        TaskCheckRun(
            id="chk-1",
            project_id=P,
            task_id="t1",
            main_sha="a",
            target_shas=[],
            state="passed",
            results=[],
            started_at=at(30),
            ended_at=at(35),
        ),
        _run("r1", agent="dev", start=5),
        _run("r2", agent="qa", start=26),
        _run("r3", task="t2", agent="dev", start=50),
    )
    await _seed(
        _usage("r1", "dev", 1_000, 100),
        _usage("r2", "qa", 2_000, 200),
        _usage("r3", "dev", 4_000, 400),
    )

    assert await _fire() == "written"
    (listed,) = await _listed(app, auth_headers)
    report = listed["report"]

    t1 = next(row for row in report["where_time_went"]["per_task"] if row["task_id"] == "t1")
    assert t1["waiting_to_start_seconds"] == (5 + 10) * 60
    assert t1["building_seconds"] == (20 + 10) * 60
    assert t1["in_check_gate_seconds"] == 5 * 60
    # (40 - 25) + (70 - 60) minutes completed, less the gate's five.
    assert t1["waiting_for_review_seconds"] == (15 + 10 - 5) * 60

    per_agent = {row["agent"]: row for row in report["cost"]["per_agent"]}
    assert per_agent["dev"]["cost_usd_micros"] == 5_000 and per_agent["dev"]["total_tokens"] == 500
    assert per_agent["qa"]["cost_usd_micros"] == 2_000 and per_agent["qa"]["runs"] == 1
    per_task = {row["task_id"]: row for row in report["cost"]["per_task"]}
    assert per_task["t1"]["cost_usd_micros"] == 3_000 and per_task["t2"]["total_tokens"] == 400
    assert report["cost"]["totals"]["cost_usd_micros"] == 7_000
    assert report["cost"]["totals"]["total_tokens"] == 700
    assert report["where_time_went"]["totals"]["building_seconds"] == t1["building_seconds"]
    # The firing's own cost is what its usage says, apart from the build's.
    assert listed["cost_usd_micros"] == 900


# ---------------------------------------------------------------------------
# FR-7, FR-8: the report
# ---------------------------------------------------------------------------


SECTIONS = (
    "where_time_went",
    "send_backs",
    "spec_missed",
    "staffing",
    "cost",
    "friction",
    "what_worked",
    "improvements",
    "lessons",
    "transcripts_read",
)


@pytest.mark.asyncio
async def test_sections_present_with_causes_and_labels(app, auth_headers, worker):
    worker(
        br.RetrospectiveAnswer(
            send_backs=[
                br.SendBackDraft(
                    transition_id="m-model",
                    task_id="t1",
                    cause="spec",
                    explanation="the spec said otherwise",
                    cites=["m-model"],
                ),
                # A cause outside the three cannot stand: the row keeps the reviewer's class.
                br.SendBackDraft(transition_id="m-odd", cause="vibes", cites=["m-odd"]),
            ],
            improvements=[
                br.Improvement(label=label, text=f"do {label}", cites=["t1"]) for label in br.LABELS
            ]
            + [br.Improvement(label="misc", text="no label", cites=["t1"])],
        )
    )
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1"))
    await _seed(
        _move("m-model", "t1", "completed", "revision_needed", 1, reason_class="defect"),
        _move("m-odd", "t1", "completed", "revision_needed", 2, reason_class="flaky"),
        _move("m-none", "t1", "completed", "revision_needed", 3),
    )
    assert await _fire() == "written"
    (listed,) = await _listed(app, auth_headers)
    report = listed["report"]

    for section in SECTIONS:
        assert section in report, section
    causes = {row["transition_id"]: row["cause"] for row in report["send_backs"]}
    assert causes == {"m-model": "spec", "m-odd": "process", "m-none": "defect"}
    assert all(row["cause"] in br.CAUSES for row in report["send_backs"])
    assert [row["label"] for row in report["improvements"]] == list(br.LABELS)
    # Empty sections say there was nothing.
    assert report["nothing"]["what_worked"] and report["nothing"]["lessons"]
    assert report["nothing"]["transcripts_read"]
    assert "send_backs" not in report["nothing"] and "improvements" not in report["nothing"]
    # Two dropped: the odd cause, and the label outside the four.
    assert report["dropped"] == 2


@pytest.mark.asyncio
async def test_the_spec_missed_section_holds_what_the_records_say(app, auth_headers, worker):
    worker(br.RetrospectiveAnswer(what_worked=[finding("fine", "t1")]))
    await _configure(app, auth_headers)
    requirement = {"project_id": P, "document_id": DOC, "key": "k", "digest": "d"}
    await _seed(
        _document(),
        SpecRequirement(id="spreq-1", identifier="FR-1", **requirement),
        Build(
            id="b-1",
            project_id=P,
            document_id=DOC,
            driver="flow",
            level="reviewed",
            created_at=at(10),
        ),
        _task("t1"),
        _task("t-added", created=30),
        SpecDocumentEvent(
            id="ev-amend",
            document_id=DOC,
            project_id=P,
            kind="amendment",
            actor_kind="agent",
            origin="control",
            detail={"id": "amd-1", "op": "add_criterion"},
        ),
        SpecDocumentEvent(
            id="ev-cannot",
            document_id=DOC,
            project_id=P,
            kind="amendment",
            actor_kind="agent",
            origin="control",
            detail={"id": "amd-2", "op": "cannot_satisfy"},
        ),
        SpecDocumentEvent(
            id="ev-rec",
            document_id=DOC,
            project_id=P,
            kind="reconcile",
            actor_kind="agent",
            origin="control",
            detail={"summary": "s", "gaps": [{"class": "missing", "summary": "the-gap"}]},
        ),
    )
    assert await _fire() == "written"
    (listed,) = await _listed(app, auth_headers)
    missed = listed["report"]["spec_missed"]
    assert [row["id"] for row in missed["amendments"]] == ["ev-amend"]
    assert [row["id"] for row in missed["unsatisfiable_criteria"]] == ["ev-cannot"]
    assert [row["task_id"] for row in missed["tasks_added_mid_build"]] == ["t-added"]
    assert missed["requirements_without_accepted_evidence"] == ["FR-1"]
    assert missed["reconcile_gaps"][0]["summary"] == "the-gap"


@pytest.mark.asyncio
async def test_ungrounded_dropped_and_counted(app, auth_headers, worker):
    worker(
        br.RetrospectiveAnswer(
            friction=[
                finding("cites its own build", "t1"),
                finding("cites another document's task", "t-other"),
                finding("cites nothing"),
            ]
        )
    )
    await _configure(app, auth_headers)
    await _seed(
        _document(),
        _document("spdoc-other", "spec/changes/other/spec.json"),
        _task("t1", readable_id="RD-1"),
        _task("t-other", document="spdoc-other"),
    )
    assert await _fire() == "written"
    (listed,) = await _listed(app, auth_headers)
    kept = listed["report"]["friction"]["findings"]
    assert [row["text"] for row in kept] == ["cites its own build"]
    assert listed["report"]["dropped"] == 2


@pytest.mark.asyncio
async def test_a_readable_id_cites_its_task_and_a_mixed_citation_is_dropped(app):
    await _seed(
        _document(),
        _document("spdoc-other", "spec/changes/other/spec.json"),
        _task("t1", readable_id="RD-1"),
        _task("t-other", document="spdoc-other"),
    )
    record = await _record()
    answer = br.RetrospectiveAnswer(
        lessons=[finding("by readable id", "RD-1"), finding("half outside", "t1", "t-other")]
    )
    report, grounded = br.build_report(record, answer, at(100))
    assert grounded and report["dropped"] == 1
    assert report["lessons"] == [{"text": "by readable id", "cites": ["t1"]}]


@pytest.mark.asyncio
async def test_a_requirement_may_be_cited_beside_a_record_but_not_alone(app):
    """Found by the acceptance drive: a real answer's send-back, classified `spec`, cited the
    document's requirement beside its transition, and was dropped for it."""
    await _seed(
        _document(),
        _document("spdoc-other", "spec/changes/other/spec.json"),
        SpecRequirement(
            id="spreq-1", project_id=P, document_id=DOC, identifier="FR-1", key="k", digest="d"
        ),
        SpecRequirement(
            id="spreq-2",
            project_id=P,
            document_id="spdoc-other",
            identifier="FR-2",
            key="k",
            digest="d",
        ),
        _task("t1"),
        _move("m1", "t1", "completed", "revision_needed", 1, reason_class="defect"),
    )
    record = await _record()
    answer = br.RetrospectiveAnswer(
        lessons=[
            finding("beside a record", "t1", "spreq-1"),
            finding("by FR id", "t1", "FR-1"),
            finding("alone", "spreq-1"),
            finding("another document's", "t1", "spreq-2"),
        ],
        send_backs=[
            br.SendBackDraft(transition_id="m1", cause="spec", cites=["m1", "spreq-1"]),
        ],
    )
    report, _ = br.build_report(record, answer, at(100))
    assert [row["text"] for row in report["lessons"]] == ["beside a record", "by FR id"]
    assert report["dropped"] == 2
    assert report["send_backs"][0]["cause"] == "spec"


@pytest.mark.asyncio
async def test_the_list_is_newest_first_with_what_the_page_shows(app, auth_headers, worker):
    fake = worker(br.RetrospectiveAnswer(lessons=[finding("one", "t1")]))
    await _configure(app, auth_headers, model=HAIKU)
    await _seed(_document(), _task("t1", status="approved"))
    assert await _fire() == "written"
    fake.fail = True
    assert await _fire(br.LAST_TASK_APPROVED) == "failed"

    newest, older = await _listed(app, auth_headers)
    assert newest["outcome"] == "failed" and "not installed" in newest["detail"]
    assert newest["trigger"] == br.LAST_TASK_APPROVED and newest["report"] is None
    assert older["outcome"] == "written" and older["trigger"] == br.REQUESTED
    assert older["model"] == HAIKU and older["parts"] == 1 and older["at"]
    assert older["report"]["lessons"][0]["text"] == "one"
    # By id too, and another document's are not this one's.
    await _seed(_document("spdoc-other", "spec/changes/other/spec.json"))
    assert await _listed(app, auth_headers, "spec/changes/other/spec.json") == []
    assert len(await _listed(app, auth_headers, DOC)) == 2
    missing = await app.get(
        f"{BASE}/manager/jobs/{JOB}/retrospectives",
        params={"path": "spec/changes/none/spec.json"},
        headers=auth_headers,
    )
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# FR-10: the vault
# ---------------------------------------------------------------------------


async def _sources(app, auth_headers):
    answer = await app.get(f"{BASE}/vault/map", headers=auth_headers)
    assert answer.status_code == 200, answer.text
    return [e for e in answer.json()["entries"] if e.get("kind") == "source"]


@pytest.fixture
def distils(monkeypatch):
    queued = []

    async def fake(project_id, source_id, *, trigger):
        queued.append((project_id, source_id, trigger))

    monkeypatch.setattr(distillation, "distil_in_background", fake)
    return queued


@pytest.mark.asyncio
async def test_vault_source_added_once_tracked_dated_and_queued(app, auth_headers, worker, distils):
    worker(
        br.RetrospectiveAnswer(
            lessons=[finding("Write the send-back's class down", "t1")],
            improvements=[br.Improvement(label="specs", text="Name the file", cites=["t1"])],
        )
    )
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1", status="approved"))
    assert await _sources(app, auth_headers) == []

    assert await _fire() == "written"
    await br.settled()

    (source,) = await _sources(app, auth_headers)
    assert source["visibility"] == "tracked" and source["dated"]
    assert "Retro demo" in source["name"]
    assert distils == [(P, source["id"], distillation.UPLOADED)]
    (listed,) = await _listed(app, auth_headers)
    assert listed["vault_source"] == source["id"]
    whole = await app.get(f"{BASE}/vault/entries/{source['id']}", headers=auth_headers)
    assert whole.status_code == 200, whole.text
    text = json.dumps(whole.json())
    assert PATH in text and "Write the send-back's class down" in text and "Name the file" in text


@pytest.mark.asyncio
async def test_a_failed_or_empty_firing_adds_no_source(app, auth_headers, worker, distils):
    fake = worker(fail=True)
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1", status="approved"))
    assert await _fire() == "failed"
    # Empty: all the model said was ungrounded.
    fake.fail = False
    fake.answer = br.RetrospectiveAnswer(lessons=[finding("from nowhere")])
    assert await _fire() == "empty"
    await br.settled()
    assert await _sources(app, auth_headers) == [] and distils == []
    empty, failed = await _listed(app, auth_headers)
    assert (empty["outcome"], failed["outcome"]) == ("empty", "failed")
    assert empty["report"]["dropped"] == 1


@pytest.mark.asyncio
async def test_a_vault_that_refuses_the_lessons_leaves_the_report_written(
    app, auth_headers, worker, distils, monkeypatch
):
    worker(br.RetrospectiveAnswer(lessons=[finding("one", "t1")]))
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1", status="approved"))

    def refuse(*args, **kwargs):
        raise vault.VaultError("no")

    monkeypatch.setattr(vault, "add_source", refuse)
    assert await _fire() == "written"
    (listed,) = await _listed(app, auth_headers)
    assert listed["report"] and "did not reach the vault" in listed["detail"]
    assert listed["vault_source"] is None and distils == []


# ---------------------------------------------------------------------------
# FR-12: it never holds the work up
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failure_does_not_block_approval_or_archive(
    app, auth_headers, run_headers, worker  # noqa: F811
):
    """A real approved document: the worker is held while the task is approved and the document
    archived, so either waiting on the job would never come back."""
    release = asyncio.Event()
    fake = worker(fail=True, hold=release)
    await _configure(app, auth_headers)
    await _approved_document(app, auth_headers, run_headers)
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == ARCHIVE_PATH))
        ).scalar_one()
        task = (
            await session.execute(select(Task).where(Task.spec_document_id == document.id))
        ).scalar_one()
        task.status = "under_review"
        task_id = task.id
        await session.commit()

    await asyncio.wait_for(_approve(app, auth_headers, task_id), 30)
    for _ in range(100):
        if fake.calls:
            break
        await asyncio.sleep(0.01)
    assert len(fake.calls) == 1 and await _firings_now() == []

    archived = await asyncio.wait_for(
        app.post(
            f"{BASE}/project/documents/phase",
            params={"path": ARCHIVE_PATH, "to": "archived"},
            json={"reason": "shipped; changes no capability", "no_capability_change": True},
            headers=auth_headers,
        ),
        30,
    )
    assert archived.status_code == 200, archived.text
    assert await _firings_now() == []

    release.set()
    (firing,) = await _firings()
    assert firing["outcome"] == "failed" and "not installed" in firing["detail"]
    assert firing["job"] == JOB


async def _firings_now():
    async with async_session_factory() as session:
        return await manager.list_firings(session, P, job=JOB)


@pytest.mark.asyncio
async def test_a_firing_that_raises_is_recorded_as_failed(app, auth_headers, worker, monkeypatch):
    worker()
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1"))

    async def explode(*args, **kwargs):
        raise RuntimeError("the record could not be read")

    monkeypatch.setattr(br, "assemble", explode)
    assert (await _press(app, auth_headers)).status_code == 202
    (firing,) = await _firings()
    assert firing["outcome"] == "failed" and "could not be read" in firing["detail"]
    # The claim went with it.
    assert (P, DOC) not in br._running


@pytest.mark.asyncio
async def test_a_rolled_back_approval_fires_nothing(app, auth_headers, worker):
    fake = worker()
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1"))
    async with async_session_factory() as session:
        task = (await session.execute(select(Task).where(Task.id == "t1"))).scalar_one()
        br.fire_after_commit(session, task)
        await session.rollback()
    assert await _firings() == [] and fake.calls == []
