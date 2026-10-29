# ruff: noqa: F811
"""Agents change a vault source through their tools: replace a passage, append, replace a file,
archive and restore.

`vault-sources-can-be-edited-replaced-and-archived` (Tier 2), the agents' half: ac-agent-replace-
passage, ac-file-not-text (agent side), ac-agent-replace, ac-record and ac-restore (agent side). The
actor of a change is the run's credential's, never the request body's.
"""

from pathlib import Path

import pytest

from hub import vault

from .test_vault_changes import PDF, _pdf, _read, _text, worker  # noqa: F401

BASE = "/api/v1/projects/proj-test"
ROUTE = "/api/v1/agent-actions/vault/sources"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PNG2 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 32


async def _agent(run_id: str, agent: str, workspace: Path) -> dict:
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
                workspace_dir=str(workspace),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _post(app, headers, source_id, verb, body=None):
    return await app.post(f"{ROUTE}/{source_id}/{verb}", json=body or {}, headers=headers)


@pytest.mark.asyncio
async def test_ac_agent_replace_passage(app, auth_headers, tmp_path) -> None:
    scout = await _agent("run-scout", "Scout", tmp_path)
    source = await _text(app, auth_headers, content="alpha beta beta\n")
    sid = source["id"]

    done = await _post(app, scout, sid, "replace-passage", {"old": "alpha", "new": "gamma"})
    assert done.status_code == 200, done.text
    assert (await _read(app, auth_headers, sid))["content"] == "gamma beta beta\n"

    twice = await _post(app, scout, sid, "replace-passage", {"old": "beta", "new": "x"})
    assert twice.status_code == 400 and "more than once" in twice.json()["detail"]
    nowhere = await _post(app, scout, sid, "replace-passage", {"old": "delta", "new": "x"})
    assert nowhere.status_code == 400 and "does not occur" in nowhere.json()["detail"]
    assert (await _read(app, auth_headers, sid))["content"] == "gamma beta beta\n"

    appended = await _post(app, scout, sid, "append", {"text": "note"})
    assert appended.status_code == 200, appended.text
    assert (await _read(app, auth_headers, sid))["content"] == "gamma beta beta\nnote"


@pytest.mark.asyncio
async def test_ac_file_not_text_agent_side(app, auth_headers, tmp_path) -> None:
    scout = await _agent("run-scout", "Scout", tmp_path)
    pdf = await _pdf(app, auth_headers)
    sid = pdf["id"]
    before = await app.get(f"{BASE}/vault/sources/{sid}/file", headers=auth_headers)

    edit = await app.put(
        f"{BASE}/vault/sources/{sid}/text",
        json={"content": "x", "version": "v"},
        headers=auth_headers,
    )
    passage = await _post(app, scout, sid, "replace-passage", {"old": "a", "new": "b"})
    append = await _post(app, scout, sid, "append", {"text": "more"})
    for refused in (edit, passage, append):
        assert refused.status_code == 409, refused.text
        assert "replacing it" in refused.json()["detail"]

    after = await app.get(f"{BASE}/vault/sources/{sid}/file", headers=auth_headers)
    assert after.content == before.content == PDF
    assert (await _read(app, auth_headers, sid))["changes"] == []


@pytest.mark.asyncio
async def test_ac_agent_replace_file(app, auth_headers, tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "new.png").write_bytes(PNG2)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "far.png").write_bytes(PNG2)
    scout = await _agent("run-scout", "Scout", workspace)
    created = await app.post(
        f"{BASE}/vault/files",
        params={"name": "Poster", "type": "document"},
        content=PNG,
        headers={**auth_headers, "Content-Type": "image/png"},
    )
    sid = created.json()["id"]

    done = await _post(app, scout, sid, "replace-file", {"path": "new.png"})
    assert done.status_code == 200, done.text
    served = await app.get(f"{BASE}/vault/sources/{sid}/file", headers=auth_headers)
    assert served.content == PNG2

    far = await _post(app, scout, sid, "replace-file", {"path": str(outside / "far.png")})
    assert far.status_code == 400 and "outside" in far.json()["detail"]
    added = await app.post(
        "/api/v1/agent-actions/vault/paths",
        json={"paths": [str(outside / "far.png")], "distil": False},
        headers=scout,
    )
    assert added.json()["results"][0]["reason"] == far.json()["detail"]

    text = await _text(app, auth_headers, content="some words\n")
    on_text = await _post(app, scout, text["id"], "replace-file", {"path": "new.png"})
    assert on_text.status_code == 409


@pytest.mark.asyncio
async def test_ac_record_names_the_credential_not_the_body(app, auth_headers, tmp_path) -> None:
    scout = await _agent("run-scout", "Scout", tmp_path)
    source = await _text(app, auth_headers, visibility="tracked")
    sid = source["id"]
    version = (
        source["version"]
        if "version" in source
        else (await _read(app, auth_headers, sid))["version"]
    )
    edit = await app.put(
        f"{BASE}/vault/sources/{sid}/text",
        json={"content": "Problems\nF-1: open\n", "version": version},
        headers=auth_headers,
    )
    assert edit.status_code == 200, edit.text

    appended = await app.post(
        f"{ROUTE}/{sid}/append",
        json={"text": "F-3: new\n", "agent": "Mallory", "run_id": "run-fake"},
        headers=scout,
    )
    assert appended.status_code in (200, 422), appended.text
    if appended.status_code == 422:  # the body cannot name an actor at all
        appended = await _post(app, scout, sid, "append", {"text": "F-3: new\n"})
        assert appended.status_code == 200, appended.text
    for verb in ("archive", "restore"):
        done = await app.post(f"{BASE}/vault/sources/{sid}/{verb}", headers=auth_headers)
        assert done.status_code == 200, done.text

    changes = (await _read(app, auth_headers, sid))["changes"]
    assert [c["action"] for c in changes] == ["edit", "edit", "archive", "restore"]
    assert changes[0]["by"] == {"kind": "operator"}
    assert changes[1]["by"] == {"kind": "agent", "agent": "Scout", "run_id": "run-scout"}
    assert changes[2]["by"] == changes[3]["by"] == {"kind": "operator"}
    assert list((tmp_path / "knowledge").rglob(f"{sid}.changes.json"))


@pytest.mark.asyncio
async def test_ac_restore_by_an_agent(app, auth_headers, tmp_path) -> None:
    scout = await _agent("run-scout", "Scout", tmp_path)
    s1 = await _text(app, auth_headers, content="one\n", name="One")
    s2 = await _text(app, auth_headers, content="two\n", name="Two")

    async def ids() -> list:
        got = await app.get(f"{BASE}/vault/map", headers=auth_headers)
        return sorted(e["id"] for e in got.json()["entries"])

    before = await ids()
    assert s1["id"] in before and s2["id"] in before

    archived = await _post(app, scout, s1["id"], "archive")
    assert archived.status_code == 200, archived.text
    assert await ids() == [s2["id"]]
    again = await _post(app, scout, s1["id"], "archive")
    assert again.status_code == 409

    restored = await _post(app, scout, s1["id"], "restore")
    assert restored.status_code == 200, restored.text
    assert await ids() == before
    assert (await _post(app, scout, s1["id"], "restore")).status_code == 409
    actions = [c["action"] for c in (await _read(app, auth_headers, s1["id"]))["changes"]]
    assert actions == ["archive", "restore"]


def test_the_tools_are_on_every_runners_surface() -> None:
    from hub import mcp_server
    from hub.api.v1.agents import _operations
    from hub.copilot_acp import HUB_MCP_TOOLS

    tools = {
        "vault_replace_passage",
        "vault_append",
        "vault_replace_file",
        "vault_archive",
        "vault_restore",
    }
    assert tools <= set(mcp_server._CALLABLE_TOOLS)
    assert tools <= set(HUB_MCP_TOOLS)
    assert tools <= {op.tool for op in _operations()}


def test_vault_module_agent_actor_shape() -> None:
    assert vault.agent_actor("Scout", "run-1") == {
        "kind": "agent",
        "agent": "Scout",
        "run_id": "run-1",
    }
