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
from hub.db.models import Agent, AIJob, JobRun, Loop, Run, SpecDocument, Task
from hub.scheduler import _agents_that_are_free, _stall_run_to_increment, resolve_reviewer
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
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

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
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

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
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

    assert choice.agent is None
    assert choice.rung == "unresolved"
    assert AUTHOR in choice.reason


async def test_rung_2_no_declaration_falls_back_to_availability(app, auth_headers, bind_runner):
    """Nothing configured: no document, no declaration, no charter. The flow still staffs it."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, "reviewer-one")

    async with async_session_factory() as db:
        task = await _task(db)
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

    assert choice.agent == "reviewer-one"
    assert choice.rung == "available"


async def test_rung_3_nobody_eligible_surfaces_a_reason(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, AUTHOR)

    async with async_session_factory() as db:
        task = await _task(db)
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

    assert choice.agent is None
    assert choice.rung == "unstaffed"
    assert "could not staff this step" in choice.reason


async def test_rung_3_reason_is_this_exact_string_for_a_completed_task(
    app, auth_headers, bind_runner
):
    """`an-unstaffed-review-names-its-holders` task 2.3, R8's own rule: assert the joined string
    with `==` against a literal, not a substring -- five earlier rounds missed the join itself by
    checking only fragments of it."""
    await _roster(app, auth_headers, bind_runner, AUTHOR)

    async with async_session_factory() as db:
        task = await _task(db, status="completed")
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

    assert choice.reason == (
        "could not staff this step: no reviewer is free. ladder-author is the one that completed "
        "this task. Land it, on the task, to review it yourself."
    )


async def test_rung_3_reason_is_this_exact_string_for_an_under_review_task(
    app, auth_headers, bind_runner
):
    """The sibling of the test above, on the other status `own_review_remedy` answers -- R8's own
    note that every earlier round measured only the `completed` join and missed that
    `capitalize_first` matters on this one."""
    await _roster(app, auth_headers, bind_runner, AUTHOR)

    async with async_session_factory() as db:
        task = await _task(db, status="under_review")
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

    assert choice.reason == (
        "could not staff this step: no reviewer is free. ladder-author is the one that completed "
        "this task. Decide it yourself: approve, reject, or send it back with revision_needed."
    )


# ---------------------------------------------------------------------------
# 4.2 — "free" is not running AND holding no active task
# ---------------------------------------------------------------------------


async def test_an_agent_running_a_turn_is_not_selected(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, AUTHOR, "busy-one", "free-one")

    async with async_session_factory() as db:
        db.add(Run(id="run-busy-one", project_id="proj-test", agent="busy-one", status="running"))
        await db.commit()
        task = await _task(db)
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

    # `busy-one` sorts first by name, so picking it would be the default and picking `free-one`
    # is the rule working.
    assert choice.agent == "free-one"


async def _live_loop(db):
    """A loop nothing has ended, so its firing will walk the tasks that carry its id."""
    db.add(
        AIJob(
            id="job-held",
            project_id="proj-test",
            name="Held",
            agent="aa-loaded",
            message="work the queue",
            cron="*/5 * * * *",
            session_mode="new",
            enabled=True,
        )
    )
    await db.commit()
    db.add(Loop(id="loop-held", project_id="proj-test", job_id="job-held", purpose="held"))
    await db.commit()
    return "loop-held"


async def _held_elsewhere(db, *, loop_id):
    db.add(
        Task(
            id="task-held",
            project_id="proj-test",
            title="already assigned elsewhere",
            status="assigned",
            assignee="aa-loaded",
            loop_id=loop_id,
        )
    )
    await db.commit()


async def test_an_agent_holding_an_active_task_is_not_selected(app, auth_headers, bind_runner):
    """Not-running alone was rejected in D4: an agent can hold three assigned tasks and be idle
    between turns, which is exactly the pile-up rung 2 exists to avoid.

    **That pile-up is a queue something will serve** (`a-task-nothing-will-move-holds-nobody`,
    design D7), so the holding is staged in a live loop, whose firing will brief `aa-loaded` on it.
    The sibling below stages the same task outside every loop and asserts the opposite."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, "aa-loaded", "zz-free")

    async with async_session_factory() as db:
        await _held_elsewhere(db, loop_id=await _live_loop(db))
        task = await _task(db)
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

    assert choice.agent == "zz-free"


async def test_an_agent_holding_only_a_task_outside_every_loop_is_selected(
    app, auth_headers, bind_runner
):
    """The same task with no `loop_id`: nothing will ever move it, so it is a bookmark, and a
    bookmark does not withdraw its assignee from review (design D1). `aa-loaded` sorts first."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, "aa-loaded", "zz-free")

    async with async_session_factory() as db:
        await _held_elsewhere(db, loop_id=None)
        task = await _task(db)
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

    assert choice.agent == "aa-loaded"


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
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

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
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

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
        choice = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

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
        alone = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )
        # The author *is* free by every measure except being the author.
        assert await _agents_that_are_free(db, "proj-test") == [AUTHOR]

    assert alone.agent is None
    assert alone.rung == "unstaffed"

    await _roster(app, auth_headers, bind_runner, "second-agent")

    async with async_session_factory() as db:
        task = await db.get(Task, "task-ladder")
        staffed = await resolve_reviewer(
            db,
            task,
            project_id="proj-test",
            exclude={AUTHOR: "is the one that completed this task"},
        )

    assert staffed.agent == "second-agent"
    assert staffed.rung == "available"


# ---------------------------------------------------------------------------
# 2.10 (`an-unstaffed-review-names-its-holders`) — a stalled tick with an over-budget reason
# still matches the row it should coalesce into
# ---------------------------------------------------------------------------


async def test_a_stall_reason_over_budget_still_matches_the_fitted_row(app):
    """2.10, rewritten by R8. As originally written this test compared the *raw* `stall_reason`
    and could never fail once task 2.4 bounds every rung-3 reason to 500 characters --
    `fit_error_summary` then returns an already-short reason unchanged, so comparing the raw
    string is identical to comparing the fitted one (F190's shape: a green test that cannot see
    its own subject).

    The comparison this test actually guards -- `latest.error_summary != fit_error_summary
    (stall_reason)` -- already shipped, for the sibling directory's own D6, at
    `scheduler.py:978`, and had no test of its own (`_stall_run_to_increment` appears nowhere
    else in `hub/tests`). It stays here because this change is what makes a long, unfitted stall
    reason ordinary.

    *Mutation:* compare the raw `stall_reason` instead of `fit_error_summary(stall_reason)`. The
    test must fail, because the row's own `error_summary` is stored fitted (500 chars, `@validates`
    on `JobRun`) while the argument passed in here is the raw 600.
    """
    reason = "z" * 600
    async with async_session_factory() as db:
        job = AIJob(
            id="job-stall-fit",
            project_id="proj-test",
            name="Stall fit",
            agent="stall-owner",
            message="work the queue",
            cron="*/5 * * * *",
            session_mode="new",
            enabled=True,
        )
        db.add(job)
        await db.commit()
        run = JobRun(
            id="run-stall-fit-first",
            job_id=job.id,
            project_id="proj-test",
            status="skipped",
            trigger="scheduled",
            error_summary=reason,
        )
        db.add(run)
        await db.commit()
        # The model's own fit (`a-refusal-names-a-remedy-that-works` D2), not this task's --
        # asserted so the premise below is what it looks like it is.
        assert len(run.error_summary) == 500
        assert run.error_summary.endswith("…")

        counted = await _stall_run_to_increment(
            db, job.id, reason, exclude_run_id="run-stall-fit-second"
        )

    assert counted is not None
    assert counted.id == run.id


async def test_a_stall_reason_that_actually_changed_does_not_match(app):
    """2.10's negative case: a genuinely different reason (not merely a fitting artefact) must
    not be coalesced into the previous row, or a queue that changed shape would hide it."""
    async with async_session_factory() as db:
        job = AIJob(
            id="job-stall-fit-changed",
            project_id="proj-test",
            name="Stall fit changed",
            agent="stall-owner",
            message="work the queue",
            cron="*/5 * * * *",
            session_mode="new",
            enabled=True,
        )
        db.add(job)
        await db.commit()
        run = JobRun(
            id="run-stall-fit-changed-first",
            job_id=job.id,
            project_id="proj-test",
            status="skipped",
            trigger="scheduled",
            error_summary="y" * 600,
        )
        db.add(run)
        await db.commit()

        counted = await _stall_run_to_increment(
            db, job.id, "z" * 600, exclude_run_id="run-stall-fit-changed-second"
        )

    assert counted is None
