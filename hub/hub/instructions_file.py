"""AGENTS.md as a project's instructions, where chosen.

Spec `a-new-project-starts-as-a-git-repository-with-an-agents-md`, task `instructions-in-agents-md`.

**Which source (FR-11).** `Project.instructions_in_agents_md` says whether the project's AGENTS.md is
its instructions. It is set when AgentWeave created the file (a new folder, or "Make this a git
repository"), and otherwise only by the operator switching it on in Settings → Instructions, which
is offered only when the folder holds an AGENTS.md. Off, instructions are the
`project_instructions` row exactly as before, and nothing here reads any file.

**A save is a commit on main (FR-9).** Agents work in their own worktrees and see main's committed
state, so an uncommitted AGENTS.md would never reach them. A save therefore commits AGENTS.md alone
on the main branch, and is refused before anything is written when the checkout is on another
branch or AGENTS.md has uncommitted changes there: overwriting the operator's own unsaved edit
would lose their work. With no main branch chosen (or no repository) the file is written and the
answer says it was not committed.

**One copy (FR-10).** Switching AGENTS.md on moves the database instructions into the file's
instructions area once, committed as a save is. The row is kept and not read while the file is the
source, so switching off returns to it unchanged.

**Once per turn (FR-8).** A runner whose CLI reads AGENTS.md by itself (`RunnerAdapter.
reads_agents_md`) gets the instructions from the file in its working directory, so the context the
Hub hands it carries a pointer instead of a second copy; every other runner gets the file's text.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Project, ProjectInstructions
from .project_repository import (
    AGENTS_MD,
    PROJECT_INSTRUCTIONS_HEADING,
    RepositoryInitError,
    _git,
    _identity_options,
)
from .utils import persist_event

logger = logging.getLogger(__name__)

#: The most characters project instructions may hold (F686). They are carried by every agent turn,
#: so their size is paid in input tokens on each one: 300,000 characters were accepted and carried
#: by every later turn (~70k input tokens for a Haiku first turn). 40,000 is the size at which
#: Claude Code itself warns that a CLAUDE.md is large enough to hurt.
MAX_INSTRUCTIONS_CHARS = 40_000

SAVE_COMMIT_MESSAGE = "Update the project's instructions (AGENTS.md)"
MOVE_COMMIT_MESSAGE = "Move the project's instructions into AGENTS.md"


class InstructionsSaveRefusedError(Exception):
    """A save to AGENTS.md was refused before anything was written; `code` names why."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SaveOutcome:
    #: Whether the save made a commit on the main branch.
    committed: bool
    #: Said to the operator when the file was written but not committed; None otherwise.
    notice: Optional[str] = None


def too_long_message(length: int) -> str:
    return (
        f"These instructions are {length:,} characters; the limit is "
        f"{MAX_INSTRUCTIONS_CHARS:,}. They are sent with every agent turn, so their "
        "size is paid on each one. Shorten them, or keep reference material in the "
        "project's files or knowledge vault and point to it from here."
    )


# --- The file and its git state (synchronous; run off the event loop) ---------------------------


def read_agents_md(root: Path) -> str:
    """The text of *root*'s AGENTS.md, or "" when there is none."""
    path = root / AGENTS_MD
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def has_agents_md(root: Path) -> bool:
    return (root / AGENTS_MD).is_file()


def save_agents_md(
    root: Path, content: str, main_branch: Optional[str], *, message: str = SAVE_COMMIT_MESSAGE
) -> SaveOutcome:
    """Write *content* to *root*'s AGENTS.md and commit it, alone, on *main_branch* (FR-9).

    Raises `InstructionsSaveRefusedError` before writing anything when the checkout is not on
    *main_branch* or AGENTS.md has uncommitted changes. A failed commit puts the file back.
    """
    path = root / AGENTS_MD
    committing = bool(main_branch) and (root / ".git").exists()
    if committing:
        assert main_branch is not None
        _refuse_unless_committable(root, main_branch)
    previous = path.read_bytes() if path.is_file() else None
    if previous is not None and previous.decode("utf-8", errors="replace") == content:
        # Nothing changed, so there is nothing to commit; not an error.
        return SaveOutcome(committed=False)

    # `newline=""`: the text is written exactly as given, so what the operator saved is what git
    # sees and what the next read shows.
    path.write_text(content, encoding="utf-8", newline="")
    if not committing:
        why = (
            "this project has no main branch set"
            if (root / ".git").exists()
            else "the project folder is not a git repository"
        )
        return SaveOutcome(
            committed=False,
            notice=(
                f"AGENTS.md was saved but not committed: {why}. Agents working in their own "
                "worktrees will not see it until it is committed."
            ),
        )
    try:
        _run(root, "add", "--", AGENTS_MD)
        _run(
            root,
            *_identity_options(root),
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "--only",
            "-m",
            message,
            "--",
            AGENTS_MD,
        )
    except RepositoryInitError as exc:
        _put_back(root, path, previous)
        raise InstructionsSaveRefusedError(
            f"AGENTS.md could not be committed, so it was left as it was: {exc}",
            code="agents_md_commit_failed",
        ) from exc
    return SaveOutcome(committed=True)


def with_moved_instructions(text: str, moved: str) -> str:
    """*text* (an AGENTS.md) with *moved* added to its instructions area (FR-10).

    The area is the end of the file under `PROJECT_INSTRUCTIONS_HEADING`; a file without that
    heading (one the operator wrote) gains it. Adding is idempotent: a file that already holds
    *moved* is returned unchanged, so the move happens once.
    """
    moved = moved.strip()
    if not moved or moved in text:
        return text
    body = text.rstrip("\n")
    if PROJECT_INSTRUCTIONS_HEADING not in text:
        body = f"{body}\n\n{PROJECT_INSTRUCTIONS_HEADING}" if body else PROJECT_INSTRUCTIONS_HEADING
    return f"{body}\n\n{moved}\n"


def _refuse_unless_committable(root: Path, main_branch: str) -> None:
    head = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    current = (head.stdout or "").strip() if head.returncode == 0 else ""
    if current != main_branch:
        on = f"on {current}" if current else "not on any branch"
        raise InstructionsSaveRefusedError(
            f"The project's checkout is {on}, not the main branch {main_branch}, so AGENTS.md "
            f"was not saved. Switch the checkout to {main_branch} and save again.",
            code="checkout_off_main",
        )
    status = _git(root, "status", "--porcelain", "--untracked-files=all", "--", AGENTS_MD)
    if status.returncode != 0:
        said = (status.stderr or status.stdout or "").strip()
        raise InstructionsSaveRefusedError(
            f"Could not read AGENTS.md's git status, so it was not saved: {said}",
            code="agents_md_status_failed",
        )
    if status.stdout.strip():
        raise InstructionsSaveRefusedError(
            "AGENTS.md has uncommitted changes in the project's checkout "
            f"({status.stdout.strip()}), so it was not saved over them. Commit or discard "
            "those changes, then save again.",
            code="agents_md_uncommitted",
        )


def _put_back(root: Path, path: Path, previous: Optional[bytes]) -> None:
    _git(root, "reset", "--quiet", "--", AGENTS_MD)
    if previous is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(previous)


def _run(root: Path, *args: str) -> None:
    result = _git(root, *args)
    if result.returncode != 0:
        said = (result.stderr or result.stdout or "").strip()
        raise RepositoryInitError(f"git {' '.join(args)} failed: {said}")


# --- The project's instructions, from whichever source is chosen -------------------------------


async def _root(session: AsyncSession, project_id: str) -> Path:
    from .project_workspace import resolve_project_workspace

    return (await resolve_project_workspace(session, project_id)).root


async def _database_instructions(session: AsyncSession, project_id: str) -> str:
    row = (
        (
            await session.execute(
                select(ProjectInstructions).where(ProjectInstructions.project_id == project_id)
            )
        )
        .scalars()
        .first()
    )
    return row.content if row else ""


async def instructions_for_turn(
    session: AsyncSession, project: Optional[Project], project_id: str, *, reads_agents_md: bool
) -> tuple[str, bool]:
    """What a turn's context carries as the project's instructions, and whether the runner reads
    them from AGENTS.md itself instead (FR-8). Off, the database row, exactly as before."""
    if project is None or not project.instructions_in_agents_md:
        return await _database_instructions(session, project_id), False
    if reads_agents_md:
        return "", True
    try:
        root = await _root(session, project_id)
    except Exception:  # noqa: BLE001 - a missing folder renders no instructions, not a failed turn
        logger.warning("agents_md_unreadable project_id=%s", project_id, exc_info=True)
        return "", False
    return await asyncio.to_thread(read_agents_md, root), False


async def instructions_state(session: AsyncSession, project: Project) -> dict:
    """What Settings → Instructions shows: the content from the chosen source, which source, and
    whether switching AGENTS.md on is offered (only when the folder holds one, FR-11)."""
    try:
        root: Optional[Path] = await _root(session, project.id)
    except Exception:  # noqa: BLE001 - an unavailable folder offers nothing and reads nothing
        root = None
    file_present = bool(root) and await asyncio.to_thread(has_agents_md, root)  # type: ignore[arg-type]
    if project.instructions_in_agents_md:
        content = await asyncio.to_thread(read_agents_md, root) if root else ""
        source = "agents_md"
    else:
        content = await _database_instructions(session, project.id)
        source = "hub"
    return {
        "content": content,
        "max_chars": MAX_INSTRUCTIONS_CHARS,
        "source": source,
        "agents_md_offered": source == "hub" and file_present,
        "main_branch": project.main_branch,
    }


async def save_to_agents_md(session: AsyncSession, project: Project, content: str) -> SaveOutcome:
    root = await _root(session, project.id)
    outcome = await asyncio.to_thread(save_agents_md, root, content, project.main_branch)
    await persist_event(
        session,
        project.id,
        "project_instructions_saved",
        {"source": "agents_md", "committed": outcome.committed, "chars": len(content)},
    )
    return outcome


async def use_agents_md(session: AsyncSession, project: Project) -> SaveOutcome:
    """Switch AGENTS.md on as *project*'s instructions, moving the database instructions into it
    once (FR-10). Refused, changing nothing, where the save that move needs would be refused."""
    root = await _root(session, project.id)
    if not await asyncio.to_thread(has_agents_md, root):
        raise InstructionsSaveRefusedError(
            "This project's folder has no AGENTS.md to use as its instructions.",
            code="no_agents_md",
        )
    outcome = await move_database_instructions(session, project, root)
    project.instructions_in_agents_md = True
    await session.commit()
    await persist_event(
        session,
        project.id,
        "project_settings_updated",
        {"changed": {"instructions_in_agents_md": {"was": False, "now": True}}, "by": "operator"},
    )
    return outcome


async def move_database_instructions(
    session: AsyncSession, project: Project, root: Path
) -> SaveOutcome:
    """Add the database instructions to *root*'s AGENTS.md, committed as a save is (FR-10). The
    database row is left as it is."""
    moved = await _database_instructions(session, project.id)
    current = await asyncio.to_thread(read_agents_md, root)
    combined = with_moved_instructions(current, moved)
    if combined == current:
        return SaveOutcome(committed=False)
    if len(combined) > MAX_INSTRUCTIONS_CHARS:
        raise InstructionsSaveRefusedError(
            "AGENTS.md with this project's instructions added would be "
            f"{len(combined):,} characters; the limit is {MAX_INSTRUCTIONS_CHARS:,}. Shorten "
            "the instructions or AGENTS.md first.",
            code="instructions_too_long",
        )
    return await asyncio.to_thread(
        save_agents_md, root, combined, project.main_branch, message=MOVE_COMMIT_MESSAGE
    )


async def stop_using_agents_md(session: AsyncSession, project: Project) -> None:
    """Back to the database instructions, which were kept unchanged (the rollback)."""
    project.instructions_in_agents_md = False
    await session.commit()
    await persist_event(
        session,
        project.id,
        "project_settings_updated",
        {"changed": {"instructions_in_agents_md": {"was": True, "now": False}}, "by": "operator"},
    )
