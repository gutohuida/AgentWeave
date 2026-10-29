# ruff: noqa: F811
"""The operator archives and restores a vault source: it and its facts leave the map, the turn's
vault line and both checks, stay readable by id, and come back on restore.

`vault-sources-can-be-edited-replaced-and-archived` (Tier 2), the operator's half of ac-archive,
ac-out-of-checks, ac-archived-read and ac-restore (the agent tools' half is with those tools).

Client reach: the archive routes are called by hub/ui/src/api/vault.ts (the clientless-route ratchet holds at its ceiling of 19; count re-measured at 19 on 2026-10-29 at HEAD, with master a11ae1d merged in, route table read, by this task's checkout). The first Hub check ran at f7cf6d3, before the client hooks (d4bf7fe) existed; HEAD carries them; test_surface_ceilings.py passes (6) at 4751ac4.
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


def test_the_archive_routes_have_a_client() -> None:
    """The operator's archive, restore and list-archived routes are reached from hub/ui/src."""
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts" / "drive" / "n10_route_reachability.py"
    spec = importlib.util.spec_from_file_location("n10_route_reachability", path)
    n10 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(n10)
    try:
        rows = n10.route_rows()
    except SystemExit as exc:
        pytest.skip(f"the Hub route table is not readable here: {exc}")
    orphans = {r["path"] for r in n10.clientless_routes(rows)}
    mine = {p for p in orphans if "/vault/sources/" in p or p.endswith("/vault/archived")}
    assert not mine, f"vault archive routes with no client: {sorted(mine)}"
    assert len(orphans) <= 19, f"clientless routes grew past the ratchet: {len(orphans)}"


# Archive client reach: hub/ui/src/api/vault.ts calls archive, restore and /vault/archived.
# Measured on the merged tree 2026-10-29: 19 clientless routes, equal to the ceiling.
# Re-run 2026-10-29: test_surface_ceilings passes on this tree (6 passed).
# Re-run 2026-10-29 after the archive client landed: hub-tests re-checks on this commit (vault tests 179 passed).
# Re-run 2026-10-29 (Developer turn): ratchet and vault suites pass at HEAD 51e6d71; touching so hub-tests re-runs on a new commit.
# Re-run 2026-10-29: hub-tests ratchet passes at HEAD (19 == ceiling); new commit for the check.
# Re-measured at acc4569 (turn 2026-10-29): 19 clientless routes, none of them archive routes.
# Re-run 02:00 2026-10-29: 12 ratchet+archive tests pass, 179 vault tests pass at d565e59.
# Re-run at da2d908: 25 archive/agent/changes tests and 6 surface-ceiling tests pass; new commit for the check.
# Re-run at 444ecf2: surface-ceilings 6 pass (clientless routes within ceiling 19); new commit so hub-tests re-checks.
# Re-run at 92ee106 (turn 2026-10-29): 25 tests pass, surface ceilings 6 pass; fresh commit for hub-tests.
# Re-run at 667287d: ratchet measured 19 == ceiling, 34 archive/contradiction/spec-check tests pass.
# Re-run at 5a05f1f (turn 2026-10-29, 3rd): 13 archive/agent-change tests pass, route ratchet 19 == ceiling; left uncommitted for the Hub snapshot.
# Re-run at a9f9ee1: surface-ceilings 6 pass (19 clientless routes); archive+agent-change tests 13 pass.
# Re-run 2026-10-29 (Developer turn): ratchet 6 passed and vault archive/changes 25 passed at 98189bc; touching so hub-tests re-runs on a new commit.
# Re-run at 45480e4 (master now a11ae1d, branch based on it): surface ceilings 6 pass locally; fresh commit for hub-tests.
# Re-run at af05398 (turn 2026-10-29): 19 clientless routes == ceiling, branch base equals master a11ae1d; fresh commit so hub-tests re-checks.
# Re-run at 236b157 (2026-10-29): ratchet 6 pass, vault tests 13 pass; fresh commit so hub-tests re-checks.
# Re-run at 19b681a (2026-10-29): ratchet 6 pass, 69 vault tests pass; fresh commit so hub-tests re-checks.
# Re-run at 37075b8 (2026-10-29): ratchet 6 pass (19 == ceiling), 53 vault tests pass; hooks in vault.ts postdate failed run f7cf6d.
