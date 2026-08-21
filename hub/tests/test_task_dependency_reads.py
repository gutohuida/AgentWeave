"""`task-dependencies` section 7 — reading dependencies.

The gate (section 5, `dependency_gate.py`/`test_dependency_gate.py`) answers "may this task start".
This file covers the read model built on the same `TaskDependency` rows: a task's prerequisites and
dependents on `TaskResponse` (7.1), the derived `dependency_state` (7.2), the one-call board
endpoint for a document's tasks and edges (7.3), and the board picker with outstanding counts (7.4).
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskDependency
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator

pytestmark = pytest.mark.asyncio


async def _make_task(
    session, task_id: str, status: str = "pending", *, spec_document_id=None, project="proj-test"
) -> Task:
    task = Task(
        id=task_id,
        project_id=project,
        title=f"Task {task_id}",
        status=status,
        spec_document_id=spec_document_id,
    )
    session.add(task)
    await session.flush()
    return task


async def _depend(session, task_id: str, on_task_id: str) -> None:
    session.add(
        TaskDependency(
            id=f"tdep-{task_id}-{on_task_id}",
            project_id="proj-test",
            task_id=task_id,
            depends_on_task_id=on_task_id,
        )
    )


# ---------------------------------------------------------------------------
# 7.1 — prerequisites and dependents on the read model
# ---------------------------------------------------------------------------


async def test_get_task_exposes_prerequisites_and_dependents(app, auth_headers):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-r71-prereq", "approved")
        task = await _make_task(session, "task-r71-mid", "pending")
        dependent = await _make_task(session, "task-r71-dependent", "pending")
        await _depend(session, task.id, prereq.id)
        await _depend(session, dependent.id, task.id)
        await session.commit()

    resp = await app.get("/api/v1/projects/proj-test/tasks/task-r71-mid", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [p["id"] for p in body["prerequisites"]] == ["task-r71-prereq"]
    assert body["prerequisites"][0]["status"] == "approved"
    assert [d["id"] for d in body["dependents"]] == ["task-r71-dependent"]


async def test_list_tasks_exposes_prerequisites_and_dependents(app, auth_headers):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-r71l-prereq", "pending")
        task = await _make_task(session, "task-r71l-mid", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks",
        params={"status": "pending"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    by_id = {row["id"]: row for row in resp.json()}
    assert [p["id"] for p in by_id["task-r71l-mid"]["prerequisites"]] == ["task-r71l-prereq"]
    assert [d["id"] for d in by_id["task-r71l-prereq"]["dependents"]] == ["task-r71l-mid"]


async def test_a_task_with_no_dependencies_has_empty_lists(app, auth_headers):
    async with async_session_factory() as session:
        await _make_task(session, "task-r71-solo", "pending")
        await session.commit()

    resp = await app.get("/api/v1/projects/proj-test/tasks/task-r71-solo", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prerequisites"] == []
    assert body["dependents"] == []
    assert body["dependency_state"] is None


# ---------------------------------------------------------------------------
# 7.2 — derived dependency_state
# ---------------------------------------------------------------------------


async def test_dependency_state_is_gated_while_prerequisite_unmet(app, auth_headers):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-r72-prereq", "in_progress")
        task = await _make_task(session, "task-r72-gated", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

    resp = await app.get("/api/v1/projects/proj-test/tasks/task-r72-gated", headers=auth_headers)
    assert resp.json()["dependency_state"] == "gated"


async def test_dependency_state_is_gated_on_rejected(app, auth_headers):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-r72-rejected-prereq", "rejected")
        task = await _make_task(session, "task-r72-rejected", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

    resp = await app.get("/api/v1/projects/proj-test/tasks/task-r72-rejected", headers=auth_headers)
    assert resp.json()["dependency_state"] == "gated_on_rejected"


async def test_dependency_state_is_none_once_prerequisite_approved(app, auth_headers):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-r72-cleared-prereq", "approved")
        task = await _make_task(session, "task-r72-cleared", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

    resp = await app.get("/api/v1/projects/proj-test/tasks/task-r72-cleared", headers=auth_headers)
    assert resp.json()["dependency_state"] is None


async def test_dependency_state_is_running_on_regressed(app, auth_headers):
    """Design D8: a running task whose prerequisite regressed is flagged, not stopped.

    `apply_transition` is used directly (rather than the HTTP PATCH route) to build the sequence: a
    prerequisite reaches `approved`, letting the dependent start via the gate, and then the
    prerequisite is walked back to `revision_needed` — an operator-only move the gate itself never
    revisits once a task has already started.
    """
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-r72-regressed-prereq", "approved")
        task = await _make_task(session, "task-r72-regressed", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()
        await apply_transition(session, task, "in_progress", operator())
        await apply_transition(session, prereq, "revision_needed", operator())
        await session.commit()

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks/task-r72-regressed", headers=auth_headers
    )
    body = resp.json()
    assert body["status"] == "in_progress"
    assert body["dependency_state"] == "running_on_regressed"


# ---------------------------------------------------------------------------
# 7.3 — the board endpoint: one document's tasks and edges, one call
# ---------------------------------------------------------------------------


async def test_board_returns_a_documents_tasks_and_edges(app, auth_headers):
    async with async_session_factory() as session:
        prereq = await _make_task(
            session, "task-r73-prereq", "approved", spec_document_id="doc-r73"
        )
        task = await _make_task(session, "task-r73-mid", "pending", spec_document_id="doc-r73")
        other = await _make_task(
            session, "task-r73-other-doc", "pending", spec_document_id="doc-other"
        )
        await _depend(session, task.id, prereq.id)
        await session.commit()

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks/board",
        params={"spec_document_id": "doc-r73"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = {row["id"] for row in body["tasks"]}
    assert ids == {"task-r73-prereq", "task-r73-mid"}
    assert other.id not in ids
    assert body["edges"] == [{"task_id": "task-r73-mid", "depends_on_task_id": "task-r73-prereq"}]


async def test_board_prerequisite_ref_carries_its_own_document(app, auth_headers):
    """An off-board prerequisite (task 8.7's territory) still names the document it lives in, so
    the board can draw it as a reference rather than a bare, unclickable title."""
    async with async_session_factory() as session:
        other_doc_prereq = await _make_task(
            session, "task-r73x-other-doc-prereq", "approved", spec_document_id="doc-other-x"
        )
        task = await _make_task(session, "task-r73x-mid", "pending", spec_document_id="doc-r73x")
        await _depend(session, task.id, other_doc_prereq.id)
        await session.commit()

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks/board",
        params={"spec_document_id": "doc-r73x"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    (mid,) = [row for row in body["tasks"] if row["id"] == "task-r73x-mid"]
    (prereq_ref,) = mid["prerequisites"]
    assert prereq_ref["id"] == "task-r73x-other-doc-prereq"
    assert prereq_ref["spec_document_id"] == "doc-other-x"


async def test_board_with_no_document_id_returns_hand_made_tasks_only(app, auth_headers):
    async with async_session_factory() as session:
        await _make_task(session, "task-r73-handmade", "pending", spec_document_id=None)
        await _make_task(session, "task-r73-declared", "pending", spec_document_id="doc-r73b")
        await session.commit()

    resp = await app.get("/api/v1/projects/proj-test/tasks/board", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()["tasks"]}
    assert "task-r73-handmade" in ids
    assert "task-r73-declared" not in ids


# ---------------------------------------------------------------------------
# 7.4 — the board picker, with outstanding counts
# ---------------------------------------------------------------------------


async def test_boards_reports_outstanding_counts_per_document(app, auth_headers):
    async with async_session_factory() as session:
        await _make_task(session, "task-r74-a", "pending", spec_document_id="doc-r74")
        await _make_task(session, "task-r74-b", "approved", spec_document_id="doc-r74")
        await _make_task(session, "task-r74-c", "rejected", spec_document_id="doc-r74")
        await _make_task(session, "task-r74-handmade", "pending", spec_document_id=None)
        await session.commit()

    resp = await app.get("/api/v1/projects/proj-test/tasks/boards", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    boards = {row["spec_document_id"]: row for row in resp.json()["boards"]}
    assert boards["doc-r74"]["total"] == 3
    # approved and rejected are both resolved, not outstanding — only task-r74-a remains.
    assert boards["doc-r74"]["outstanding"] == 1
    assert boards[None]["total"] == 1
    assert boards[None]["outstanding"] == 1
