"""Directory marker and project lifecycle contracts (phase 0.5)."""

from __future__ import annotations

import json
import shutil

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import Charter, Project, Run, Runner
from hub.project_lifecycle import ProjectLifecycleService
from hub.project_workspace import PROJECT_MARKER_PATH, ProjectIdentityConflict, ProjectPathError


def _marker(directory) -> dict:
    return json.loads((directory / PROJECT_MARKER_PATH).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_open_existing_registers_atomically_and_seeds_project_defaults(app, tmp_path) -> None:
    directory = tmp_path / "existing"
    directory.mkdir()

    async with async_session_factory() as session:
        project = await ProjectLifecycleService(session).open_existing(directory)
        project_id = project.id

    assert _marker(directory) == {"version": 1, "project_id": project_id}
    async with async_session_factory() as session:
        stored = await session.get(Project, project_id)
        runner_count = await session.scalar(
            select(func.count()).select_from(Runner).where(Runner.project_id == project_id)
        )
        charter_count = await session.scalar(
            select(func.count()).select_from(Charter).where(Charter.project_id == project_id)
        )
    assert stored is not None
    assert stored.directory_state == "available"
    assert stored.last_opened_at is not None
    assert stored.last_seen_at is not None
    assert runner_count == 2
    assert charter_count and charter_count > 0


@pytest.mark.asyncio
async def test_opening_the_same_directory_twice_returns_the_same_project(app, tmp_path) -> None:
    directory = tmp_path / "same"
    directory.mkdir()
    async with async_session_factory() as session:
        service = ProjectLifecycleService(session)
        first = await service.open_existing(directory)
        second = await service.open_existing(directory / ".")
    assert second.id == first.id


@pytest.mark.asyncio
async def test_missing_project_can_be_relocated_by_opening_its_marker(app, tmp_path) -> None:
    original = tmp_path / "original"
    relocated = tmp_path / "relocated"
    original.mkdir()
    async with async_session_factory() as session:
        project = await ProjectLifecycleService(session).open_existing(original)
        project_id = project.id

    original.rename(relocated)
    async with async_session_factory() as session:
        rebound = await ProjectLifecycleService(session).open_existing(relocated)
    assert rebound.id == project_id
    assert rebound.working_directory == str(relocated.resolve())


@pytest.mark.asyncio
async def test_copied_marker_conflicts_until_explicitly_registered_as_new(app, tmp_path) -> None:
    original = tmp_path / "original"
    copied = tmp_path / "copied"
    original.mkdir()
    copied.mkdir()
    async with async_session_factory() as session:
        first = await ProjectLifecycleService(session).open_existing(original)
        first_id = first.id

    marker_copy = copied / PROJECT_MARKER_PATH
    marker_copy.parent.mkdir()
    shutil.copy2(original / PROJECT_MARKER_PATH, marker_copy)

    async with async_session_factory() as session:
        with pytest.raises(ProjectIdentityConflict, match="copied"):
            await ProjectLifecycleService(session).open_existing(copied)

    async with async_session_factory() as session:
        replacement = await ProjectLifecycleService(session).open_existing(
            copied, register_copy_as_new=True
        )
    assert replacement.id != first_id
    assert _marker(copied)["project_id"] == replacement.id


@pytest.mark.asyncio
async def test_orphaned_marker_is_adopted_under_its_own_id(app, tmp_path) -> None:
    """A marker naming a project id this database has never seen (case 3) must be
    adopted under that same id rather than refused, and seeded like a new project.
    """
    directory = tmp_path / "orphan"
    directory.mkdir()
    orphan_id = "proj-orphanedid01"
    marker_path = directory / PROJECT_MARKER_PATH
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text(json.dumps({"version": 1, "project_id": orphan_id}), encoding="utf-8")

    async with async_session_factory() as session:
        adopted = await ProjectLifecycleService(session).open_existing(directory)

    assert adopted.id == orphan_id
    assert adopted.charters_seeded is True
    assert _marker(directory)["project_id"] == orphan_id

    async with async_session_factory() as session:
        stored = await session.get(Project, orphan_id)
        runner_count = await session.scalar(
            select(func.count()).select_from(Runner).where(Runner.project_id == orphan_id)
        )
        charter_count = await session.scalar(
            select(func.count()).select_from(Charter).where(Charter.project_id == orphan_id)
        )
    assert stored is not None
    assert stored.working_directory == str(directory.resolve())
    assert runner_count == 2
    assert charter_count and charter_count > 0


@pytest.mark.asyncio
async def test_deleted_project_directory_is_adopted_back_under_the_same_id(app, tmp_path) -> None:
    """`delete()` never touches the filesystem, so the marker survives. Reopening the
    same directory afterward must restore the original id rather than being refused.
    """
    directory = tmp_path / "delete-then-reopen"
    directory.mkdir()

    async with async_session_factory() as session:
        service = ProjectLifecycleService(session)
        project = await service.open_existing(directory)
        original_id = project.id
        await service.delete(original_id)

    async with async_session_factory() as session:
        assert await session.get(Project, original_id) is None

    async with async_session_factory() as session:
        reopened = await ProjectLifecycleService(session).open_existing(directory)

    assert reopened.id == original_id
    async with async_session_factory() as session:
        runner_count = await session.scalar(
            select(func.count()).select_from(Runner).where(Runner.project_id == original_id)
        )
    assert runner_count == 2


@pytest.mark.asyncio
async def test_active_run_blocks_relocation(app, tmp_path) -> None:
    original = tmp_path / "original"
    relocated = tmp_path / "relocated"
    original.mkdir()
    async with async_session_factory() as session:
        project = await ProjectLifecycleService(session).open_existing(original)
        project_id = project.id
        session.add(Run(id="run-active-relocate", project_id=project_id, agent="writer"))
        await session.commit()

    original.rename(relocated)
    async with async_session_factory() as session:
        with pytest.raises(ProjectPathError) as caught:
            await ProjectLifecycleService(session).open_existing(relocated)
    assert caught.value.code == "project_relocation_active"


@pytest.mark.asyncio
async def test_copied_active_worktree_metadata_blocks_relocation(app, tmp_path) -> None:
    original = tmp_path / "original"
    relocated = tmp_path / "relocated"
    original.mkdir()
    async with async_session_factory() as session:
        await ProjectLifecycleService(session).open_existing(original)

    original.rename(relocated)
    (relocated / ".agentweave" / "worktrees" / "writer").mkdir(parents=True)
    async with async_session_factory() as session:
        with pytest.raises(ProjectPathError) as caught:
            await ProjectLifecycleService(session).open_existing(relocated)
    assert caught.value.code == "project_relocation_active"


@pytest.mark.asyncio
async def test_marker_write_failure_rolls_back_new_project(app, tmp_path, monkeypatch) -> None:
    directory = tmp_path / "rollback"
    directory.mkdir()

    def fail_marker(*args, **kwargs):
        raise OSError("read-only marker location")

    monkeypatch.setattr("hub.project_lifecycle._write_marker", fail_marker)
    async with async_session_factory() as session:
        with pytest.raises(ProjectPathError) as caught:
            await ProjectLifecycleService(session).open_existing(directory)
    assert caught.value.code == "project_marker_write_failed"

    async with async_session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(Project).where(Project.name == "rollback")
        )
    assert count == 0


@pytest.mark.asyncio
async def test_first_open_binds_the_single_unbound_legacy_project(app, tmp_path) -> None:
    """The `app` fixture bootstraps one unbound legacy project (proj-test, no
    working_directory). The first explicit open of any directory must bind that
    project rather than creating a second one, preserving its id and foreign rows.
    """
    directory = tmp_path / "legacy"
    directory.mkdir()

    async with async_session_factory() as session:
        bootstrapped = await session.get(Project, "proj-test")
        assert bootstrapped is not None
        assert bootstrapped.working_directory is None
        assert bootstrapped.path_key is None

    async with async_session_factory() as session:
        project = await ProjectLifecycleService(session).open_existing(directory)

    assert project.id == "proj-test"
    assert project.working_directory == str(directory.resolve())
    assert _marker(directory)["project_id"] == "proj-test"

    async with async_session_factory() as session:
        total_projects = await session.scalar(select(func.count()).select_from(Project))
    assert total_projects == 1


@pytest.mark.asyncio
async def test_second_open_after_legacy_binding_creates_a_new_project(app, tmp_path) -> None:
    """Once the single unbound legacy project has been bound, opening a second
    directory must register a genuinely new project rather than reusing the first.
    """
    first_directory = tmp_path / "legacy"
    second_directory = tmp_path / "second"
    first_directory.mkdir()
    second_directory.mkdir()

    async with async_session_factory() as session:
        bound = await ProjectLifecycleService(session).open_existing(first_directory)
        assert bound.id == "proj-test"

    async with async_session_factory() as session:
        second = await ProjectLifecycleService(session).open_existing(second_directory)

    assert second.id != "proj-test"
    async with async_session_factory() as session:
        total_projects = await session.scalar(select(func.count()).select_from(Project))
    assert total_projects == 2


@pytest.mark.asyncio
async def test_create_new_creates_exactly_one_directory_and_registers_it(app, tmp_path) -> None:
    target = tmp_path / "created"
    async with async_session_factory() as session:
        project = await ProjectLifecycleService(session).create_new(target)
    assert target.is_dir()
    assert _marker(target)["project_id"] == project.id

    async with async_session_factory() as session:
        runner_count = await session.scalar(
            select(func.count()).select_from(Runner).where(Runner.project_id == project.id)
        )
        charter_count = await session.scalar(
            select(func.count()).select_from(Charter).where(Charter.project_id == project.id)
        )
    assert runner_count == 2
    assert charter_count and charter_count > 0

    async with async_session_factory() as session:
        with pytest.raises(ProjectPathError, match="use open for a directory that already exists"):
            await ProjectLifecycleService(session).create_new(target)
