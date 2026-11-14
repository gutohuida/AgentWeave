"""Agents are told how to choose and shape a chart (`dashboards-that-feel-alive-and-draw-right-the-
first-time`, FR-7 `ac-guidance` and FR-8 `ac-examples-draw`).

The guidance is read from what an agent is actually offered: the save tool's description as the
MCP server lists it, and the tool line of the agent's context. The worked examples are read back
out of the note a project's vault was seeded with, not from the constant they were written from,
and each is run through the query service and the drawing check as a panel of its stated kind.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

import pytest

from hub import dashboard_query, data_notes, vault
from hub.api.v1 import agents as agent_routes
from hub.api.v1.dashboards import drawing_warning
from hub.db.engine import async_session_factory
from hub.db.models import Run, Task
from hub.mcp_server import mcp

#: Each kind of question, and the phrase in the guidance naming the kind that suits it.
QUESTIONS = {
    "number": "One figure",
    "bar": "A ranking or comparison",
    "stacked_bar": "Parts of a whole",
    "line": "Change over time",
    "table": "Detail rows",
}
#: The four shaping rules, each as words the guidance must carry.
SHAPING = (
    ("order rows as drawn", r"[Oo]rder the rows as they should be drawn|order rows as they should"),
    ("about 15 labels", r"about 15 labels"),
    ("time in order for a line", r"time in (ascending )?order for a line"),
    ("alias to readable names", r"[Aa]lias every column|alias columns"),
)


def _assert_guidance(text: str, where: str) -> None:
    flat = " ".join(text.split())
    for kind, question in QUESTIONS.items():
        match = re.search(re.escape(question) + r"[^.;]*?`" + kind + "`", flat, re.IGNORECASE)
        assert match, f"{where}: no kind named for {question!r} (expected `{kind}`)"
    for rule, pattern in SHAPING:
        assert re.search(pattern, flat), f"{where}: shaping rule {rule!r} missing"


@pytest.mark.asyncio
async def test_ac_guidance_the_save_tool_says_which_kind_and_how_to_shape() -> None:
    listed = {tool.name: tool for tool in await mcp.list_tools()}
    _assert_guidance(listed["save_dashboard"].description or "", "tools/list save_dashboard")

    described = [op.text for op in agent_routes._operations() if op.tool == "save_dashboard"]
    assert described, "save_dashboard is missing from the agent context's tool list"
    _assert_guidance(described[0], "agent context save_dashboard")


def _examples(note: str) -> List[Tuple[str, str]]:
    section = note.split("## Worked examples", 1)[1].split("## Added by agents", 1)[0]
    return re.findall(r"Kind: `(\w+)`\.\s*```sql\n(.*?)\n```", section, re.DOTALL)


async def _seed_tasks_and_runs(project_id: str) -> None:
    now = datetime.now(timezone.utc)
    statuses = ("completed", "completed", "failed", "running", "completed", "failed")
    async with async_session_factory() as db:
        for n in range(8):
            db.add(
                Task(
                    id=f"task-guide{n:04d}",
                    project_id=project_id,
                    title=f"t{n}",
                    description="d",
                    status="approved" if n % 2 else "pending",
                    assignee=("Builder", "Reviewer", None)[n % 3],
                )
            )
        for n, status in enumerate(statuses * 2):
            started = now - timedelta(days=n % 4, hours=n)
            db.add(
                Run(
                    id=f"run-guide{n:04d}",
                    project_id=project_id,
                    agent=("Builder", "Reviewer")[n % 2],
                    task_id=f"task-guide{n % 8:04d}",
                    status=status,
                    started_at=started,
                    ended_at=None if status == "running" else started + timedelta(minutes=5),
                )
            )
        await db.commit()


@pytest.mark.asyncio
async def test_ac_examples_draw_every_worked_example_draws_on_a_seeded_project(
    app, bind_project_workspace, tmp_path
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    project_id = (await bind_project_workspace(root)).id
    await _seed_tasks_and_runs(project_id)

    entry = vault.read_entry(
        root, vault.default_private_location(project_id), data_notes.NOTE_ID, 0
    )
    assert entry is not None, "the project's vault was not seeded with the data note"
    examples = _examples(entry["content"])
    assert sorted(kind for kind, _ in examples) == sorted(QUESTIONS), examples

    for kind, sql in examples:
        result = await dashboard_query.run_query(project_id, sql)
        assert result["rows"], f"the {kind} example returned no rows:\n{sql}"
        warning = drawing_warning(kind, result["columns"], result["rows"])
        assert warning is None, f"the {kind} example does not draw: {warning}\n{sql}"
        if kind == "line":
            days = [row[0] for row in result["rows"]]
            assert len(days) > 1 and days == sorted(days), days
        if kind in ("bar", "stacked_bar"):
            assert len(result["rows"]) <= 15


def test_a_note_seeded_before_the_examples_gets_them_appended_once(tmp_path) -> None:
    root, private = tmp_path / "project", tmp_path / "private"
    root.mkdir()
    old_text = data_notes.NOTE_TEXT.split("## Worked examples")[0] + "## Added by agents\n"
    vault.seed_source(
        root, private, entry_id=data_notes.NOTE_ID, name=data_notes.NOTE_NAME, type="note",
        content=old_text, added_by="hub",
    )  # fmt: skip

    assert data_notes.seed(root, private) is not None
    text = vault.read_entry(root, private, data_notes.NOTE_ID, 0)["content"]
    assert text.startswith(old_text), "what was there was rewritten"
    assert text.count("## Worked examples") == 1
    assert sorted(
        kind for kind, _ in re.findall(r"Kind: `(\w+)`\.\s*```sql\n(.*?)\n```", text, re.DOTALL)
    ) == sorted(
        QUESTIONS
    )  # noqa: E501
    assert data_notes.seed(root, private) is None, "seeded twice"
