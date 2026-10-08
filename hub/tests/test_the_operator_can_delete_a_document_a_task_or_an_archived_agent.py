"""The operator can delete a document or a task, and a runner only archived agents hold (F532).

`spec/changes/the-operator-can-delete-a-document-a-task-or-an-archived-agent` (the path predates the
operator keeping "an agent is archived, never deleted"; the title says what it does). A document
delete takes its requirements, evidence, events, tasks and stopped flows; a task delete takes its
links, transitions, evidence and queued input and clears it from history rows; both refuse what
the corpus or a live run depends on. A runner held only by archived agents deletes, unbinding them.
"""

import re

import pytest
from sqlalchemy import select

from hub import deletion
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    Base,
    Conversation,
    EvidenceFootprint,
    InboundQueueEntry,
    Loop,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecRequirement,
    Task,
)
from tests.test_a_finished_change_is_folded_into_its_capability import (
    BASE,
    CAP,
    CHANGE,
    _approved_change,
    _create_capability,
    _finish_tasks,
)

TASKS = "/api/v1/projects/proj-test/tasks"
RUNNERS = "/api/v1/projects/proj-test/runners"
AGENTS = "/api/v1/projects/proj-test/agents"

# Columns that point at a task, requirement, evidence row, document, loop or job. Every one must be
# named by the deletion module, or a new table would silently keep references to deleted rows
# (`PRAGMA foreign_keys` is never on for this app's SQLite).
_REFERENCE = re.compile(r"(^|_)(task_id|requirement_id|evidence_id|document_id|loop_id|job_id)$")


def test_every_reference_column_is_covered_by_a_cascade():
    covered = {(table, column) for table, column, _ in deletion.all_references()}
    missing = sorted(
        (table.name, column.name)
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if _REFERENCE.search(column.name) and (table.name, column.name) not in covered
    )
    assert missing == []


async def _rows(path=CHANGE):
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one_or_none()
        if document is None:
            return None
        tasks = (
            (await session.execute(select(Task).where(Task.spec_document_id == document.id)))
            .scalars()
            .all()
        )
        requirements = (
            (
                await session.execute(
                    select(SpecRequirement).where(SpecRequirement.document_id == document.id)
                )
            )
            .scalars()
            .all()
        )
        return document, tasks, requirements


async def _entry(session, entry_id):
    """`InboundQueueEntry`'s primary key is `sequence`; `session.get` by id would always miss."""
    return (
        await session.execute(select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id))
    ).scalar_one_or_none()


async def _seed_history(task_id: str, requirement_id: str, *, run_status="completed"):
    """Evidence with a footprint, a run, a bound conversation, a queued and a delivered entry."""
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-del",
                project_id="proj-test",
                agent="alice",
                task_id=task_id,
                status=run_status,
                turn_depth=0,
            )
        )
        session.add(
            Conversation(id="conv-del", project_id="proj-test", agent="alice", task_id=task_id)
        )
        session.add(
            RequirementEvidence(
                id="ev-del",
                project_id="proj-test",
                requirement_id=requirement_id,
                task_id=task_id,
                digest="d",
                kind="test_result",
                actor_kind="operator",
                run_id="run-del",
            )
        )
        session.add(
            EvidenceFootprint(
                id="fp-del", project_id="proj-test", evidence_id="ev-del", kind="commit"
            )
        )
        for entry_id, state in (("q-queued", "queued"), ("q-done", "delivered")):
            session.add(
                InboundQueueEntry(
                    id=entry_id,
                    project_id="proj-test",
                    agent="alice",
                    origin_type="operator",
                    content="c",
                    hop_depth=0,
                    task_id=task_id,
                    state=state,
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_deleting_a_document_takes_what_it_produced_and_its_file(app, auth_headers, tmp_path):
    await _approved_change(app, auth_headers)
    document, tasks, requirements = await _rows()
    await _seed_history(tasks[0].id, requirements[0].id)
    async with async_session_factory() as session:
        session.add(
            AIJob(
                id="job-del",
                project_id="proj-test",
                name="flow",
                agent="alice",
                message="m",
                cron="0 0 1 1 *",
                enabled=False,
            )
        )
        session.add(
            Loop(
                id="loop-del",
                project_id="proj-test",
                job_id="job-del",
                spec_document_id=document.id,
            )
        )
        await session.commit()

    response = await app.delete(f"{BASE}/documents/{CHANGE}", headers=auth_headers)

    assert response.status_code == 200, response.text
    assert await _rows() is None
    assert not (tmp_path / CHANGE).exists()
    gone_ids = {
        document.id,
        *(t.id for t in tasks),
        *(r.id for r in requirements),
        "ev-del",
        "loop-del",
        "job-del",
    }
    async with async_session_factory() as session:
        for table, column, _ in deletion.all_references():
            values = (
                (
                    await session.execute(
                        select(Base.metadata.tables[table].c[column]).where(
                            Base.metadata.tables[table].c[column].in_(gone_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert values == [], f"{table}.{column} still names a deleted row"
        run = await session.get(Run, "run-del")
        # `Conversation`'s primary key is `sequence`; its `id` is a plain column.
        conversation = (
            await session.execute(select(Conversation).where(Conversation.id == "conv-del"))
        ).scalar_one_or_none()
        delivered = await _entry(session, "q-done")
    assert run is not None and run.task_id is None
    assert conversation is not None and conversation.task_id is None
    assert delivered is not None and delivered.task_id is None


@pytest.mark.asyncio
async def test_deleting_a_document_drops_it_from_the_index(app, auth_headers, tmp_path):
    await _approved_change(app, auth_headers)
    other = "spec/changes/other/spec.html"
    await _approved_change(app, auth_headers, path=other)
    reindexed = await app.post(f"{BASE}/spec/reindex", json={"home": other}, headers=auth_headers)
    assert reindexed.status_code == 200, reindexed.text
    assert CHANGE in (tmp_path / "spec/index.json").read_text(encoding="utf-8")

    response = await app.delete(f"{BASE}/documents/{CHANGE}", headers=auth_headers)

    assert response.status_code == 200, response.text
    index = (tmp_path / "spec/index.json").read_text(encoding="utf-8")
    assert CHANGE not in index and other in index


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["capability", "archived", "folded", "flow", "run"])
async def test_a_refused_document_delete_changes_nothing(app, auth_headers, tmp_path, case):
    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers)
    document, tasks, _ = await _rows()
    path, code = (
        CHANGE,
        {
            "capability": "delete_capability",
            "archived": "delete_archived",
            "folded": "delete_folded",
            "flow": "delete_flow_running",
            "run": "delete_run_active",
        }[case],
    )
    if case == "capability":
        path = CAP
    if case in ("archived", "folded"):
        await _finish_tasks()
        folded = await app.post(
            f"{BASE}/documents/{CHANGE}/fold",
            json={"into": CAP, "archive": case == "archived"},
            headers=auth_headers,
        )
        assert folded.status_code == 200, folded.text
    async with async_session_factory() as session:
        if case == "flow":
            session.add(
                AIJob(
                    id="job-live",
                    project_id="proj-test",
                    name="flow",
                    agent="alice",
                    message="m",
                    cron="*/5 * * * *",
                    enabled=True,
                )
            )
            session.add(
                Loop(
                    id="loop-live",
                    project_id="proj-test",
                    job_id="job-live",
                    spec_document_id=document.id,
                )
            )
        if case == "run":
            session.add(
                Run(
                    id="run-live",
                    project_id="proj-test",
                    agent="alice",
                    task_id=tasks[0].id,
                    status="running",
                    turn_depth=0,
                )
            )
        await session.commit()

    response = await app.delete(f"{BASE}/documents/{path}", headers=auth_headers)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == code
    assert (tmp_path / path).exists()
    assert (await _rows(path)) is not None


@pytest.mark.asyncio
async def test_deleting_a_task_takes_its_links_and_clears_history(app, auth_headers, tmp_path):
    await _approved_change(app, auth_headers)
    _, tasks, requirements = await _rows()
    other = await app.post(TASKS, json={"title": "Depends on it"}, headers=auth_headers)
    other_id = other.json()["id"]
    linked = await app.post(
        f"{TASKS}/{other_id}/dependencies", json={"depends_on": tasks[0].id}, headers=auth_headers
    )
    assert linked.status_code == 201, linked.text
    moved = await app.patch(
        f"{TASKS}/{tasks[0].id}", json={"status": "in_progress"}, headers=auth_headers
    )
    assert moved.status_code == 200, moved.text
    await _seed_history(tasks[0].id, requirements[0].id)

    response = await app.delete(f"{TASKS}/{tasks[0].id}", headers=auth_headers)

    assert response.status_code == 204, response.text
    assert (await app.get(f"{TASKS}/{tasks[0].id}", headers=auth_headers)).status_code == 404
    assert (await app.get(f"{TASKS}/{other_id}", headers=auth_headers)).status_code == 200
    async with async_session_factory() as session:
        for table, column, _ in deletion.TASK_REFERENCES:
            col = Base.metadata.tables[table].c[column]
            left = (await session.execute(select(col).where(col == tasks[0].id))).scalars().all()
            assert left == [], f"{table}.{column} still names the deleted task"
        assert (await session.get(RequirementEvidence, "ev-del")) is None
        assert (await session.get(EvidenceFootprint, "fp-del")) is None
        assert (await _entry(session, "q-queued")) is None
        delivered = await _entry(session, "q-done")
        assert delivered is not None and delivered.task_id is None
        assert (await session.get(Run, "run-del")).task_id is None


@pytest.mark.asyncio
async def test_a_task_with_an_active_run_is_not_deleted(app, auth_headers, tmp_path):
    await _approved_change(app, auth_headers)
    _, tasks, requirements = await _rows()
    await _seed_history(tasks[0].id, requirements[0].id, run_status="running")

    response = await app.delete(f"{TASKS}/{tasks[0].id}", headers=auth_headers)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "delete_run_active"
    assert (await app.get(f"{TASKS}/{tasks[0].id}", headers=auth_headers)).status_code == 200


@pytest.mark.asyncio
async def test_a_missing_task_or_document_is_a_404(app, auth_headers, tmp_path):
    assert (await app.delete(f"{TASKS}/task-nope", headers=auth_headers)).status_code == 404
    missing = await app.delete(
        f"{BASE}/documents/spec/changes/nope/spec.html", headers=auth_headers
    )
    assert missing.status_code == 404


async def _runner_with(app, auth_headers, add_agent, name, *, archive):
    """A runner and an agent bound to it, the way `test_runners_api` builds one: `add_agent` plus a
    PATCH, because creating an agent on a `claude` runner checks the CLI is on PATH and CI has none.
    """
    runner = await app.post(
        RUNNERS, json={"name": f"r-{name}", "cli": "claude"}, headers=auth_headers
    )
    assert runner.status_code in (200, 201), runner.text
    runner_id = runner.json()["id"]
    await add_agent(name)
    bound = await app.patch(f"{AGENTS}/{name}", json={"runner_id": runner_id}, headers=auth_headers)
    assert bound.status_code == 200, bound.text
    if archive:
        archived = await app.post(f"{AGENTS}/{name}/archive", json={}, headers=auth_headers)
        assert archived.status_code == 200, archived.text
    return runner_id


@pytest.mark.asyncio
async def test_a_runner_only_archived_agents_hold_deletes_and_keeps_them(
    app, auth_headers, add_agent, tmp_path
):
    runner_id = await _runner_with(app, auth_headers, add_agent, "retiree", archive=True)
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-kept",
                project_id="proj-test",
                agent="retiree",
                status="completed",
                turn_depth=0,
            )
        )
        await session.commit()

    response = await app.delete(f"{RUNNERS}/{runner_id}", headers=auth_headers)

    assert response.status_code == 204, response.text
    async with async_session_factory() as session:
        agent = (await session.execute(select(Agent).where(Agent.name == "retiree"))).scalar_one()
        assert agent.lifecycle == "archived" and agent.runner_id is None
        assert (await session.get(Run, "run-kept")) is not None


@pytest.mark.asyncio
async def test_a_runner_an_open_agent_holds_is_still_refused(
    app, auth_headers, add_agent, tmp_path
):
    runner_id = await _runner_with(app, auth_headers, add_agent, "worker", archive=False)

    response = await app.delete(f"{RUNNERS}/{runner_id}", headers=auth_headers)

    assert response.status_code == 409, response.text
    assert "worker" in response.text
