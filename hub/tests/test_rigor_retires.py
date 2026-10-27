"""Document rigor retires (`amendments-main-watch-and-the-next-slice`, task `rigor-retires`).

Red on master: an agent's save of an exploring document whose row says `gate` became an edit
proposal instead of a write; the rigor and proposals routes answered; a task outside any build of a
gate document was refused approval without accepted evidence. Now every save before approval
applies, the routes are gone, a task with no level is judged by `sketch`'s rule, and migration 0153
keeps an open contract/gate task's rule as its level and marks pending proposals stale.

Named by acceptance criterion: `-k save` (gate-document-save-applies); the rest is
rigor-gone-and-backfilled.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, SpecEditProposal
from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

from .test_spec_roadmaps import (  # noqa: F401 -- fixtures
    BASE,
    _agent_create,
    _agent_submit,
    _approve,
    _move,
    _propose,
    _slice_doc,
    planner,
)


async def _set_rigor(path: str, rigor: str) -> None:
    async with async_session_factory() as session:
        row = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()
        row.rigor = rigor
        await session.commit()


@pytest.mark.asyncio
async def test_save_of_a_gate_document_applies(app, auth_headers, planner):  # noqa: F811
    path = await _agent_create(app, planner)
    first = await _agent_submit(app, planner, path, _slice_doc(roadmap=None))
    assert first.status_code == 200, first.text
    await _set_rigor(path, "gate")
    before = (await app.get(f"{BASE}/spec", params={"path": path}, headers=auth_headers)).json()

    saved = await _agent_submit(
        app, planner, path, _slice_doc(roadmap=None, title="Slice one, retitled")
    )

    assert saved.status_code == 200, saved.text
    assert "proposals" not in saved.json() and "identifiers" in saved.json()
    after = (await app.get(f"{BASE}/spec", params={"path": path}, headers=auth_headers)).json()
    assert after["content_version"] != before["content_version"]
    async with async_session_factory() as session:
        assert (await session.execute(select(SpecEditProposal))).scalars().first() is None


@pytest.mark.asyncio
async def test_the_rigor_and_proposals_routes_are_gone(app, auth_headers, planner):  # noqa: F811
    path = await _agent_create(app, planner)
    assert (await _agent_submit(app, planner, path, _slice_doc(roadmap=None))).status_code == 200

    rigor = await app.post(
        f"{BASE}/documents/{path}/rigor", json={"rigor": "gate"}, headers=auth_headers
    )
    history = await app.get(f"{BASE}/documents/{path}/rigor-history", headers=auth_headers)
    proposals = await app.get(f"{BASE}/documents/{path}/proposals", headers=auth_headers)
    accept = await app.post(f"{BASE}/documents/{path}/proposals/p-1/accept", headers=auth_headers)

    # A POST to a path a GET route still matches (`/documents/{path:path}`) answers 405, not 404:
    # either way no route takes it.
    assert [r.status_code for r in (history, proposals)] == [404, 404]
    assert rigor.status_code in (404, 405) and accept.status_code in (404, 405)
    documents = (await app.get(f"{BASE}/documents", headers=auth_headers)).json()
    assert all("rigor" not in row for row in documents["documents"])


@pytest.mark.asyncio
async def test_a_task_with_no_level_is_judged_as_sketch(app, auth_headers, planner):  # noqa: F811
    """A task outside any build of a document whose row still says `gate` is approved without
    accepted evidence, as a sketch document's is (on master it was refused)."""
    path = await _agent_create(app, planner)
    assert (await _agent_submit(app, planner, path, _slice_doc(roadmap=None))).status_code == 200
    assert (await _propose(app, auth_headers, path))["blocking"] == []
    await _set_rigor(path, "gate")
    approved = await _approve(app, auth_headers, path)
    assert approved.status_code == 200, approved.text
    (task_id,) = approved.json()["tasks_created"]

    await _move(app, auth_headers, task_id, "in_progress", "completed", "under_review", "approved")


# --- migration 0153 ------------------------------------------------------------------------------


_DOC = (
    "INSERT INTO spec_documents (id, project_id, path, title, kind, phase, rigor, created_at, "
    "updated_at) VALUES (?, 'proj-old', ?, 'T', 'change-spec', 'approved', ?, "
    "'2026-10-01T00:00:00', '2026-10-01T00:00:00')"
)
_TASK = (
    "INSERT INTO tasks (id, project_id, title, description, status, priority, created_at, updated, "
    "divergence_policy, workspace_scheme, spec_document_id, build_id, level) VALUES (?, 'proj-old', "
    "'T', '', ?, 'medium', '2026-10-01T00:00:00', '2026-10-01T00:00:00', 'surface', 'task', ?, ?, ?)"
)


def _levels(conn):
    return dict(conn.execute("SELECT id, level FROM tasks").fetchall())


def test_0153_backfills_levels_and_stales_proposals_and_round_trips(tmp_path) -> None:
    db_file = tmp_path / "rigor.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0153')")
        conn.commit()
    _downgrade_to(db_url, "0152")
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES ('proj-old', 'Old', "
            "'2026-10-01T00:00:00')"
        )
        conn.execute(_DOC, ("doc-gate", "spec/changes/g/spec.json", "gate"))
        conn.execute(_DOC, ("doc-contract", "spec/changes/c/spec.json", "contract"))
        conn.execute(_DOC, ("doc-sketch", "spec/changes/s/spec.json", "sketch"))
        conn.execute(_TASK, ("t-gate", "in_progress", "doc-gate", None, None))
        conn.execute(_TASK, ("t-contract", "pending", "doc-contract", None, None))
        conn.execute(_TASK, ("t-gate-done", "approved", "doc-gate", None, None))
        conn.execute(_TASK, ("t-built", "pending", "doc-gate", "build-1", "fast"))
        conn.execute(_TASK, ("t-sketch", "completed", "doc-sketch", None, None))
        conn.execute(
            "INSERT INTO spec_edit_proposals (id, document_id, unit_kind, unit_key, change_kind, "
            "proposed_payload, status, created_at, resolution_reason) VALUES ('sep-1', 'doc-gate', "
            "'metadata', 'metadata', 'modify', '{}', 'pending', '2026-10-01T00:00:00', '')"
        )
        conn.execute(
            "INSERT INTO spec_edit_proposals (id, document_id, unit_kind, unit_key, change_kind, "
            "proposed_payload, status, created_at, resolution_reason) VALUES ('sep-2', 'doc-gate', "
            "'metadata', 'metadata', 'modify', '{}', 'rejected', '2026-10-01T00:00:00', 'no')"
        )
        conn.commit()

    _upgrade_to(db_url, "0153")

    with sqlite3.connect(db_file) as conn:
        assert _levels(conn) == {
            "t-gate": "gated",
            "t-contract": "reviewed",
            "t-gate-done": None,
            "t-built": "fast",
            "t-sketch": None,
        }
        rows = {
            row[0]: row[1:]
            for row in conn.execute("SELECT id, status, resolution_reason FROM spec_edit_proposals")
        }
        assert rows["sep-1"][0] == "stale" and "rigor retired" in rows["sep-1"][1]
        assert rows["sep-2"] == ("rejected", "no")

    _downgrade_to(db_url, "0152")

    with sqlite3.connect(db_file) as conn:
        assert _levels(conn) == {
            "t-gate": None,
            "t-contract": None,
            "t-gate-done": None,
            "t-built": "fast",
            "t-sketch": None,
        }
        statuses = dict(conn.execute("SELECT id, status FROM spec_edit_proposals").fetchall())
        assert statuses == {"sep-1": "pending", "sep-2": "rejected"}
