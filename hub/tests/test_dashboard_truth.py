"""The dashboard says what is true — F17, F14 and F9 from the 2026-08-23 stress-test drive.

Three surfaces that were confidently wrong about work the Hub itself had done:

* **F17** — every Hub-managed agent read "No activity yet" forever, because `last_seen` came from
  heartbeat rows and only a self-registered agent writes one.
* **F14** — a task whose run sits waiting on `ask_user` read `in_progress` with no reason, so the
  board claimed progress while the answer was on the operator's desk.
* **F9** — approving a task cherry-picks into the operator's main branch, and nothing said so
  before they clicked.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hub.agent_activity import latest_activity_by_agent
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AgentHeartbeat,
    AgentOutput,
    EvidenceFootprint,
    Project,
    Question,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecRequirement,
    Task,
    TaskRequirementLink,
)

NOW = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)


def ago(minutes: int) -> datetime:
    return NOW - timedelta(minutes=minutes)


async def _agent(session, name: str, *, self_registered: bool = False) -> Agent:
    row = Agent(
        id=f"agent-{name}",
        project_id="proj-test",
        name=name,
        self_registered=self_registered,
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# F17 — last_seen means "last observed doing anything", not "last heartbeat"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_hub_spawned_agent_that_never_heartbeats_still_reports_activity(app):
    """The exact measured case: nine runs, hundreds of output rows, zero heartbeats."""
    async with async_session_factory() as session:
        await _agent(session, "builder")
        session.add(
            Run(
                id="run-1",
                project_id="proj-test",
                agent="builder",
                status="completed",
                started_at=ago(40),
                ended_at=ago(31),
            )
        )
        session.add(
            AgentOutput(
                id="out-1",
                project_id="proj-test",
                agent="builder",
                content="done",
                timestamp=ago(30),
            )
        )
        await session.commit()

        seen = await latest_activity_by_agent(session, "proj-test", ["builder"])

    assert seen["builder"] == ago(30), "the newest of run/output timestamps wins"


@pytest.mark.asyncio
async def test_a_run_that_has_only_started_already_counts(app):
    """`started_at` is the one non-NULL timestamp, and a live run is the most active an agent gets.

    Without this the rail would still read "No activity yet" for the whole of a first run, which is
    precisely the moment the operator is looking at it.
    """
    async with async_session_factory() as session:
        await _agent(session, "builder")
        session.add(
            Run(
                id="run-live",
                project_id="proj-test",
                agent="builder",
                status="running",
                started_at=ago(2),
            )
        )
        await session.commit()

        seen = await latest_activity_by_agent(session, "proj-test", ["builder"])

    assert seen["builder"] == ago(2)


@pytest.mark.asyncio
async def test_a_heartbeat_still_counts_and_can_be_the_newest_thing(app):
    """A self-registered agent that only ever heartbeats reads exactly as it did before."""
    async with async_session_factory() as session:
        await _agent(session, "poller", self_registered=True)
        session.add(
            Run(
                id="run-old",
                project_id="proj-test",
                agent="poller",
                status="completed",
                started_at=ago(90),
                ended_at=ago(80),
            )
        )
        session.add(
            AgentHeartbeat(
                id="hb-1",
                project_id="proj-test",
                agent="poller",
                status="idle",
                timestamp=ago(1),
            )
        )
        await session.commit()

        seen = await latest_activity_by_agent(session, "proj-test", ["poller"])

    assert seen["poller"] == ago(1)


@pytest.mark.asyncio
async def test_an_agent_with_nothing_recorded_is_absent_rather_than_none(app):
    """Callers keep writing `.get(name)` and keep getting the NULL they used to get."""
    async with async_session_factory() as session:
        await _agent(session, "fresh")
        await session.commit()

        seen = await latest_activity_by_agent(session, "proj-test", ["fresh"])

    assert seen == {}


@pytest.mark.asyncio
async def test_activity_never_leaks_across_projects(app):
    async with async_session_factory() as session:
        session.add(Project(id="proj-other", name="Other"))
        await session.flush()
        await _agent(session, "builder")
        session.add(
            Run(
                id="run-elsewhere",
                project_id="proj-other",
                agent="builder",
                status="completed",
                started_at=ago(3),
                ended_at=ago(2),
            )
        )
        await session.commit()

        seen = await latest_activity_by_agent(session, "proj-test", ["builder"])

    assert seen == {}


@pytest.mark.asyncio
async def test_the_agents_route_reports_the_derived_last_seen(app, auth_headers):
    """The surface, not the helper: `AgentCard` and `OverviewPage` read this response."""
    async with async_session_factory() as session:
        await _agent(session, "builder")
        session.add(
            Run(
                id="run-1",
                project_id="proj-test",
                agent="builder",
                status="completed",
                started_at=ago(20),
                ended_at=ago(10),
            )
        )
        await session.commit()

    response = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert response.status_code == 200, response.text
    builder = next(a for a in response.json() if a["name"] == "builder")
    assert builder["last_seen"] is not None
    assert builder["last_seen"].startswith("2026-08-23T17:50")


@pytest.mark.asyncio
async def test_the_project_rail_reports_the_same_derived_last_seen(app, auth_headers):
    """The rail (`AgentTree`) reads `/projects`, not `/agents`. The two must not disagree."""
    async with async_session_factory() as session:
        await _agent(session, "builder")
        session.add(
            Run(
                id="run-1",
                project_id="proj-test",
                agent="builder",
                status="completed",
                started_at=ago(20),
                ended_at=ago(10),
            )
        )
        await session.commit()

    response = await app.get("/api/v1/projects", headers=auth_headers)
    assert response.status_code == 200, response.text
    project = next(p for p in response.json() if p["id"] == "proj-test")
    builder = next(a for a in project["agents"] if a["name"] == "builder")
    assert builder["last_seen"] is not None
    assert builder["last_seen"].startswith("2026-08-23T17:50")


# ---------------------------------------------------------------------------
# F14 — a task waiting on the operator says so, without its status moving
# ---------------------------------------------------------------------------


async def _waiting_task(session, *, run_status: str = "running", **question_kwargs) -> Task:
    task = Task(
        id="task-1",
        project_id="proj-test",
        title="Add a trial-balance report",
        status="in_progress",
        assignee="builder",
    )
    session.add(task)
    session.add(
        Run(
            id="run-1",
            project_id="proj-test",
            agent="builder",
            status=run_status,
            task_id="task-1",
            started_at=ago(5),
        )
    )
    fields = {
        "blocking": True,
        "answered": False,
        "declined": False,
        "question": "Which ledger should this report read?",
        **question_kwargs,
    }
    session.add(
        Question(
            id="q-1",
            project_id="proj-test",
            from_agent="builder",
            created_by_run_id="run-1",
            created_at=ago(4),
            **fields,
        )
    )
    await session.commit()
    return task


@pytest.mark.asyncio
async def test_a_live_run_waiting_on_a_question_is_reported_without_moving_the_task(
    app, auth_headers
):
    """The measured defect: `in_progress`, `blocked_reason: null`, and an agent that had stopped."""
    async with async_session_factory() as session:
        await _waiting_task(session)

    response = await app.get("/api/v1/projects/proj-test/tasks/task-1", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "in_progress", "F14 reports the wait, it does not park the task"
    assert body["blocked_reason"] is None
    assert body["awaiting_answer_reason"] == (
        "Waiting on your answer: Which ledger should this report read?"
    )


@pytest.mark.asyncio
async def test_the_board_list_carries_it_too(app, auth_headers):
    """The card the operator is actually looking at comes from the list route."""
    async with async_session_factory() as session:
        await _waiting_task(session)

    response = await app.get("/api/v1/projects/proj-test/tasks", headers=auth_headers)
    assert response.status_code == 200, response.text
    task = next(t for t in response.json() if t["id"] == "task-1")
    assert task["awaiting_answer_reason"].startswith("Waiting on your answer:")


@pytest.mark.asyncio
async def test_an_answered_question_stops_being_reported(app, auth_headers):
    async with async_session_factory() as session:
        await _waiting_task(session, answered=True, answer="the general ledger")

    response = await app.get("/api/v1/projects/proj-test/tasks/task-1", headers=auth_headers)
    assert response.json()["awaiting_answer_reason"] is None


@pytest.mark.asyncio
async def test_a_declined_question_stops_being_reported(app, auth_headers):
    """Matching `unanswered_blocking_question`: declining closes the question."""
    async with async_session_factory() as session:
        await _waiting_task(session, declined=True)

    response = await app.get("/api/v1/projects/proj-test/tasks/task-1", headers=auth_headers)
    assert response.json()["awaiting_answer_reason"] is None


@pytest.mark.asyncio
async def test_a_non_blocking_question_is_a_note_and_not_a_wait(app, auth_headers):
    """`ask_user(blocking=False)` is the agent carrying on. Nothing is waiting."""
    async with async_session_factory() as session:
        await _waiting_task(session, blocking=False)

    response = await app.get("/api/v1/projects/proj-test/tasks/task-1", headers=auth_headers)
    assert response.json()["awaiting_answer_reason"] is None


@pytest.mark.asyncio
async def test_an_ended_run_no_longer_reports_a_live_wait(app, auth_headers):
    """Once the run ends, `block_task_for_question` owns the fact and moves the status.

    A finished run cannot receive an answer, so continuing to claim the task is waiting on one
    would be the same lie in the other direction.
    """
    async with async_session_factory() as session:
        await _waiting_task(session, run_status="completed")

    response = await app.get("/api/v1/projects/proj-test/tasks/task-1", headers=auth_headers)
    assert response.json()["awaiting_answer_reason"] is None


@pytest.mark.asyncio
async def test_a_parked_task_reports_the_wait_in_the_same_words(app, auth_headers):
    """`blocked_task_id` is the other route in — so a blocked card and an in_progress one waiting
    on the same question read alike rather than being two different-looking situations."""
    async with async_session_factory() as session:
        await _waiting_task(session, run_status="completed")
        task = await session.get(Task, "task-1")
        task.status = "blocked"
        task.blocked_reason = "Waiting on your answer: Which ledger should this report read?"
        question = await session.get(Question, "q-1")
        question.blocked_task_id = "task-1"
        await session.commit()

    response = await app.get("/api/v1/projects/proj-test/tasks/task-1", headers=auth_headers)
    body = response.json()
    assert body["awaiting_answer_reason"] == body["blocked_reason"]


@pytest.mark.asyncio
async def test_another_agents_open_question_does_not_touch_this_task(app, auth_headers):
    """The same exclusion `unanswered_blocking_question` documents: an unrelated agent's
    unfinished business is not evidence that this task is waiting."""
    async with async_session_factory() as session:
        task = Task(
            id="task-1",
            project_id="proj-test",
            title="Add a trial-balance report",
            status="in_progress",
        )
        session.add(task)
        session.add(
            Run(
                id="run-other",
                project_id="proj-test",
                agent="critic",
                status="running",
                started_at=ago(5),
            )
        )
        session.add(
            Question(
                id="q-1",
                project_id="proj-test",
                from_agent="critic",
                created_by_run_id="run-other",
                created_at=ago(4),
                blocking=True,
                answered=False,
                declined=False,
                question="unrelated",
            )
        )
        await session.commit()

    response = await app.get("/api/v1/projects/proj-test/tasks/task-1", headers=auth_headers)
    assert response.json()["awaiting_answer_reason"] is None


# ---------------------------------------------------------------------------
# F9 — approving is a write, and the preview says what it will write
# ---------------------------------------------------------------------------


async def _task_with_accepted_commit(
    session, *, commit="cecbc88751ea", branch="agentweave/builder"
):
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
    task = Task(
        id="task-1",
        project_id="proj-test",
        title="Balance the ledger",
        status="under_review",
    )
    session.add(task)
    session.add(
        TaskRequirementLink(
            id="link-1", project_id="proj-test", task_id="task-1", requirement_id="req-1"
        )
    )
    session.add(
        RequirementEvidence(
            id="ev-1",
            project_id="proj-test",
            requirement_id="req-1",
            digest="d" * 64,
            kind="commit",
            actor_kind="agent",
            actor="builder",
            summary="balanced",
            review_state="accepted",
        )
    )
    session.add(
        EvidenceFootprint(
            id="fp-1",
            project_id="proj-test",
            evidence_id="ev-1",
            kind="git",
            commit_sha=commit,
            branch=branch,
            observed_at=ago(10),
        )
    )
    await session.commit()
    return task


@pytest.mark.asyncio
async def test_the_preview_names_the_commit_and_both_branches(app, auth_headers):
    """The whole point of F9: before clicking approve, the operator sees the write."""
    async with async_session_factory() as session:
        await _task_with_accepted_commit(session)
        project = await session.get(Project, "proj-test")
        project.main_branch = "master"
        await session.commit()

    response = await app.get(
        "/api/v1/projects/proj-test/tasks/task-1/integration-preview", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["will_merge"] is True
    assert body["main_branch"] == "master"
    assert body["targets"] == [
        {"commit_sha": "cecbc88751ea", "source_branch": "agentweave/builder"}
    ]
    assert body["reason"] == ""


@pytest.mark.asyncio
async def test_no_main_branch_is_a_stated_reason_not_a_failure(app, auth_headers):
    async with async_session_factory() as session:
        await _task_with_accepted_commit(session)

    response = await app.get(
        "/api/v1/projects/proj-test/tasks/task-1/integration-preview", headers=auth_headers
    )
    body = response.json()
    assert body["will_merge"] is False
    assert "no main branch" in body["reason"]


@pytest.mark.asyncio
async def test_evidence_still_awaiting_review_merges_nothing(app, auth_headers):
    """Only `accepted` evidence contributes — the same rule `integration_targets` enforces, so the
    preview cannot promise a merge the approval would then skip."""
    async with async_session_factory() as session:
        await _task_with_accepted_commit(session)
        project = await session.get(Project, "proj-test")
        project.main_branch = "master"
        evidence = await session.get(RequirementEvidence, "ev-1")
        evidence.review_state = "awaiting"
        await session.commit()

    response = await app.get(
        "/api/v1/projects/proj-test/tasks/task-1/integration-preview", headers=auth_headers
    )
    body = response.json()
    assert body["will_merge"] is False
    assert body["targets"] == []
    assert "no accepted evidence" in body["reason"]


@pytest.mark.asyncio
async def test_a_task_from_another_project_is_not_previewable(app, auth_headers):
    async with async_session_factory() as session:
        session.add(Project(id="proj-other", name="Other"))
        await session.flush()
        session.add(
            Task(id="task-elsewhere", project_id="proj-other", title="Elsewhere", status="pending")
        )
        await session.commit()

    response = await app.get(
        "/api/v1/projects/proj-test/tasks/task-elsewhere/integration-preview",
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# F6's other half — the board agrees with the rail about what an agent is doing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_task_whose_agent_is_running_does_not_report_it_idle(app, auth_headers):
    """Measured on 2026-08-23: `status: in_progress`, and `assignee_status: "idle"` about an agent
    that was at that moment running. Q1 gave the task an assignee; the status stayed heartbeat-only.
    """
    async with async_session_factory() as session:
        await _agent(session, "builder")
        session.add(
            Task(
                id="task-1",
                project_id="proj-test",
                title="Balance the ledger",
                status="in_progress",
                assignee="builder",
            )
        )
        session.add(
            Run(
                id="run-live",
                project_id="proj-test",
                agent="builder",
                status="running",
                task_id="task-1",
                started_at=ago(3),
            )
        )
        await session.commit()

    response = await app.get("/api/v1/projects/proj-test/tasks/task-1", headers=auth_headers)
    body = response.json()
    assert body["assignee_status"] == "running"
    assert body["assignee_last_seen"] is not None


@pytest.mark.asyncio
async def test_a_stalled_heartbeat_survives_a_derivation_that_has_no_run_to_offer(
    app, auth_headers
):
    """The activity derivation does not, by itself, talk a stalled agent back into running.

    Named for what it actually pins, which is narrower than it first read: there is deliberately no
    live `Run` row here. `stalled` is what `effective_heartbeat_status` makes of a `running`
    heartbeat older than two minutes, and nothing in `_attach_assignee_liveness` may quietly undo
    that on the strength of a `last_seen` it derived from output or from an already-finished run.

    What happens when a live run *does* coexist with a stalled heartbeat is the next test, and the
    answer there is the opposite one — on purpose.
    """
    async with async_session_factory() as session:
        await _agent(session, "builder", self_registered=True)
        session.add(
            Task(
                id="task-1",
                project_id="proj-test",
                title="Balance the ledger",
                status="in_progress",
                assignee="builder",
            )
        )
        session.add(
            AgentHeartbeat(
                id="hb-1",
                project_id="proj-test",
                agent="builder",
                status="running",
                timestamp=ago(60),
            )
        )
        await session.commit()

    body = (await app.get("/api/v1/projects/proj-test/tasks/task-1", headers=auth_headers)).json()
    assert body["assignee_status"] == "stalled"
    assert body["assignee_status_msg"]


@pytest.mark.asyncio
async def test_a_live_run_outranks_a_stalled_heartbeat_here_exactly_as_it_does_on_the_roster(
    app, auth_headers
):
    """A live `Run` wins over the heartbeat, `stalled` included — and that is a copied precedence.

    `agents.py` has done this since long before F6: `if agent_name in agents_with_active_run:
    effective_status, effective_status_message = "running", None`, unconditionally, after
    `effective_heartbeat_status` has had its say. `projects.py`'s rail does the same.

    This is not an argument that a run row is better evidence of health than a heartbeat. It is the
    only way three surfaces can describe one agent identically, which is the whole of what F6
    reported — a card calling an agent idle while the rail beside it called the same agent running.
    Pinned so that the precedence cannot be softened on one surface alone: if it is ever
    reconsidered, this test fails alongside the roster's own, which is the point.
    """
    async with async_session_factory() as session:
        await _agent(session, "builder", self_registered=True)
        session.add(
            Task(
                id="task-1",
                project_id="proj-test",
                title="Balance the ledger",
                status="in_progress",
                assignee="builder",
            )
        )
        session.add(
            AgentHeartbeat(
                id="hb-1",
                project_id="proj-test",
                agent="builder",
                status="running",
                timestamp=ago(60),
            )
        )
        session.add(
            Run(
                id="run-live",
                project_id="proj-test",
                agent="builder",
                status="running",
                task_id="task-1",
                started_at=ago(1),
            )
        )
        await session.commit()

    board = (await app.get("/api/v1/projects/proj-test/tasks/task-1", headers=auth_headers)).json()
    roster = (await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)).json()
    seat = next(entry for entry in roster if entry["name"] == "builder")

    assert board["assignee_status"] == "running"
    assert board["assignee_status_msg"] is None
    # The assertion that matters is not either value on its own — it is that they are the same one.
    assert board["assignee_status"] == seat["status"]


@pytest.mark.asyncio
async def test_an_idle_agent_with_no_live_run_still_reads_idle(app, auth_headers):
    async with async_session_factory() as session:
        await _agent(session, "builder")
        session.add(
            Task(
                id="task-1",
                project_id="proj-test",
                title="Balance the ledger",
                status="in_progress",
                assignee="builder",
            )
        )
        session.add(
            Run(
                id="run-done",
                project_id="proj-test",
                agent="builder",
                status="completed",
                task_id="task-1",
                started_at=ago(30),
                ended_at=ago(25),
            )
        )
        await session.commit()

    body = (await app.get("/api/v1/projects/proj-test/tasks/task-1", headers=auth_headers)).json()
    assert body["assignee_status"] == "idle"
    # But it still says when the work happened, which it never used to.
    assert body["assignee_last_seen"] is not None
