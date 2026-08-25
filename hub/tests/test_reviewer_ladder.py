"""`loop-becomes-a-flow` group 4 — a flow resolves a reviewer by declaration, then by availability.

Design D4's ladder, one rung per test:

```
   1.  the task's declared reviewer, if it resolves
   1b. a declaration that does NOT resolve  -> surface it; never substitute
   2.  no declaration: any agent not running and holding no active task
   3.  surface: "could not staff this step"
```

**Rung 2 is the one the change is really about**, and its existence is an answer to a stated
objection: *"I don't want to end up in a old problem where having a squad to develop is a price
that you need to pay before even starting development."* With nothing configured — no document, no
declaration, no charter — rung 2 staffs the review. Every test here that reaches it does so with a
bare roster.

**Rung 1b is the one with an argument behind it**, and it is why `resolve_reviewer` calls
`review_turn.resolve_declared_reviewer` rather than resolving the declaration a second time. Two
implementations of "who did the document name" is the drift shape this repo has been bitten by
three times, and the shipped one already carries the reasoning: an operator reading "reviewed by
critic" when `critic` does not exist and `auditor` reviewed it has been told something false about
who checked the work.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, SpecDocument, Task
from hub.scheduler import _agents_that_are_free, resolve_reviewer
from hub.spec_payload import SCHEMA_VERSION, embed_payload

from .test_agent_trigger import _init_repo
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

AUTHOR = "ladder-author"


async def _task(db, *, task_id="task-ladder", document_id=None, task_key=None, status="completed"):
    task = Task(
        id=task_id,
        project_id="proj-test",
        title="finished work awaiting a reviewer",
        status=status,
        spec_document_id=document_id,
        spec_task_key=task_key,
    )
    db.add(task)
    await db.commit()
    return task


async def _declare_reviewer(repo, db, *, name):
    """A document on disk declaring *name* as the reviewer of task key `t1`.

    Written with the real `embed_payload` rather than a hand-rolled envelope: a fixture that fakes
    the envelope stops testing the thing that reads it the moment the envelope changes.
    """
    document = repo / "spec" / "ladder.html"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(
        embed_payload(
            {"schema_version": SCHEMA_VERSION, "tasks": [{"key": "t1", "reviewer": name}]}
        ),
        encoding="utf-8",
    )
    db.add(
        SpecDocument(
            id="doc-ladder",
            project_id="proj-test",
            path="spec/ladder.html",
            title="Ladder",
            phase="current",
            kind="capability",
        )
    )
    await db.commit()


# ---------------------------------------------------------------------------
# 4.1 — each rung, independently
# ---------------------------------------------------------------------------


async def test_rung_1_a_declared_reviewer_that_resolves_is_used(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic", "auditor")

    async with async_session_factory() as db:
        await _declare_reviewer(repo, db, name="critic")
        task = await _task(db, document_id="doc-ladder", task_key="t1")
        choice = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})

    assert choice.agent == "critic"
    assert choice.rung == "declared"
    # `auditor` is free and alphabetically first. A declaration that resolves outranks availability,
    # or the declaration would be advisory.
    assert choice.agent != "auditor"


async def test_rung_1b_a_declaration_that_does_not_resolve_is_surfaced_never_substituted(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """The rung this ladder was amended for.

    It said "fall back to availability" until 2026-08-24, when `resolve_declared_reviewer` shipped
    doing the opposite deliberately. `auditor` is on the roster, free, and must not be chosen.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, "auditor")

    async with async_session_factory() as db:
        await _declare_reviewer(repo, db, name="critic")
        task = await _task(db, document_id="doc-ladder", task_key="t1")
        choice = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})

    assert choice.agent is None
    assert choice.rung == "unresolved"
    assert "critic" in choice.reason
    assert choice.reason != ""


async def test_rung_1b_also_covers_a_declaration_naming_the_author(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """A declared reviewer that resolves to the agent that completed the work.

    Rung 1b rather than rung 2, and the distinction is the same one: the document named somebody
    who may not do it, which is a fact about the document, not about who happens to be free.
    Silently staffing `auditor` here would be the substitution 1b exists to refuse — and the
    operator would read the review as having been done by the person the document names.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, "auditor")

    async with async_session_factory() as db:
        await _declare_reviewer(repo, db, name=AUTHOR)
        task = await _task(db, document_id="doc-ladder", task_key="t1")
        choice = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})

    assert choice.agent is None
    assert choice.rung == "unresolved"
    assert AUTHOR in choice.reason


async def test_rung_2_no_declaration_falls_back_to_availability(app, auth_headers, bind_runner):
    """Nothing configured: no document, no declaration, no charter. The flow still staffs it."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, "reviewer-one")

    async with async_session_factory() as db:
        task = await _task(db)
        choice = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})

    assert choice.agent == "reviewer-one"
    assert choice.rung == "available"


async def test_rung_3_nobody_eligible_surfaces_a_reason(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, AUTHOR)

    async with async_session_factory() as db:
        task = await _task(db)
        choice = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})

    assert choice.agent is None
    assert choice.rung == "unstaffed"
    assert "could not staff this step" in choice.reason


# ---------------------------------------------------------------------------
# 4.2 — "free" is not running AND holding no active task
# ---------------------------------------------------------------------------


async def test_an_agent_running_a_turn_is_not_selected(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, AUTHOR, "busy-one", "free-one")

    async with async_session_factory() as db:
        db.add(Run(id="run-busy-one", project_id="proj-test", agent="busy-one", status="running"))
        await db.commit()
        task = await _task(db)
        choice = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})

    # `busy-one` sorts first by name, so picking it would be the default and picking `free-one`
    # is the rule working.
    assert choice.agent == "free-one"


async def test_an_agent_holding_an_active_task_is_not_selected(app, auth_headers, bind_runner):
    """Not-running alone was rejected in D4: an agent can hold three assigned tasks and be idle
    between turns, which is exactly the pile-up rung 2 exists to avoid."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, "aa-loaded", "zz-free")

    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-held",
                project_id="proj-test",
                title="already assigned elsewhere",
                status="assigned",
                assignee="aa-loaded",
            )
        )
        await db.commit()
        task = await _task(db)
        choice = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})

    assert choice.agent == "zz-free"


async def test_a_completed_task_does_not_make_its_assignee_busy(app, auth_headers, bind_runner):
    """`completed` is not a live status, so holding one does not make an agent unavailable.

    Worth pinning: if it did, the first agent to finish anything would stop being eligible to
    review for as long as its own work sat unapproved, and a two-agent project would deadlock the
    moment both had finished something.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, "aa-finished")

    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-finished-elsewhere",
                project_id="proj-test",
                title="finished, awaiting review",
                status="completed",
                assignee="aa-finished",
            )
        )
        await db.commit()
        task = await _task(db)
        choice = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})

    assert choice.agent == "aa-finished"


async def test_free_agents_are_returned_in_a_stable_order(app, auth_headers, bind_runner):
    """Two firings must staff the same agent. "Whichever row came back first" is not the
    deterministic selection the proposal requires."""
    await _roster(app, auth_headers, bind_runner, "zeta", "alpha", "mid")

    async with async_session_factory() as db:
        first = await _agents_that_are_free(db, "proj-test")
        second = await _agents_that_are_free(db, "proj-test")

    assert first == second == sorted(first)


# ---------------------------------------------------------------------------
# 4.3 — no runner bound is unavailable, not an error
# ---------------------------------------------------------------------------


async def test_an_agent_with_no_runner_bound_is_not_selected(app, auth_headers, bind_runner):
    """`trigger_agent_directly` refuses to spawn a runnerless agent, so selecting one would turn a
    staffing question into a launch failure one step later.

    Unavailable rather than an error: the firing reports that it could not staff the step, which is
    something the operator can act on, instead of dying in the spawn path.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    # On the roster, alphabetically first, and deliberately never given a runner.
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"aa-unbound": {"runner": "claude"}}}},
        headers=auth_headers,
    )

    async with async_session_factory() as db:
        task = await _task(db)
        choice = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})

    assert choice.agent is None
    assert choice.rung == "unstaffed"
    assert "aa-unbound" not in (choice.agent or "")


async def test_an_archived_agent_is_not_selected(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, AUTHOR, "aa-gone", "zz-here")

    async with async_session_factory() as db:
        from sqlalchemy import select

        gone = (
            (
                await db.execute(
                    select(Agent).where(Agent.project_id == "proj-test", Agent.name == "aa-gone")
                )
            )
            .scalars()
            .one()
        )
        gone.lifecycle = "archived"
        await db.commit()
        task = await _task(db)
        choice = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})

    assert choice.agent == "zz-here"


# ---------------------------------------------------------------------------
# 4.4 — a single-agent project reaches rung 3 by the general rule
# ---------------------------------------------------------------------------


async def test_a_single_agent_project_reaches_rung_3_with_no_special_case(
    app, auth_headers, bind_runner
):
    """D4's own test of whether the ladder is right, and 4.4 asks for the *path* rather than only
    the outcome — so this asserts the rung, and that the author was excluded by the general
    exclusion rather than by a branch about project size.

    The proof that no special case exists: adding one more agent to the same project, changing
    nothing else, produces a staffed review. If a single-agent branch existed, that would not
    follow from the same code.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR)

    async with async_session_factory() as db:
        task = await _task(db)
        alone = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})
        # The author *is* free by every measure except being the author.
        assert await _agents_that_are_free(db, "proj-test") == [AUTHOR]

    assert alone.agent is None
    assert alone.rung == "unstaffed"

    await _roster(app, auth_headers, bind_runner, "second-agent")

    async with async_session_factory() as db:
        task = await db.get(Task, "task-ladder")
        staffed = await resolve_reviewer(db, task, project_id="proj-test", exclude={AUTHOR})

    assert staffed.agent == "second-agent"
    assert staffed.rung == "available"
