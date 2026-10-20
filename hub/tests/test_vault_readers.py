"""The vault names which agents read each entry.

`the-vault-names-who-read-an-entry` (Tier 2, migration 0139; F836). The Vault tab's "Used by" could
only say how many reads an entry had, never by whom. An agent's `vault_read` at offset 0 now also
records its agent, taken from the run credential (no request field or header can name one), and both
maps and both entry routes list `readers`: one row per agent, most recent first.
"""

import asyncio
from typing import List

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run

BASE = "/api/v1/projects/proj-test"
AGENT_ACTIONS = "/api/v1/agent-actions"


async def _source(app, auth_headers, name: str) -> dict:
    body = {"name": name, "type": "document", "content": "Line one.\nLine two.\n"}
    created = await app.post(f"{BASE}/vault/sources", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()


async def _run_headers(run_id: str, agent: str) -> dict:
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
    got = await app.get(
        f"{AGENT_ACTIONS}/vault/entries/{entry_id}", params={"offset": offset}, headers=headers
    )
    assert got.status_code == 200, got.text
    return got.json()


def _who(entry: dict) -> List[tuple]:
    return [(r["agent"], r["count"]) for r in entry["readers"]]


@pytest.mark.asyncio
async def test_an_entry_names_the_agents_that_read_it_most_recent_first(app, auth_headers) -> None:
    source = await _source(app, auth_headers, "Release checklist")
    unread = await _source(app, auth_headers, "Never opened")
    builder = await _run_headers("run-builder", "Builder")
    qa = await _run_headers("run-qa", "QA1")

    await _read(app, builder, source["id"])
    await _read(app, builder, source["id"])
    await _read(app, builder, source["id"], offset=10)  # a later page is not a read
    await asyncio.sleep(0.01)
    # A header naming another agent is ignored: identity is the credential's.
    answered = await _read(app, {**qa, "X-Agent-Name": "Builder"}, source["id"])
    assert _who(answered) == [("QA1", 1), ("Builder", 2)]

    mapped = (await app.get(f"{BASE}/vault/map", headers=auth_headers)).json()["entries"]
    by_id = {entry["id"]: entry for entry in mapped}
    assert _who(by_id[source["id"]]) == [("QA1", 1), ("Builder", 2)]
    assert by_id[source["id"]]["fetches"] == 3
    assert by_id[unread["id"]]["readers"] == []
    assert all(r["last_read_at"].endswith("Z") for r in by_id[source["id"]]["readers"])

    one = (await app.get(f"{BASE}/vault/entries/{source['id']}", headers=auth_headers)).json()
    assert _who(one) == [("QA1", 1), ("Builder", 2)]

    agent_map = (await app.get(f"{AGENT_ACTIONS}/vault/map", headers=qa)).json()["entries"]
    assert _who({e["id"]: e for e in agent_map}[source["id"]]) == [("QA1", 1), ("Builder", 2)]


@pytest.mark.asyncio
async def test_the_operators_read_names_no_reader(app, auth_headers) -> None:
    source = await _source(app, auth_headers, "Kickoff call")
    await app.get(f"{BASE}/vault/entries/{source['id']}", headers=auth_headers)
    one = (await app.get(f"{BASE}/vault/entries/{source['id']}", headers=auth_headers)).json()
    assert one["readers"] == [] and one["fetches"] == 0


def test_readers_are_a_hub_table_beside_the_counts() -> None:
    from hub.db.models import VaultReader

    assert VaultReader.__tablename__ == "vault_readers"
    assert {c.name for c in VaultReader.__table__.primary_key.columns} == {
        "project_id",
        "entry_id",
        "agent",
    }
