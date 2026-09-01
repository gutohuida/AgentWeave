"""Tests for /api/v1/projects/proj-test/runners — runner-agent-charter-separation phase 1.

Covers the `runner-registry` capability spec: project-scoped runner CRUD,
first-boot seeding of default claude/codex runners, and binding an agent to
a runner via PATCH /api/v1/projects/proj-test/agents/{name}.
"""

import pytest

# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_runners_are_seeded_on_first_boot(app, auth_headers):
    """The `app` fixture's init_db() call must have already seeded one claude and
    one codex runner for the bootstrap project — no explicit action needed."""
    resp = await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)
    assert resp.status_code == 200
    runners = resp.json()
    clis = sorted(r["cli"] for r in runners)
    assert clis == ["claude", "codex"]
    assert all(r["id"].startswith("runner-") for r in runners)


@pytest.mark.asyncio
async def test_seeding_does_not_duplicate_on_repeat_init(app, auth_headers):
    from hub.db.engine import init_db

    await init_db()
    await init_db()

    resp = await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)
    assert resp.status_code == 200
    runners = resp.json()
    assert len(runners) == 2


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_runner(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/runners",
        json={"name": "Claude Opus", "cli": "claude", "model": "claude-opus-5"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("runner-")
    assert data["name"] == "Claude Opus"
    assert data["cli"] == "claude"
    assert data["model"] == "claude-opus-5"
    assert data["flags"] is None


@pytest.mark.asyncio
async def test_create_runner_rejects_unsupported_cli(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/runners",
        json={"name": "Bogus", "cli": "opencode"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_runner_rejects_a_model_the_catalog_does_not_declare(app, auth_headers):
    """runner-registry spec: 'An undeclared model is refused.'"""
    resp = await app.post(
        "/api/v1/projects/proj-test/runners",
        json={"name": "Bogus model", "cli": "claude", "model": "not-a-real-model"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_runner_rejects_a_model_the_catalog_does_not_declare(app, auth_headers):
    created = (
        await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": "Valid start", "cli": "codex"},
            headers=auth_headers,
        )
    ).json()
    resp = await app.patch(
        f"/api/v1/projects/proj-test/runners/{created['id']}",
        json={"model": "not-a-real-model"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_an_existing_runner_with_an_unrecognised_model_stays_readable_and_flagged(
    app, auth_headers
):
    """runner-registry spec: existing runners keep working; flagged as unrecognised on edit."""
    from hub.db.engine import async_session_factory
    from hub.db.models import Runner

    async with async_session_factory() as session:
        session.add(
            Runner(
                id="runner-legacy-model",
                project_id="proj-test",
                name="Legacy",
                cli="claude",
                model="claude-2-legacy",
            )
        )
        await session.commit()

    resp = await app.get(
        "/api/v1/projects/proj-test/runners/runner-legacy-model", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "claude-2-legacy"
    assert body["model_unrecognised"] is True

    listing = await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)
    assert any(r["id"] == "runner-legacy-model" for r in listing.json())

    # Editing a field other than model does not require the model to be revalidated —
    # the operator is only told it's unrecognised, not blocked from unrelated edits.
    renamed = await app.patch(
        "/api/v1/projects/proj-test/runners/runner-legacy-model",
        json={"name": "Legacy Renamed"},
        headers=auth_headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["model"] == "claude-2-legacy"
    assert renamed.json()["model_unrecognised"] is True


@pytest.mark.asyncio
async def test_a_recognised_model_is_not_flagged(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/runners",
        json={"name": "Recognised", "cli": "claude", "model": "claude-sonnet-5"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["model_unrecognised"] is False


@pytest.mark.asyncio
async def test_launchability_by_provider_probes_every_catalog_provider_with_no_runner_needed(
    app, auth_headers
):
    resp = await app.get(
        "/api/v1/projects/proj-test/runners/launchability-by-provider", headers=auth_headers
    )
    assert resp.status_code == 200
    providers = resp.json()["providers"]
    assert set(providers.keys()) == {"claude", "codex"}
    for verdict in providers.values():
        assert "runnable" in verdict
        assert "reason" in verdict


@pytest.mark.asyncio
async def test_get_runner(app, auth_headers):
    created = (
        await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": "Codex Fast", "cli": "codex"},
            headers=auth_headers,
        )
    ).json()

    resp = await app.get(
        f"/api/v1/projects/proj-test/runners/{created['id']}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Codex Fast"


@pytest.mark.asyncio
async def test_get_runner_404(app, auth_headers):
    resp = await app.get(
        "/api/v1/projects/proj-test/runners/runner-does-not-exist", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_runner(app, auth_headers):
    created = (
        await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": "Original", "cli": "claude"},
            headers=auth_headers,
        )
    ).json()

    resp = await app.patch(
        f"/api/v1/projects/proj-test/runners/{created['id']}",
        json={"name": "Renamed", "model": "claude-sonnet-5"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Renamed"
    assert data["model"] == "claude-sonnet-5"
    assert data["cli"] == "claude"


@pytest.mark.asyncio
async def test_delete_runner(app, auth_headers):
    created = (
        await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": "Throwaway", "cli": "codex"},
            headers=auth_headers,
        )
    ).json()

    resp = await app.delete(
        f"/api/v1/projects/proj-test/runners/{created['id']}", headers=auth_headers
    )
    assert resp.status_code == 204

    resp = await app.get(
        f"/api/v1/projects/proj-test/runners/{created['id']}", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_runner_bound_to_agent_is_refused(app, auth_headers):
    runner = (
        await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": "Bound", "cli": "claude"},
            headers=auth_headers,
        )
    ).json()

    reg = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "bound-agent", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert reg.status_code in (200, 201)

    bind = await app.patch(
        "/api/v1/projects/proj-test/agents/bound-agent",
        json={"runner_id": runner["id"]},
        headers=auth_headers,
    )
    assert bind.status_code == 200
    assert bind.json()["runner_id"] == runner["id"]

    resp = await app.delete(
        f"/api/v1/projects/proj-test/runners/{runner['id']}", headers=auth_headers
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_agent_list_surfaces_bound_runner_id(app, auth_headers):
    runner = (
        await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": "Listed", "cli": "codex"},
            headers=auth_headers,
        )
    ).json()
    reg = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "listed-agent", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert reg.status_code in (200, 201)
    bind = await app.patch(
        "/api/v1/projects/proj-test/agents/listed-agent",
        json={"runner_id": runner["id"]},
        headers=auth_headers,
    )
    assert bind.status_code == 200

    listed = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert listed.status_code == 200
    entry = next(a for a in listed.json() if a["name"] == "listed-agent")
    assert entry["runner_id"] == runner["id"]
    assert entry["charter_id"] is None


@pytest.mark.asyncio
async def test_bind_agent_to_unknown_runner_is_refused(app, auth_headers):
    reg = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "unbound-agent", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert reg.status_code in (200, 201)

    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/unbound-agent",
        json={"runner_id": "runner-does-not-exist"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Clearing a model, and re-submitting one the runner already records
# (runner-model-is-chosen-from-the-catalog, tasks 1.4 and 1.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_with_an_explicit_null_model_clears_it(app, auth_headers):
    """runner-registry: 'The provider's default is a choice, and clearing is honoured.'

    A picker's unset option sends `model: null`. Gating on `is not None` made that a
    silent no-op answered 200 with the old model, so the screen was wrong in a way the
    operator could not see.
    """
    created = (
        await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": "Has a model", "cli": "claude", "model": "claude-sonnet-5"},
            headers=auth_headers,
        )
    ).json()

    resp = await app.patch(
        f"/api/v1/projects/proj-test/runners/{created['id']}",
        json={"model": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["model"] is None

    fetched = await app.get(
        f"/api/v1/projects/proj-test/runners/{created['id']}", headers=auth_headers
    )
    assert fetched.json()["model"] is None


@pytest.mark.asyncio
async def test_patch_carrying_no_model_at_all_leaves_the_model_alone(app, auth_headers):
    """runner-registry: 'A request carrying no model at all leaves the model alone.'

    The companion of the test above: absent and explicit-null are different requests and
    must be answered differently.
    """
    created = (
        await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": "Keeps its model", "cli": "claude", "model": "claude-sonnet-5"},
            headers=auth_headers,
        )
    ).json()

    resp = await app.patch(
        f"/api/v1/projects/proj-test/runners/{created['id']}",
        json={"name": "Renamed but unchanged model"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed but unchanged model"
    assert resp.json()["model"] == "claude-sonnet-5"


@pytest.mark.asyncio
async def test_patch_with_an_empty_string_model_is_still_refused(app, auth_headers):
    """`""` is not a spelling of "unset" — a caller sending it is asking for a model
    named the empty string, which no provider declares."""
    created = (
        await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": "Empty string", "cli": "claude", "model": "claude-sonnet-5"},
            headers=auth_headers,
        )
    ).json()

    resp = await app.patch(
        f"/api/v1/projects/proj-test/runners/{created['id']}",
        json={"model": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert (
        await app.get(f"/api/v1/projects/proj-test/runners/{created['id']}", headers=auth_headers)
    ).json()["model"] == "claude-sonnet-5"


@pytest.mark.asyncio
async def test_a_legacy_runner_accepts_a_resubmission_of_the_model_it_already_records(
    app, auth_headers
):
    """runner-registry: 'A legacy runner can still be saved.'

    A picker's selected value *is* the stored model, so every save of a legacy runner
    carries its unrecognised model back to the Hub. Refusing that would make such a
    runner uneditable in every other respect too. The row cannot be created through the
    API, so it is built through the session.
    """
    from hub.db.engine import async_session_factory
    from hub.db.models import Runner

    async with async_session_factory() as session:
        session.add(
            Runner(
                id="runner-legacy-resubmit",
                project_id="proj-test",
                name="Legacy resubmit",
                cli="claude",
                model="claude-3-legacy-9",
            )
        )
        await session.commit()

    resp = await app.patch(
        "/api/v1/projects/proj-test/runners/runner-legacy-resubmit",
        json={"name": "Legacy renamed", "model": "claude-3-legacy-9"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Legacy renamed"
    assert resp.json()["model"] == "claude-3-legacy-9"
    assert resp.json()["model_unrecognised"] is True


@pytest.mark.asyncio
async def test_a_legacy_runner_still_refuses_a_different_undeclared_model(app, auth_headers):
    """The carve-out above is for the model the runner already records, and only that
    one: moving it to a *different* undeclared model is genuinely a new setting."""
    from hub.db.engine import async_session_factory
    from hub.db.models import Runner

    async with async_session_factory() as session:
        session.add(
            Runner(
                id="runner-legacy-moved",
                project_id="proj-test",
                name="Legacy moved",
                cli="claude",
                model="claude-3-legacy-9",
            )
        )
        await session.commit()

    resp = await app.patch(
        "/api/v1/projects/proj-test/runners/runner-legacy-moved",
        json={"model": "claude-4-legacy-7"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert (
        await app.get(
            "/api/v1/projects/proj-test/runners/runner-legacy-moved", headers=auth_headers
        )
    ).json()["model"] == "claude-3-legacy-9"
