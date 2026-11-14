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
select b.model as "Model", count(*) as "Send-backs"
from task_transitions s join built b on b.task_id = s.task_id
where s.to_status = 'revision_needed' group by b.model
```

Send-backs per model *by reason* is a `stacked_bar`: keep `group by b.model` and give each reason
(`task_transitions.reason_class`: `defect`, `regression`, `broken-check`, `merge-needed`,
`evidence-only`, `flaky`; empty on older moves) its own column, rather than grouping by the reason
too, which gives long rows that do not stack:

```sql
with built as (  -- as above
  select tt.task_id, u.model
  from task_transitions tt join turn_usage u on u.run_id = tt.run_id
  where tt.to_status = 'completed'
    and tt.sequence = (select max(l.sequence) from task_transitions l
                       where l.task_id = tt.task_id and l.to_status = 'completed'))
select b.model as "Model",
       sum(s.reason_class = 'defect') as "Defect",
       sum(s.reason_class = 'regression') as "Regression",
       sum(s.reason_class = 'broken-check') as "Broken check",
       sum(s.reason_class = 'merge-needed') as "Merge needed",
       sum(s.reason_class = 'evidence-only') as "Evidence only",
       sum(s.reason_class = 'flaky') as "Flaky",
       sum(s.reason_class is null) as "No reason"
from task_transitions s join built b on b.task_id = s.task_id
where s.to_status = 'revision_needed'
group by b.model
order by count(*) desc
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

#: The worked examples, one per chart kind, as (kind, question, query). Each reads only `tasks` and
#: `runs`, so it draws on any project that has tasks and runs (`dashboards-that-feel-alive-and-
#: draw-right-the-first-time`, FR-8); a note seeded before they were known gets them appended.
EXAMPLES: Tuple[Tuple[str, str, str], ...] = (
    (
        "number",
        "One figure: how many runs this week",
        """select count(*) as "Runs this week"
from runs
where started_at >= date('now', '-6 days')""",
    ),
    (
        "bar",
        "A ranking: tasks per agent, the top 15",
        """select coalesce(assignee, '(unassigned)') as "Agent", count(*) as "Tasks"
from tasks
group by 1
order by 2 desc
limit 15""",
    ),
    (
        "stacked_bar",
        "A breakdown by two labels: runs per agent by status, one column per status",
        """select agent as "Agent",
       sum(status = 'completed') as "Completed",
       sum(status = 'failed') as "Failed",
       sum(status not in ('completed', 'failed')) as "Other"
from runs
group by agent
order by count(*) desc
limit 15""",
    ),
    (
        "line",
        "Change over time: runs per day",
        """select date(started_at) as "Day", count(*) as "Runs"
from runs
group by 1
order by 1""",
    ),
    (
        "table",
        "Detail rows: the latest runs",
        """select started_at as "Started", agent as "Agent", status as "Status", task_id as "Task"
from runs
order by started_at desc
limit 20""",
    ),
)

_EXAMPLES_HEADING = "## Worked examples"
_EXAMPLES_INTRO = """One query per chart kind, each drawable as it stands. Bars are drawn in the query's order, so a
ranking orders by its value and keeps the top 15; a line orders by its time; every column is
aliased to the name the legend and tooltip show. A breakdown by two labels ("X per A by B") is a
stacked bar whose query pivots: one row per A, one `sum(<b> = '<value>')` column per value of B.
Every value column stays a number, because the app formats it: round money
(`round(sum(api_equivalent_usd_micros) / 1e6, 2) as "Cost (USD)"`) and never `printf` it or join a
currency sign on, which makes it text that no chart can draw.
"""

_ADDED_BY_AGENTS = "## Added by agents"


def _section(heading: str, text: str) -> str:
    return f"### {heading}\n\n{text}\n"


def _example_heading(kind: str, question: str) -> str:
    return f"Worked example ({kind}): {question}"


def _example(kind: str, question: str, sql: str) -> str:
    return _section(_example_heading(kind, question), f"Kind: `{kind}`.\n\n```sql\n{sql}\n```")


NOTE_TEXT = f"""# {NOTE_NAME}

What the rows a dashboard query reads actually mean, and where a straightforward count gives the
wrong answer. Read this before writing a dashboard query. Every agent may add to it: when a number
surprised you and you found out why, append what you learned with `vault_append("{NOTE_ID}", ...)`,
naming the tables and columns it concerns.

## Traps

""" + (
    "\n".join(_section(h, t) for h, t in TRAPS)
    + f"\n{_EXAMPLES_HEADING}\n\n{_EXAMPLES_INTRO}\n"
    + "\n".join(_example(k, q, sql) for k, q, sql in EXAMPLES)
    + f"\n{_ADDED_BY_AGENTS}\n"
)


def seed(project_root: Path, private_root: Path) -> Optional[Dict[str, Any]]:
    """Seed the note into the vault of *project_root*; None when it is already there and holds
    every trap and worked example. A note seeded before a trap or an example was known gets the
    missing ones appended after whatever is there, agents' additions included; nothing in it is
    rewritten."""
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
        [(f"### {h}", "\n" + _section(h, t)) for h, t in TRAPS]
        + [(_EXAMPLES_HEADING, f"\n{_EXAMPLES_HEADING}\n\n{_EXAMPLES_INTRO}")]
        + [(f"### {_example_heading(k, q)}", "\n" + _example(k, q, sql)) for k, q, sql in EXAMPLES],
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
