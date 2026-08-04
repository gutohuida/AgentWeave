"""GET /api/v1/model-catalog (2026-08-04-hub-model-control-and-provisioning)."""

from __future__ import annotations

import pytest

from hub.db.models import RUNNER_CLIS


@pytest.mark.asyncio
async def test_model_catalog_lists_every_spawnable_provider(app, auth_headers) -> None:
    response = await app.get("/api/v1/model-catalog", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    providers = {p["provider"] for p in body["providers"]}
    assert providers == set(RUNNER_CLIS)


@pytest.mark.asyncio
async def test_model_catalog_declares_models_and_controls(app, auth_headers) -> None:
    response = await app.get("/api/v1/model-catalog", headers=auth_headers)
    body = response.json()

    claude = next(p for p in body["providers"] if p["provider"] == "claude")
    assert any(m["id"] == "claude-sonnet-5" for m in claude["models"])
    effort = next(c for c in claude["controls"] if c["id"] == "effort")
    assert effort["apply"]["style"] == "flag"
    assert {v["id"] for v in effort["values"]} == {"low", "medium", "high", "xhigh", "max"}

    codex = next(p for p in body["providers"] if p["provider"] == "codex")
    codex_effort = next(c for c in codex["controls"] if c["id"] == "effort")
    assert codex_effort["apply"]["style"] == "config"


@pytest.mark.asyncio
async def test_model_catalog_requires_authentication(app) -> None:
    response = await app.get("/api/v1/model-catalog")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_model_catalog_is_not_project_scoped(app, auth_headers) -> None:
    # No project_id in the path — the catalog is identical for every project.
    response = await app.get("/api/v1/model-catalog", headers=auth_headers)
    assert response.status_code == 200
