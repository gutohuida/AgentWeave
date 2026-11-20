"""A conversation owns its document (`every-spec-entry-point-leads-into-the-journey`, ESEPL-2).

FR-11 (`conversation-owns-its-document`) and the Hub half of FR-12
(`no-document-crosses-conversations`): `conversations.spec_document_id` (migration 0188), set by
`PUT .../spec-document` and by every operator message sent under a document (Explore's first
message among them), cleared only by `PUT` with `path: null`, and read back by
`GET .../spec-documents` from wherever the conversation is reopened.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from hub.config import settings
from hub.db.engine import async_session_factory
from hub.db.models import Base, Conversation, InboundQueueEntry, SpecDocument

P = "proj-test"
BASE = f"/api/v1/projects/{P}"
AGENT = "speccer"
OTHER_AGENT = "elsewhere"


# --- migration 0188 ---------------------------------------------------------------------------

ALEMBIC_INI = Path(__file__).parent.parent / "hub" / "alembic.ini"


def _alembic(db_url: str, verb: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        getattr(command, verb)(cfg, revision)


def _database_at_head(db_file: Path) -> str:
    built = sa.create_engine(f"sqlite:///{db_file}")
    try:
        Base.metadata.create_all(built)
        with built.begin() as conn:
            conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(sa.text("INSERT INTO alembic_version VALUES ('0188')"))
    finally:
        built.dispose()
    return f"sqlite+aiosqlite:///{db_file}"


def _conversation_columns(db_file: Path) -> set[str]:
    with sqlite3.connect(db_file) as conn:
        return {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}


def _conversation_indexes(db_file: Path) -> set[str]:
    with sqlite3.connect(db_file) as conn:
        return {row[1] for row in conn.execute("PRAGMA index_list(conversations)")}


def _conversation_checks(db_file: Path) -> int:
    with sqlite3.connect(db_file) as conn:
        created = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'conversations'"
        ).fetchone()[0]
    return created.count("CHECK")


def _conversation_foreign_keys(db_file: Path) -> list[tuple]:
    with sqlite3.connect(db_file) as conn:
        # (id, seq, table, from, to, on_update, on_delete, match)
        return list(conn.execute("PRAGMA foreign_key_list(conversations)"))


def _insert_conversation(db_file: Path) -> tuple:
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at, working_directory, path_key, "
            "directory_state) VALUES ('proj-old', 'Old', '2026-01-01 00:00:00', '/x', 'k:x', "
            "'available')"
        )
        conn.execute(
            "INSERT INTO conversations (id, project_id, agent, lifecycle, title_set_by_operator, "
            "origin, own_worktree, created_at, updated_at) VALUES ('conv-old', 'proj-old', 'a', "
            "'open', 0, 'operator', 0, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        )
        conn.commit()
        return conn.execute(
            "SELECT id, project_id, agent, lifecycle, title, origin FROM conversations"
        ).fetchone()


def test_migration_0188_adds_the_column_and_downgrade_drops_it(tmp_path) -> None:
    """Down from a database `create_all` built (table-level FOREIGN KEY), then up again the way
    the operator's database takes it (an `ALTER TABLE ADD COLUMN ... REFERENCES`), then down."""
    db_file = tmp_path / "hub.db"
    db_url = _database_at_head(db_file)
    assert "spec_document_id" in _conversation_columns(db_file)
    checks = _conversation_checks(db_file)
    other_indexes = _conversation_indexes(db_file) - {"ix_conversations_spec_document_id"}
    other_fks = [fk[2:5] for fk in _conversation_foreign_keys(db_file) if fk[2] != "spec_documents"]

    _alembic(db_url, "downgrade", "0187")
    assert "spec_document_id" not in _conversation_columns(db_file)
    assert "ix_conversations_spec_document_id" not in _conversation_indexes(db_file)
    # That downgrade recreated the table (its FOREIGN KEY was table-level); nothing else is lost.
    assert _conversation_checks(db_file) == checks >= 2
    assert _conversation_indexes(db_file) == other_indexes
    assert [fk[2:5] for fk in _conversation_foreign_keys(db_file)] == other_fks
    assert not [fk for fk in _conversation_foreign_keys(db_file) if fk[2] == "spec_documents"]
    before = _insert_conversation(db_file)

    _alembic(db_url, "upgrade", "0188")
    assert "spec_document_id" in _conversation_columns(db_file)
    assert "ix_conversations_spec_document_id" in _conversation_indexes(db_file)
    fks = [fk for fk in _conversation_foreign_keys(db_file) if fk[2] == "spec_documents"]
    assert [(fk[3], fk[4], fk[6]) for fk in fks] == [("spec_document_id", "id", "SET NULL")]
    with sqlite3.connect(db_file) as conn:
        # No row is changed and nothing is backfilled: an existing conversation has no document.
        assert (
            conn.execute(
                "SELECT id, project_id, agent, lifecycle, title, origin FROM conversations"
            ).fetchone()
            == before
        )
        assert conn.execute("SELECT spec_document_id FROM conversations").fetchone() == (None,)

    _alembic(db_url, "downgrade", "0187")
    assert "spec_document_id" not in _conversation_columns(db_file)
    assert "ix_conversations_spec_document_id" not in _conversation_indexes(db_file)
    with sqlite3.connect(db_file) as conn:
        assert (
            conn.execute(
                "SELECT id, project_id, agent, lifecycle, title, origin FROM conversations"
            ).fetchone()
            == before
        )


def test_migration_0188_set_null_on_document_delete(tmp_path) -> None:
    """ON DELETE SET NULL holds where foreign keys are enforced."""
    db_file = tmp_path / "hub.db"
    db_url = _database_at_head(db_file)
    _alembic(db_url, "downgrade", "0187")
    _insert_conversation(db_file)
    _alembic(db_url, "upgrade", "0188")
    with sqlite3.connect(db_file) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO spec_documents (id, project_id, path, title, kind, phase, rigor, "
            "created_at, updated_at) VALUES ('spdoc-x', 'proj-old', 'spec/x.json', 'X', "
            "'change-spec', 'exploring', 'standard', '2026-01-01', '2026-01-01')"
        )
        conn.execute("UPDATE conversations SET spec_document_id = 'spdoc-x'")
        conn.execute("DELETE FROM spec_documents WHERE id = 'spdoc-x'")
        assert conn.execute("SELECT spec_document_id FROM conversations").fetchone() == (None,)


# --- routes and the trigger -------------------------------------------------------------------


async def _create_document(app, auth_headers, title: str) -> str:
    created = await app.post(
        f"{BASE}/project/documents", json={"title": title}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    return created.json()["path"]


async def _trigger(app, auth_headers, message: str, **fields) -> dict:
    response = await app.post(
        f"{BASE}/agent/trigger",
        json={"agent": fields.pop("agent", AGENT), "message": message, **fields},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _attached(app, auth_headers, conversation_id: str):
    read = await app.get(
        f"{BASE}/conversations/{conversation_id}/spec-documents", headers=auth_headers
    )
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["offers"] == []
    return body["attached"]


async def _put(app, auth_headers, conversation_id: str, path):
    return await app.put(
        f"{BASE}/conversations/{conversation_id}/spec-document",
        json={"path": path},
        headers=auth_headers,
    )


async def _entry_documents(conversation_id: str) -> list:
    async with async_session_factory() as db:
        rows = await db.execute(
            select(InboundQueueEntry.spec_document)
            .where(InboundQueueEntry.conversation_id == conversation_id)
            .order_by(InboundQueueEntry.sequence)
        )
        return list(rows.scalars())


async def _document_row(path: str) -> tuple:
    async with async_session_factory() as db:
        row = (
            (await db.execute(select(SpecDocument).where(SpecDocument.path == path)))
            .scalars()
            .one()
        )
        return (row.id, row.path, row.title, row.phase, row.step, row.content_digest)


@pytest.fixture
async def speccer(add_agent, bind_runner):
    await add_agent(AGENT)
    await bind_runner(AGENT, cli="claude")


@pytest.mark.asyncio
async def test_reopened_conversation_restores_the_document_opened_without_a_message(
    app, auth_headers, speccer
):
    """reopened-conversation-restores-its-document: opened with PUT, no message sent; every
    later read (a reopen from the sidebar, a reload) answers X."""
    started = await _trigger(app, auth_headers, "hello")
    conversation_id = started["conversation_id"]
    assert await _attached(app, auth_headers, conversation_id) is None
    x = await _create_document(app, auth_headers, "X")

    put = await _put(app, auth_headers, conversation_id, x)
    assert put.status_code == 200, put.text
    assert put.json()["attached"]["path"] == x

    for _reopen in range(2):
        attached = await _attached(app, auth_headers, conversation_id)
        assert attached == {"path": x, "title": "X", "phase": "exploring", "step": "intake"}
    async with async_session_factory() as db:
        stored = await db.get(Conversation, conversation_id)
        if stored is None:
            stored = (
                (await db.execute(select(Conversation).where(Conversation.id == conversation_id)))
                .scalars()
                .one()
            )
        assert stored.spec_document_id == (await _document_row(x))[0]


@pytest.mark.asyncio
async def test_stop_exploring_clears_the_document_and_leaves_it_unchanged(
    app, auth_headers, speccer
):
    """stop-exploring-clears-the-document: PUT with path null; the reopened conversation has no
    document, and X itself is as it was."""
    x = await _create_document(app, auth_headers, "X")
    conversation_id = (await _trigger(app, auth_headers, "start", spec_document=x))[
        "conversation_id"
    ]
    assert (await _attached(app, auth_headers, conversation_id))["path"] == x
    before = await _document_row(x)

    cleared = await _put(app, auth_headers, conversation_id, None)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json() == {"attached": None}

    assert await _attached(app, auth_headers, conversation_id) is None
    assert await _document_row(x) == before


@pytest.mark.asyncio
async def test_explore_creation_sets_the_conversation_document(app, auth_headers, speccer):
    """Explore creates its document, then sends the first message under it: the conversation
    that message starts owns the document."""
    x = await _create_document(app, auth_headers, "Explore this")
    started = await _trigger(app, auth_headers, "explore this", spec_document=x)

    attached = await _attached(app, auth_headers, started["conversation_id"])
    assert attached is not None and attached["path"] == x
    assert attached["step"] == "intake"


@pytest.mark.asyncio
async def test_a_message_with_no_document_keeps_the_conversation_document(
    app, auth_headers, speccer
):
    """Only stopping exploring clears it; a later message sent with none does not."""
    x = await _create_document(app, auth_headers, "X")
    conversation_id = (await _trigger(app, auth_headers, "one", spec_document=x))["conversation_id"]
    await _trigger(app, auth_headers, "two", conversation_id=conversation_id)
    assert (await _attached(app, auth_headers, conversation_id))["path"] == x


@pytest.mark.asyncio
async def test_a_message_under_another_document_moves_the_conversation_to_it(
    app, auth_headers, speccer
):
    """The document 'last sent under' is the conversation's."""
    x = await _create_document(app, auth_headers, "X")
    y = await _create_document(app, auth_headers, "Y")
    conversation_id = (await _trigger(app, auth_headers, "one", spec_document=x))["conversation_id"]
    await _trigger(app, auth_headers, "two", conversation_id=conversation_id, spec_document=y)
    assert (await _attached(app, auth_headers, conversation_id))["path"] == y


@pytest.mark.asyncio
async def test_two_conversations_keep_their_own_documents(
    app, auth_headers, speccer, add_agent, bind_runner
):
    """drive-two-conversations-keep-their-own-documents, Hub half of
    switching-conversation-drops-the-document and new-conversation-starts-without-a-document:
    A has X; B (same agent) and C (another agent) start with none, a message in either is queued
    with no document, and A's document is still X."""
    await add_agent(OTHER_AGENT)
    await bind_runner(OTHER_AGENT, cli="claude")
    x = await _create_document(app, auth_headers, "X")
    a = (await _trigger(app, auth_headers, "in A", spec_document=x))["conversation_id"]
    b = (await _trigger(app, auth_headers, "in B"))["conversation_id"]
    c = (await _trigger(app, auth_headers, "in C", agent=OTHER_AGENT))["conversation_id"]
    assert len({a, b, c}) == 3

    assert await _attached(app, auth_headers, b) is None
    await _trigger(app, auth_headers, "again in B", conversation_id=b)
    assert await _entry_documents(b) == [None, None]
    assert await _attached(app, auth_headers, b) is None
    assert await _attached(app, auth_headers, c) is None
    assert await _entry_documents(c) == [None]
    assert (await _attached(app, auth_headers, a))["path"] == x
    assert await _entry_documents(a) == [x]


@pytest.mark.asyncio
async def test_unknown_conversation_and_unknown_document_are_404(app, auth_headers, speccer):
    conversation_id = (await _trigger(app, auth_headers, "hello"))["conversation_id"]

    missing = await app.get(f"{BASE}/conversations/conv-nope/spec-documents", headers=auth_headers)
    assert missing.status_code == 404, missing.text
    assert missing.json()["detail"]["code"] == "unknown_conversation"
    missing_put = await _put(app, auth_headers, "conv-nope", None)
    assert missing_put.status_code == 404
    assert missing_put.json()["detail"]["code"] == "unknown_conversation"

    unknown = await _put(app, auth_headers, conversation_id, "spec/changes/nothing/spec.json")
    assert unknown.status_code == 404, unknown.text
    assert unknown.json()["detail"]["code"] == "unknown_document"
    assert await _attached(app, auth_headers, conversation_id) is None


@pytest.mark.asyncio
async def test_a_conversation_of_another_project_is_404(app, auth_headers, speccer):
    conversation_id = (await _trigger(app, auth_headers, "hello"))["conversation_id"]
    async with async_session_factory() as db:
        row = (
            (await db.execute(select(Conversation).where(Conversation.id == conversation_id)))
            .scalars()
            .one()
        )
        row.project_id = "proj-other"
        await db.commit()
    read = await app.get(
        f"{BASE}/conversations/{conversation_id}/spec-documents", headers=auth_headers
    )
    assert read.status_code == 404
    assert read.json()["detail"]["code"] == "unknown_conversation"


@pytest.mark.asyncio
async def test_a_deleted_document_reads_as_no_document(app, auth_headers, speccer):
    x = await _create_document(app, auth_headers, "X")
    conversation_id = (await _trigger(app, auth_headers, "one", spec_document=x))["conversation_id"]
    deleted = await app.delete(f"{BASE}/project/documents/{x}", headers=auth_headers)
    assert deleted.status_code in (200, 204), deleted.text
    assert await _attached(app, auth_headers, conversation_id) is None
