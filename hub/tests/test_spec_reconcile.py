"""Tests for POST /project/specs/reconcile — drift computation, home
selection, prune authorization, source expiry/conflict, and project
isolation.

Each test uses its own isolated project + API key (see `project` fixture)
rather than the shared bootstrap project, because drift computation looks
at *every* snapshot and content row for a project — sharing a project
across tests would make one test's leftover snapshots pollute another's
"active source" set.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from hub.api.v1.spec import ACTIVE_SOURCE_TTL_SECONDS
from hub.db.engine import async_session_factory
from hub.db.models import ApiKey, Project, ProjectSpecSnapshot

BASE = "/api/v1/project"


@pytest_asyncio.fixture
async def project(app):
    project_id = f"proj-spec-{secrets.token_hex(4)}"
    api_key = f"aw_live_{secrets.token_hex(16)}"
    async with async_session_factory() as session:
        session.add(Project(id=project_id, name="Spec Reconcile Test Project"))
        session.add(ApiKey(id=api_key, project_id=project_id, revoked=False))
        await session.commit()
    return {
        "project_id": project_id,
        "headers": {"Authorization": f"Bearer {api_key}"},
    }


def _manifest_json(home="spec/agentweave-spec.html", extra_docs=None, home_kind="baseline"):
    docs = [
        {
            "path": home,
            "title": "Baseline",
            "kind": home_kind,
            "status": "living",
            "parent": None,
            "order": 10,
        }
    ]
    if extra_docs:
        docs.extend(extra_docs)
    return {"version": 1, "home": home, "documents": docs}


async def _sync(app, headers, path, content="<html><head></head></html>"):
    resp = await app.post(
        f"{BASE}/specs/sync", json={"path": path, "content": content}, headers=headers
    )
    assert resp.status_code == 200
    return resp


async def _reconcile(app, headers, source_id, manifest=None, paths=None, prune=False):
    import json as _json

    body = {
        "source_id": source_id,
        "manifest_text": _json.dumps(manifest) if manifest is not None else None,
        "manifest_state": "valid" if manifest is not None else "absent",
        "discovered_paths": paths or [],
        "prune": prune,
    }
    return await app.post(f"{BASE}/specs/reconcile", json=body, headers=headers)


async def _expire_snapshot(project_id: str, source_id: str) -> None:
    """Force a snapshot's updated_at far enough in the past to be inactive."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProjectSpecSnapshot).where(
                ProjectSpecSnapshot.project_id == project_id,
                ProjectSpecSnapshot.source_id == source_id,
            )
        )
        row = result.scalars().first()
        assert row is not None
        row.updated_at = datetime.now(timezone.utc) - timedelta(
            seconds=ACTIVE_SOURCE_TTL_SECONDS + 60
        )
        await session.commit()


class TestReconcileBasics:
    @pytest.mark.asyncio
    async def test_reconcile_without_manifest_returns_deterministic_home(self, app, project):
        await _sync(app, project["headers"], "spec/spec.html")
        resp = await _reconcile(app, project["headers"], "src-a", paths=["spec/spec.html"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["home"] == "spec/spec.html"
        assert data["manifest"]["state"] == "absent"

    @pytest.mark.asyncio
    async def test_legacy_content_with_no_snapshot_is_unindexed(self, app, project):
        await _sync(app, project["headers"], "spec/spec.html")
        list_resp = await app.get(f"{BASE}/specs", headers=project["headers"])
        specs = list_resp.json()["specs"]
        assert specs == [
            {"path": "spec/spec.html", "updated_at": specs[0]["updated_at"], "state": "unindexed"}
        ]

    @pytest.mark.asyncio
    async def test_valid_manifest_sets_home_and_metadata(self, app, project):
        await _sync(app, project["headers"], "spec/agentweave-spec.html")
        manifest = _manifest_json()
        resp = await _reconcile(
            app, project["headers"], "src-a", manifest=manifest, paths=["spec/agentweave-spec.html"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["home"] == "spec/agentweave-spec.html"
        assert data["manifest"]["state"] == "valid"
        assert data["manifest"]["version"] == 1

        list_resp = await app.get(f"{BASE}/specs", headers=project["headers"])
        entry = list_resp.json()["specs"][0]
        assert entry["state"] == "filed"
        assert entry["kind"] == "baseline"
        assert entry["title"] == "Baseline"


class TestDriftDiagnostics:
    @pytest.mark.asyncio
    async def test_unfiled_document(self, app, project):
        await _sync(app, project["headers"], "spec/agentweave-spec.html")
        await _sync(app, project["headers"], "spec/extra.html")
        manifest = _manifest_json()
        resp = await _reconcile(
            app,
            project["headers"],
            "src-a",
            manifest=manifest,
            paths=["spec/agentweave-spec.html", "spec/extra.html"],
        )
        data = resp.json()
        codes = {(d["code"], d["path"]) for d in data["diagnostics"]}
        assert ("unfiled_document", "spec/extra.html") in codes

        list_resp = await app.get(f"{BASE}/specs", headers=project["headers"])
        by_path = {s["path"]: s for s in list_resp.json()["specs"]}
        assert by_path["spec/extra.html"]["state"] == "unfiled"

    @pytest.mark.asyncio
    async def test_missing_document(self, app, project):
        # Manifest declares a document that was never synced as content.
        manifest = _manifest_json(
            extra_docs=[
                {
                    "path": "spec/changes/never-synced/spec.html",
                    "title": "Never synced",
                    "kind": "change-spec",
                    "status": "draft",
                    "parent": None,
                    "order": 20,
                }
            ]
        )
        await _sync(app, project["headers"], "spec/agentweave-spec.html")
        resp = await _reconcile(
            app, project["headers"], "src-a", manifest=manifest, paths=["spec/agentweave-spec.html"]
        )
        data = resp.json()
        assert data["missing"] == [
            {
                "path": "spec/changes/never-synced/spec.html",
                "title": "Never synced",
                "kind": "change-spec",
                "status": "draft",
                "parent": None,
                "order": 20,
            }
        ]
        codes = {d["code"] for d in data["diagnostics"]}
        assert "missing_document" in codes

    @pytest.mark.asyncio
    async def test_intrinsic_metadata_conflict(self, app, project):
        await _sync(
            app,
            project["headers"],
            "spec/agentweave-spec.html",
            content="<html><head><title>Renamed</title></head></html>",
        )
        manifest = _manifest_json()  # cached title is "Baseline"
        resp = await _reconcile(
            app, project["headers"], "src-a", manifest=manifest, paths=["spec/agentweave-spec.html"]
        )
        data = resp.json()
        conflicts = [d for d in data["diagnostics"] if d["code"] == "intrinsic_metadata_conflict"]
        assert len(conflicts) == 1
        assert conflicts[0]["field"] == "title"
        assert conflicts[0]["expected"] == "Baseline"
        assert conflicts[0]["actual"] == "Renamed"

    @pytest.mark.asyncio
    async def test_invalid_manifest_reported_but_content_still_syncs(self, app, project):
        await _sync(app, project["headers"], "spec/spec.html")
        resp = await app.post(
            f"{BASE}/specs/reconcile",
            json={
                "source_id": "src-a",
                "manifest_text": "{not json",
                "manifest_state": "valid",  # client mis-self-reports; Hub re-validates
                "discovered_paths": ["spec/spec.html"],
                "prune": False,
            },
            headers=project["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["manifest"]["state"] == "invalid"
        codes = {d["code"] for d in data["diagnostics"]}
        assert "manifest_invalid_json" in codes

        # Content is still there — an invalid manifest never deletes anything.
        get_resp = await app.get(
            f"{BASE}/spec", params={"path": "spec/spec.html"}, headers=project["headers"]
        )
        assert get_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unknown_parent_and_cycle_diagnostics(self, app, project):
        manifest = {
            "version": 1,
            "home": "spec/a.html",
            "documents": [
                {
                    "path": "spec/a.html",
                    "title": "A",
                    "kind": "baseline",
                    "status": "living",
                    "parent": "spec/does-not-exist.html",
                    "order": 10,
                }
            ],
        }
        resp = await _reconcile(app, project["headers"], "src-a", manifest=manifest, paths=[])
        data = resp.json()
        codes = {d["code"] for d in data["diagnostics"]}
        assert "manifest_unknown_parent" in codes


class TestPrune:
    @pytest.mark.asyncio
    async def test_ordinary_reconcile_never_deletes(self, app, project):
        await _sync(app, project["headers"], "spec/spec.html")
        await _reconcile(app, project["headers"], "src-a", paths=["spec/spec.html"])
        # Deletion from disk — inventory no longer includes the path — but prune=False.
        resp = await _reconcile(app, project["headers"], "src-a", paths=[])
        assert resp.status_code == 200
        assert resp.json()["pruned"] == []

        get_resp = await app.get(
            f"{BASE}/spec", params={"path": "spec/spec.html"}, headers=project["headers"]
        )
        assert get_resp.status_code == 200  # still there

        list_resp = await app.get(f"{BASE}/specs", headers=project["headers"])
        entry = list_resp.json()["specs"][0]
        assert entry["state"] == "stale"

    @pytest.mark.asyncio
    async def test_explicit_prune_removes_true_orphan(self, app, project):
        await _sync(app, project["headers"], "spec/spec.html")
        await _reconcile(app, project["headers"], "src-a", paths=["spec/spec.html"])
        resp = await _reconcile(app, project["headers"], "src-a", paths=[], prune=True)
        assert resp.status_code == 200
        assert resp.json()["pruned"] == ["spec/spec.html"]

        get_resp = await app.get(
            f"{BASE}/spec", params={"path": "spec/spec.html"}, headers=project["headers"]
        )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_prune_preserves_path_claimed_by_another_active_source(self, app, project):
        await _sync(app, project["headers"], "spec/shared.html")
        # Two machines both know about spec/shared.html.
        await _reconcile(app, project["headers"], "src-a", paths=["spec/shared.html"])
        await _reconcile(app, project["headers"], "src-b", paths=["spec/shared.html"])

        # src-a's checkout no longer has it (maybe not yet synced there), but
        # src-b still claims it — prune must not delete it.
        resp = await _reconcile(app, project["headers"], "src-a", paths=[], prune=True)
        assert resp.status_code == 200
        assert resp.json()["pruned"] == []

        get_resp = await app.get(
            f"{BASE}/spec", params={"path": "spec/shared.html"}, headers=project["headers"]
        )
        assert get_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_expired_source_no_longer_claims_its_paths(self, app, project):
        await _sync(app, project["headers"], "spec/old.html")
        await _reconcile(app, project["headers"], "src-old", paths=["spec/old.html"])
        await _expire_snapshot(project["project_id"], "src-old")

        # A second, currently-active source doesn't know about spec/old.html at all.
        resp = await _reconcile(app, project["headers"], "src-new", paths=[], prune=True)
        assert resp.status_code == 200
        assert resp.json()["pruned"] == ["spec/old.html"]


class TestSourceConflict:
    @pytest.mark.asyncio
    async def test_two_active_manifests_disagree(self, app, project):
        await _sync(app, project["headers"], "spec/agentweave-spec.html")
        manifest_a = _manifest_json(home="spec/agentweave-spec.html")
        manifest_b = _manifest_json(home="spec/agentweave-spec.html", home_kind="system-map")
        await _reconcile(app, project["headers"], "src-a", manifest=manifest_a, paths=[])
        resp = await _reconcile(app, project["headers"], "src-b", manifest=manifest_b, paths=[])
        codes = {d["code"] for d in resp.json()["diagnostics"]}
        assert "active_source_conflict" in codes

    @pytest.mark.asyncio
    async def test_newest_valid_manifest_wins_for_home(self, app, project):
        await _sync(app, project["headers"], "spec/a.html")
        await _sync(app, project["headers"], "spec/b.html")
        manifest_a = _manifest_json(home="spec/a.html")
        manifest_a["documents"][0]["path"] = "spec/a.html"
        manifest_b = _manifest_json(home="spec/b.html")
        manifest_b["documents"][0]["path"] = "spec/b.html"

        await _reconcile(app, project["headers"], "src-a", manifest=manifest_a, paths=[])
        resp = await _reconcile(app, project["headers"], "src-b", manifest=manifest_b, paths=[])
        assert resp.json()["home"] == "spec/b.html"  # src-b reconciled last


class TestReconcileValidation:
    @pytest.mark.asyncio
    async def test_rejects_oversized_manifest(self, app, project):
        huge = "x" * (256 * 1024 + 1)
        resp = await app.post(
            f"{BASE}/specs/reconcile",
            json={
                "source_id": "src-a",
                "manifest_text": huge,
                "manifest_state": "valid",
                "discovered_paths": [],
                "prune": False,
            },
            headers=project["headers"],
        )
        assert resp.status_code == 413

    @pytest.mark.asyncio
    async def test_rejects_unsafe_discovered_path(self, app, project):
        resp = await app.post(
            f"{BASE}/specs/reconcile",
            json={
                "source_id": "src-a",
                "manifest_text": None,
                "manifest_state": "absent",
                "discovered_paths": ["../etc/passwd.html"],
                "prune": False,
            },
            headers=project["headers"],
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_invalid_manifest_state_enum(self, app, project):
        resp = await app.post(
            f"{BASE}/specs/reconcile",
            json={
                "source_id": "src-a",
                "manifest_text": None,
                "manifest_state": "not-a-state",
                "discovered_paths": [],
                "prune": False,
            },
            headers=project["headers"],
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_missing_source_id(self, app, project):
        resp = await app.post(
            f"{BASE}/specs/reconcile",
            json={
                "source_id": "",
                "manifest_text": None,
                "manifest_state": "absent",
                "discovered_paths": [],
                "prune": False,
            },
            headers=project["headers"],
        )
        assert resp.status_code == 422


class TestSSEPayloads:
    @pytest.mark.asyncio
    async def test_manifest_reconcile_broadcasts_reason_without_path(self, app, project):
        with patch("hub.api.v1.spec.sse_manager.broadcast", new_callable=AsyncMock) as mock_bc:
            await _reconcile(app, project["headers"], "src-a", manifest=_manifest_json(), paths=[])
        mock_bc.assert_awaited_once_with(
            project["project_id"], "spec_updated", {"reason": "manifest"}
        )

    @pytest.mark.asyncio
    async def test_inventory_only_reconcile_broadcasts_inventory_reason(self, app, project):
        with patch("hub.api.v1.spec.sse_manager.broadcast", new_callable=AsyncMock) as mock_bc:
            await _reconcile(app, project["headers"], "src-a", paths=["spec/spec.html"])
        mock_bc.assert_awaited_once_with(
            project["project_id"], "spec_updated", {"reason": "inventory"}
        )

    @pytest.mark.asyncio
    async def test_prune_broadcasts_prune_reason(self, app, project):
        await _sync(app, project["headers"], "spec/spec.html")
        await _reconcile(app, project["headers"], "src-a", paths=["spec/spec.html"])
        with patch("hub.api.v1.spec.sse_manager.broadcast", new_callable=AsyncMock) as mock_bc:
            await _reconcile(app, project["headers"], "src-a", paths=[], prune=True)
        mock_bc.assert_awaited_once_with(project["project_id"], "spec_updated", {"reason": "prune"})

    @pytest.mark.asyncio
    async def test_per_file_sync_still_broadcasts_path(self, app, project):
        with patch("hub.api.v1.spec.sse_manager.broadcast", new_callable=AsyncMock) as mock_bc:
            await _sync(app, project["headers"], "spec/spec.html")
        mock_bc.assert_awaited_once_with(
            project["project_id"], "spec_updated", {"path": "spec/spec.html"}
        )


class TestProjectIsolation:
    @pytest_asyncio.fixture
    async def other_project(self, app):
        project_id = f"proj-spec-other-{secrets.token_hex(4)}"
        api_key = f"aw_live_{secrets.token_hex(16)}"
        async with async_session_factory() as session:
            session.add(Project(id=project_id, name="Other Spec Project"))
            session.add(ApiKey(id=api_key, project_id=project_id, revoked=False))
            await session.commit()
        return {"project_id": project_id, "headers": {"Authorization": f"Bearer {api_key}"}}

    @pytest.mark.asyncio
    async def test_snapshots_and_drift_are_isolated_per_project(self, app, project, other_project):
        await _sync(app, project["headers"], "spec/mine.html")
        await _reconcile(app, project["headers"], "src-a", paths=["spec/mine.html"])

        other_list = await app.get(f"{BASE}/specs", headers=other_project["headers"])
        assert other_list.json()["specs"] == []

        other_get = await app.get(
            f"{BASE}/spec", params={"path": "spec/mine.html"}, headers=other_project["headers"]
        )
        assert other_get.status_code == 404

    @pytest.mark.asyncio
    async def test_prune_in_one_project_does_not_touch_another(self, app, project, other_project):
        await _sync(app, project["headers"], "spec/shared-name.html")
        await _sync(app, other_project["headers"], "spec/shared-name.html")
        await _reconcile(app, project["headers"], "src-a", paths=["spec/shared-name.html"])
        await _reconcile(app, other_project["headers"], "src-a", paths=[], prune=True)

        # other_project pruned its own copy...
        other_get = await app.get(
            f"{BASE}/spec",
            params={"path": "spec/shared-name.html"},
            headers=other_project["headers"],
        )
        assert other_get.status_code == 404

        # ...but project's copy (same path, different project) is untouched.
        mine_get = await app.get(
            f"{BASE}/spec", params={"path": "spec/shared-name.html"}, headers=project["headers"]
        )
        assert mine_get.status_code == 200
