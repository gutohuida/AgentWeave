"""Agents (and the operator) add files to the vault by path, in bulk.

`agents-add-files-to-the-vault-by-path` (Tier 1, vault-1019). The project's directory is the test's
`tmp_path` (conftest), the vault's private root a temporary directory. The distillation worker is
faked as `test_vault_distillation.py` fakes it, answering no facts, so each distilled text source
is exactly one spawn and no contradiction check follows.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import distillation, manager
from hub.db.engine import async_session_factory
from hub.db.models import EventLog
from hub.worker import WorkerResult

BASE = "/api/v1/projects/proj-test"
AGENT_ROUTE = "/api/v1/agent-actions/vault/paths"
JOB = "vault-distillation"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
MEBIBYTE = 1024 * 1024


class _Worker:
    def __init__(self) -> None:
        self.calls: list = []

    async def __call__(self, **kwargs) -> WorkerResult:
        self.calls.append(kwargs)
        return WorkerResult("ok", parsed=distillation.Distilled(facts=[]))


@pytest.fixture
def worker(monkeypatch):
    fake = _Worker()
    monkeypatch.setattr(distillation, "run_worker", fake)
    return fake


async def _run_headers(run_id: str, agent: str, workspace: Path) -> dict:
    """A live run's minted credential, its workspace recorded as a real launch records it."""
    from hub.agent_auth import hash_run_token
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


def _inbox(folder: Path) -> None:
    folder.mkdir(parents=True)
    (folder / "a.md").write_bytes(b"# Refunds\n\nThe refund limit is 437 euros.\n")
    (folder / "b.txt").write_bytes(b"Returns are accepted within 30 days.\n")
    (folder / "c.pdf").write_bytes(PDF)
    (folder / "d.png").write_bytes(PNG)
    (folder / "e.exe").write_bytes(b"MZ\x90\x00")
    (folder / "f.pdf").write_bytes(PDF + b"\x00" * (10 * MEBIBYTE + 1))
    (folder / "z-copy.md").write_bytes((folder / "a.md").read_bytes())
    (folder / ".hidden.md").write_bytes(b"never listed\n")


async def _map(app, auth_headers) -> list:
    got = await app.get(f"{BASE}/vault/map", headers=auth_headers)
    assert got.status_code == 200, got.text
    return got.json()["entries"]


async def _firings() -> list:
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(EventLog).where(EventLog.event_type == manager.FIRED_EVENT)))
            .scalars()
            .all()
        )
    return [row.data for row in rows if (row.data or {}).get("job") == JOB]


async def _job_on(app, auth_headers) -> None:
    runner = await app.post(
        f"{BASE}/runners",
        json={"name": "distiller", "cli": "claude", "model": "claude-haiku-4-5-20251001"},
        headers=auth_headers,
    )
    assert runner.status_code == 201, runner.text
    patched = await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"enabled": True, "runner_id": runner.json()["id"]},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text


# ---------------------------------------------------------------------------
# The acceptance seam: an agent run adds a folder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_adds_a_folder_marked_as_its_own_and_distils_only_when_asked(
    app, auth_headers, tmp_path, worker
) -> None:
    workspace = tmp_path / "ws"
    _inbox(workspace / "inbox")
    headers = await _run_headers("run-ingest", "alpha", workspace)
    # The job is on from the start: distil=false must hold it back anyway.
    await _job_on(app, auth_headers)

    got = await app.post(AGENT_ROUTE, json={"paths": ["inbox"], "distil": False}, headers=headers)
    assert got.status_code == 200, got.text
    body = got.json()
    results = {Path(r["path"]).name: r for r in body["results"]}
    assert sorted(results) == ["a.md", "b.txt", "c.pdf", "d.png", "e.exe", "f.pdf", "z-copy.md"]
    added = {name for name, r in results.items() if r["status"] == "added"}
    assert added == {"a.md", "b.txt", "c.pdf", "d.png"}
    assert results["z-copy.md"]["status"] == "skipped"
    assert results["z-copy.md"]["duplicate_of"] == results["a.md"]["source"]["id"]
    assert results["e.exe"]["status"] == "refused"
    assert ".md" in results["e.exe"]["reason"]  # names what would work
    assert results["f.pdf"]["status"] == "refused"
    assert "10 MiB" in results["f.pdf"]["reason"]
    assert body["counts"] == {"added": 4, "skipped": 1, "refused": 2}
    assert body["distillation"]["requested"] is False
    assert body["distillation"]["queued"] == 0

    entries = [e for e in await _map(app, auth_headers) if e["kind"] == "source"]
    assert len(entries) == 4
    assert {e["added_by"] for e in entries} == {"alpha"}
    assert worker.calls == [] and await _firings() == []
    stored = tmp_path / "knowledge" / "sources"
    meta = json.loads((stored / f"{results['a.md']['source']['id']}.json").read_text("utf-8"))
    assert meta["added_by"] == "alpha"
    assert (stored / f"{results['a.md']['source']['id']}.md").read_bytes() == (
        workspace / "inbox" / "a.md"
    ).read_bytes()

    # The same folder again: everything already there is skipped, nothing new is written.
    again = await app.post(AGENT_ROUTE, json={"paths": ["inbox"], "distil": False}, headers=headers)
    assert again.json()["counts"] == {"added": 0, "skipped": 5, "refused": 2}

    # A second folder with distil=true: one call queues the batch and says what it costs.
    second = workspace / "second"
    second.mkdir()
    (second / "g.md").write_bytes(b"Shipping is free above 50 euros.\n")
    (second / "h.txt").write_bytes(b"Support answers within one working day.\n")
    distilled = await app.post(
        AGENT_ROUTE, json={"paths": [str(second)], "distil": True}, headers=headers
    )
    assert distilled.status_code == 200, distilled.text
    plan = distilled.json()["distillation"]
    assert plan["requested"] is True and plan["queued"] == 2
    assert plan["paid_calls"]["at_least"] == 2
    assert plan["paid_calls"]["at_most"] >= 2
    assert len(worker.calls) == 2
    fired = await _firings()
    assert len(fired) == 2
    queued_ids = {r["source"]["id"] for r in distilled.json()["results"]}
    assert {f["subject"]["source"] for f in fired} == queued_ids


@pytest.mark.asyncio
async def test_distil_must_be_stated_and_a_job_that_cannot_run_refuses_before_writing(
    app, auth_headers, tmp_path
) -> None:
    workspace = tmp_path / "ws"
    _inbox(workspace / "inbox")
    headers = await _run_headers("run-ingest-2", "alpha", workspace)

    unstated = await app.post(AGENT_ROUTE, json={"paths": ["inbox"]}, headers=headers)
    assert unstated.status_code == 422, unstated.text

    refused = await app.post(
        AGENT_ROUTE, json={"paths": ["inbox"], "distil": True}, headers=headers
    )
    assert refused.status_code == 409, refused.text
    assert "distil" in refused.json()["detail"]
    assert not (tmp_path / "knowledge").exists()


@pytest.mark.asyncio
async def test_an_agent_path_outside_its_workspace_and_the_project_is_refused(
    app, auth_headers, tmp_path, tmp_path_factory
) -> None:
    workspace = tmp_path / ".agentweave" / "worktrees" / "alpha"
    workspace.mkdir(parents=True)
    # Dropped in the project directory, not the agent's worktree: the fallback finds it.
    _inbox(tmp_path / "inbox")
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    (elsewhere / "secret.md").write_bytes(b"not for the vault\n")
    headers = await _run_headers("run-ingest-3", "alpha", workspace)

    got = await app.post(
        AGENT_ROUTE,
        json={
            "paths": [
                "inbox/a.md",
                str(elsewhere / "secret.md"),
                "../../../inbox/b.txt",
                "nope.md",
            ],
            "distil": False,
        },
        headers=headers,
    )
    assert got.status_code == 200, got.text
    results = got.json()["results"]
    assert [r["status"] for r in results] == ["added", "refused", "added", "refused"]
    assert "outside" in results[1]["reason"]
    assert "No file or folder" in results[3]["reason"]


@pytest.mark.asyncio
async def test_the_operator_route_adds_any_readable_path_without_added_by(
    app, auth_headers, tmp_path_factory
) -> None:
    elsewhere = tmp_path_factory.mktemp("dump") / "dump"
    _inbox(elsewhere)
    got = await app.post(
        f"{BASE}/vault/paths",
        json={"paths": [str(elsewhere)], "distil": False, "visibility": "private"},
        headers=auth_headers,
    )
    assert got.status_code == 200, got.text
    added = [r["source"] for r in got.json()["results"] if r["status"] == "added"]
    assert len(added) == 4
    assert all(s["visibility"] == "private" and s["added_by"] is None for s in added)

    relative = await app.post(
        f"{BASE}/vault/paths", json={"paths": ["inbox"], "distil": False}, headers=auth_headers
    )
    assert relative.status_code == 200, relative.text
    [result] = relative.json()["results"]
    assert result["status"] == "refused" and "absolute" in result["reason"]


@pytest.mark.asyncio
async def test_a_batch_past_the_limit_is_refused_before_anything_is_written(
    app, auth_headers, tmp_path, monkeypatch
) -> None:
    from hub import vault_intake

    monkeypatch.setattr(vault_intake, "MAX_BATCH_FILES", 3)
    workspace = tmp_path / "ws"
    _inbox(workspace / "inbox")
    headers = await _run_headers("run-ingest-4", "alpha", workspace)
    got = await app.post(AGENT_ROUTE, json={"paths": ["inbox"], "distil": False}, headers=headers)
    assert got.status_code == 400, got.text
    assert "3" in got.json()["detail"]
    assert not (tmp_path / "knowledge").exists()


def test_vault_add_is_on_every_runners_surface() -> None:
    from hub import mcp_server
    from hub.api.v1.agents import _operations
    from hub.copilot_acp import HUB_MCP_TOOLS

    assert "vault_add" in mcp_server._CALLABLE_TOOLS
    assert "vault_add" in HUB_MCP_TOOLS
    assert "vault_add" in {operation.tool for operation in _operations()}


def test_the_tools_restated_values_agree_with_the_vaults() -> None:
    from typing import get_args

    from hub import mcp_server, vault

    assert set(get_args(mcp_server.VaultSourceType)) == set(vault.TYPES) - {vault.DECISION}
    assert set(get_args(mcp_server.VaultVisibility)) == set(vault.VISIBILITIES)
