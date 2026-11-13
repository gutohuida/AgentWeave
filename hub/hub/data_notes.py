"""The vault note on what the project's data means, and its traps.

`ask-any-agent-for-a-dashboard-and-get-one-that-stays`, FR-8: every project's vault holds it
before any dashboard tool is first called, including projects registered before this shipped,
and it is never overwritten once agents have added to it. It is seeded at Hub startup for every
registered project and whenever a project is opened or created, under one fixed id
(`NOTE_ID`), so the dashboard tools' guidance can name it and a second seeding finds it there.
The text below is only the starting point: agents append what they learn with `vault_append`.

It is a private source at the project's private vault location, with no stub under `knowledge/`
(`vault.seed_source`): seeding never writes into the project's folder, so opening a folder still
writes only `.agentweave/` and a new project's first commit stays clean.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import vault

logger = logging.getLogger(__name__)

#: The same in every project: `src-` and the first 12 hex digits of
#: sha256("agentweave:what-the-data-means").
NOTE_ID = "src-27723331ae1d"
NOTE_NAME = "What the project's data means, and its traps"

#: How the dashboard tools' guidance names the note.
GUIDANCE = (
    f'Before writing a query, read the vault note `{NOTE_ID}` ("{NOTE_NAME}") with '
    "`vault_read`: it says what the data means and its traps. When you find another trap, add it "
    "with `vault_append`."
)

NOTE_TEXT = f"""# {NOTE_NAME}

What the rows a dashboard query reads actually mean, and where a straightforward count gives the
wrong answer. Read this before writing a dashboard query. Every agent may add to it: when a number
surprised you and you found out why, append what you learned with `vault_append("{NOTE_ID}", ...)`,
naming the tables and columns it concerns.

## Traps

### A send-back rejects every piece of evidence from that commit

When a reviewer sends a task back, the evidence recorded from that commit is rejected together,
not just the piece that was wrong. Counting rejected evidence rows therefore counts send-backs
times the requirements each touched, not defects: a single send-back of a task serving five
requirements reads as five rejections. To count how often work came back, count the send-backs
(`task_transitions` rows with `to_status = 'revision_needed'`), or distinct tasks and commits among
rejected `requirement_evidence` rows (`review_state = 'rejected'`), not the rejected rows.

### Cost per spec counts its tasks' building and reviewing runs

The cost of a specification document is the cost of every run on its tasks: the builders' runs
and the reviewers' runs alike. Summing only the builder's runs (`runs.agent` = the task's
assignee) understates it, and a task reviewed several times costs more than one built once. Join
`turn_usage` (`api_equivalent_usd_micros`, millionths of a dollar; empty when the run was not
priced, which is not zero) through `runs.task_id` to the document's tasks, whoever ran them. Runs
that touched no task of the document (authoring the spec, chat) are not part of it.

## Added by agents
"""


def seed(project_root: Path, private_root: Path) -> Optional[Dict[str, Any]]:
    """Seed the note into the vault of *project_root*; None when it is already there."""
    return vault.seed_source(
        project_root,
        private_root,
        entry_id=NOTE_ID,
        name=NOTE_NAME,
        type="note",
        content=NOTE_TEXT,
        added_by="hub",
    )


async def seed_project(session: AsyncSession, project_id: str, project_root: Path) -> None:
    """`seed` for one project, logging rather than raising: a project that cannot take the note
    still opens, and the next start or open tries again."""
    try:
        settings = await vault.get_settings(session, project_id)
        private_root = Path(settings["effective_private_location"])
        if await asyncio.to_thread(seed, project_root, private_root) is not None:
            logger.info("data_notes_seeded project_id=%s", project_id)
    except Exception:  # noqa: BLE001 -- best-effort; reported, never fatal to an open
        logger.warning("could not seed the data note in %s", project_id, exc_info=True)


async def seed_every_project() -> None:
    """Seed the note into every registered project whose folder is reachable (Hub startup)."""
    from . import project_workspace
    from .db.engine import async_session_factory
    from .db.models import Project

    async with async_session_factory() as session:
        project_ids = (await session.execute(select(Project.id))).scalars().all()
        for project_id in project_ids:
            try:
                workspace = await project_workspace.resolve_project_workspace(session, project_id)
            except project_workspace.ProjectWorkspaceError:
                continue  # an unavailable project is seeded when it is opened again
            await seed_project(session, project_id, workspace.root)
