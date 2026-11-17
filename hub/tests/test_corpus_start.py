"""A project with no specs is offered a start (`a-project-with-no-specs-is-offered-a-start`).

Task `server`: the corpus-state read (FR-1, FR-4), the specification set-up item (FR-3), the start
route (FR-5, FR-10) and the two turns it queues (FR-6, FR-9). Every project here is opened on a
real temporary folder, so emptiness and code are read from disk as the Hub reads them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from hub import corpus_start, project_workspace, turn_scheduler
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    Charter,
    Conversation,
    InboundQueueEntry,
    SetupDismissal,
    SpecDocument,
    SpecDocumentEvent,
)
from hub.utils import short_id

#: Taken at import, before conftest's autouse fixture roots every project at `tmp_path`: these
#: tests are about the folder each project was really opened in.
_REAL_RESOLVE = project_workspace.resolve_project_workspace


@pytest.fixture(autouse=True)
def _projects_resolve_to_their_own_folders(monkeypatch) -> None:
    monkeypatch.setattr(project_workspace, "resolve_project_workspace", _REAL_RESOLVE)


@pytest.fixture
def scheduled(monkeypatch):
    calls = []

    async def recording(project_id, agent):
        calls.append((project_id, agent))

    monkeypatch.setattr(turn_scheduler, "schedule_agent", recording)
    return calls


def _code_folder(tmp_path: Path, name: str = "with-code") -> Path:
    root = tmp_path / name
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    return root


def _empty_folder(tmp_path: Path, name: str = "empty") -> Path:
    root = tmp_path / name
    root.mkdir()
    return root


def _unadopted_folder(tmp_path: Path, name: str = "unadopted") -> Path:
    root = tmp_path / name
    (root / "spec" / "changes" / "x").mkdir(parents=True)
    (root / "spec" / "changes" / "x" / "spec.json").write_text(
        '{"schema_version": 1, "kind": "change-spec", "title": "X"}', encoding="utf-8"
    )
    return root


async def _open(app, auth_headers, root: Path) -> str:
    opened = await app.post("/api/v1/projects/open", json={"path": str(root)}, headers=auth_headers)
    assert opened.status_code == 200, opened.text
    return opened.json()["id"]


def _base(project_id: str) -> str:
    return f"/api/v1/projects/{project_id}/project"


async def _state(app, auth_headers, project_id: str) -> dict:
    read = await app.get(f"{_base(project_id)}/corpus", headers=auth_headers)
    assert read.status_code == 200, read.text
    return read.json()


async def _setup(app, auth_headers, project_id: str) -> dict:
    listed = await app.get("/api/v1/projects", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    (project,) = [p for p in listed.json() if p["id"] == project_id]
    return project["setup"]


def _ids(items: list[dict]) -> list[str]:
    return [item["id"] for item in items]


async def _agent(project_id: str, name: str, charter: str | None = None) -> None:
    async with async_session_factory() as session:
        charter_id = None
        if charter is not None:
            charter_id = await session.scalar(
                select(Charter.id).where(Charter.project_id == project_id, Charter.name == charter)
            )
            if charter_id is None:
                charter_id = f"charter-{short_id()}"
                session.add(Charter(id=charter_id, project_id=project_id, name=charter))
        session.add(
            Agent(
                id=f"agent-{short_id()}",
                project_id=project_id,
                name=name,
                config={},
                charter_id=charter_id,
            )
        )
        await session.commit()


async def _documents(project_id: str) -> list[SpecDocument]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(SpecDocument).where(SpecDocument.project_id == project_id)
                )
            )
            .scalars()
            .all()
        )


async def _entries(project_id: str) -> list[InboundQueueEntry]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.project_id == project_id)
                )
            )
            .scalars()
            .all()
        )


# FR-1 ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_code_empty_and_unadopted_folders_read_as_their_own_start(
    app, auth_headers, tmp_path
) -> None:
    """ac-detect-code: code and no spec/ recommends existing code; an empty folder recommends
    greenfield; an unadopted spec file is not an empty corpus."""
    with_code = await _open(app, auth_headers, _code_folder(tmp_path))
    empty = await _open(app, auth_headers, _empty_folder(tmp_path))
    unadopted = await _open(app, auth_headers, _unadopted_folder(tmp_path))

    first = await _state(app, auth_headers, with_code)
    second = await _state(app, auth_headers, empty)
    third = await _state(app, auth_headers, unadopted)

    assert (first["empty"], first["has_code"], first["recommended"]) == (
        True,
        True,
        "existing-code",
    )
    assert first["starts"] == ["existing-code", "greenfield"]
    assert (second["empty"], second["has_code"], second["recommended"]) == (
        True,
        False,
        "greenfield",
    )
    assert third["empty"] is False
    assert third["recommended"] is None and third["starts"] == []
    assert third["unadopted"] == ["spec/changes/x/spec.json"]
    assert third["document"] == "spec/changes/x/spec.json"


@pytest.mark.asyncio
async def test_a_project_whose_only_document_is_archived_is_not_empty(
    app, auth_headers, tmp_path
) -> None:
    """ac-archived-not-empty: an archived document still counts, and no set-up item is shown."""
    project_id = await _open(app, auth_headers, _code_folder(tmp_path))
    created = await app.post(
        f"{_base(project_id)}/documents", json={"title": "Old"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    async with async_session_factory() as session:
        (row,) = (
            (
                await session.execute(
                    select(SpecDocument).where(SpecDocument.project_id == project_id)
                )
            )
            .scalars()
            .all()
        )
        row.phase = "archived"
        await session.commit()

    state = await _state(app, auth_headers, project_id)

    assert state["empty"] is False
    assert state["document"] == created.json()["path"]
    setup = await _setup(app, auth_headers, project_id)
    assert "specification" not in _ids(setup["items"]) + _ids(setup["dismissed"])


# FR-4 ---------------------------------------------------------------------------------------


def test_preselect_is_the_one_spec_author_else_the_first_open_agent() -> None:
    """ac-preselect-fallback, and the rule ac-agent-choice preselects by."""
    spec = corpus_start.SPEC_AUTHOR_CHARTER
    assert corpus_start.preselect([("Alpha", None), ("Bravo", spec)]) == "Bravo"
    assert corpus_start.preselect([("Alpha", "Developer"), ("Bravo", None)]) == "Alpha"
    assert corpus_start.preselect([("Alpha", spec), ("Bravo", spec), ("Carol", None)]) == "Alpha"
    assert corpus_start.preselect([]) is None


@pytest.mark.asyncio
async def test_the_corpus_state_preselects_the_spec_author_among_open_agents(
    app, auth_headers, tmp_path
) -> None:
    """ac-agent-choice (Hub side): two open agents, the second Spec Author, preselect the second
    and list both; an archived Spec Author is not counted; a project with none preselects none."""
    project_id = await _open(app, auth_headers, _code_folder(tmp_path))
    await _agent(project_id, "Alpha")
    await _agent(project_id, "Bravo", charter=corpus_start.SPEC_AUTHOR_CHARTER)
    nobody = await _open(app, auth_headers, _empty_folder(tmp_path))

    state = await _state(app, auth_headers, project_id)
    assert [a["name"] for a in state["agents"]] == ["Alpha", "Bravo"]
    assert state["preselected_agent"] == "Bravo"

    async with async_session_factory() as session:
        bravo = await session.scalar(
            select(Agent).where(Agent.project_id == project_id, Agent.name == "Bravo")
        )
        bravo.lifecycle = "archived"
        await session.commit()
    state = await _state(app, auth_headers, project_id)
    assert [a["name"] for a in state["agents"]] == ["Alpha"]
    assert state["preselected_agent"] == "Alpha"

    none = await _state(app, auth_headers, nobody)
    assert none["agents"] == [] and none["preselected_agent"] is None


# FR-3 ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_specification_item_is_dismissed_restored_and_gone_once_a_document_exists(
    app, auth_headers, tmp_path
) -> None:
    """ac-overview-item and ac-overview-gone (Hub side): shown while empty, dismissable and
    restorable like the repository item, and gone without a dismissal once a document exists."""
    project_id = await _open(app, auth_headers, _code_folder(tmp_path))
    setup = await _setup(app, auth_headers, project_id)
    (item,) = [i for i in setup["items"] if i["id"] == "specification"]
    assert item["key"] == "specification" and item["dismissable"] is True

    dismissed = await app.put(
        f"/api/v1/projects/{project_id}/setup/dismissed/specification", headers=auth_headers
    )
    assert dismissed.status_code == 200, dismissed.text
    setup = await _setup(app, auth_headers, project_id)
    assert "specification" not in _ids(setup["items"])
    assert "specification" in _ids(setup["dismissed"])

    restored = await app.delete(
        f"/api/v1/projects/{project_id}/setup/dismissed/specification", headers=auth_headers
    )
    assert restored.status_code == 200, restored.text
    setup = await _setup(app, auth_headers, project_id)
    assert "specification" in _ids(setup["items"])

    created = await app.post(
        f"{_base(project_id)}/documents", json={"title": "First"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    setup = await _setup(app, auth_headers, project_id)
    assert "specification" not in _ids(setup["items"])
    assert "specification" not in _ids(setup["dismissed"])
    async with async_session_factory() as session:
        assert await session.get(SetupDismissal, (project_id, "specification")) is None


# FR-5 ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_existing_code_start_creates_a_system_map_and_queues_the_turn(
    app, auth_headers, tmp_path, scheduled
) -> None:
    """ac-start-existing (Hub side): a system map in exploring, created by the operator; a new
    conversation holding one queued operator-origin entry for the chosen agent, carrying the
    document; the agent scheduled; the corpus no longer empty."""
    project_id = await _open(app, auth_headers, _code_folder(tmp_path))
    await _agent(project_id, "Alpha")
    await _agent(project_id, "Bravo", charter=corpus_start.SPEC_AUTHOR_CHARTER)

    started = await app.post(
        f"{_base(project_id)}/corpus/start",
        json={"start": "existing-code", "agent": "Alpha"},
        headers=auth_headers,
    )

    assert started.status_code == 201, started.text
    body = started.json()
    assert body["state"] == "queued" and body["agent"] == "Alpha"
    (document,) = await _documents(project_id)
    assert (document.kind, document.phase, document.path) == (
        "system-map",
        "exploring",
        body["document"]["path"],
    )
    async with async_session_factory() as session:
        created = await session.scalar(
            select(SpecDocumentEvent).where(
                SpecDocumentEvent.document_id == document.id, SpecDocumentEvent.kind == "created"
            )
        )
        assert created.actor_kind == "operator"
        conversation = await session.scalar(
            select(Conversation).where(
                Conversation.project_id == project_id,
                Conversation.id == body["conversation_id"],
            )
        )
        assert conversation is not None and conversation.agent == "Alpha"
        assert conversation.origin == "operator"
    (entry,) = await _entries(project_id)
    assert entry.id == body["entry_id"]
    assert (entry.agent, entry.origin_type, entry.conversation_id, entry.spec_document) == (
        "Alpha",
        "operator",
        body["conversation_id"],
        document.path,
    )
    assert entry.content == corpus_start.existing_code_message(document.path)
    assert scheduled == [(project_id, "Alpha")]
    state = await _state(app, auth_headers, project_id)
    assert state["empty"] is False and state["document"] == document.path


@pytest.mark.asyncio
async def test_a_start_with_no_agent_named_goes_to_the_preselected_one(
    app, auth_headers, tmp_path, scheduled
) -> None:
    project_id = await _open(app, auth_headers, _code_folder(tmp_path))
    await _agent(project_id, "Alpha")
    await _agent(project_id, "Bravo", charter=corpus_start.SPEC_AUTHOR_CHARTER)

    started = await app.post(
        f"{_base(project_id)}/corpus/start", json={"start": "existing-code"}, headers=auth_headers
    )

    assert started.status_code == 201, started.text
    assert started.json()["agent"] == "Bravo"


@pytest.mark.asyncio
async def test_the_greenfield_start_creates_a_roadmap_and_queues_the_interview(
    app, auth_headers, tmp_path, scheduled
) -> None:
    """ac-greenfield (Hub side): a roadmap in exploring and the interview queued."""
    project_id = await _open(app, auth_headers, _empty_folder(tmp_path))
    await _agent(project_id, "Greeter")

    started = await app.post(
        f"{_base(project_id)}/corpus/start",
        json={"start": "greenfield", "agent": "Greeter"},
        headers=auth_headers,
    )

    assert started.status_code == 201, started.text
    (document,) = await _documents(project_id)
    assert (document.kind, document.phase) == ("roadmap", "exploring")
    (entry,) = await _entries(project_id)
    assert entry.content == corpus_start.greenfield_message(document.path)
    assert entry.spec_document == document.path
    assert scheduled == [(project_id, "Greeter")]


@pytest.mark.asyncio
async def test_a_second_start_is_refused_naming_the_document_and_creates_nothing(
    app, auth_headers, tmp_path, scheduled
) -> None:
    """ac-double-start."""
    project_id = await _open(app, auth_headers, _code_folder(tmp_path))
    await _agent(project_id, "Alpha")
    first = await app.post(
        f"{_base(project_id)}/corpus/start", json={"start": "existing-code"}, headers=auth_headers
    )
    assert first.status_code == 201, first.text
    path = first.json()["document"]["path"]

    again = await app.post(
        f"{_base(project_id)}/corpus/start", json={"start": "greenfield"}, headers=auth_headers
    )

    assert again.status_code == 409, again.text
    detail = again.json()["detail"]
    assert detail["code"] == "corpus_not_empty"
    assert detail["document"] == path and path in detail["message"]
    assert [d.path for d in await _documents(project_id)] == [path]
    assert len(await _entries(project_id)) == 1


@pytest.mark.asyncio
async def test_a_start_on_an_unadopted_corpus_is_refused(
    app, auth_headers, tmp_path, scheduled
) -> None:
    project_id = await _open(app, auth_headers, _unadopted_folder(tmp_path))
    await _agent(project_id, "Alpha")

    refused = await app.post(
        f"{_base(project_id)}/corpus/start", json={"start": "greenfield"}, headers=auth_headers
    )

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["document"] == "spec/changes/x/spec.json"
    assert await _documents(project_id) == []


@pytest.mark.asyncio
async def test_a_start_with_no_open_agent_or_a_stranger_creates_nothing(
    app, auth_headers, tmp_path, scheduled
) -> None:
    project_id = await _open(app, auth_headers, _code_folder(tmp_path))

    nobody = await app.post(
        f"{_base(project_id)}/corpus/start", json={"start": "existing-code"}, headers=auth_headers
    )
    assert nobody.status_code == 422, nobody.text
    assert nobody.json()["detail"]["code"] == "no_open_agent"

    await _agent(project_id, "Alpha")
    stranger = await app.post(
        f"{_base(project_id)}/corpus/start",
        json={"start": "existing-code", "agent": "Zed"},
        headers=auth_headers,
    )
    assert stranger.status_code == 422, stranger.text
    assert stranger.json()["detail"]["code"] == "agent_not_open"
    assert await _documents(project_id) == []
    assert await _entries(project_id) == []
    assert scheduled == []


# FR-10 --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_start_in_the_query_string_is_refused_and_the_same_in_the_body_succeeds(
    app, auth_headers, tmp_path, scheduled
) -> None:
    """ac-query-refused."""
    project_id = await _open(app, auth_headers, _code_folder(tmp_path))
    await _agent(project_id, "Alpha")

    misplaced = await app.post(
        f"{_base(project_id)}/corpus/start?start=existing-code&agent=Alpha", headers=auth_headers
    )
    assert misplaced.status_code == 400, misplaced.text
    assert "sent as a query parameter" in misplaced.json()["detail"]
    assert "agent, start" in misplaced.json()["detail"]
    async with async_session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(SpecDocument)
            .where(SpecDocument.project_id == project_id)
        )
    assert count == 0 and await _entries(project_id) == []

    in_body = await app.post(
        f"{_base(project_id)}/corpus/start",
        json={"start": "existing-code", "agent": "Alpha"},
        headers=auth_headers,
    )
    assert in_body.status_code == 201, in_body.text


# FR-6, FR-9 ---------------------------------------------------------------------------------


def test_the_existing_code_message_asks_for_each_element() -> None:
    """ac-existing-prompt."""
    path = "spec/changes/amber-griffin/spec.json"
    text = corpus_start.existing_code_message(path)
    lowered = text.lower()
    assert f"`{path}`" in text and "system-map" in text
    assert "read the code" in lowered
    for element in ("areas", "capabilities", "relate"):
        assert element in lowered, element
    assert "the map's `capabilities.creates`" in text
    assert "one capability draft per proposed capability" in lowered
    assert "change document with no tasks" in lowered
    assert "own `capabilities.creates` holds exactly that capability's title" in text
    assert "cites the files" in lowered and "path:line" in text
    assert "unresolved open question" in lowered and "resolved: false" in text
    assert "evidence limits" in lowered and "evidence.limits" in text
    assert "did not read" in lowered


def test_the_greenfield_message_asks_to_interview_first_in_the_reply() -> None:
    """ac-greenfield-prompt."""
    path = "spec/changes/amber-griffin/spec.json"
    text = corpus_start.greenfield_message(path)
    lowered = text.lower()
    assert f"`{path}`" in text and "roadmap" in lowered
    assert "interview the operator before writing any slices" in lowered
    for topic in ("problem", "users", "scope", "non-goals"):
        assert topic in lowered, topic
    assert "ask your questions in your reply" in lowered
    assert "first reply asks your first questions" in lowered
