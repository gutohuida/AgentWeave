"""Transactional registration lifecycle for local directory-backed projects."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import RUNNER_CLIS, Charter, Project, Run, Runner
from .project_workspace import (
    PROJECT_MARKER_PATH,
    PROJECT_MARKER_VERSION,
    CanonicalProjectPath,
    ProjectIdentityConflict,
    ProjectPathError,
    ProjectWorkspaceUnavailable,
    canonicalize_project_directory,
    configured_workspace_root,
)
from .utils import short_id


class ProjectLifecycleService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        hub_data_directory: Optional[Path] = None,
        workspace_root: Optional[Union[str, Path]] = None,
    ) -> None:
        self.session = session
        self.hub_data_directory = hub_data_directory
        if workspace_root is None:
            workspace_root = configured_workspace_root()
        self.workspace_root = workspace_root

    async def open_existing(
        self,
        directory: Union[str, Path],
        *,
        name: Optional[str] = None,
        register_copy_as_new: bool = False,
        _allow_legacy_binding: bool = True,
    ) -> Project:
        canonical = canonicalize_project_directory(
            directory,
            hub_data_directory=self.hub_data_directory,
            workspace_root=self.workspace_root,
        )
        existing_by_path = await self.session.scalar(
            select(Project).where(Project.path_key == canonical.path_key)
        )
        if existing_by_path is not None:
            _require_marker(canonical.path, existing_by_path.id)
            _observe(existing_by_path, canonical)
            await self.session.commit()
            return existing_by_path

        marker = _read_marker(canonical.path)
        if marker is not None:
            marked_project = await self.session.get(Project, marker["project_id"])
            if marked_project is not None and not register_copy_as_new:
                await self._guard_relocation(marked_project, canonical)
                _observe(marked_project, canonical)
                await self.session.commit()
                return marked_project
            if not register_copy_as_new:
                raise ProjectIdentityConflict(
                    "marked directory is a copied or orphaned project identity; "
                    "register the copy explicitly as new"
                )

        project = None
        if marker is None and _allow_legacy_binding:
            project = await self._single_unbound_legacy_project()
        if project is None:
            project = Project(
                id=f"proj-{short_id()}",
                name=name or canonical.path.name,
                charters_seeded=False,
            )
            self.session.add(project)
            await self._seed_new_project(project)

        _observe(project, canonical)
        await self._write_marker_and_commit(project, canonical.path)
        return project

    async def create_new(
        self, directory: Union[str, Path], *, name: Optional[str] = None
    ) -> Project:
        target = Path(directory).expanduser()
        if not target.is_absolute():
            raise ProjectPathError("new project directory must be an absolute path")
        if target.exists():
            raise ProjectPathError("create requires a target that does not exist")
        parent = canonicalize_project_directory(
            target.parent,
            hub_data_directory=self.hub_data_directory,
            workspace_root=self.workspace_root,
        ).path
        target = parent / target.name
        try:
            target.mkdir()
        except OSError as exc:
            raise ProjectPathError(
                f"could not create project directory: {exc}", code="project_create_failed"
            ) from exc

        try:
            return await self.open_existing(
                target, name=name, register_copy_as_new=False, _allow_legacy_binding=False
            )
        except Exception:
            _remove_created_project_directory(target)
            raise

    async def relocate(self, project_id: str, directory: Union[str, Path]) -> Project:
        canonical = canonicalize_project_directory(
            directory,
            hub_data_directory=self.hub_data_directory,
            workspace_root=self.workspace_root,
        )
        project = await self.session.get(Project, project_id)
        if project is None:
            raise ProjectPathError("unknown project", code="project_not_found")
        marker = _read_marker(canonical.path)
        if marker is None or marker["project_id"] != project.id:
            raise ProjectIdentityConflict("relocation target does not carry the project marker")
        await self._guard_relocation(project, canonical)
        _observe(project, canonical)
        await self.session.commit()
        return project

    async def _guard_relocation(self, project: Project, destination: CanonicalProjectPath) -> None:
        if project.path_key == destination.path_key:
            return

        old_available = False
        if project.working_directory:
            try:
                canonicalize_project_directory(
                    project.working_directory,
                    hub_data_directory=self.hub_data_directory,
                    workspace_root=self.workspace_root,
                )
                old_available = True
            except ProjectWorkspaceUnavailable:
                pass
        if old_available:
            raise ProjectIdentityConflict(
                "project marker was copied while the registered directory is still available"
            )

        active_runs = await self.session.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.project_id == project.id, Run.status == "running")
        )
        worktree_root = destination.path / ".agentweave" / "worktrees"
        active_worktree_metadata = worktree_root.is_dir() and any(worktree_root.iterdir())
        if active_runs or active_worktree_metadata:
            raise ProjectPathError(
                "project cannot be relocated while a run or worktree mutation is active",
                code="project_relocation_active",
            )

    async def _single_unbound_legacy_project(self) -> Optional[Project]:
        projects = (
            (
                await self.session.execute(
                    select(Project).where(
                        Project.working_directory.is_(None), Project.path_key.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        return projects[0] if len(projects) == 1 else None

    async def _seed_new_project(self, project: Project) -> None:
        for cli in RUNNER_CLIS:
            self.session.add(
                Runner(
                    id=f"runner-{short_id()}",
                    project_id=project.id,
                    name=f"{cli.capitalize()} (default)",
                    cli=cli,
                )
            )

        charters_dir = Path(__file__).parent / "data" / "charters"
        manifest = json.loads((charters_dir / "charters.json").read_text(encoding="utf-8"))
        for key, metadata in manifest["charters"].items():
            self.session.add(
                Charter(
                    id=f"charter-{short_id()}",
                    project_id=project.id,
                    name=metadata["name"],
                    content=(charters_dir / f"{key}.md").read_text(encoding="utf-8"),
                )
            )
        project.charters_seeded = True

    async def _write_marker_and_commit(self, project: Project, root: Path) -> None:
        marker_path = root / PROJECT_MARKER_PATH
        previous = marker_path.read_bytes() if marker_path.is_file() else None
        try:
            _write_marker(root, project.id)
            await self.session.commit()
        except OSError as exc:
            await self.session.rollback()
            _restore_marker(marker_path, previous)
            if previous is None:
                try:
                    marker_path.parent.rmdir()
                except OSError:
                    pass
            raise ProjectPathError(
                f"could not write project marker: {exc}", code="project_marker_write_failed"
            ) from exc
        except Exception:
            await self.session.rollback()
            _restore_marker(marker_path, previous)
            raise


def _observe(project: Project, canonical: CanonicalProjectPath) -> None:
    now = datetime.now(timezone.utc)
    project.working_directory = str(canonical.path)
    project.path_key = canonical.path_key
    project.directory_state = "available"
    project.last_opened_at = now
    project.last_seen_at = now


def _read_marker(root: Path) -> Optional[dict[str, Any]]:
    marker_path = root / PROJECT_MARKER_PATH
    if not marker_path.exists():
        return None
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectIdentityConflict("project marker is unreadable or invalid") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("version") != PROJECT_MARKER_VERSION
        or not isinstance(payload.get("project_id"), str)
        or set(payload) != {"version", "project_id"}
    ):
        raise ProjectIdentityConflict("project marker has an unsupported format")
    return payload


def _require_marker(root: Path, project_id: str) -> None:
    marker = _read_marker(root)
    if marker is None or marker["project_id"] != project_id:
        raise ProjectIdentityConflict("registered directory has a conflicting project marker")


def _write_marker(root: Path, project_id: str) -> None:
    marker_path = root / PROJECT_MARKER_PATH
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker_path.with_suffix(".json.tmp")
    payload = {"version": PROJECT_MARKER_VERSION, "project_id": project_id}
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, marker_path)


def _restore_marker(marker_path: Path, previous: Optional[bytes]) -> None:
    try:
        if previous is None:
            marker_path.unlink(missing_ok=True)
        else:
            marker_path.write_bytes(previous)
    except OSError:
        # The caller receives the original failure; phase 1 turns this rare partial
        # rollback into an API repair diagnostic.
        pass


def _remove_created_project_directory(target: Path) -> None:
    marker_dir = target / ".agentweave"
    for candidate in (marker_dir / "project.json.tmp", marker_dir / "project.json"):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            return
    try:
        marker_dir.rmdir()
    except OSError:
        pass
    try:
        target.rmdir()
    except OSError:
        pass
