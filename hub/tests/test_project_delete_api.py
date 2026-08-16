"""Formal coverage for ``DELETE /api/v1/projects/{project_id}``.

Complements the throwaway HTTP checks done live during Q4b phase 2 (see
``.claude/autonomous/2026-08-16-app-and-test-reform-log.md`` Entry 8) with committed,
reviewable coverage: an exhaustive no-orphan sweep across every ``project_id``-bearing
table (not a sample), a second project's isolation, the active-run refusal, the
mutation-checked proof that the workspace directory is never touched, and the two
non-blocking cases (terminal run, open conversation) tasks.md's phase 3 calls for.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AgentHeartbeat,
    AgentJobDeletion,
    AgentOutput,
    AIJob,
    ApiKey,
    Base,
    Charter,
    Checkpoint,
    CheckpointNote,
    Conversation,
    EventLog,
    EvidenceFootprint,
    EvidenceReview,
    InboundQueueEntry,
    JobRun,
    Message,
    PermissionRequest,
    Project,
    ProjectInstructions,
    ProjectSession,
    Question,
    RequirementDrift,
    RequirementEvidence,
    Run,
    RunDivergence,
    Runner,
    SpecDocument,
    SpecDocumentEvent,
    SpecRequirement,
    SpecRequirementRevision,
    SpecRigorEvent,
    Task,
    TaskIntegration,
    TaskRequirementLink,
    TaskRequirementReference,
    TaskTransition,
    TurnUsage,
    UnaskedQuestion,
    WorkerInvocation,
)
from hub.project_lifecycle import ProjectLifecycleService
from hub.project_workspace import ProjectPathError

# Every table `_project_scoped_tables()` (hub/hub/project_lifecycle.py) sweeps, i.e. every
# table other than `projects` carrying a `project_id` column — introspected directly from
# `Base.metadata.sorted_tables` rather than hand-copied, so this list is checked against the
# live model registry in `test_sweep_covers_every_project_scoped_table_in_the_model_registry`
# below instead of silently drifting out of date.
PROJECT_SCOPED_TABLE_NAMES = [
    "requirement_drift",
    "evidence_reviews",
    "evidence_footprints",
    "turn_usage",
    "task_requirement_links",
    "spec_requirement_revisions",
    "requirement_evidence",
    "task_transitions",
    "task_requirement_references",
    "task_integrations",
    "spec_rigor_events",
    "spec_requirements",
    "spec_document_events",
    "runs",
    "run_divergences",
    "messages",
    "job_runs",
    "inbound_queue_entries",
    "checkpoints",
    "agents",
    "agent_outputs",
    "worker_invocations",
    "unasked_questions",
    "tasks",
    "spec_documents",
    "runners",
    "questions",
    "project_sessions",
    "project_instructions",
    "permission_requests",
    "event_logs",
    "conversations",
    "checkpoint_notes",
    "charters",
    "api_keys",
    "ai_jobs",
    "agent_heartbeats",
    "agent_job_deletions",
]


def test_sweep_covers_every_project_scoped_table_in_the_model_registry() -> None:
    live = {
        table.name
        for table in Base.metadata.sorted_tables
        if table.name != "projects" and "project_id" in table.c
    }
    assert live == set(PROJECT_SCOPED_TABLE_NAMES)


async def _seed_full_project(session, project_id: str, tag: str) -> None:
    """Add one row to every project-scoped table, all referencing *project_id*.

    *tag* keeps primary keys unique when this is called twice in the same test (two
    projects, or a project seeded across two test phases).
    """

    session.add(Charter(id=f"charter-{tag}", project_id=project_id, name="Charter"))
    session.add(Runner(id=f"runner-{tag}", project_id=project_id, name="Runner", cli="claude"))
    session.add(Agent(id=f"agent-{tag}", project_id=project_id, name=f"agent-{tag}"))
    session.add(Task(id=f"task-{tag}", project_id=project_id, title="Task"))
    session.add(Conversation(id=f"conv-{tag}", project_id=project_id, agent=f"agent-{tag}"))
    session.add(
        Message(
            id=f"msg-{tag}",
            project_id=project_id,
            sender=f"agent-{tag}",
            recipient="operator",
            conversation_id=f"conv-{tag}",
        )
    )
    session.add(
        Run(
            id=f"run-{tag}",
            project_id=project_id,
            agent=f"agent-{tag}",
            status="completed",
            conversation_id=f"conv-{tag}",
            task_id=f"task-{tag}",
        )
    )
    session.add(
        TurnUsage(
            id=f"turnusage-{tag}",
            run_id=f"run-{tag}",
            project_id=project_id,
            agent=f"agent-{tag}",
            status="unavailable",
        )
    )
    session.add(
        RunDivergence(
            id=f"rundiv-{tag}",
            project_id=project_id,
            run_id=f"run-{tag}",
            agent=f"agent-{tag}",
            task_id=f"task-{tag}",
            task_status_at_end="in_progress",
            run_exit_status="nonzero",
            policy_applied="surface",
            outcome="surfaced",
        )
    )
    session.add(
        AIJob(
            id=f"job-{tag}",
            project_id=project_id,
            name="Job",
            agent=f"agent-{tag}",
            message="do work",
            cron="0 0 * * *",
        )
    )
    session.add(JobRun(id=f"jobrun-{tag}", job_id=f"job-{tag}", project_id=project_id))
    session.add(
        AgentJobDeletion(
            id=f"jobdel-{tag}",
            job_id=f"job-{tag}",
            project_id=project_id,
            agent=f"agent-{tag}",
            run_id=f"run-{tag}",
        )
    )
    session.add(
        InboundQueueEntry(
            id=f"inbound-{tag}",
            project_id=project_id,
            agent=f"agent-{tag}",
            origin_type="operator",
            content="hello",
            hop_depth=0,
        )
    )
    session.add(
        Checkpoint(
            id=f"checkpoint-{tag}",
            project_id=project_id,
            conversation_id=f"conv-{tag}",
            agent=f"agent-{tag}",
            trigger="operator",
            status="unwritten",
            lineage_id=f"lineage-{tag}",
        )
    )
    session.add(
        CheckpointNote(
            id=f"checkpointnote-{tag}",
            project_id=project_id,
            conversation_id=f"conv-{tag}",
            agent=f"agent-{tag}",
            intent="testing",
        )
    )
    session.add(
        WorkerInvocation(
            id=f"worker-{tag}",
            project_id=project_id,
            kind="probe",
            prompt_version="v1",
            cli="claude",
            outcome="ok",
        )
    )
    session.add(
        Question(
            id=f"question-{tag}",
            project_id=project_id,
            from_agent=f"agent-{tag}",
            question="why?",
        )
    )
    session.add(
        UnaskedQuestion(
            id=f"unasked-{tag}", project_id=project_id, agent=f"agent-{tag}", question="why not?"
        )
    )
    session.add(
        PermissionRequest(
            id=f"perm-{tag}", project_id=project_id, agent=f"agent-{tag}", tool_name="bash"
        )
    )
    session.add(EventLog(id=f"event-{tag}", project_id=project_id, event_type="test_event"))
    session.add(AgentHeartbeat(id=f"heartbeat-{tag}", project_id=project_id, agent=f"agent-{tag}"))
    session.add(
        AgentOutput(id=f"output-{tag}", project_id=project_id, agent=f"agent-{tag}", content="hi")
    )
    session.add(ProjectSession(project_id=project_id, data={"tag": tag}))
    session.add(ProjectInstructions(project_id=project_id, content="instructions"))
    session.add(ApiKey(id=f"aw_live_{tag}_key", project_id=project_id))

    session.add(SpecDocument(id=f"specdoc-{tag}", project_id=project_id, path=f"spec-{tag}.md"))
    session.add(
        SpecRigorEvent(
            id=f"rigor-{tag}",
            project_id=project_id,
            document_id=f"specdoc-{tag}",
            from_rigor="low",
            to_rigor="high",
            actor_kind="operator",
        )
    )
    session.add(
        SpecDocumentEvent(
            id=f"specdocevent-{tag}",
            document_id=f"specdoc-{tag}",
            project_id=project_id,
            kind="created",
            actor_kind="operator",
            origin="control",
        )
    )
    session.add(
        SpecRequirement(
            id=f"req-{tag}",
            project_id=project_id,
            document_id=f"specdoc-{tag}",
            identifier="FR-1",
            key=f"fr1-{tag}",
            digest="digest",
        )
    )
    session.add(
        SpecRequirementRevision(
            id=f"reqrev-{tag}",
            project_id=project_id,
            requirement_id=f"req-{tag}",
            document_id=f"specdoc-{tag}",
            digest="digest",
            source="hub",
            classification="created",
            actor_kind="operator",
        )
    )
    session.add(
        TaskRequirementLink(
            id=f"tasklink-{tag}", project_id=project_id, task_id=f"task-{tag}", requirement_id=f"req-{tag}"
        )
    )
    session.add(
        TaskRequirementReference(
            id=f"taskref-{tag}", project_id=project_id, task_id=f"task-{tag}", reference="#FR-1"
        )
    )
    session.add(
        RequirementEvidence(
            id=f"evidence-{tag}",
            project_id=project_id,
            requirement_id=f"req-{tag}",
            digest="digest",
            kind="test",
            actor_kind="operator",
        )
    )
    session.add(
        EvidenceReview(
            id=f"evreview-{tag}",
            project_id=project_id,
            evidence_id=f"evidence-{tag}",
            decision="accepted",
            actor_kind="operator",
        )
    )
    session.add(
        EvidenceFootprint(
            id=f"evfootprint-{tag}", project_id=project_id, evidence_id=f"evidence-{tag}", kind="paths"
        )
    )
    session.add(
        RequirementDrift(
            id=f"drift-{tag}", project_id=project_id, requirement_id=f"req-{tag}", evidence_id=f"evidence-{tag}"
        )
    )
    session.add(
        TaskIntegration(
            id=f"integration-{tag}",
            project_id=project_id,
            task_id=f"task-{tag}",
            outcome="merged",
            actor_kind="operator",
        )
    )
    session.add(
        TaskTransition(
            id=f"transition-{tag}",
            project_id=project_id,
            task_id=f"task-{tag}",
            from_status="pending",
            to_status="in_progress",
            actor_kind="operator",
        )
    )
    await session.flush()


async def _counts_for_project(session, project_id: str) -> dict:
    """Row count in every project-scoped table, plus `projects` itself, for *project_id*."""

    counts = {}
    for table in Base.metadata.sorted_tables:
        if table.name != "projects" and "project_id" not in table.c:
            continue
        column = table.c.id if table.name == "projects" else table.c.project_id
        counts[table.name] = await session.scalar(
            select(func.count()).select_from(table).where(column == project_id)
        )
    return counts


@pytest.mark.asyncio
async def test_delete_removes_a_representative_sample_of_project_scoped_rows(app) -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-victim", name="Victim"))
        await session.flush()
        await _seed_full_project(session, "proj-victim", "v1")
        await session.commit()

    async with async_session_factory() as session:
        await ProjectLifecycleService(session).delete("proj-victim")

    async with async_session_factory() as session:
        assert await session.get(Project, "proj-victim") is None
        for table_name, model in (
            ("agents", Agent),
            ("runners", Runner),
            ("charters", Charter),
            ("tasks", Task),
            ("conversations", Conversation),
            ("messages", Message),
            ("runs", Run),
            ("event_logs", EventLog),
        ):
            count = await session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.project_id == "proj-victim")
            )
            assert count == 0, f"{table_name} still has rows for the deleted project"


@pytest.mark.asyncio
async def test_delete_leaves_no_orphans_in_any_project_scoped_table(app) -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-victim", name="Victim"))
        await session.flush()
        await _seed_full_project(session, "proj-victim", "v2")
        await session.commit()

    async with async_session_factory() as session:
        before = await _counts_for_project(session, "proj-victim")
    # Sanity: the seed actually populated every table this test claims to check —
    # otherwise a table left at 0 both before and after would pass for the wrong reason.
    assert all(count and count > 0 for count in before.values()), before

    async with async_session_factory() as session:
        await ProjectLifecycleService(session).delete("proj-victim")

    async with async_session_factory() as session:
        after = await _counts_for_project(session, "proj-victim")
    assert all(count == 0 for count in after.values()), after
    assert set(after) == set(PROJECT_SCOPED_TABLE_NAMES) | {"projects"}


@pytest.mark.asyncio
async def test_a_second_untouched_project_survives_the_first_projects_deletion(app) -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-victim", name="Victim"))
        session.add(Project(id="proj-survivor", name="Survivor"))
        await session.flush()
        await _seed_full_project(session, "proj-victim", "vic")
        await _seed_full_project(session, "proj-survivor", "sur")
        await session.commit()

    async with async_session_factory() as session:
        survivor_before = await _counts_for_project(session, "proj-survivor")
    assert all(count and count > 0 for count in survivor_before.values()), survivor_before

    async with async_session_factory() as session:
        await ProjectLifecycleService(session).delete("proj-victim")

    async with async_session_factory() as session:
        assert await session.get(Project, "proj-survivor") is not None
        survivor_after = await _counts_for_project(session, "proj-survivor")
    assert survivor_after == survivor_before


@pytest.mark.asyncio
async def test_a_running_run_refuses_deletion_and_nothing_is_removed(app) -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-victim", name="Victim"))
        await session.flush()
        await _seed_full_project(session, "proj-victim", "running")
        # `_seed_full_project` already added a "completed" run; add a second, running one —
        # the guard only needs one active run to fire, and this proves it does not require
        # every run to be running.
        session.add(Run(id="run-active", project_id="proj-victim", agent="agent-running", status="running"))
        await session.commit()

    async with async_session_factory() as session:
        before = await _counts_for_project(session, "proj-victim")
        with pytest.raises(ProjectPathError) as excinfo:
            await ProjectLifecycleService(session).delete("proj-victim")
        assert excinfo.value.code == "project_has_active_run"

    async with async_session_factory() as session:
        assert await session.get(Project, "proj-victim") is not None
        after = await _counts_for_project(session, "proj-victim")
    assert after == before


@pytest.mark.asyncio
async def test_workspace_directory_survives_deletion(app, tmp_path, bind_project_workspace) -> None:
    """`design.md` D4. Mutation-checked by hand for this iteration (not baked into the test,
    since a self-injected mutation would prove the injection works, not that this assertion
    is sensitive to a real regression in `delete()`): temporarily added `shutil.rmtree` of
    the workspace directory inside `ProjectLifecycleService.delete()`, reran this test,
    watched it fail on the `directory.is_dir()` assertion, then reverted — see the log entry
    for this iteration.
    """

    directory = tmp_path / "workspace"
    directory.mkdir()
    marker_file = directory / "marker.txt"
    marker_file.write_text("do not touch", encoding="utf-8")
    source_file = directory / "src" / "main.py"
    source_file.parent.mkdir()
    source_file.write_text("print('hello')\n", encoding="utf-8")

    project = await bind_project_workspace(directory)

    async with async_session_factory() as session:
        await ProjectLifecycleService(session).delete(project.id)

    assert directory.is_dir()
    assert marker_file.read_text(encoding="utf-8") == "do not touch"
    assert source_file.read_text(encoding="utf-8") == "print('hello')\n"


@pytest.mark.asyncio
async def test_a_terminal_run_does_not_block_deletion(app) -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-victim", name="Victim"))
        session.add(
            Run(id="run-done", project_id="proj-victim", agent="agent-x", status="completed")
        )
        await session.commit()

    async with async_session_factory() as session:
        await ProjectLifecycleService(session).delete("proj-victim")

    async with async_session_factory() as session:
        assert await session.get(Project, "proj-victim") is None


@pytest.mark.asyncio
async def test_a_project_with_conversations_and_messages_deletes_normally(app) -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-victim", name="Victim"))
        session.add(Conversation(id="conv-open", project_id="proj-victim", agent="agent-x"))
        session.add(
            Message(
                id="msg-open",
                project_id="proj-victim",
                sender="agent-x",
                recipient="operator",
                conversation_id="conv-open",
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        await ProjectLifecycleService(session).delete("proj-victim")

    async with async_session_factory() as session:
        assert await session.get(Project, "proj-victim") is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.project_id == "proj-victim")
            )
        ) == 0
        assert (
            await session.scalar(
                select(func.count()).select_from(Message).where(Message.project_id == "proj-victim")
            )
        ) == 0


@pytest.mark.asyncio
async def test_agent_job_deletions_removed_despite_no_declared_foreign_key(app) -> None:
    """`agent_job_deletions` carries `project_id` with no `ForeignKey` (design.md D2's
    named exception) — the generic column-name sweep must not depend on a relationship
    existing to find it.
    """

    async with async_session_factory() as session:
        session.add(Project(id="proj-victim", name="Victim"))
        session.add(
            AgentJobDeletion(
                id="jobdel-solo",
                job_id="job-solo",
                project_id="proj-victim",
                agent="agent-x",
                run_id="run-solo",
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        await ProjectLifecycleService(session).delete("proj-victim")

    async with async_session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AgentJobDeletion)
            .where(AgentJobDeletion.project_id == "proj-victim")
        )
    assert count == 0


# tasks.md 3.9: `design.md` D1 states this change adds no migration, so
# `test_migrations.py` and `test_project_persistence.py` need no head-revision bump.
# That is a property of *those* files (both already assert the current head, 0073, set by
# Q3's conversation-sequence migration — unrelated to this change), not of this one, so it
# is verified by running them, not by a test living here — see the log entry for this
# iteration for the recorded run.
