"""Transactional registration lifecycle for local directory-backed projects."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import project_repository, readable_ids
from .data_notes import seed_project as seed_data_notes
from .db.models import RUNNER_CLIS, Base, Charter, DeletedProject, Project, Run, Runner
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
from .repo_hygiene import seed_repo_excludes
from .utils import persist_event, short_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeletedProjectSummary:
    id: str
    name: str


@dataclass(frozen=True)
class RepositoryPreview:
    """What 'Make this a git repository' would commit: *files* as they are, plus AGENTS.md when
    *agents_md* (it is written only on confirmation, so it is not among *files*)."""

    files: list[str]
    agents_md: bool


class RepositoryOfferError(Exception):
    """The folder cannot be made a repository as offered; `code` says why."""

    def __init__(self, message: str, *, code: str) -> None:
        self.code = code
        super().__init__(message)


class ProjectLifecycleService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        hub_data_directory: Optional[Path] = None,
        workspace_root: Optional[str | Path] = None,
    ) -> None:
        self.session = session
        self.hub_data_directory = hub_data_directory
        if workspace_root is None:
            workspace_root = configured_workspace_root()
        self.workspace_root = workspace_root

    async def _canonicalize(self, directory: str | Path) -> CanonicalProjectPath:
        """Resolve *directory* off the event loop: on an unreachable network share the resolve
        blocks for about 21 s, and the whole Hub must not wait with it (F806)."""
        return await asyncio.to_thread(
            canonicalize_project_directory,
            directory,
            hub_data_directory=self.hub_data_directory,
            workspace_root=self.workspace_root,
        )

    async def open_existing(
        self,
        directory: str | Path,
        *,
        name: Optional[str] = None,
        register_copy_as_new: bool = False,
        implicit: bool = False,
        _allow_legacy_binding: bool = True,
    ) -> Project:
        """Open *directory* as a project, registering it when this Hub does not have it.

        `implicit` is a bare `agentweave` start registering the folder it was run from (F736): it
        refuses, rather than re-registers, a folder whose marker names a project this database
        deleted -- that marker may be another database's binding, and the operator did not ask
        for this folder. Only an open the operator asks for re-registers it under a new id (F609).
        """
        canonical = await self._canonicalize(directory)
        existing_by_path = await self.session.scalar(
            select(Project).where(Project.path_key == canonical.path_key)
        )
        if existing_by_path is not None:
            _require_marker(canonical.path, existing_by_path.id)
            _observe(existing_by_path, canonical)
            await self.session.commit()
            seed_repo_excludes(canonical.path)
            await seed_data_notes(self.session, existing_by_path.id, canonical.path)
            return existing_by_path

        marker = await asyncio.to_thread(_read_marker, canonical.path)
        await self._refuse_inside_another_project(
            canonical, marker["project_id"] if marker is not None else None
        )
        if marker is not None:
            marked_project = await self.session.get(Project, marker["project_id"])
            if marked_project is not None:
                if not register_copy_as_new:
                    await self._guard_relocation(marked_project, canonical)
                    moved = marked_project.path_key != canonical.path_key
                    _observe(marked_project, canonical)
                    await self.session.commit()
                    seed_repo_excludes(canonical.path)
                    await seed_data_notes(self.session, marked_project.id, canonical.path)
                    # This is the spec's relocation scenario — "an unavailable project's marked
                    # directory is opened at a new path" — reached through open, not through the
                    # relocate route. Guarded on an actual move so an ordinary re-open does not
                    # pay for two git subprocesses.
                    if moved:
                        _repair_checkout_registrations(canonical.path)
                    return marked_project
            elif not register_copy_as_new and await self._was_deleted(marker["project_id"]):
                if implicit:
                    message = (
                        f"{canonical.path} is marked as project {marker['project_id']}, which "
                        "this Hub deleted, so starting AgentWeave there did not register it again "
                        "(its marker may belong to another Hub's database). To register it as a "
                        "new project, open the folder from the app."
                    )
                    logger.warning(
                        "implicit_open_refused project_id=%s path=%s reason=deleted_project_marker",
                        marker["project_id"],
                        canonical.path,
                    )
                    raise ProjectIdentityConflict(message, code="deleted_project_marker")
            elif not register_copy_as_new:
                project = Project(
                    id=marker["project_id"],
                    name=name or canonical.path.name,
                    charters_seeded=False,
                )
                self.session.add(project)
                await self._seed_new_project(project)
                _observe(project, canonical)
                await self._write_marker_and_commit(project, canonical.path)
                seed_repo_excludes(canonical.path)
                await seed_data_notes(self.session, project.id, canonical.path)
                logger.info(
                    "project_adopted project_id=%s path=%s",
                    project.id,
                    canonical.path,
                )
                # Adoption is deliberately silent at the time it happens — the operator asked to
                # open a folder and it opened. But it is not nothing: this project was registered
                # in some other database, and its id came from the folder rather than being minted
                # here. A log line says that to whoever reads the server output; this row says it
                # to the operator, in the app, afterwards. Written after the commit above, because
                # the row carries a foreign key to the project it describes.
                await persist_event(
                    self.session,
                    project.id,
                    "project_adopted",
                    {"path": str(canonical.path), "adopted_id": project.id},
                )
                return project

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
        seed_repo_excludes(canonical.path)
        await seed_data_notes(self.session, project.id, canonical.path)
        return project

    async def create_new(self, directory: str | Path, *, name: Optional[str] = None) -> Project:
        target = Path(directory).expanduser()
        if not target.is_absolute():
            raise ProjectPathError("new project directory must be an absolute path")
        if await asyncio.to_thread(target.exists):
            raise ProjectPathError(
                "create requires a target that does not exist; "
                "use open for a directory that already exists"
            )
        parent = (await self._canonicalize(target.parent)).path
        target = parent / target.name
        try:
            target.mkdir()
        except OSError as exc:
            raise ProjectPathError(
                f"could not create project directory: {exc}", code="project_create_failed"
            ) from exc

        try:
            # Before the marker exists, so the folder reads as one nothing instructs yet (FR-3),
            # and before registration, so a git failure registers nothing.
            branch = await asyncio.to_thread(project_repository.initialise_repository, target)
        except project_repository.GitUnavailableError:
            # A Hub with no git (its Docker image) still creates projects, as it did before: an
            # empty folder, the same as opening a folder that is not a repository.
            logger.warning("project_created_without_git path=%s", target, exc_info=True)
            _remove_created_repository(target)
            branch = None
        except project_repository.RepositoryInitError as exc:
            _remove_created_project_directory(target)
            raise ProjectPathError(
                f"could not make the new project folder a git repository: {exc}",
                code="project_create_failed",
            ) from exc

        try:
            project = await self.open_existing(
                target, name=name, register_copy_as_new=False, _allow_legacy_binding=False
            )
        except Exception:
            _remove_created_project_directory(target)
            raise

        if branch:
            await self._record_hub_made_branch(project, branch)
        if branch and await asyncio.to_thread((target / project_repository.AGENTS_MD).is_file):
            # AgentWeave created it, so it is the project's instructions from the start (FR-11).
            project.instructions_in_agents_md = True
            await self.session.commit()
        return project

    async def _record_hub_made_branch(self, project: Project, branch: str) -> None:
        """The Hub made *branch*, so it is the project's main branch from the start (FR-1);
        recorded the way `_adopt_detected_main_branch` records its own choice."""
        if project.main_branch:
            return
        project.main_branch = branch
        await self.session.commit()
        await persist_event(
            self.session,
            project.id,
            "project_settings_updated",
            {"changed": {"main_branch": {"was": None, "now": branch}}, "by": "hub"},
        )

    async def preview_repository(self, project_id: str) -> "RepositoryPreview":
        """What making this project's folder a repository would commit (FR-6). Writes nothing."""
        root = await self._repository_candidate(project_id)
        agents_md = await self._would_create_agents_md(project_id, root)
        try:
            files = await asyncio.to_thread(project_repository.preview_first_commit, root)
        except project_repository.GitUnavailableError as exc:
            raise RepositoryOfferError(str(exc), code="git_unavailable") from exc
        except project_repository.RepositoryInitError as exc:
            raise RepositoryOfferError(str(exc), code="repository_failed") from exc
        return RepositoryPreview(files=files, agents_md=agents_md)

    async def make_repository(self, project_id: str, files: list[str]) -> Project:
        """Make the folder a repository whose first commit holds the previewed *files* (FR-6).

        *files* is what the operator was shown. The preview is taken again here, and a folder that
        no longer matches it is refused: the operator confirmed a list, not whatever the folder
        holds by the time the request lands. A failure removes the repository and an AGENTS.md
        this call wrote, and nothing else; the operator's own files are never touched.
        """
        preview = await self.preview_repository(project_id)
        if sorted(set(files)) != preview.files:
            raise RepositoryOfferError(
                "the folder's files changed since the preview; look at the list again and "
                "confirm what it shows now",
                code="preview_stale",
            )
        root = await self._repository_candidate(project_id)
        try:
            branch = await asyncio.to_thread(
                project_repository.initialise_repository,
                root,
                files=preview.files,
                agents_md=preview.agents_md,
            )
        except project_repository.RepositoryInitError as exc:
            _remove_offered_repository(root, wrote_agents_md=preview.agents_md)
            code = (
                "git_unavailable"
                if isinstance(exc, project_repository.GitUnavailableError)
                else "repository_failed"
            )
            raise RepositoryOfferError(
                f"could not make the project folder a git repository: {exc}", code=code
            ) from exc

        project = await self.session.get(Project, project_id)
        assert project is not None  # `_repository_candidate` resolved it
        logger.info(
            "project_repository_created project_id=%s files=%d agents_md=%s",
            project_id,
            len(preview.files),
            preview.agents_md,
        )
        await persist_event(
            self.session,
            project_id,
            "project_repository_created",
            {"files": len(preview.files), "agents_md": preview.agents_md, "branch": branch},
        )
        if branch:
            await self._record_hub_made_branch(project, branch)
        if preview.agents_md:
            await self._adopt_created_agents_md(project, root)
        return project

    async def _adopt_created_agents_md(self, project: Project, root: Path) -> None:
        """AgentWeave created this AGENTS.md, so it becomes the instructions (FR-11), taking any
        database instructions with it in a commit of their own (FR-10). Where that move cannot be
        made, the project stays on its database instructions rather than lose them from turns."""
        from . import instructions_file

        try:
            await instructions_file.move_database_instructions(self.session, project, root)
        except instructions_file.InstructionsSaveRefusedError:
            logger.warning("agents_md_not_adopted project_id=%s", project.id, exc_info=True)
            return
        project.instructions_in_agents_md = True
        await self.session.commit()

    async def _repository_candidate(self, project_id: str) -> Path:
        from .project_workspace import resolve_project_workspace

        root = (await resolve_project_workspace(self.session, project_id)).root
        if await asyncio.to_thread((root / ".git").exists):
            raise RepositoryOfferError(
                f"{root} is already a git repository", code="already_repository"
            )
        return root

    async def _would_create_agents_md(self, project_id: str, root: Path) -> bool:
        """FR-3 for a registered folder. The marker this Hub wrote on opening it does not count;
        one the folder carried in -- an adopted project, whose id came from the folder -- does
        (operator, 2026-11-10)."""
        from .db.models import EventLog

        adopted = await self.session.scalar(
            select(func.count())
            .select_from(EventLog)
            .where(EventLog.project_id == project_id, EventLog.event_type == "project_adopted")
        )
        return await asyncio.to_thread(
            project_repository.should_create_agents_md, root, marker_counts=bool(adopted)
        )

    async def relocate(self, project_id: str, directory: str | Path) -> Project:
        canonical = await self._canonicalize(directory)
        project = await self.session.get(Project, project_id)
        if project is None:
            raise ProjectPathError("unknown project", code="project_not_found")
        marker = await asyncio.to_thread(_read_marker, canonical.path)
        if marker is None or marker["project_id"] != project.id:
            raise ProjectIdentityConflict(
                await self._relocation_marker_refusal(project, canonical, marker)
            )
        await self._guard_relocation(project, canonical)
        moved = project.path_key != canonical.path_key
        _observe(project, canonical)
        await self.session.commit()
        if moved:
            _repair_checkout_registrations(canonical.path)
        return project

    async def delete(
        self, project_id: str, *, remove_private: bool = False
    ) -> DeletedProjectSummary:
        """Remove a project and every row scoped to it. Never touches the project's directory.

        Deletes by introspecting `Base.metadata` for every table carrying a `project_id`
        column, rather than a hand-maintained list of ORM relationships — a fixed list
        drifts silently as tables are added; the sweep is complete by construction. See
        `openspec/changes/2026-08-16-delete-project-api/design.md` D2.

        This function must never import from `project_workspace.py` or call a
        filesystem API on the project's directory — `Project.working_directory` is read only to
        report what was removed, never opened, listed, or deleted (design.md D4).

        `remove_private` (fix-D1, F592) also removes the project's private vault entries, which
        live outside its directory, before any row goes: a refusal or a failed removal deletes no
        record, so the operator can retry. The id is remembered in `deleted_projects`, so
        reopening the folder registers a new project rather than this one (F609).
        """
        project = await self.session.get(Project, project_id)
        if project is None:
            raise ProjectPathError("unknown project", code="project_not_found")

        active_runs = await self.session.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.project_id == project_id, Run.status == "running")
        )
        if active_runs:
            raise ProjectPathError(
                "project cannot be deleted while a run is active",
                code="project_has_active_run",
            )

        summary = DeletedProjectSummary(id=project.id, name=project.name)
        if remove_private:
            from . import vault

            try:
                await vault.remove_private_entries(self.session, project_id)
            except vault.VaultError as exc:
                raise ProjectPathError(str(exc), code="private_location_shared") from exc
            except OSError as exc:
                raise ProjectPathError(
                    f"The project's private vault entries could not be removed ({exc}); nothing "
                    "was deleted. Close whatever holds them and delete again.",
                    code="private_entries_not_removed",
                ) from exc
        for table in _project_scoped_tables():
            await self.session.execute(table.delete().where(table.c.project_id == project_id))
        await self.session.delete(project)
        if await self.session.get(DeletedProject, project_id) is None:
            self.session.add(DeletedProject(id=project_id))
        await self.session.commit()
        return summary

    async def _refuse_inside_another_project(
        self, canonical: CanonicalProjectPath, own_id: Optional[str]
    ) -> None:
        """Refuse a directory nested with another registered project's, in either direction.

        Inside one (F646): its marker would land in that project's repository, and each project's
        agents could edit the other's files. Containing one (F685): the same sharing seen from the
        outside -- and once accepted, every later project under it was refused as nested in it.
        """
        separator = "\\" if canonical.path_key.startswith("windows:") else "/"
        own_prefix = canonical.path_key.rstrip(separator) + separator
        rows = await self.session.execute(
            select(Project.id, Project.name, Project.path_key, Project.working_directory).where(
                Project.path_key.isnot(None)
            )
        )
        for other_id, name, path_key, directory in rows:
            if other_id == own_id:
                continue
            if canonical.path_key.startswith(path_key.rstrip(separator) + separator):
                raise ProjectIdentityConflict(
                    f"{canonical.path} is inside the directory of project {name} ({other_id}, "
                    f"{directory}). A project inside another's directory shares its files and "
                    "repository: open that project instead, or move this folder outside it.",
                    code="project_nested",
                )
            if path_key.startswith(own_prefix):
                raise ProjectIdentityConflict(
                    f"{canonical.path} contains the directory of project {name} ({other_id}, "
                    f"{directory}). A project around another's directory shares its files and "
                    "repository: open a folder that contains no project, or delete that project "
                    "first.",
                    code="project_nested",
                )

    async def _relocation_marker_refusal(
        self,
        project: Project,
        canonical: CanonicalProjectPath,
        marker: Optional[dict[str, Any]],
    ) -> str:
        """Say why *canonical* is not where *project* moved to, naming whose folder it is (F726)."""
        remedy = (
            f"Relocate to the folder {project.name} was moved to: the one whose "
            f"{PROJECT_MARKER_PATH.as_posix()} names {project.id}."
        )
        if marker is None:
            return (
                f"{canonical.path} is not {project.name}'s folder: it has no "
                f"{PROJECT_MARKER_PATH.as_posix()}. {remedy}"
            )
        owner_id = marker["project_id"]
        owner = await self.session.get(Project, owner_id)
        if owner is not None:
            whose = f"project {owner.name} ({owner.id}, {owner.working_directory})"
            other_way = f"open {owner.name} to work in it"
        else:
            whose = f"project {owner_id}, which this Hub does not have"
            other_way = "open it as a project of its own"
        return (
            f"{canonical.path} belongs to {whose}: its {PROJECT_MARKER_PATH.as_posix()} names "
            f"that project, not {project.name} ({project.id}). {remedy} Or {other_way}."
        )

    async def _was_deleted(self, project_id: str) -> bool:
        """Whether this database deleted *project_id*: its folder's marker is then not adopted
        (`a-deleted-project-stays-deleted`), while a marker from another database still is."""
        return await self.session.get(DeletedProject, project_id) is not None

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

        # `Project.path_key` is unique, so without this the commit below raised `IntegrityError`
        # and the route answered a bare 500 (F172). The ordinary way here is folder work: another
        # project was moved away and still claims this path, and this one was moved into its place.
        claimant = await self.session.scalar(
            select(Project).where(
                Project.path_key == destination.path_key, Project.id != project.id
            )
        )
        if claimant is not None:
            raise ProjectIdentityConflict(
                f"{destination.path} is still registered to project {claimant.id} "
                f"({claimant.name}, {claimant.directory_state}). Relocate that project to where "
                "it now lives, or delete it, then relocate this one.",
                code="project_path_claimed",
            )

        active_runs = await self.session.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.project_id == project.id, Run.status == "running")
        )
        # Runs only. This used to also refuse when `.agentweave/worktrees` or `.agentweave/tasks`
        # held anything at all, on the correct observation (task 6.9) that a git worktree
        # registration stores an **absolute** path and relocating breaks every one of them. But an
        # agent worktree is permanent — one ordinary completed turn creates it and nothing removes
        # it — so "a checkout exists" is a fact about the project's history, not about activity,
        # and the effect was that a project could be relocated exactly until its first turn and
        # never again. The spec's own condition is "no active run or worktree mutation"
        # (`local-project-workspace`, "A project directory is relocated"); this now tests that,
        # and `_repair_checkout_registrations` fixes the absolute paths instead of refusing over
        # them. Refusing never un-broke anything anyway: the operator has already moved the
        # directory by the time they ask, so the only thing the refusal preserved was a Hub
        # pointing at a path that is gone.
        if active_runs:
            raise ProjectPathError(
                "project cannot be relocated while a run is active",
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
        project.acronym = await readable_ids.derive(
            self.session, project.id, project.name or "", readable_ids.PROJECT_FALLBACK
        )
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
                with contextlib.suppress(OSError):
                    marker_path.parent.rmdir()
            raise ProjectPathError(
                f"could not write project marker: {exc}", code="project_marker_write_failed"
            ) from exc
        except Exception:
            await self.session.rollback()
            _restore_marker(marker_path, previous)
            raise


def _project_scoped_tables() -> list[Table]:
    """Every table other than `projects` that carries a `project_id` column.

    `Base.metadata.sorted_tables` orders tables so a referenced table precedes what
    references it (the order table *creation* needs); reversed, satellites that
    reference another project-scoped table (e.g. `evidence_reviews` -> `requirement_evidence`)
    are deleted before the table they reference. SQLite enforces no foreign key here
    (`PRAGMA foreign_keys` is never turned on), so this order is not required for
    correctness today, but keeps this code correct if that ever changes.
    """
    return [
        table
        for table in reversed(Base.metadata.sorted_tables)
        if table.name != "projects" and "project_id" in table.c
    ]


#: Where an agent, task, or review checkout lives inside a project. Relative on purpose — the whole
#: point is that these move with the project and their *registrations* do not.
_CHECKOUT_ROOTS = (("worktrees",), ("tasks",), ("reviews",))


def _repair_checkout_registrations(root: Path) -> None:
    """Point every checkout under *root* back at the repository it now lives in.

    A linked git worktree is held together by two absolute paths — the main repo's
    `.git/worktrees/<name>/gitdir` and the checkout's own `.git` file — and moving a project
    directory invalidates both, in every checkout it contains. `git worktree repair`, given the
    checkouts' new paths, rewrites both sides; measured on a real relocated project, a checkout
    that answered `fatal: not a git repository` was fully usable immediately after.

    Best-effort by design. A project that is not a git repository has nothing to repair, a
    checkout git cannot place is left alone and reported, and neither is allowed to fail the
    relocation — the operator has already moved the directory, and refusing to record that is
    strictly worse than recording it with a checkout still needing attention.
    """
    from .worktrees import GitCommandError, _run_git, is_git_repo

    if not is_git_repo(root):
        return
    checkouts = [
        child
        for segments in _CHECKOUT_ROOTS
        for parent in [root.joinpath(".agentweave", *segments)]
        if parent.is_dir()
        for child in sorted(parent.iterdir())
        if child.is_dir()
    ]
    if not checkouts:
        return
    try:
        _run_git(root, "worktree", "repair", *(str(path) for path in checkouts))
        _run_git(root, "worktree", "prune", check=False)
    except (GitCommandError, OSError):
        logger.warning(
            "could not repair worktree registrations under %s after relocation", root, exc_info=True
        )


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
    """Remove what `create_new` put in *target*, and *target* once it is empty. Never more."""
    _remove_created_repository(target)
    marker_dir = target / ".agentweave"
    for candidate in (marker_dir / "project.json.tmp", marker_dir / "project.json"):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            return
    with contextlib.suppress(OSError):
        marker_dir.rmdir()
    with contextlib.suppress(OSError):
        target.rmdir()


def _remove_offered_repository(root: Path, *, wrote_agents_md: bool) -> None:
    """Undo a failed 'Make this a git repository': the `.git` it made (there was none before), and
    AGENTS.md only when it wrote one. The folder's own files stay exactly as they were."""
    if wrote_agents_md:
        _remove_created_repository(root)
    else:
        _remove_git_directory(root)


def _remove_created_repository(target: Path) -> None:
    """The repository and AGENTS.md `project_repository.initialise_repository` made in *target*."""
    with contextlib.suppress(OSError):
        (target / project_repository.AGENTS_MD).unlink(missing_ok=True)
    _remove_git_directory(target)


def _remove_git_directory(target: Path) -> None:
    import shutil
    import stat

    def _writable_then_retry(function, path, _excinfo) -> None:  # type: ignore[no-untyped-def]
        # Git writes its objects read-only, which Windows refuses to delete.
        with contextlib.suppress(OSError):
            os.chmod(path, stat.S_IWRITE)
            function(path)

    if (target / ".git").is_dir():
        shutil.rmtree(target / ".git", onerror=_writable_then_retry)
