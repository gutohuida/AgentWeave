"""The knowledge vault's text sources: settings, upload, the map, reading by id.

`a-vault-the-operator-fills-with-text-and-agents-can-read` (Tier 2). The project's directory is the
test's own `tmp_path` (conftest's `_default_project_workspace`), and the vault's default private
root is a temporary directory (conftest's `_vaults_stay_out_of_the_real_home`), so nothing here
touches the operator's home.
"""

import json
from pathlib import Path

import pytest

from hub import vault

BASE = "/api/v1/projects/proj-test"
TRANSCRIPT = "Kickoff with Acme.\n\nDana: the refund limit is 437 euros.\n"


async def _settings(app, auth_headers) -> dict:
    got = await app.get(f"{BASE}/vault/settings", headers=auth_headers)
    assert got.status_code == 200, got.text
    return got.json()


async def _upload(app, auth_headers, **fields) -> dict:
    body = {"name": "Acme kickoff", "type": "transcript", "content": TRANSCRIPT, **fields}
    created = await app.post(f"{BASE}/vault/sources", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()


async def _private_location(app, auth_headers, tmp_path_factory) -> Path:
    location = tmp_path_factory.mktemp("private-vault")
    put = await app.put(
        f"{BASE}/vault/settings", json={"private_location": str(location)}, headers=auth_headers
    )
    assert put.status_code == 200, put.text
    return location


def _files(root: Path) -> list:
    if not root.exists():
        return []
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# ---------------------------------------------------------------------------
# vault-settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settings_default_to_tracked_and_the_hubs_own_private_folder(
    app, auth_headers
) -> None:
    got = await _settings(app, auth_headers)
    assert got["private_location"] is None
    assert got["default_visibility"] == "tracked"
    assert Path(got["effective_private_location"]) == vault.vaults_root() / "proj-test"


@pytest.mark.asyncio
async def test_settings_refuse_locations_in_the_project_and_bad_values(
    app, auth_headers, tmp_path, tmp_path_factory
) -> None:
    """settings-routes: each bad PUT answers 400 and leaves the stored values as they were."""
    outside = tmp_path_factory.mktemp("outside")
    a_file = outside / "not-a-dir.txt"
    a_file.write_text("x", encoding="utf-8")
    bad = [
        {"private_location": "relative/vault"},
        {"private_location": str(tmp_path / "private")},
        {"private_location": str(tmp_path)},
        {"private_location": str(tmp_path / ".agentweave" / "worktrees" / "task-1" / "v")},
        {"private_location": str(tmp_path / "sub" / ".." / "private")},
        {"private_location": str(a_file / "sub")},
        {"default_visibility": "public"},
    ]
    for body in bad:
        refused = await app.put(f"{BASE}/vault/settings", json=body, headers=auth_headers)
        assert refused.status_code == 400, (body, refused.text)
        assert (await _settings(app, auth_headers))["private_location"] is None
        assert (await _settings(app, auth_headers))["default_visibility"] == "tracked"
    assert not (tmp_path / "private").exists()

    chosen = outside / "vault"
    valid = await app.put(
        f"{BASE}/vault/settings",
        json={"private_location": str(chosen), "default_visibility": "private"},
        headers=auth_headers,
    )
    assert valid.status_code == 200, valid.text
    got = await _settings(app, auth_headers)
    assert Path(got["private_location"]) == chosen
    assert Path(got["effective_private_location"]) == chosen
    assert got["default_visibility"] == "private"
    assert chosen.is_dir()

    cleared = await app.put(
        f"{BASE}/vault/settings", json={"private_location": None}, headers=auth_headers
    )
    assert cleared.status_code == 200, cleared.text
    got = await _settings(app, auth_headers)
    assert got["private_location"] is None
    assert got["default_visibility"] == "private"


# ---------------------------------------------------------------------------
# source-uploaded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_tracked_source_is_written_under_knowledge_byte_for_byte(
    app, auth_headers, tmp_path
) -> None:
    text = "Line one, with a café.\r\nLine two.\n"
    entry = await _upload(app, auth_headers, content=text)
    assert entry["visibility"] == "tracked"
    assert entry["available"] is True
    sources = tmp_path / "knowledge" / "sources"
    assert (sources / f"{entry['id']}.md").read_bytes() == text.encode("utf-8")
    meta = json.loads((sources / f"{entry['id']}.json").read_text(encoding="utf-8"))
    assert meta["id"] == entry["id"]
    assert meta["name"] == "Acme kickoff"
    assert meta["type"] == "transcript"
    assert meta["visibility"] == "tracked"


@pytest.mark.asyncio
async def test_a_private_source_leaves_only_a_stub_in_the_project(
    app, auth_headers, tmp_path, tmp_path_factory
) -> None:
    location = await _private_location(app, auth_headers, tmp_path_factory)
    secret = "CANARY-31 the contact prefers Tuesdays.\n"
    entry = await _upload(
        app, auth_headers, name="Contact", type="note", content=secret, visibility="private"
    )
    assert entry["visibility"] == "private"
    assert entry["available"] is True
    assert _files(location) == [f"sources/{entry['id']}.json", f"sources/{entry['id']}.md"]
    assert (location / "sources" / f"{entry['id']}.md").read_text(encoding="utf-8") == secret
    in_project = _files(tmp_path / "knowledge")
    assert in_project == [f"sources/{entry['id']}.json"]
    stub = (tmp_path / "knowledge" / "sources" / f"{entry['id']}.json").read_text(encoding="utf-8")
    assert "CANARY-31" not in stub
    assert json.loads(stub)["holder"] == vault.holder_name()


@pytest.mark.asyncio
async def test_the_project_default_decides_where_an_upload_goes(
    app, auth_headers, tmp_path, tmp_path_factory
) -> None:
    location = await _private_location(app, auth_headers, tmp_path_factory)
    put = await app.put(
        f"{BASE}/vault/settings", json={"default_visibility": "private"}, headers=auth_headers
    )
    assert put.status_code == 200, put.text
    entry = await _upload(app, auth_headers)
    assert entry["visibility"] == "private"
    assert (location / "sources" / f"{entry['id']}.md").is_file()
    assert not (tmp_path / "knowledge" / "sources" / f"{entry['id']}.md").exists()


@pytest.mark.asyncio
async def test_invalid_uploads_are_refused_and_write_nothing(app, auth_headers, tmp_path) -> None:
    bad = [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 201},
        {"type": "memo"},
        {"content": ""},
        {"visibility": "public"},
    ]
    for fields in bad:
        body = {"name": "n", "type": "note", "content": "text", **fields}
        refused = await app.post(f"{BASE}/vault/sources", json=body, headers=auth_headers)
        assert refused.status_code == 400, (fields, refused.text)
    huge = "é" * (vault.MAX_CONTENT_BYTES // 2 + 1)
    too_big = await app.post(
        f"{BASE}/vault/sources",
        json={"name": "n", "type": "note", "content": huge},
        headers=auth_headers,
    )
    assert too_big.status_code == 413, too_big.text
    assert _files(tmp_path / "knowledge") == []


# ---------------------------------------------------------------------------
# map-listed
# ---------------------------------------------------------------------------


def _foreign_stub(project_root: Path, entry_id: str = "src-0123456789ab") -> str:
    sources = project_root / "knowledge" / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    (sources / f"{entry_id}.json").write_text(
        json.dumps(
            {
                "id": entry_id,
                "name": "Someone else's notes",
                "type": "note",
                "visibility": "private",
                "holder": "colleague-laptop",
                "created_at": "2026-01-01T00:00:00.000000Z",
            }
        ),
        encoding="utf-8",
    )
    return entry_id


@pytest.mark.asyncio
async def test_the_map_is_built_from_the_files_newest_first(
    app, auth_headers, tmp_path, tmp_path_factory
) -> None:
    await _private_location(app, auth_headers, tmp_path_factory)
    first = await _upload(app, auth_headers, content=("A" * 250 + "\n") * 3)
    second = await _upload(
        app, auth_headers, name="Mine", type="note", content="Mine.\n", visibility="private"
    )
    foreign = _foreign_stub(tmp_path)

    got = await app.get(f"{BASE}/vault/map", headers=auth_headers)
    assert got.status_code == 200, got.text
    entries = got.json()["entries"]
    assert [e["id"] for e in entries] == [second["id"], first["id"], foreign]
    by_id = {e["id"]: e for e in entries}
    assert len(by_id[first["id"]]["opening"]) == vault.OPENING_CHARS
    assert by_id[second["id"]]["available"] is True
    assert by_id[second["id"]]["opening"] == "Mine."
    assert by_id[foreign]["available"] is False
    assert by_id[foreign]["opening"] is None
    assert by_id[foreign]["holder"] == "colleague-laptop"
    for entry in entries:
        assert set(entry) >= {
            "id",
            "name",
            "type",
            "visibility",
            "created_at",
            "holder",
            "available",
            "opening",
        }


@pytest.mark.asyncio
async def test_the_map_skips_files_that_are_not_records(app, auth_headers, tmp_path) -> None:
    sources = tmp_path / "knowledge" / "sources"
    sources.mkdir(parents=True)
    (sources / "README.md").write_text("hello", encoding="utf-8")
    (sources / "src-zzzzzzzzzzzz.json").write_text("{}", encoding="utf-8")
    (sources / "src-aaaaaaaaaaaa.json").write_text("not json", encoding="utf-8")
    (sources / "src-bbbbbbbbbbbb.json").write_text(
        json.dumps({"id": "src-cccccccccccc"}), encoding="utf-8"
    )
    got = await app.get(f"{BASE}/vault/map", headers=auth_headers)
    assert got.status_code == 200, got.text
    assert got.json()["entries"] == []


# ---------------------------------------------------------------------------
# entry-read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_long_source_is_read_in_pages(app, auth_headers, tmp_path) -> None:
    text = "".join(f"{i:05d} " for i in range(20_000))
    assert len(text) == 120_000
    entry = await _upload(app, auth_headers, content=text)
    pieces, offset = [], 0
    while offset is not None:
        got = await app.get(
            f"{BASE}/vault/entries/{entry['id']}", params={"offset": offset}, headers=auth_headers
        )
        assert got.status_code == 200, got.text
        body = got.json()
        assert len(body["content"]) <= vault.PAGE_CHARS
        pieces.append(body["content"])
        offset = body["next_offset"]
    assert len(pieces) == 3
    assert "".join(pieces) == text


@pytest.mark.asyncio
async def test_a_stub_held_elsewhere_and_unknown_ids(app, auth_headers, tmp_path) -> None:
    foreign = _foreign_stub(tmp_path)
    got = await app.get(f"{BASE}/vault/entries/{foreign}", headers=auth_headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["available"] is False
    assert body["content"] is None
    assert body["next_offset"] is None
    assert "colleague-laptop" in body["note"]

    for unknown in ("src-ffffffffffff", "src-..", "README", "..%2Fsecret"):
        missing = await app.get(f"{BASE}/vault/entries/{unknown}", headers=auth_headers)
        assert missing.status_code == 404, (unknown, missing.text)


# ---------------------------------------------------------------------------
# one-storage-interface
# ---------------------------------------------------------------------------


class _MemoryStorage:
    def __init__(self) -> None:
        self.files: dict = {}

    def write(self, root: str, relative: str, data: bytes) -> None:
        self.files[(root, relative)] = data

    def read(self, root: str, relative: str):
        return self.files.get((root, relative))

    def list(self, root: str, directory: str) -> list:
        prefix = directory.rstrip("/") + "/"
        return sorted(
            rel[len(prefix) :] for (r, rel) in self.files if r == root and rel.startswith(prefix)
        )


@pytest.mark.asyncio
async def test_the_routes_work_unchanged_on_another_storage(
    app, auth_headers, tmp_path, monkeypatch
) -> None:
    memory = _MemoryStorage()
    monkeypatch.setattr(vault, "storage", memory)
    entry = await _upload(app, auth_headers)
    listed = await app.get(f"{BASE}/vault/map", headers=auth_headers)
    assert [e["id"] for e in listed.json()["entries"]] == [entry["id"]]
    read = await app.get(f"{BASE}/vault/entries/{entry['id']}", headers=auth_headers)
    assert read.json()["content"] == TRANSCRIPT
    assert memory.files
    assert not (tmp_path / "knowledge").exists()


# ---------------------------------------------------------------------------
# agent-tools
# ---------------------------------------------------------------------------


async def _run_headers(run_id: str, agent: str) -> dict:
    """A live run's minted credential: the only identity the agent-actions routes accept."""
    from hub.agent_auth import hash_run_token
    from hub.db.engine import async_session_factory
    from hub.db.models import Agent, Run

    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as db:
        db.add(Agent(id=f"agent-{agent}", project_id="proj-test", name=agent))
        db.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_an_agent_reads_the_map_and_an_entry_with_its_run_credential(
    app, auth_headers
) -> None:
    entry = await _upload(app, auth_headers)
    headers = await _run_headers("run-vault-reader", "reader")

    listed = await app.get("/api/v1/agent-actions/vault/map", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [e["id"] for e in listed.json()["entries"]] == [entry["id"]]

    read = await app.get(f"/api/v1/agent-actions/vault/entries/{entry['id']}", headers=headers)
    assert read.status_code == 200, read.text
    assert read.json()["content"] == TRANSCRIPT

    unknown = await app.get("/api/v1/agent-actions/vault/entries/src-ffffffffffff", headers=headers)
    assert unknown.status_code == 404, unknown.text
    anonymous = await app.get("/api/v1/agent-actions/vault/map")
    assert anonymous.status_code in (401, 403), anonymous.text


@pytest.mark.asyncio
async def test_no_agent_route_writes_to_the_vault(app) -> None:
    """Only the operator (and later the manager) writes: every agent-actions vault route is a GET."""
    from hub.main import app as fastapi_app

    from ._routing import iter_api_routes

    methods = {
        method
        for path, route in iter_api_routes(fastapi_app)
        if "/agent-actions/vault" in path
        for method in route.methods
    }
    assert methods and methods <= {"GET", "HEAD"}


def test_the_two_tools_are_on_every_runners_surface() -> None:
    from hub import mcp_server
    from hub.api.v1.agents import _operations
    from hub.copilot_acp import HUB_MCP_TOOLS

    for tool in ("vault_map", "vault_read"):
        assert tool in mcp_server._CALLABLE_TOOLS
        assert tool in HUB_MCP_TOOLS
        assert tool in {operation.tool for operation in _operations()}


# ---------------------------------------------------------------------------
# map-in-turn
# ---------------------------------------------------------------------------


async def _context() -> dict:
    from sqlalchemy import select

    from hub.api.v1.agents import _render_hub_agent_context
    from hub.db.engine import async_session_factory
    from hub.db.models import Agent

    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(Agent).where(Agent.project_id == "proj-test", Agent.name == "vaulter")
            )
        ).scalar_one()
        return await _render_hub_agent_context(
            agent="vaulter",
            project_id="proj-test",
            db=db,
            session_data=None,
            agent_row=row,
            work_dir="/tmp/project",
            access_path="mcp",
            runner="copilot",
        )


@pytest.mark.asyncio
async def test_an_empty_vault_adds_nothing_to_a_turn(app, auth_headers, add_agent) -> None:
    await add_agent("vaulter")
    rendered = await _context()
    assert "Knowledge vault" not in rendered["context"]


@pytest.mark.asyncio
async def test_a_turn_names_the_vault_in_one_line_in_its_per_turn_part(
    app, auth_headers, add_agent
) -> None:
    """The operator's choice (2026-10-09): a one-line pointer, not an index of entries."""
    await add_agent("vaulter")
    first = await _upload(app, auth_headers, name="First meeting")
    second = await _upload(app, auth_headers, name="Refund rules", type="rules")
    rendered = await _context()
    per_turn = rendered["per_turn"]
    assert "Knowledge vault" not in rendered["stable"]
    section = per_turn[per_turn.index("### Knowledge vault") :].split(chr(10) * 2)[0].splitlines()
    assert len(section) == 2, section
    line = section[1]
    assert "2 entries" in line
    assert "vault_map()" in line and "vault_read(" in line
    assert first["id"] not in per_turn and second["id"] not in per_turn
    assert "Refund rules" not in per_turn


@pytest.mark.asyncio
async def test_the_pointer_stays_one_line_however_large_the_vault(
    app, auth_headers, add_agent, tmp_path
) -> None:
    await add_agent("vaulter")
    for i in range(200):
        vault.add_source(
            tmp_path,
            vault.default_private_location("proj-test"),
            name=f"Meeting number {i:03d}",
            type="transcript",
            content=f"Meeting {i}.",
            visibility="tracked",
        )
    rendered = await _context()
    per_turn = rendered["per_turn"]
    section = per_turn[per_turn.index("### Knowledge vault") :].split(chr(10) * 2)[0].splitlines()
    assert len(section) == 2, section
    assert "200 entries" in section[1]
    assert "src-" not in per_turn


def test_one_entry_is_named_in_the_singular() -> None:
    lines = vault.render_turn_index([{"id": "src-0123456789ab"}])
    assert "with 1 entry (" in lines[1]
    assert vault.render_turn_index([]) == []
