"""A profile's pool of runners (`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool`,
task pool-model): the pool's shape (FR-1), the migration that seeds it (FR-2), editing it through the
agents API (FR-3) and the legacy binding that sets its default (FR-4).

Every test here reads the pool back through `GET /agents`, the route the settings page and the
acceptance drive read, and asserts `runner_id` beside it: the two agreeing is the contract.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from hub.api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from tests.test_migrations import (
    _create_all_at,
    _downgrade_to,
    _insert_agent,
    _run,
    _upgrade_to,
)

BASE = "/api/v1/projects/proj-test"


async def _runner(app, auth_headers, name: str, model: str, cli: str = "claude") -> str:
    created = await app.post(
        f"{BASE}/runners", json={"name": name, "cli": cli, "model": model}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _agent(app, auth_headers, name: str) -> dict:
    roster = (await app.get(f"{BASE}/agents?lifecycle=all", headers=auth_headers)).json()
    return next(a for a in roster if a["name"] == name)


def _shape(pool: list) -> list:
    return [(e["runner_id"], e["effort"], e["default"]) for e in pool]


async def _set_pool(app, auth_headers, name: str, entries: list):
    return await app.patch(f"{BASE}/agents/{name}", json={"pool": entries}, headers=auth_headers)


@pytest.fixture
async def haiku_sonnet(app, auth_headers, add_agent):
    """`builder` bound to Haiku the legacy way, then given Sonnet beside it: Haiku the default."""
    haiku = await _runner(app, auth_headers, "Claude Haiku", "claude-haiku-5-5")
    sonnet = await _runner(app, auth_headers, "Claude Sonnet", "claude-sonnet-5-5")
    await add_agent("builder")
    bound = await app.patch(
        f"{BASE}/agents/builder", json={"runner_id": haiku}, headers=auth_headers
    )
    assert bound.status_code == 200, bound.text
    resp = await _set_pool(
        app,
        auth_headers,
        "builder",
        [{"runner_id": haiku, "default": True}, {"runner_id": sonnet}],
    )
    assert resp.status_code == 200, resp.text
    return haiku, sonnet


# ---------------------------------------------------------------- FR-1: the pool's shape


@pytest.mark.asyncio
async def test_a_bound_runner_is_a_one_entry_pool_marked_default(app, auth_headers, add_agent):
    runner = await _runner(app, auth_headers, "Claude Haiku", "claude-haiku-5-5")
    await add_agent("solo")
    resp = await app.patch(f"{BASE}/agents/solo", json={"runner_id": runner}, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    agent = await _agent(app, auth_headers, "solo")
    assert agent["runner_id"] == runner
    assert agent["pool"] == [
        {
            "id": agent["pool"][0]["id"],
            "runner_id": runner,
            "runner_name": "Claude Haiku",
            "cli": "claude",
            "model": "claude-haiku-5-5",
            "effort": None,
            "default": True,
        }
    ]
    assert resp.json()["pool"] == agent["pool"]


@pytest.mark.asyncio
async def test_an_agent_with_no_runner_has_an_empty_pool(app, auth_headers, add_agent):
    await add_agent("unbound")
    agent = await _agent(app, auth_headers, "unbound")
    assert agent["pool"] == [] and agent["runner_id"] is None


@pytest.mark.asyncio
async def test_pool_shape_an_emptied_pool_is_refused_a_start_as_no_runner_is(
    app, auth_headers, add_agent, haiku_sonnet
):
    """Criterion pool-shape: a non-empty pool has exactly one default, and an emptied one is
    refused a start with the very refusal an agent that never had a runner gets."""
    agent = await _agent(app, auth_headers, "builder")
    assert [e["default"] for e in agent["pool"]].count(True) == 1

    resp = await _set_pool(app, auth_headers, "builder", [])
    assert resp.status_code == 200, resp.text
    agent = await _agent(app, auth_headers, "builder")
    assert agent["pool"] == [] and agent["runner_id"] is None

    await add_agent("never-bound")

    async def _refusal(name):
        async with async_session_factory() as session:
            conversation = new_conversation(project_id="proj-test", agent=name, origin="operator")
            session.add(conversation)
            await session.commit()
            with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
                with pytest.raises(TriggerAgentError) as caught:
                    await trigger_agent_directly(
                        project_id="proj-test",
                        agent=name,
                        message="go",
                        conversation_id=conversation.id,
                        session=session,
                    )
        return caught.value

    emptied, never = await _refusal("builder"), await _refusal("never-bound")
    assert emptied.status_code == never.status_code == 409
    assert str(emptied).replace("builder", "X") == str(never).replace("never-bound", "X")
    assert "No runner is bound" in str(emptied)


@pytest.mark.asyncio
async def test_two_defaults_or_none_in_a_first_pool_is_refused(app, auth_headers, add_agent):
    haiku = await _runner(app, auth_headers, "Claude Haiku", "claude-haiku-5-5")
    sonnet = await _runner(app, auth_headers, "Claude Sonnet", "claude-sonnet-5-5")
    await add_agent("fresh")

    both = await _set_pool(
        app,
        auth_headers,
        "fresh",
        [{"runner_id": haiku, "default": True}, {"runner_id": sonnet, "default": True}],
    )
    assert both.status_code == 400
    assert "exactly one default" in both.json()["detail"]

    neither = await _set_pool(
        app, auth_headers, "fresh", [{"runner_id": haiku}, {"runner_id": sonnet}]
    )
    assert neither.status_code == 400
    assert "default" in neither.json()["detail"]
    assert (await _agent(app, auth_headers, "fresh"))["pool"] == []

    # A first pool of one entry needs no flag: its only entry is the default.
    one = await _set_pool(app, auth_headers, "fresh", [{"runner_id": sonnet}])
    assert one.status_code == 200, one.text
    agent = await _agent(app, auth_headers, "fresh")
    assert _shape(agent["pool"]) == [(sonnet, None, True)] and agent["runner_id"] == sonnet


# ---------------------------------------------------------------- FR-3: editing the pool


@pytest.mark.asyncio
async def test_pool_edit_refusals_an_unoffered_effort_names_the_effort_and_model(
    app, auth_headers, haiku_sonnet
):
    """Criterion pool-edit-refusals, first half."""
    haiku, sonnet = haiku_sonnet
    opus = await _runner(app, auth_headers, "Claude Opus", "claude-opus-5-5")
    before = await _agent(app, auth_headers, "builder")

    resp = await _set_pool(
        app,
        auth_headers,
        "builder",
        [*before["pool"], {"runner_id": opus, "effort": "ultra"}],
    )

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "'ultra'" in detail and "Opus 5.5" in detail
    after = await _agent(app, auth_headers, "builder")
    assert after["pool"] == before["pool"] and after["runner_id"] == haiku


@pytest.mark.asyncio
async def test_pool_edit_refusals_removing_the_default_without_another_names_it(
    app, auth_headers, haiku_sonnet
):
    """Criterion pool-edit-refusals, second half."""
    haiku, sonnet = haiku_sonnet
    before = await _agent(app, auth_headers, "builder")

    resp = await _set_pool(app, auth_headers, "builder", [{"runner_id": sonnet}])

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "Haiku 5.5" in detail and "default" in detail
    after = await _agent(app, auth_headers, "builder")
    assert after["pool"] == before["pool"] and after["runner_id"] == haiku

    # Naming another default in the same change is what makes it allowed.
    ok = await _set_pool(app, auth_headers, "builder", [{"runner_id": sonnet, "default": True}])
    assert ok.status_code == 200, ok.text
    after = await _agent(app, auth_headers, "builder")
    assert _shape(after["pool"]) == [(sonnet, None, True)] and after["runner_id"] == sonnet


@pytest.mark.asyncio
async def test_an_unknown_runner_or_a_listed_twice_entry_is_refused(
    app, auth_headers, haiku_sonnet
):
    haiku, sonnet = haiku_sonnet
    before = await _agent(app, auth_headers, "builder")

    missing = await _set_pool(
        app, auth_headers, "builder", [*before["pool"], {"runner_id": "runner-nope"}]
    )
    assert missing.status_code == 404 and "runner-nope" in missing.json()["detail"]

    twice = await _set_pool(
        app, auth_headers, "builder", [*before["pool"], {"runner_id": sonnet, "effort": None}]
    )
    assert twice.status_code == 400 and "twice" in twice.json()["detail"]

    mixed = await app.patch(
        f"{BASE}/agents/builder",
        json={"pool": before["pool"], "runner_id": sonnet},
        headers=auth_headers,
    )
    assert mixed.status_code == 400
    assert (await _agent(app, auth_headers, "builder"))["pool"] == before["pool"]


@pytest.mark.asyncio
async def test_pool_edit_add_opus_high_make_it_default_then_remove_the_old_entry(
    app, auth_headers, add_agent
):
    """Criterion pool-edit-ui, the API calls the settings page makes: add Claude Opus high, make it
    the default, remove the old entry; GET agent shows the new pool and runner_id names Opus."""
    haiku = await _runner(app, auth_headers, "Claude Haiku", "claude-haiku-5-5")
    opus = await _runner(app, auth_headers, "Claude Opus", "claude-opus-5-5")
    await add_agent("editor")
    await app.patch(f"{BASE}/agents/editor", json={"runner_id": haiku}, headers=auth_headers)
    start = (await _agent(app, auth_headers, "editor"))["pool"]

    added = await _set_pool(
        app, auth_headers, "editor", [*start, {"runner_id": opus, "effort": "high"}]
    )
    assert added.status_code == 200, added.text
    pool = added.json()["pool"]
    assert _shape(pool) == [(haiku, None, True), (opus, "high", False)]

    made_default = await _set_pool(
        app, auth_headers, "editor", [{**e, "default": e["runner_id"] == opus} for e in pool]
    )
    assert made_default.status_code == 200, made_default.text
    assert made_default.json()["runner_id"] == opus

    removed = await _set_pool(
        app, auth_headers, "editor", [e for e in made_default.json()["pool"] if e["default"]]
    )
    assert removed.status_code == 200, removed.text

    agent = await _agent(app, auth_headers, "editor")
    assert _shape(agent["pool"]) == [(opus, "high", True)]
    assert agent["runner_id"] == opus
    # An entry kept across edits keeps its id, so the page's keys stay stable.
    assert agent["pool"][0]["id"] == pool[1]["id"]


# ---------------------------------------------------------------- FR-4: the legacy binding


@pytest.mark.asyncio
async def test_legacy_bind_sets_default_provider_and_model_adds_opus_as_default(
    app, auth_headers, haiku_sonnet
):
    """Criterion legacy-bind-sets-default."""
    haiku, sonnet = haiku_sonnet

    resp = await app.patch(
        f"{BASE}/agents/builder",
        json={"provider": "claude", "model": "opus"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    agent = await _agent(app, auth_headers, "builder")
    opus = agent["runner_id"]
    assert opus not in (haiku, sonnet)
    runner = (await app.get(f"{BASE}/runners/{opus}", headers=auth_headers)).json()
    assert runner["cli"] == "claude" and runner["model"] in ("opus", "claude-opus-5-5")
    assert _shape(agent["pool"]) == [
        (haiku, None, False),
        (sonnet, None, False),
        (opus, None, True),
    ]


@pytest.mark.asyncio
async def test_legacy_runner_id_bind_makes_an_entry_already_there_the_default(
    app, auth_headers, haiku_sonnet
):
    haiku, sonnet = haiku_sonnet

    resp = await app.patch(
        f"{BASE}/agents/builder", json={"runner_id": sonnet}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    agent = await _agent(app, auth_headers, "builder")
    assert _shape(agent["pool"]) == [(haiku, None, False), (sonnet, None, True)]
    assert agent["runner_id"] == sonnet

    # Re-sending the bound runner changes nothing.
    again = await app.patch(
        f"{BASE}/agents/builder", json={"runner_id": sonnet}, headers=auth_headers
    )
    assert again.status_code == 200
    assert (await _agent(app, auth_headers, "builder"))["pool"] == agent["pool"]

    # Unbinding empties the pool: an agent with no runner has none.
    cleared = await app.patch(
        f"{BASE}/agents/builder", json={"runner_id": None}, headers=auth_headers
    )
    assert cleared.status_code == 200
    agent = await _agent(app, auth_headers, "builder")
    assert agent["pool"] == [] and agent["runner_id"] is None


@pytest.mark.asyncio
async def test_a_runner_a_pool_holds_cannot_be_deleted(app, auth_headers, haiku_sonnet):
    """A non-default entry binds its runner to the agent as the default always has."""
    haiku, sonnet = haiku_sonnet
    resp = await app.delete(f"{BASE}/runners/{sonnet}", headers=auth_headers)
    assert resp.status_code == 409, resp.text
    assert "builder" in resp.json()["detail"]
    agent = await _agent(app, auth_headers, "builder")
    assert _shape(agent["pool"]) == [(haiku, None, True), (sonnet, None, False)]


@pytest.mark.asyncio
async def test_an_archived_agents_pool_loses_a_deleted_runner_and_keeps_a_default(
    app, auth_headers, haiku_sonnet
):
    haiku, sonnet = haiku_sonnet
    archived = await app.post(f"{BASE}/agents/builder/archive", headers=auth_headers)
    assert archived.status_code == 200, archived.text

    resp = await app.delete(f"{BASE}/runners/{haiku}", headers=auth_headers)
    assert resp.status_code == 204, resp.text
    agent = await _agent(app, auth_headers, "builder")
    assert _shape(agent["pool"]) == [(sonnet, None, True)] and agent["runner_id"] == sonnet


# ---------------------------------------------------------------- FR-2: the migration's seed


def _seed_agents(db_file) -> None:
    with sqlite3.connect(db_file) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        (
            conn.execute(
                "INSERT INTO projects (id, name, created_at) VALUES ('proj-m', 'm', '2026-11-19')"
            )
            if not conn.execute("SELECT 1 FROM projects WHERE id='proj-m'").fetchone()
            else None
        )
        conn.execute(
            "INSERT INTO runners (id, project_id, name, cli, model, created_at, updated_at) "
            "VALUES ('runner-h', 'proj-m', 'Haiku', 'claude', 'claude-haiku-5-5', "
            "'2026-11-19', '2026-11-19')"
        )
        _insert_agent(conn, "agent-bound", "proj-m", "bound")
        _insert_agent(conn, "agent-free", "proj-m", "free")
        conn.execute("UPDATE agents SET runner_id = 'runner-h' WHERE id = 'agent-bound'")
        conn.commit()


def _pool_rows(db_file) -> list:
    with sqlite3.connect(db_file) as conn:
        return conn.execute(
            "SELECT agent_id, project_id, runner_id, effort, is_default FROM agent_pool_entries "
            "ORDER BY agent_id"
        ).fetchall()


def _at_0185_without_the_table(tmp_path, name):
    db_file = tmp_path / name
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0186')")
        conn.commit()
    _downgrade_to(db_url, "0185")
    return db_file, db_url


def test_migration_seeds_pools_one_default_entry_per_bound_agent(tmp_path) -> None:
    """Criterion migration-seeds-pools: every agent with a runner gets one entry on it, no effort,
    default; an agent with no runner gets none. The downgrade drops the table and nothing else."""
    db_file, db_url = _at_0185_without_the_table(tmp_path, "seed.db")
    with sqlite3.connect(db_file) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "agent_pool_entries" not in tables
    _seed_agents(db_file)

    _upgrade_to(db_url, "0186")

    assert _pool_rows(db_file) == [("agent-bound", "proj-m", "runner-h", None, 1)]
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT runner_id FROM agents WHERE id='agent-bound'").fetchone() == (
            "runner-h",
        )

    # Idempotent: a second pass seeds nothing more.
    _downgrade_to(db_url, "0185")
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT count(*) FROM agents").fetchone() == (2,)
    _upgrade_to(db_url, "0186")
    assert len(_pool_rows(db_file)) == 1


def test_migration_seeds_pools_when_create_all_already_made_the_table(tmp_path) -> None:
    """`init_db` runs `create_all` before `alembic upgrade`, so on a real startup the table exists,
    empty, when 0186 runs. The seed must still happen."""
    db_file = tmp_path / "startup.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0185')")
        conn.commit()
    _seed_agents(db_file)
    assert _pool_rows(db_file) == []

    _upgrade_to(db_url, "0186")

    assert _pool_rows(db_file) == [("agent-bound", "proj-m", "runner-h", None, 1)]


# ------------------------------------------- pool-add-by-model (spec a-profile-s-pool-and-a-new-
# chat-can-use-any-model-of-any-provider, FR-2): an entry named by provider and model


async def _runner_ids() -> list:
    from sqlalchemy import select

    from hub.db.models import Runner

    async with async_session_factory() as session:
        rows = await session.execute(select(Runner.id).where(Runner.project_id == "proj-test"))
        return sorted(rows.scalars().all())


@pytest.mark.asyncio
async def test_pool_add_by_model_reuses_the_projects_runner_for_two_profiles(
    app, auth_headers, add_agent
):
    """ac-api-reuse: Sonnet 5.5 by provider and model, to two profiles' pools, names the runner the
    project already has for it, and the runner count does not change."""
    haiku = await _runner(app, auth_headers, "Haiku", "claude-haiku-5-5")
    sonnet = await _runner(app, auth_headers, "Sonnet", "claude-sonnet-5-5")
    before = await _runner_ids()
    for name in ("builder", "checker"):
        await add_agent(name)
        resp = await _set_pool(
            app,
            auth_headers,
            name,
            [
                {"runner_id": haiku, "default": True},
                {"provider": "claude", "model": "claude-sonnet-5-5", "effort": "high"},
            ],
        )
        assert resp.status_code == 200, resp.text
        assert _shape(resp.json()["pool"]) == [(haiku, None, True), (sonnet, "high", False)]
        assert _shape((await _agent(app, auth_headers, name))["pool"]) == _shape(
            resp.json()["pool"]
        )
    assert await _runner_ids() == before


@pytest.mark.asyncio
async def test_pool_add_by_model_makes_one_runner_for_a_model_no_runner_uses(
    app, auth_headers, add_agent
):
    """ac-pool-adds-unused at the API: Opus 5.5 at High, which no runner uses, is added; the Hub
    makes one plain runner for it, and adding it to a second profile makes no second one."""
    haiku = await _runner(app, auth_headers, "Haiku", "claude-haiku-5-5")
    before = await _runner_ids()
    made = set()
    for name in ("builder", "checker"):
        await add_agent(name)
        resp = await _set_pool(
            app,
            auth_headers,
            name,
            [
                {"runner_id": haiku, "default": True},
                {"provider": "claude", "model": "claude-opus-5-5", "effort": "high"},
            ],
        )
        assert resp.status_code == 200, resp.text
        opus = next(e for e in resp.json()["pool"] if e["model"] == "claude-opus-5-5")
        assert (opus["cli"], opus["effort"], opus["default"]) == ("claude", "high", False)
        made.add(opus["runner_id"])
    assert len(made) == 1
    assert await _runner_ids() == sorted([*before, *made])


@pytest.mark.asyncio
async def test_pool_add_by_model_the_same_model_twice_in_one_edit_is_one_runner(
    app, auth_headers, add_agent
):
    await add_agent("builder")
    resp = await _set_pool(
        app,
        auth_headers,
        "builder",
        [
            {"provider": "codex", "model": "gpt-6-luna", "default": True},
            {"provider": "codex", "model": "gpt-6-luna", "effort": "high"},
        ],
    )
    assert resp.status_code == 200, resp.text
    pool = resp.json()["pool"]
    assert len({e["runner_id"] for e in pool}) == 1
    assert (await _agent(app, auth_headers, "builder"))["runner_id"] == pool[0]["runner_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry, named",
    [
        ({"provider": "claude", "model": "not-a-model"}, "not-a-model"),
        ({"provider": "not-a-cli", "model": "claude-opus-5-5"}, "not-a-cli"),
        ({"provider": "claude", "model": "claude-opus-5-5", "effort": "ludicrous"}, "ludicrous"),
    ],
)
async def test_pool_add_by_model_an_unknown_model_is_refused_and_changes_nothing(
    app, auth_headers, haiku_sonnet, entry, named
):
    """ac-api-unknown: a 4xx naming what the catalog does not hold; the pool and the project's
    runners are as they were."""
    haiku, _ = haiku_sonnet
    pool_before = (await _agent(app, auth_headers, "builder"))["pool"]
    runners_before = await _runner_ids()

    resp = await _set_pool(
        app, auth_headers, "builder", [{"runner_id": haiku, "default": True}, entry]
    )

    assert 400 <= resp.status_code < 500, resp.text
    assert named in resp.json()["detail"]
    assert (await _agent(app, auth_headers, "builder"))["pool"] == pool_before
    assert await _runner_ids() == runners_before
