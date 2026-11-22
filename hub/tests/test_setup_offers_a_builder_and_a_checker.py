"""The setup offer (`profiles-threads-and-builds-everywhere` D6, FR-8).

A new project's setup list carries a dismissable `profiles` item in place of the old `agent` item,
and POST /setup/profiles creates a builder and a checker profile in one transaction, after which
the offer is gone. Criteria `setup-offer-shown` and `setup-offer-creates-two`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Agent
from hub.runner_adapters import base as adapter_base


@pytest.fixture(autouse=True)
def _runners_can_run(monkeypatch) -> None:
    monkeypatch.setattr(adapter_base.shutil, "which", lambda name, *a, **k: f"/bin/{name}")


async def _setup(app, auth_headers, project_id: str = "proj-test") -> dict:
    listed = await app.get("/api/v1/projects", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    (project,) = [p for p in listed.json() if p["id"] == project_id]
    return project["setup"]


def _ids(items: list[dict]) -> list[str]:
    return [item["id"] for item in items]


async def _agents() -> list[Agent]:
    async with async_session_factory() as session:
        rows = await session.execute(
            select(Agent).where(Agent.project_id == "proj-test").order_by(Agent.name)
        )
        return list(rows.scalars().all())


async def _runner(app, auth_headers, name: str) -> str:
    made = await app.post(
        "/api/v1/projects/proj-test/runners",
        json={"name": name, "cli": "claude"},
        headers=auth_headers,
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def _charter(app, auth_headers, name: str) -> str:
    made = await app.post(
        "/api/v1/projects/proj-test/charters",
        json={"name": name, "content": f"You are the {name}."},
        headers=auth_headers,
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


@pytest.mark.asyncio
async def test_setup_offer_shown_until_dismissed_and_creates_nothing(app, auth_headers) -> None:
    """setup-offer-shown: present at first, absent after dismissal, and no profile exists."""
    first = await _setup(app, auth_headers)
    (offer,) = [item for item in first["items"] if item["id"] == "profiles"]
    assert offer["key"] == "profiles" and offer["dismissable"] is True
    assert "agent" not in _ids(first["items"])

    dismissed = await app.put(
        "/api/v1/projects/proj-test/setup/dismissed/profiles", headers=auth_headers
    )
    assert dismissed.status_code == 200, dismissed.text

    again = await _setup(app, auth_headers)
    assert "profiles" not in _ids(again["items"])
    assert "profiles" in _ids(again["dismissed"])
    assert await _agents() == []


@pytest.mark.asyncio
async def test_setup_offer_creates_a_builder_and_a_checker_and_is_gone(app, auth_headers) -> None:
    """setup-offer-creates-two: Builder with no charter, Checker with Verifier, a runner each."""
    builder_runner = await _runner(app, auth_headers, "builds")
    checker_runner = await _runner(app, auth_headers, "checks")
    verifier = await _charter(app, auth_headers, "Verifier")

    created = await app.post(
        "/api/v1/projects/proj-test/setup/profiles",
        json={
            "builder": {"name": "Builder", "charter_id": None, "runner_id": builder_runner},
            "checker": {"name": "Checker", "charter_id": verifier, "runner_id": checker_runner},
        },
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["builder"]["name"] == "Builder" and body["checker"]["name"] == "Checker"
    agents = {agent.name: agent for agent in await _agents()}
    assert set(agents) == {"Builder", "Checker"}
    assert all(agent.lifecycle == "open" for agent in agents.values())
    assert (agents["Builder"].charter_id, agents["Builder"].runner_id) == (None, builder_runner)
    assert (agents["Checker"].charter_id, agents["Checker"].runner_id) == (verifier, checker_runner)
    setup = await _setup(app, auth_headers)
    assert "profiles" not in _ids(setup["items"])

    # Used, not just met: archiving both does not bring the offer back.
    for name in ("Builder", "Checker"):
        archived = await app.post(
            f"/api/v1/projects/proj-test/agents/{name}/archive", headers=auth_headers
        )
        assert archived.status_code == 200, archived.text
    assert "profiles" not in _ids((await _setup(app, auth_headers))["items"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "builder_name, checker_name, why",
    [
        ("Same", "Same", "different names"),
        ("Same", "same", "different names"),
        ("Builder", "Taken", "already exists"),
    ],
)
async def test_setup_offer_refusals_create_nothing(
    app, auth_headers, add_agent, builder_name, checker_name, why
) -> None:
    """setup-offer-creates-two: the same-name attempt (and a taken name) is refused, 409, and
    nothing is created, the builder that passed its own checks included."""
    await add_agent("Taken", lifecycle="archived")
    runner = await _runner(app, auth_headers, "only")

    refused = await app.post(
        "/api/v1/projects/proj-test/setup/profiles",
        json={
            "builder": {"name": builder_name, "runner_id": runner},
            "checker": {"name": checker_name, "runner_id": runner},
        },
        headers=auth_headers,
    )

    assert refused.status_code == 409, refused.text
    assert why in refused.json()["detail"]
    assert [agent.name for agent in await _agents()] == ["Taken"]
    assert "profiles" in _ids((await _setup(app, auth_headers))["items"])


@pytest.mark.asyncio
async def test_setup_offer_refuses_a_runner_that_is_not_the_projects(app, auth_headers) -> None:
    runner = await _runner(app, auth_headers, "only")

    refused = await app.post(
        "/api/v1/projects/proj-test/setup/profiles",
        json={
            "builder": {"name": "Builder", "runner_id": runner},
            "checker": {"name": "Checker", "runner_id": "runner-elsewhere"},
        },
        headers=auth_headers,
    )

    assert refused.status_code == 409, refused.text
    assert "checker" in refused.json()["detail"]
    assert await _agents() == []


@pytest.mark.asyncio
async def test_setup_offer_creates_both_on_catalog_models_no_runner_uses(app, auth_headers) -> None:
    """dialogs-agree, ac-setup-unused-model: a builder on Opus 5.5 and a checker on Sonnet 5.5,
    named by provider and model, each get the plain runner for their model, made because none
    existed, and that model as their pool default."""
    created = await app.post(
        "/api/v1/projects/proj-test/setup/profiles",
        json={
            "builder": {"name": "Builder", "provider": "claude", "model": "claude-opus-5-5"},
            "checker": {"name": "Checker", "provider": "claude", "model": "claude-sonnet-5-5"},
        },
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    roster = (await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)).json()
    defaults = {
        a["name"]: next(e for e in a["pool"] if e["default"])["model"]
        for a in roster
        if a["name"] in {"Builder", "Checker"}
    }
    assert defaults == {"Builder": "claude-opus-5-5", "Checker": "claude-sonnet-5-5"}


@pytest.mark.asyncio
async def test_setup_offer_refuses_a_model_the_catalog_does_not_hold(app, auth_headers) -> None:
    refused = await app.post(
        "/api/v1/projects/proj-test/setup/profiles",
        json={
            "builder": {"name": "Builder", "provider": "claude", "model": "claude-opus-5-5"},
            "checker": {"name": "Checker", "provider": "claude", "model": "not-a-model"},
        },
        headers=auth_headers,
    )

    assert refused.status_code == 409, refused.text
    assert "checker" in refused.json()["detail"] and "not-a-model" in refused.json()["detail"]
    assert await _agents() == []
