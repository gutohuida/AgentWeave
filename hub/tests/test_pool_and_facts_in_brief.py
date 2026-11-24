"""The author's brief carries each profile's pool and the facts field
(`the-spec-process-uses-what-the-hub-already-knows`, FR-1 and FR-8)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import spec_journey
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AgentPoolEntry, Runner


async def _runner(db, rid, model):
    db.add(Runner(id=rid, project_id="proj-test", name=rid, cli="claude", model=model))


async def _agent_id(db, name):
    return (
        await db.execute(
            select(Agent.id).where(Agent.project_id == "proj-test", Agent.name == name)
        )
    ).scalar_one()


# pool-brief
@pytest.mark.asyncio
async def test_the_tasks_step_lists_every_pool_entry_and_how_to_name_one(app, add_agent):
    await add_agent("Developer")
    await add_agent("QA")
    async with async_session_factory() as db:
        await _runner(db, "runner-opus", "claude-opus-5-5")
        await _runner(db, "runner-sonnet", "claude-sonnet-5-5")
        await db.flush()
        dev, qa = await _agent_id(db, "Developer"), await _agent_id(db, "QA")
        db.add_all(
            [
                AgentPoolEntry(
                    id="pe-1",
                    project_id="proj-test",
                    agent_id=dev,
                    runner_id="runner-opus",
                    is_default=True,
                    position=0,
                ),
                AgentPoolEntry(
                    id="pe-2",
                    project_id="proj-test",
                    agent_id=dev,
                    runner_id="runner-sonnet",
                    effort="high",
                    position=1,
                ),
                AgentPoolEntry(
                    id="pe-3",
                    project_id="proj-test",
                    agent_id=qa,
                    runner_id="runner-opus",
                    is_default=True,
                ),
            ]
        )
        await db.commit()
    async with async_session_factory() as db:
        pools = await spec_journey.open_pools(db, "proj-test")
    text = spec_journey.duty(spec_journey.TASKS, size="large", pools=pools)
    dev_line = next(ln for ln in text.splitlines() if ln.startswith("  - `Developer`"))
    assert "`runner-opus` claude-opus-5-5 (default)" in dev_line
    assert "`runner-sonnet` claude-sonnet-5-5, effort high" in dev_line
    qa_line = next(ln for ln in text.splitlines() if ln.startswith("  - `QA`"))
    assert qa_line.count("`runner-") == 1 and "(default)" in qa_line
    assert "builder_entry" in text and "checker_entry" in text


def test_no_pools_adds_no_pool_lines():
    assert "builder_entry" not in spec_journey.duty(spec_journey.TASKS, size="large")


# facts-in-brief
def test_the_requirements_step_says_a_requirement_may_list_its_facts():
    text = spec_journey.duty(spec_journey.REQUIREMENTS)
    assert "`facts`" in text and "by id" in text and "lists none" in text


def test_the_submit_tool_description_names_the_facts_field():
    source = (Path(__file__).parents[1] / "hub" / "mcp_server.py").read_text(encoding="utf-8")
    block = source[source.index("def submit_spec_document") :]
    assert re.search(r"^\s+`facts`\s+optional", block, flags=re.MULTILINE)
