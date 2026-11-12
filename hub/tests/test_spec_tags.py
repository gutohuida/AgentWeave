"""`find-a-spec-s-tasks-without-knowing-its-name`, task `picker`: a spec's short tag and the board
picker's recency order (FR-1, FR-2, FR-4)."""

from datetime import datetime, timedelta, timezone

import pytest

from hub import spec_tags
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, SpecDocument, Task
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test"
AGENT = "/api/v1/agent-actions/spec/documents"
BOARDS = f"{BASE}/tasks/boards"

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def run_headers():
    token = "aw_run_tags-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-tags",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _make(app, auth_headers, run_headers, path, title, tag=None):
    created = await app.post(
        f"{BASE}/project/documents",
        json={"path": path, "title": title, "kind": "change-spec"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    document = {"schema_version": SCHEMA_VERSION, "kind": "change-spec", "title": title}
    if tag is not None:
        document["tag"] = tag
    return await app.post(AGENT, json={"path": path, "document": document}, headers=run_headers)


async def _doc_row(path):
    async with async_session_factory() as session:
        from sqlalchemy import select

        return (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()


async def test_a_written_tag_is_stored_and_served_by_the_boards_route(
    app, auth_headers, run_headers
):
    saved = await _make(
        app,
        auth_headers,
        run_headers,
        "spec/changes/a/spec.json",
        "Rework the board",
        "tasks board",
    )
    assert saved.status_code == 200, saved.text
    row = await _doc_row("spec/changes/a/spec.json")
    async with async_session_factory() as session:
        session.add(
            Task(id="task-tag-a", project_id="proj-test", title="t", spec_document_id=row.id)
        )
        await session.commit()

    boards = (await app.get(BOARDS, headers=auth_headers)).json()["boards"]
    assert [b["tag"] for b in boards if b["spec_document_id"] == row.id] == ["tasks board"]


async def test_a_written_tag_another_spec_holds_is_refused_naming_it(
    app, auth_headers, run_headers
):
    first = await _make(
        app, auth_headers, run_headers, "spec/changes/a/spec.json", "One", "tasks board"
    )
    assert first.status_code == 200, first.text

    second = await _make(
        app, auth_headers, run_headers, "spec/changes/b/spec.json", "Two", "Tasks Board"
    )
    assert second.status_code == 422, second.text
    assert "One" in str(second.json()) and "Tasks Board" in str(second.json())
    assert second.json()["detail"]["code"] == "tag_taken"
    assert (await _doc_row("spec/changes/a/spec.json")).tag == "tasks board"
    assert (await _doc_row("spec/changes/b/spec.json")).tag is None


async def test_a_tag_over_24_characters_is_refused(app, auth_headers, run_headers):
    response = await _make(
        app, auth_headers, run_headers, "spec/changes/a/spec.json", "One", "x" * 25
    )
    assert response.status_code == 422, response.text


async def test_derived_tags_differ_and_fit_when_titles_collide(app, auth_headers, run_headers):
    for path in ("spec/changes/a/spec.json", "spec/changes/b/spec.json"):
        assert (
            await _make(
                app, auth_headers, run_headers, path, "Find a spec's tasks without knowing its name"
            )
        ).status_code == 200
    async with async_session_factory() as session:
        for path in ("a", "b"):
            row = await _doc_row(f"spec/changes/{path}/spec.json")
            session.add(
                Task(
                    id=f"task-dt-{path}", project_id="proj-test", title="t", spec_document_id=row.id
                )
            )
        await session.commit()

    boards = (await app.get(BOARDS, headers=auth_headers)).json()["boards"]
    tags = [b["tag"] for b in boards if b["spec_document_id"]]
    assert len(tags) == 2 and len(set(tags)) == 2
    assert all(0 < len(tag) <= 24 for tag in tags)
    # Stored, so a second read answers with the same tags.
    again = (await app.get(BOARDS, headers=auth_headers)).json()["boards"]
    assert sorted(b["tag"] for b in again if b["spec_document_id"]) == sorted(tags)


async def test_boards_lists_the_most_recently_active_spec_first(app, auth_headers):
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        for doc_id, title, age in (
            ("doc-aaa", "Alpha", timedelta(days=7)),
            ("doc-zzz", "Zeta", timedelta(hours=1)),
        ):
            session.add(
                SpecDocument(
                    id=doc_id,
                    project_id="proj-test",
                    path=f"spec/changes/{doc_id}/spec.json",
                    title=title,
                )
            )
            session.add(
                Task(
                    id=f"task-{doc_id}",
                    project_id="proj-test",
                    title="t",
                    spec_document_id=doc_id,
                    created_at=now - age,
                    updated=now - age,
                )
            )
        session.add(
            Task(id="task-loose", project_id="proj-test", title="t", created_at=now, updated=now)
        )
        await session.commit()

    boards = (await app.get(BOARDS, headers=auth_headers)).json()["boards"]
    assert [b["spec_document_id"] for b in boards] == ["doc-zzz", "doc-aaa", None]
    assert boards[0]["last_activity"] > boards[1]["last_activity"]


def test_derive_keeps_within_the_limit_and_yields_to_what_is_taken():
    title = "Find a spec's tasks without knowing its name"
    first = spec_tags.derive(title)
    assert len(first) <= spec_tags.MAX_LENGTH
    second = spec_tags.derive(title, [first.upper()])
    assert second != first and len(second) <= spec_tags.MAX_LENGTH
    assert len(spec_tags.derive("Supercalifragilisticexpialidocious" * 2)) <= spec_tags.MAX_LENGTH
