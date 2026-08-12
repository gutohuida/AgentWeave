"""What the agent is told about the directory it is running in.

Change `2026-08-12-run-without-a-git-repository`, task 4.5. A writing agent in a project that
is not a git repository now runs in the project directory instead of being refused. That is a
different arrangement from a read-only agent sharing the checkout, and the difference is
load-bearing: an agent that does not know there is no repository proposes branches, offers to
commit, and reads a failed `git status` as a broken machine rather than as the arrangement.
"""

import pytest
from sqlalchemy import select

from hub.api.v1.agents import _render_hub_agent_context
from hub.db.engine import async_session_factory
from hub.db.models import Agent


async def _register(app, auth_headers, name):
    response = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": name, "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _render(agent_name, **kwargs):
    async with async_session_factory() as db:
        agent_row = (
            (
                await db.execute(
                    select(Agent).where(Agent.project_id == "proj-test", Agent.name == agent_name)
                )
            )
            .scalars()
            .first()
        )
        rendered = await _render_hub_agent_context(
            agent=agent_name,
            project_id="proj-test",
            db=db,
            session_data=None,
            agent_row=agent_row,
            work_dir="/tmp/project",
            **kwargs,
        )
    return rendered["context"]


@pytest.mark.asyncio
async def test_an_agent_with_no_repository_is_told_so(app, auth_headers):
    await _register(app, auth_headers, "placebound")

    context = await _render("placebound", isolated=False, isolation_unavailable=True)

    assert "### Your workspace" in context
    assert "not a git repository" in context
    assert "do not offer to commit or branch" in context.lower()


@pytest.mark.asyncio
async def test_an_agent_with_no_repository_is_told_it_shares_the_directory(app, auth_headers):
    """The accepted risk of design.md Decision 7, stated to the party who can act on it.

    Two writing agents in one directory can overwrite each other with no conflict to resolve.
    The Hub does not serialize them, so the only mitigation available is that each knows.
    """
    await _register(app, auth_headers, "sharer")

    context = await _render("sharer", isolated=False, isolation_unavailable=True)

    assert "same directory" in context
    assert "overwrite each other" in context


@pytest.mark.asyncio
async def test_a_read_only_agent_is_not_told_the_repository_is_missing(app, auth_headers):
    """Sharing by configuration inside a real repository. Nothing about git is absent, so
    claiming it is would be false — and would tell an agent that can read the repository not
    to try."""
    await _register(app, auth_headers, "reader")

    context = await _render("reader", isolated=False, isolation_unavailable=False)

    assert "This is the project's shared checkout, not an isolated worktree." in context
    assert "not a git repository" not in context


@pytest.mark.asyncio
async def test_an_isolated_agent_is_told_about_its_branch(app, auth_headers):
    """The unchanged case, pinned here because the new branch sits directly above it."""
    await _register(app, auth_headers, "isolated-one")

    context = await _render("isolated-one", isolated=True, isolation_unavailable=False)

    assert "isolated git worktree on branch `agentweave/isolated-one`" in context
    assert "not a git repository" not in context
