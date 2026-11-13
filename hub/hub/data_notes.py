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
from typing import Any, Dict, Optional, Tuple

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

#: The known traps, as (heading, text). The note is seeded with all of them; a note seeded before
#: a trap was added gets that trap appended at the next seeding, never rewritten.
TRAPS: Tuple[Tuple[str, str], ...] = (
    (
        "A send-back rejects every piece of evidence from that commit",
        """When a reviewer sends a task back, the evidence recorded from that commit is rejected together,
not just the piece that was wrong. Counting rejected evidence rows therefore counts send-backs
times the requirements each touched, not defects: a single send-back of a task serving five
requirements reads as five rejections. To count how often work came back, count the send-backs
(`task_transitions` rows with `to_status = 'revision_needed'`), or distinct tasks and commits among
rejected `requirement_evidence` rows (`review_state = 'rejected'`), not the rejected rows.""",
    ),
    (
        "Cost per spec counts its tasks' building and reviewing runs",
        """The cost of a specification document is the cost of every run on its tasks: the builders' runs
and the reviewers' runs alike. Summing only the builder's runs (`runs.agent` = the task's
assignee) understates it, and a task reviewed several times costs more than one built once. Join
`turn_usage` (`api_equivalent_usd_micros`, millionths of a dollar; empty when the run was not
priced, which is not zero) through `runs.task_id` to the document's tasks, whoever ran them. Runs
that touched no task of the document (authoring the spec, chat) are not part of it.""",
    ),
    (
        "A send-back's run is the reviewer's, not the builder's",
        """`task_transitions.run_id` is the run that made the move. A move to `revision_needed` is made by
the reviewer, so joining a send-back's `run_id` to `turn_usage.model` gives the reviewer's model,
not the model whose work came back. To attribute a task's send-backs (or any outcome of its
review) to the model that built it, take the model of the run behind the task's latest move to
`completed` (the builder's hand-in), and count the task's moves to `revision_needed` under it.
Keep exactly one row per task: a task sent back was built, and moved to `completed`, more than
once, and joining every one of those moves counts each send-back once per build.

```sql
with built as (  -- one row per task: the model of its latest move to completed
  select tt.task_id, u.model
  from task_transitions tt join turn_usage u on u.run_id = tt.run_id
  where tt.to_status = 'completed'
    and tt.sequence = (select max(l.sequence) from task_transitions l
                       where l.task_id = tt.task_id and l.to_status = 'completed'))
select b.model, count(*) as send_backs
from task_transitions s join built b on b.task_id = s.task_id
where s.to_status = 'revision_needed' group by b.model
```

A run's model is in `turn_usage.model` (`runs` has none); `task_transitions.sequence` orders a
task's moves (higher is later).""",
    ),
    (
        "A task's time or cost is the sum of its runs: sum per task before averaging",
        """A task has several runs: every build and every review is its own run, and a task sent back is
built and reviewed again. Averaging over the runs joined to tasks gives the average run, not the
average task. For "how long (or how much) does a task of each kind take", first sum each task's
runs (`group by` the task), then average those per-task totals over the tasks of each kind
(`tasks.spec_task_key`). A run's duration in seconds is
`(julianday(ended_at) - julianday(started_at)) * 86400`; a run with no `ended_at` has not
finished, so leave it out.""",
    ),
)

_ADDED_BY_AGENTS = "## Added by agents"


def _section(heading: str, text: str) -> str:
    return f"### {heading}\n\n{text}\n"


NOTE_TEXT = f"""# {NOTE_NAME}

What the rows a dashboard query reads actually mean, and where a straightforward count gives the
wrong answer. Read this before writing a dashboard query. Every agent may add to it: when a number
surprised you and you found out why, append what you learned with `vault_append("{NOTE_ID}", ...)`,
naming the tables and columns it concerns.

## Traps

""" + "\n".join(_section(h, t) for h, t in TRAPS) + f"\n{_ADDED_BY_AGENTS}\n"


def seed(project_root: Path, private_root: Path) -> Optional[Dict[str, Any]]:
    """Seed the note into the vault of *project_root*; None when it is already there and holds
    every trap. A note seeded before a trap was known gets the missing traps appended after
    whatever is there, agents' additions included; nothing in it is rewritten."""
    created = vault.seed_source(
        project_root,
        private_root,
        entry_id=NOTE_ID,
        name=NOTE_NAME,
        type="note",
        content=NOTE_TEXT,
        added_by="hub",
    )
    if created is not None:
        return created
    return vault.append_missing_sections(
        project_root,
        private_root,
        NOTE_ID,
        [(f"### {h}", "\n" + _section(h, t)) for h, t in TRAPS],
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
