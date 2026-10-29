# ruff: noqa: F811
"""The operator archives and restores a vault source: it and its facts leave the map, the turn's
vault line and both checks, stay readable by id, and come back on restore.

`vault-sources-can-be-edited-replaced-and-archived` (Tier 2), the operator's half of ac-archive,
ac-out-of-checks, ac-archived-read and ac-restore (the agent tools' half is with those tools).

Client reach: the archive routes are called by hub/ui/src/api/vault.ts (clientless-route ratchet, 19 at its ceiling).
"""

import json
from pathlib import Path

import pytest

from hub import vault, vault_spec_check

from ._spec_versions import content_version  # noqa: F401
from .test_spec_documents_api import PATH, _create, run_headers  # noqa: F401
from .test_spec_journey_briefing import _place
from .test_vault_spec_check import (  # noqa: F401, F811  (worker is a fixture)
    PROJECT,
    QUOTE,
    _check_now,
    _enable,
    _fact,
    _requirement,
    _saved,
    _source,
    worker,
)

BASE = "/api/v1/projects/proj-test"


async def _map_ids(app, auth_headers) -> list:
    got = await app.get(f"{BASE}/vault/map", headers=auth_headers)
    assert got.status_code == 200, got.text
    return [e["id"] for e in got.json()["entries"]]


async def _archive(app, auth_headers, source_id, verb="archive"):
    return await app.post(f"{BASE}/vault/sources/{source_id}/{verb}", headers=auth_headers)


async def _vault(app, auth_headers, tmp_path):
    """S1 and S2, a fact citing only S1, and a fact citing both."""
    s1 = await _source(app, auth_headers, "January call", "2026-01-10")
    s2 = await _source(app, auth_headers, "March call", "2026-03-10")
    only = await _fact(app, auth_headers, tmp_path, s1, "Refunds up to 300 need none.")
    both = vault.add_fact(
        tmp_path,
        Path(
            (await app.get(f"{BASE}/vault/settings", headers=auth_headers)).json()[
                "effective_private_location"
            ]
        ),
        claim="Refunds are reviewed.",
        citations=[
            {"source": s1["id"], "quote": QUOTE, "line_start": 2, "line_end": 2},
            {"source": s2["id"], "quote": QUOTE, "line_start": 2, "line_end": 2},
        ],
        visibility="tracked",
        made_by={"job": "vault-distillation", "model": "m"},
    )["id"]
    return s1, s2, only, both


def _turn_lines(tmp_path, private) -> list:
    return vault.render_turn_index(vault.build_map(tmp_path, private))


@pytest.mark.asyncio
async def test_ac_archive(app, auth_headers, tmp_path) -> None:
    s1, s2, only, both = await _vault(app, auth_headers, tmp_path)
    private = vault.default_private_location("proj-test")
    assert "4 entries" in _turn_lines(tmp_path, private)[1]

    archived = await _archive(app, auth_headers, s1["id"])
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived"] is True

    ids = await _map_ids(app, auth_headers)
    assert s1["id"] not in ids and only not in ids
    assert s2["id"] in ids and both in ids
    assert "2 entries" in _turn_lines(tmp_path, private)[1]

    # Archiving again is refused; nothing else changes.
    assert (await _archive(app, auth_headers, s1["id"])).status_code == 409

    await _archive(app, auth_headers, s2["id"])
    assert await _map_ids(app, auth_headers) == []
    assert _turn_lines(tmp_path, private) == []

    listed = await app.get(f"{BASE}/vault/archived", headers=auth_headers)
    assert {s["id"] for s in listed.json()["sources"]} == {s1["id"], s2["id"]}


@pytest.mark.asyncio
async def test_ac_archived_read(app, auth_headers, tmp_path) -> None:
    s1, _s2, only, _both = await _vault(app, auth_headers, tmp_path)
    await _archive(app, auth_headers, s1["id"])
    for entry_id in (s1["id"], only):
        got = await app.get(f"{BASE}/vault/entries/{entry_id}", headers=auth_headers)
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["archived"] is True
        assert "ARCHIVED" in body["content"]


@pytest.mark.asyncio
async def test_ac_restore(app, auth_headers, tmp_path) -> None:
    s1, _s2, only, _both = await _vault(app, auth_headers, tmp_path)
    private = vault.default_private_location("proj-test")
    before = await _map_ids(app, auth_headers)
    compared = [f["id"] for f in vault.dated_facts(tmp_path, private, current_only=True)]

    await _archive(app, auth_headers, s1["id"])
    assert (await _archive(app, auth_headers, s1["id"], "restore")).status_code == 200
    assert (await _archive(app, auth_headers, s1["id"], "restore")).status_code == 409

    assert await _map_ids(app, auth_headers) == before
    assert "4 entries" in _turn_lines(tmp_path, private)[1]
    assert [f["id"] for f in vault.dated_facts(tmp_path, private, current_only=True)] == compared
    got = await app.get(f"{BASE}/vault/entries/{only}", headers=auth_headers)
    assert got.json()["archived"] is False and "ARCHIVED" not in got.json()["content"]

    entry = (await app.get(f"{BASE}/vault/entries/{s1['id']}", headers=auth_headers)).json()
    assert [c["action"] for c in entry["changes"]] == ["archive", "restore"]
    assert all(c["by"] == {"kind": "operator"} for c in entry["changes"])


@pytest.mark.asyncio
async def test_a_private_sources_archived_state_is_in_its_stub(app, auth_headers, tmp_path) -> None:
    body = {"name": "Secret", "type": "note", "content": "x\n", "visibility": "private"}
    made = (await app.post(f"{BASE}/vault/sources", json=body, headers=auth_headers)).json()
    await _archive(app, auth_headers, made["id"])
    stub = json.loads(
        (tmp_path / "knowledge" / "sources" / f"{made['id']}.json").read_text(encoding="utf-8")
    )
    assert isinstance(stub["archived_at"], str) and "content" not in stub
    assert made["id"] not in await _map_ids(app, auth_headers)


@pytest.mark.asyncio
async def test_ac_out_of_checks(
    app, auth_headers, run_headers, worker, tmp_path
) -> None:  # noqa: F811
    s1 = await _source(app, auth_headers, "January call", "2026-01-10")
    s2 = await _source(app, auth_headers, "March call", "2026-03-10")
    old = await _fact(app, auth_headers, tmp_path, s1, "Old archived claim about refunds.")
    live = await _fact(app, auth_headers, tmp_path, s2, "Live claim about refunds.")
    private = vault.default_private_location("proj-test")
    await _archive(app, auth_headers, s1["id"])

    # The contradiction check's compared set (distillation reads dated_facts) leaves it out.
    assert [f["id"] for f in vault.dated_facts(tmp_path, private, current_only=True)] == [live]

    # So does the spec-vault-check's prompt.
    await _enable(app, auth_headers)
    await _create(app, auth_headers)
    await _saved(app, run_headers, _requirement("r1", "Refunds up to 300 euros need no approval."))
    await _place(step="build", size="large")
    fake = worker([])
    sent = await _check_now(app, auth_headers)
    assert sent.status_code == 202, sent.text
    for _ in range(100):
        if fake.calls:
            break
        import asyncio

        await asyncio.sleep(0.02)
    assert fake.calls, "the vault check never fired"
    prompt = fake.calls[0]["prompt"]
    assert live in prompt and "Live claim about refunds." in prompt
    assert old not in prompt and "Old archived claim" not in prompt
    assert vault_spec_check is not None and PROJECT
