"""The stable/per-turn/tool-surface split of the agent context (`a-copilot-agent-runs-over-acp`
task 1.11, design D5).

A Copilot agent gets its **stable** context once, in the agent file of its Hub-owned home, and the
**per-turn** context and the **tool surface** in each prompt. `_render_hub_agent_context` returns
the three beside the unchanged `context`, which Claude and Codex keep reading.

`context` for a Claude run is compared against a snapshot written from the renderer **before**
the split was added (`fixtures/context_split_claude_snapshot.md`). Set
`AW_UPDATE_CONTEXT_SNAPSHOT=1` to rewrite it -- only when a change to the context is intended.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from sqlalchemy import select

from hub.api.v1.agents import _render_hub_agent_context
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Charter, ProjectInstructions

SNAPSHOT = Path(__file__).parent / "fixtures" / "context_split_claude_snapshot.md"
QUALITY = {
    "quality": {
        "docs_threshold": "never",
        "review_required": True,
        "echo_chamber_guard": "off",
    }
}


async def _fixture(app, auth_headers, add_agent):
    await add_agent("splitter")
    await add_agent("peer")
    async with async_session_factory() as db:
        db.add(
            Charter(
                id="charter-split",
                project_id="proj-test",
                name="Builder",
                content="Build carefully.\n\n### Habits\n- test first",
            )
        )
        db.add(
            ProjectInstructions(
                project_id="proj-test", content="Use py -3.11.\n\n### Layout\n- hub/ is the Hub"
            )
        )
        agent = (
            (
                await db.execute(
                    select(Agent).where(Agent.project_id == "proj-test", Agent.name == "splitter")
                )
            )
            .scalars()
            .one()
        )
        agent.charter_id = "charter-split"
        await db.commit()


async def _render(runner="claude"):
    async with async_session_factory() as db:
        agent_row = (
            (
                await db.execute(
                    select(Agent).where(Agent.project_id == "proj-test", Agent.name == "splitter")
                )
            )
            .scalars()
            .one()
        )
        return await _render_hub_agent_context(
            agent="splitter",
            project_id="proj-test",
            db=db,
            session_data=QUALITY,
            agent_row=agent_row,
            work_dir="/tmp/project",
            isolated=False,
            access_path="mcp",
            runner=runner,
        )


def _sections(text: str) -> list[str]:
    return re.findall(r"^#{2,3} .+$", text, flags=re.MULTILINE)


@pytest.mark.asyncio
async def test_context_for_a_claude_run_is_unchanged(app, auth_headers, add_agent):
    await _fixture(app, auth_headers, add_agent)
    context = (await _render())["context"]
    if os.environ.get("AW_UPDATE_CONTEXT_SNAPSHOT"):
        SNAPSHOT.write_text(context, encoding="utf-8", newline="\n")
        pytest.skip("snapshot rewritten")
    assert context == SNAPSHOT.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_the_three_parts_hold_every_section_exactly_once(app, auth_headers, add_agent):
    await _fixture(app, auth_headers, add_agent)
    rendered = await _render("copilot")
    parts = [rendered["stable"], rendered["per_turn"], rendered["tool_surface"]]
    together = sorted(section for part in parts for section in _sections(part))
    assert together == sorted(_sections(rendered["context"]))
    assert len(together) == len(set(together)), together
    # Nothing is dropped or duplicated between sections either: the parts are the context's own
    # lines, redistributed.
    assert sorted(line for part in parts for line in part.splitlines() if line.strip()) == sorted(
        line for line in rendered["context"].splitlines() if line.strip()
    )


@pytest.mark.asyncio
async def test_charter_and_instructions_are_stable(app, auth_headers, add_agent):
    await _fixture(app, auth_headers, add_agent)
    rendered = await _render("copilot")
    for text in ("## Charter: Builder", "Build carefully.", "## Project Instructions", "py -3.11"):
        assert text in rendered["stable"]
        assert text not in rendered["per_turn"]
        assert text not in rendered["tool_surface"]
    assert "## Communication Mode" in rendered["stable"]
    assert "## Project Operating Profile" in rendered["stable"]


@pytest.mark.asyncio
async def test_workspace_is_per_turn_and_tool_surface_is_its_own(app, auth_headers, add_agent):
    await _fixture(app, auth_headers, add_agent)
    rendered = await _render("copilot")
    assert "### Your workspace" in rendered["per_turn"]
    assert "### Team" in rendered["per_turn"]
    assert "### Quality Gates" in rendered["per_turn"]
    assert "### Your workspace" not in rendered["stable"]
    surface = rendered["tool_surface"].strip()
    assert surface
    assert surface not in rendered["stable"]
    assert surface not in rendered["per_turn"]
    assert surface in rendered["context"]
