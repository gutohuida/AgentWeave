"""Docker mounted workspace-root contracts (phase 6.1).

Covers the ``local-project-workspace`` requirement "Docker registrations are
limited to a mounted workspace root": when the Hub is configured with an
explicit container workspace root (``AW_WORKSPACE_ROOT``), only directories
visible beneath that root may be registered; anything else is refused with a
typed mount diagnostic. The Hub must never mount the Docker socket or guess
host/container path mappings.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select

import hub.config
from hub.config import Settings
from hub.db.engine import async_session_factory
from hub.db.models import Project
from hub.project_lifecycle import ProjectLifecycleService
from hub.project_workspace import (
    ProjectWorkspaceUnavailable,
    canonicalize_project_directory,
    resolve_project_workspace,
)


def test_workspace_root_setting_defaults_to_unset() -> None:
    assert Settings().aw_workspace_root == ""


def test_workspace_root_setting_reads_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("AW_WORKSPACE_ROOT", "/workspaces")
    assert Settings().aw_workspace_root == "/workspaces"


def test_directory_beneath_the_workspace_root_is_accepted(tmp_path) -> None:
    root = tmp_path / "workspaces"
    project = root / "demo"
    project.mkdir(parents=True)

    canonical = canonicalize_project_directory(project, workspace_root=root)

    assert canonical.path == project.resolve()


def test_directory_outside_the_workspace_root_is_refused_with_mount_diagnostic(
    tmp_path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    outside = tmp_path / "host-only"
    outside.mkdir()

    with pytest.raises(ProjectWorkspaceUnavailable) as caught:
        canonicalize_project_directory(outside, workspace_root=root)

    assert caught.value.code == "project_workspace_not_mounted"
    assert caught.value.directory_state == "not_mounted"
    message = str(caught.value)
    assert str(root.resolve()) in message
    assert "mount" in message.casefold()


def test_missing_path_outside_the_root_reports_the_mount_diagnostic(tmp_path) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    host_only = tmp_path / "not-visible-in-container"

    with pytest.raises(ProjectWorkspaceUnavailable) as caught:
        canonicalize_project_directory(host_only, workspace_root=root)

    assert caught.value.code == "project_workspace_not_mounted"


def test_symlink_escaping_the_workspace_root_is_refused(tmp_path) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    outside = tmp_path / "host-only"
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks/junctions unavailable: {exc}")

    with pytest.raises(ProjectWorkspaceUnavailable) as caught:
        canonicalize_project_directory(link, workspace_root=root)

    assert caught.value.code == "project_workspace_not_mounted"


def test_relative_path_beneath_the_root_is_still_refused_as_non_absolute(tmp_path) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    from hub.project_workspace import ProjectPathError

    with pytest.raises(ProjectPathError):
        canonicalize_project_directory("workspaces/demo", workspace_root=root)


@pytest.mark.asyncio
async def test_open_existing_beneath_the_root_registers(app, tmp_path) -> None:
    root = tmp_path / "workspaces"
    project = root / "demo"
    project.mkdir(parents=True)

    async with async_session_factory() as session:
        opened = await ProjectLifecycleService(session, workspace_root=root).open_existing(project)
        assert opened.working_directory == str(project.resolve())
        assert opened.directory_state == "available"


@pytest.mark.asyncio
async def test_open_existing_outside_the_root_is_refused_without_persisting(app, tmp_path) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    outside = tmp_path / "host-only"
    outside.mkdir()

    async with async_session_factory() as session:
        with pytest.raises(ProjectWorkspaceUnavailable) as caught:
            await ProjectLifecycleService(session, workspace_root=root).open_existing(outside)
        assert caught.value.code == "project_workspace_not_mounted"
        remaining = (await session.execute(select(Project))).scalars().all()
        assert all(p.path_key is None for p in remaining)


@pytest.mark.asyncio
async def test_create_new_outside_the_root_is_refused_and_creates_nothing(app, tmp_path) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    target = tmp_path / "host-only" / "new-project"

    async with async_session_factory() as session:
        with pytest.raises(ProjectWorkspaceUnavailable) as caught:
            await ProjectLifecycleService(session, workspace_root=root).create_new(target)
        assert caught.value.code == "project_workspace_not_mounted"
    assert not target.exists()


@pytest.mark.asyncio
async def test_relocate_outside_the_root_is_refused_and_keeps_the_old_binding(
    app, tmp_path
) -> None:
    root = tmp_path / "workspaces"
    original = root / "demo"
    original.mkdir(parents=True)

    async with async_session_factory() as session:
        project = await ProjectLifecycleService(session, workspace_root=root).open_existing(
            original
        )
        original.rename(tmp_path / "host-only")
        with pytest.raises(ProjectWorkspaceUnavailable) as caught:
            await ProjectLifecycleService(session, workspace_root=root).relocate(
                project.id, tmp_path / "host-only"
            )
        assert caught.value.code == "project_workspace_not_mounted"
        assert project.working_directory == str(original.resolve())


@pytest.mark.asyncio
async def test_resolve_revalidates_containment_against_the_configured_root(app, tmp_path) -> None:
    root = tmp_path / "workspaces"
    project_dir = root / "demo"
    project_dir.mkdir(parents=True)

    async with async_session_factory() as session:
        project = await ProjectLifecycleService(session, workspace_root=root).open_existing(
            project_dir
        )

    async with async_session_factory() as session:
        workspace = await resolve_project_workspace(session, project.id, workspace_root=root)
        assert workspace.root == project_dir.resolve()

    other_root = tmp_path / "other-root"
    other_root.mkdir()
    async with async_session_factory() as session:
        with pytest.raises(ProjectWorkspaceUnavailable) as caught:
            await resolve_project_workspace(session, project.id, workspace_root=other_root)
        assert caught.value.code == "project_workspace_not_mounted"
        refreshed = await session.get(Project, project.id)
        assert refreshed.directory_state == "not_mounted"


@pytest.mark.asyncio
async def test_service_reads_the_configured_root_from_settings(app, tmp_path, monkeypatch) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    outside = tmp_path / "host-only"
    outside.mkdir()
    monkeypatch.setattr(hub.config.settings, "aw_workspace_root", str(root))

    async with async_session_factory() as session:
        with pytest.raises(ProjectWorkspaceUnavailable) as caught:
            await ProjectLifecycleService(session).open_existing(outside)
        assert caught.value.code == "project_workspace_not_mounted"

    inside = root / "demo"
    inside.mkdir()
    async with async_session_factory() as session:
        opened = await ProjectLifecycleService(session).open_existing(inside)
        assert opened.directory_state == "available"


@pytest.mark.asyncio
async def test_open_endpoint_returns_the_typed_mount_diagnostic(
    app, auth_headers, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    outside = tmp_path / "host-only"
    outside.mkdir()
    monkeypatch.setattr(hub.config.settings, "aw_workspace_root", str(root))

    refused = await app.post(
        "/api/v1/projects/open",
        json={"path": str(outside)},
        headers=auth_headers,
    )
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "project_workspace_not_mounted"
    assert detail["directory_state"] == "not_mounted"
    assert str(root.resolve()) in detail["message"]

    inside = root / "demo"
    inside.mkdir()
    accepted = await app.post(
        "/api/v1/projects/open",
        json={"path": str(inside)},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["directory_state"] == "available"


@pytest.mark.asyncio
async def test_create_endpoint_refuses_paths_outside_the_root(
    app, auth_headers, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    target = tmp_path / "host-only" / "new-project"
    monkeypatch.setattr(hub.config.settings, "aw_workspace_root", str(root))

    refused = await app.post(
        "/api/v1/projects/create",
        json={"path": str(target)},
        headers=auth_headers,
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "project_workspace_not_mounted"
    assert not target.exists()


def test_compose_mounts_a_configurable_host_root_at_the_container_workspace_root() -> None:
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )

    env_match = re.search(r"AW_WORKSPACE_ROOT=(\S+)", compose)
    assert env_match, "docker-compose.yml must set AW_WORKSPACE_ROOT for the hub service"
    container_root = env_match.group(1)

    volume_match = re.search(
        rf"-\s+\$\{{AW_WORKSPACE_HOST_ROOT[^}}]*\}}:{re.escape(container_root)}\b", compose
    )
    assert volume_match, (
        "docker-compose.yml must mount a configurable host root "
        f"(AW_WORKSPACE_HOST_ROOT) at {container_root}"
    )


def test_compose_never_mounts_the_docker_socket() -> None:
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "docker.sock" not in compose
