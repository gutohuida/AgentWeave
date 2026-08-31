"""F163: landing a loop's work costs three hand transitions, two of which begin as refusals.

The measurement, from the 2026-08-30 drive: a loop's task sits `completed`, still held by the agent
that completed it. `PATCH {"status": "approved"}` is refused — `completed` does not reach `approved`
in the map. `PATCH {"status": "under_review"}` is refused — `_guard_reviewer_is_not_the_author` says
the task still names its author. Only the third shape works, and the operator has to rediscover it
each time. Both refusals are correct; neither is the operator's mistake.

`POST /tasks/{id}/land` is the composition that already had to happen: release the author's hold,
`-> under_review`, `-> approved`. Nothing new is legal — the map is untouched, and
`test_the_map_is_not_widened` is what fails if that is ever quietly reversed.

**What these tests are actually about is the transaction.** The gate is pre-evaluated so that a
refused landing gives approval's own refusal rather than a failure found two steps in, but a
pre-check is not what makes the action safe: `apply_transition` stages and does not commit, and it
is the single commit at the end of the handler that makes "refused for any reason leaves nothing
half-applied" true. `test_a_refusal_on_the_second_step_leaves_the_hold_in_place` is the one that
observes that directly, by forcing a refusal the pre-check cannot foresee.
"""

import pytest
from sqlalchemy import select

from hub import run_liveness, task_integration, task_transition_service, worktrees
from hub.agent_auth import hash_run_token
from hub.api.v1 import tasks as tasks_route
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, Task, TaskTransition
from hub.task_transition_service import ORIGIN_ACTOR, ActorNotPermittedError
from hub.task_transitions import TRANSITIONS

from .test_approval_waits_for_the_turn import LiveTurn
from .test_loop_lands_its_work import commit_on_task_branch, loop_task, make_loop
from .test_task_integration import (
    TASKS,
    commits_on,
    files_on,
    git,
    integrations,
    make_repo,
    set_main_branch,
)

AGENT_TASKS = "/api/v1/agent-actions/tasks"

#: The run the `builder` fixture below owns. Named as a constant because the liveness registry is
#: keyed by run id, and a test that registered the wrong key would prove nothing while passing.
BUILDER_RUN = "run-landing"


@pytest.fixture
async def builder():
    """The agent that does the work, and the run it does it in.

    Declared here rather than imported from a sibling, for the reason
    `test_loop_lands_its_work.builder` states: a fixture imported by name shadows itself in every
    signature that takes it, which ten sibling files each declare their own to avoid.
    """
    async with async_session_factory() as session:
        session.add(Agent(id="ag-landing", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id=BUILDER_RUN,
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_landing-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_landing-secret"}


async def held_and_completed(app, auth_headers, run_headers, task_id):
    """Drive *task_id* to `completed`, held by the agent that completed it.

    This is the shape F163 is about, and building it through the two real surfaces is the point:
    the operator assigns, and the **agent's own run** claims and completes, so
    `agent_that_completed` really answers `builder` and `assignee` really names them. A task driven
    to `completed` by the operator alone has no author to release and would let the landing action
    pass for the wrong reason.
    """
    assigned = await app.patch(
        f"{TASKS}/{task_id}", json={"assignee": "builder"}, headers=auth_headers
    )
    assert assigned.status_code == 200, assigned.text
    for next_status in ("in_progress", "completed"):
        moved = await app.patch(
            f"{AGENT_TASKS}/{task_id}", json={"status": next_status}, headers=run_headers
        )
        assert moved.status_code == 200, moved.text
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        assert task.status == "completed"
        assert (
            task.assignee == "builder"
        ), "the window this closes is a task still held by its author"
        completer = await task_transition_service.agent_that_completed(session, task_id)
        assert completer == "builder", "the author has to be recorded, or the guards are asleep"


async def land(app, auth_headers, task_id):
    return await app.post(f"{TASKS}/{task_id}/land", headers=auth_headers)


async def history(task_id):
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(TaskTransition)
                .where(TaskTransition.task_id == task_id)
                .order_by(TaskTransition.sequence)
            )
        ).scalars()
        return [
            (row.from_status, row.to_status, row.actor_kind, row.actor_agent, row.origin)
            for row in rows
        ]


async def task_row(task_id):
    async with async_session_factory() as session:
        return await session.get(Task, task_id)


@pytest.fixture
def live_builder_turn(request):
    """Register the handle a live turn holds for `builder`'s run, and always remove it.

    `run_liveness.active_ptys` is module-global state shared with every other test in the session,
    so the teardown is unconditional rather than at the end of the test body.
    """
    request.addfinalizer(lambda: run_liveness.active_ptys.pop(BUILDER_RUN, None))

    def go_live():
        run_liveness.active_ptys[BUILDER_RUN] = LiveTurn()

    return go_live


# ---------------------------------------------------------------------------
# 6.1 — one action reaches `approved` and merges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_action_lands_a_loops_completed_work(app, auth_headers, builder, tmp_path):
    """Task 6.1, arm 1: one call, and the work is in the product.

    The three assertions that matter are the last three: `approved`, a `MERGED` integration naming
    the turn's commit, and that commit reachable from `main`. The status alone would pass against a
    route that transitioned and merged nothing, which is F162's whole shape.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Landing loop")
    task = await loop_task(app, auth_headers, loop)
    await held_and_completed(app, auth_headers, builder, task)

    work = commit_on_task_branch(tmp_path, task, "feature.py", "print('hi')\n")
    git(tmp_path, "checkout", "-q", "main")
    assert work not in commits_on(tmp_path, "main")

    landed = await land(app, auth_headers, task)
    assert landed.status_code == 200, landed.text
    assert landed.json()["status"] == "approved"
    assert landed.json()["assignee"] is None

    recorded = await integrations(app, auth_headers, task)
    assert [row["outcome"] for row in recorded] == [task_integration.MERGED]
    assert recorded[0]["commit_sha"] == work
    assert work in commits_on(tmp_path, "main")
    assert "feature.py" in files_on(tmp_path, "main")


# ---------------------------------------------------------------------------
# 6.5 — the history records what happened, and says the operator asked for it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_history_records_every_transition_as_the_operators_own(
    app, auth_headers, builder, tmp_path
):
    """Task 6.5. Both moves are recorded, both `operator`, both **actor-caused**.

    `origin` is the assertion this test exists for. `ORIGIN_RUNTIME` means the Hub made a move at a
    moment the actor did not choose, and the divergence check reads it to answer *did this run
    advance its task* — recording either of these as runtime would put a claim in an integrity
    record that nothing observed. The operator asked for all of this; saying it in one word instead
    of three does not make two of the steps the system's own bookkeeping.

    **The release of the author's hold is not among the rows, and cannot be.** `TaskTransition`
    records a move from one *status* to another; `assignee` has no history table, and the ordinary
    PATCH route folds the same write into the same request (F70's ordering, `tasks.py:1262`). The
    spec delta said "the release of its author's hold, the move into review, and the approval" and
    was corrected to say what the record can hold; what remains checkable about the release is the
    task, asserted below.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="History loop")
    task = await loop_task(app, auth_headers, loop)
    await held_and_completed(app, auth_headers, builder, task)
    commit_on_task_branch(tmp_path, task, "feature.py", "print('hi')\n")
    git(tmp_path, "checkout", "-q", "main")

    before = await history(task)
    landed = await land(app, auth_headers, task)
    assert landed.status_code == 200, landed.text

    assert (await history(task))[len(before) :] == [
        ("completed", "under_review", "operator", None, ORIGIN_ACTOR),
        ("under_review", "approved", "operator", None, ORIGIN_ACTOR),
    ]
    assert (await task_row(task)).assignee is None


# ---------------------------------------------------------------------------
# 6.2 — no new edge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_map_is_not_widened(app, auth_headers, builder):
    """Task 6.2. The shortcut is a composition, never an edge.

    An added `completed -> approved` would let *every* task in the product skip review with only a
    guard in the way — and a guard is one condition, where the map is a structure. Asserted on the
    map itself **and** through the route, because the map is what governs and the 409 is what an
    operator would notice if it stopped.
    """
    assert "approved" not in TRANSITIONS["completed"]

    loop = await make_loop(app, auth_headers, name="Map loop")
    task = await loop_task(app, auth_headers, loop)
    await held_and_completed(app, auth_headers, builder, task)

    refused = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)
    assert refused.status_code == 409, refused.text


# ---------------------------------------------------------------------------
# 6.1 / 6.3 — refusals, and what they leave behind
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_landing_is_refused_while_the_turn_is_live(
    app, auth_headers, builder, live_builder_turn, tmp_path
):
    """Task 6.1, arm 3: F162 reached through the new door, refused with approval's own refusal.

    The refusal has to be the *same typed* one, not a second sentence that means the same thing —
    a surface renders `detail["unfinished"]`, and a route that invented its own message would be a
    second place for the wording of a live turn to drift.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Live loop")
    task = await loop_task(app, auth_headers, loop)
    await held_and_completed(app, auth_headers, builder, task)
    live_builder_turn()

    refused = await land(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "gate_unsatisfied"
    assert detail["unfinished"] == [{"agent": "builder", "run_id": BUILDER_RUN}]

    # Nothing moved, nothing was released, nothing was merged.
    row = await task_row(task)
    assert row.status == "completed"
    assert row.assignee == "builder"
    assert await integrations(app, auth_headers, task) == []
    assert [entry[1] for entry in await history(task)] == ["in_progress", "completed"]


@pytest.mark.asyncio
async def test_the_gate_is_decided_before_anything_is_attempted(
    app, auth_headers, builder, live_builder_turn, monkeypatch, tmp_path
):
    """Task 6.3, the pre-check itself — and the only way to see it.

    **The pre-check is invisible from outside**, and saying so is worth more than a test that
    pretends otherwise. Remove it and the landing still refuses with the identical body: step three
    (`-> approved`) evaluates the same gate, raises the same `GateUnsatisfiedError`, and the
    transaction rolls the staged `under_review` back. Every black-box assertion in this file passes
    either way, which is exactly what makes an unobserved line rot.

    So this observes the ordering directly. What the pre-check buys is that a refusal approval would
    have given is decided *before* the composition starts moving, rather than found two steps in —
    and that is a property of the call sequence, not of the response.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Order loop")
    task = await loop_task(app, auth_headers, loop)
    await held_and_completed(app, auth_headers, builder, task)
    live_builder_turn()

    attempted = []

    async def record(session, task_row_, to_status, actor, origin="actor"):
        attempted.append(to_status)
        raise AssertionError("the landing action moved a task it was about to refuse")

    monkeypatch.setattr(tasks_route, "apply_transition", record)

    refused = await land(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "gate_unsatisfied"
    assert attempted == [], "the gate was decided after a transition was already attempted"


@pytest.mark.asyncio
async def test_a_refusal_on_the_second_step_leaves_the_hold_in_place(
    app, auth_headers, builder, monkeypatch, tmp_path
):
    """Task 6.3. A refusal the pre-check cannot foresee, and the task is exactly as it was found.

    The refusal is forced rather than provoked, and that is deliberate: **in the composition as
    built, `_guard_reviewer_is_not_the_author` can never fire.** The hold is released first, and
    that guard returns immediately for a task nobody holds. So the only way to observe what the
    transaction guarantees is to make step two refuse, which is what this does — and what it proves
    is the general property the delta claims, that a refusal *for any reason* leaves the task as it
    was, rather than only for the reasons the pre-check knows about.

    Without one commit around all three, this test fails on its first assertion: the assignee is
    written before step two runs, and a handler that committed per step would have released the
    author's hold on a task that never reached review.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Half loop")
    task = await loop_task(app, auth_headers, loop)
    await held_and_completed(app, auth_headers, builder, task)
    commit_on_task_branch(tmp_path, task, "feature.py", "print('hi')\n")
    git(tmp_path, "checkout", "-q", "main")
    before = await history(task)

    async def refuse_the_entry(session, task_row_, to_status, actor):
        if to_status == "under_review":
            raise ActorNotPermittedError("no entry to review for this task")

    monkeypatch.setattr(
        task_transition_service, "_guard_reviewer_is_not_the_author", refuse_the_entry
    )

    refused = await land(app, auth_headers, task)
    assert refused.status_code == 403, refused.text

    row = await task_row(task)
    assert row.assignee == "builder", "the author's hold survived a refusal on the step after it"
    assert row.status == "completed"
    assert await history(task) == before
    assert await integrations(app, auth_headers, task) == []


@pytest.mark.asyncio
async def test_landing_is_refused_on_a_task_that_is_not_completed(app, auth_headers, builder):
    """The action carries *completed* work; anything else is refused rather than adapted.

    A task already `under_review` has a one-call approval that works, so landing would add nothing
    but a cleared assignee — which, on a task a reviewer holds, is the review taken off them
    without saying so.
    """
    loop = await make_loop(app, auth_headers, name="Early loop")
    task = await loop_task(app, auth_headers, loop)

    refused = await land(app, auth_headers, task)
    assert refused.status_code == 409, refused.text
    assert "pending" in refused.json()["detail"]
    assert (await task_row(task)).status == "pending"


@pytest.mark.asyncio
async def test_landing_an_unknown_task_is_a_404(app, auth_headers):
    missing = await land(app, auth_headers, "tsk-nope")
    assert missing.status_code == 404, missing.text


# ---------------------------------------------------------------------------
# The branch this leaves behind
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_landing_releases_the_checkout_and_keeps_the_branch(
    app, auth_headers, builder, tmp_path
):
    """`approved` is terminal for a workspace, and landing reaches it by the same route.

    Asserted because the landing action is a second way into a terminal status, and every
    end-of-life behaviour approval carries has to arrive with it — otherwise the shortcut is a
    quieter approval rather than the same one.
    """
    make_repo(tmp_path)
    await set_main_branch("main")

    loop = await make_loop(app, auth_headers, name="Release loop")
    task = await loop_task(app, auth_headers, loop)
    await held_and_completed(app, auth_headers, builder, task)
    commit_on_task_branch(tmp_path, task, "feature.py", "print('hi')\n")
    git(tmp_path, "checkout", "-q", "main")

    landed = await land(app, auth_headers, task)
    assert landed.status_code == 200, landed.text

    branch = worktrees.task_branch_name(task)
    assert (
        git(tmp_path, "rev-parse", "--verify", branch).returncode == 0
    ), "the branch is the record of what the task did and is kept"
