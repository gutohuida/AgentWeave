"""The vault map is shaped by what agents ask for.

`the-vault-map-is-shaped-by-what-agents-ask-for` (Tier 2, migration 0126). An agent's `vault_read`
at offset 0 is counted per entry; the counts are listed on both maps and both entry routes, and the
map's areas (a source and the facts citing it) are ordered by them. The real agent turn that makes
the reads is the acceptance drive's (`scripts/drive/d1027_access_tuning.py`); here a run credential
calls the agent route directly.
"""

import asyncio
import time
from pathlib import Path
from typing import List

import pytest
from sqlalchemy import select

from hub import vault, vault_access
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, VaultFetch

BASE = "/api/v1/projects/proj-test"
AGENT_ACTIONS = "/api/v1/agent-actions"
LONG = ("A line of the long source that goes on.\n") * 2500  # > one 50,000 character page


async def _source(app, auth_headers, name: str, content: str = "Line one.\nLine two.\n") -> dict:
    body = {"name": name, "type": "transcript", "content": content}
    created = await app.post(f"{BASE}/vault/sources", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    await asyncio.sleep(0.01)  # created_at orders the map; keep two uploads apart
    return created.json()


async def _private_root(app, auth_headers) -> Path:
    settings = await app.get(f"{BASE}/vault/settings", headers=auth_headers)
    return Path(settings.json()["effective_private_location"])


async def _fact(app, auth_headers, tmp_path, source: dict, claim: str) -> str:
    meta = vault.add_fact(
        tmp_path,
        await _private_root(app, auth_headers),
        claim=claim,
        citations=[{"source": source["id"], "quote": "Line one.", "line_start": 1, "line_end": 1}],
        visibility=source["visibility"],
        made_by={"job": "vault-distillation", "model": "claude-haiku-4-5-20251001"},
    )
    await asyncio.sleep(0.01)
    return meta["id"]


async def _run_headers(run_id: str = "run-access", agent: str = "reader") -> dict:
    from hub.agent_auth import hash_run_token

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


async def _read(app, headers, entry_id: str, offset: int = 0):
    return await app.get(
        f"{AGENT_ACTIONS}/vault/entries/{entry_id}", params={"offset": offset}, headers=headers
    )


async def _map(app, auth_headers) -> List[dict]:
    got = await app.get(f"{BASE}/vault/map", headers=auth_headers)
    assert got.status_code == 200, got.text
    return got.json()["entries"]


def _ids(entries: List[dict]) -> List[str]:
    return [e["id"] for e in entries]


async def _stored() -> dict:
    async with async_session_factory() as db:
        rows = (await db.execute(select(VaultFetch))).scalars().all()
        return {row.entry_id: row.count for row in rows}


# ---------------------------------------------------------------------------
# count-fetch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_read_at_offset_zero_counts_once_and_its_next_page_does_not(
    app, auth_headers
) -> None:
    source = await _source(app, auth_headers, "Long", LONG)
    headers = await _run_headers()

    first = await _read(app, headers, source["id"])
    assert first.status_code == 200, first.text
    assert first.json()["next_offset"] is not None
    assert await _stored() == {source["id"]: 1}

    page = await _read(app, headers, source["id"], offset=first.json()["next_offset"])
    assert page.status_code == 200, page.text
    assert await _stored() == {source["id"]: 1}


@pytest.mark.asyncio
async def test_a_404_the_operators_read_and_both_maps_do_not_count(app, auth_headers) -> None:
    source = await _source(app, auth_headers, "Quiet")
    headers = await _run_headers()

    assert (await _read(app, headers, "src-000000000000")).status_code == 404
    mine = await app.get(f"{BASE}/vault/entries/{source['id']}", headers=auth_headers)
    assert mine.status_code == 200
    await _map(app, auth_headers)
    assert (await app.get(f"{AGENT_ACTIONS}/vault/map", headers=headers)).status_code == 200
    assert await _stored() == {}


@pytest.mark.asyncio
async def test_two_reads_at_the_same_moment_are_both_counted(app, auth_headers) -> None:
    source = await _source(app, auth_headers, "Busy")
    headers = await _run_headers()

    answers = await asyncio.gather(*[_read(app, headers, source["id"]) for _ in range(2)])

    assert [a.status_code for a in answers] == [200, 200]
    assert await _stored() == {source["id"]: 2}


@pytest.mark.asyncio
async def test_a_count_that_cannot_be_recorded_does_not_fail_the_read(
    app, auth_headers, monkeypatch
) -> None:
    source = await _source(app, auth_headers, "Unlucky")
    headers = await _run_headers()

    async def boom(*args, **kwargs):
        raise RuntimeError("the counter is down")

    monkeypatch.setattr(vault_access, "record_fetch", boom)

    got = await _read(app, headers, source["id"])

    assert got.status_code == 200, got.text
    assert got.json()["content"].startswith("Line one.")
    assert await _stored() == {}


@pytest.mark.asyncio
async def test_a_fact_read_is_counted_too(app, auth_headers, tmp_path) -> None:
    source = await _source(app, auth_headers, "Cited")
    fact = await _fact(app, auth_headers, tmp_path, source, "Line one is true.")
    headers = await _run_headers()

    assert (await _read(app, headers, fact)).status_code == 200
    assert await _stored() == {fact: 1}


# ---------------------------------------------------------------------------
# counts-listed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_counts_are_listed_alike_on_both_maps_and_both_entry_routes(
    app, auth_headers, tmp_path
) -> None:
    read = await _source(app, auth_headers, "Read twice")
    other = await _source(app, auth_headers, "Other")
    fact = await _fact(app, auth_headers, tmp_path, other, "X.")
    headers = await _run_headers()
    for _ in range(2):
        await _read(app, headers, read["id"])

    operator = {e["id"]: e for e in await _map(app, auth_headers)}
    agents = (await app.get(f"{AGENT_ACTIONS}/vault/map", headers=headers)).json()["entries"]
    agents = {e["id"]: e for e in agents}

    assert operator[read["id"]]["fetches"] == 2
    time.strptime(operator[read["id"]]["last_fetched_at"][:19], "%Y-%m-%dT%H:%M:%S")
    assert operator[fact]["fetches"] == 0 and operator[fact]["last_fetched_at"] is None
    for entry_id, entry in operator.items():
        assert (agents[entry_id]["fetches"], agents[entry_id]["last_fetched_at"]) == (
            entry["fetches"],
            entry["last_fetched_at"],
        )

    by_operator = await app.get(f"{BASE}/vault/entries/{read['id']}", headers=auth_headers)
    assert by_operator.json()["fetches"] == 2
    assert by_operator.json()["last_fetched_at"] == operator[read["id"]]["last_fetched_at"]
    by_agent = await _read(app, headers, read["id"])
    assert by_agent.json()["fetches"] == 3  # its own read is in the count it is told
    cold = await app.get(f"{BASE}/vault/entries/{fact}", headers=auth_headers)
    assert cold.json()["fetches"] == 0 and cold.json()["last_fetched_at"] is None


# ---------------------------------------------------------------------------
# map-order
# ---------------------------------------------------------------------------


async def _three_areas(app, auth_headers, tmp_path):
    """Sources A, B, C oldest to newest; A1 (older) and A2 cite A, B1 cites B."""
    a = await _source(app, auth_headers, "A")
    b = await _source(app, auth_headers, "B")
    c = await _source(app, auth_headers, "C")
    a1 = await _fact(app, auth_headers, tmp_path, a, "A one.")
    a2 = await _fact(app, auth_headers, tmp_path, a, "A two.")
    b1 = await _fact(app, auth_headers, tmp_path, b, "B one.")
    return a["id"], b["id"], c["id"], a1, a2, b1


@pytest.mark.asyncio
async def test_with_no_reads_the_map_is_the_newest_first_map(app, auth_headers, tmp_path) -> None:
    a, b, c, a1, a2, b1 = await _three_areas(app, auth_headers, tmp_path)
    assert _ids(await _map(app, auth_headers)) == [c, b, b1, a, a2, a1]


@pytest.mark.asyncio
async def test_the_most_read_area_leads_its_source_first_then_its_most_read_facts(
    app, auth_headers, tmp_path
) -> None:
    a, b, c, a1, a2, b1 = await _three_areas(app, auth_headers, tmp_path)
    headers = await _run_headers()
    for entry_id in (a1, a1, b):
        await _read(app, headers, entry_id)

    entries = await _map(app, auth_headers)

    assert _ids(entries) == [a, a1, a2, b, b1, c]
    assert {e["id"]: e["fetches"] for e in entries} == {a: 0, a1: 2, a2: 0, b: 1, b1: 0, c: 0}
    agents = (await app.get(f"{AGENT_ACTIONS}/vault/map", headers=headers)).json()["entries"]
    assert agents == entries


@pytest.mark.asyncio
async def test_facts_in_an_area_are_ordered_by_reads_then_newest(
    app, auth_headers, tmp_path
) -> None:
    a, b, c, a1, a2, b1 = await _three_areas(app, auth_headers, tmp_path)
    headers = await _run_headers()
    await _read(app, headers, a1)
    assert _ids(await _map(app, auth_headers))[:3] == [a, a1, a2]
    await _read(app, headers, a2)
    await _read(app, headers, a2)
    assert _ids(await _map(app, auth_headers))[:3] == [a, a2, a1]


@pytest.mark.asyncio
async def test_a_deleted_entrys_count_is_absent_from_the_map(app, auth_headers, tmp_path) -> None:
    a, b, c, a1, a2, b1 = await _three_areas(app, auth_headers, tmp_path)
    headers = await _run_headers()
    for _ in range(3):
        await _read(app, headers, c)
    async with async_session_factory() as db:
        await vault_access.record_fetch(db, "proj-test", "src-deadbeef0000")

    entries = await _map(app, auth_headers)

    assert _ids(entries) == [c, b, b1, a, a2, a1]
    assert "src-deadbeef0000" not in _ids(entries)


def test_areas_tie_on_reads_by_their_source_newest_first_and_orphans_stay_last() -> None:
    def source(i: str, created: str) -> dict:
        return {"id": i, "kind": "source", "created_at": created}

    def fact(i: str, created: str, sources: list) -> dict:
        return {"id": i, "kind": "fact", "created_at": created, "sources": sources}

    entries = [
        source("src-new", "2026-03-01"),
        fact("fct-orphan", "2026-03-05", ["src-gone"]),
        source("src-old", "2026-01-01"),
        fact("fct-old1", "2026-01-02", ["src-old"]),
    ]
    counts = {"fct-orphan": (9, "2026-03-06"), "fct-old1": (1, "2026-03-06")}

    shaped = vault_access.shape(entries, counts)

    assert [e["id"] for e in shaped] == ["src-old", "fct-old1", "src-new", "fct-orphan"]
    assert shaped[1]["fetches"] == 1 and shaped[2]["fetches"] == 0
    assert shaped[3]["fetches"] == 9  # an orphan area is last whatever its reads


# ---------------------------------------------------------------------------
# agents-told
# ---------------------------------------------------------------------------


def test_the_tool_description_and_the_instruction_line_name_the_ordering_and_fetches() -> None:
    from hub import mcp_server
    from hub.api.v1.agents import _operations

    tool = " ".join(mcp_server.vault_map.__doc__.split())
    line = " ".join(next(op.text for op in _operations() if op.tool == "vault_map").split())
    for text in (tool, line):
        assert "fetches" in text
        assert "how often agents have read" in text
        assert "newest first" in text  # as the tie-break, after the reads
    assert "what the business has told this project, newest first." not in tool


def test_the_counts_are_stored_in_a_hub_table_and_nowhere_under_the_vault() -> None:
    assert VaultFetch.__tablename__ == "vault_fetches"
    assert [c.name for c in VaultFetch.__table__.primary_key.columns] == ["project_id", "entry_id"]
    assert {c.name for c in VaultFetch.__table__.columns} == {
        "project_id",
        "entry_id",
        "count",
        "last_fetched_at",
    }
