"""D1/D3/D4: which checkout a turn actually executes in, once a task can own one.

Phase 2 built `ensure_task_worktree` and phase 3 moved the binding above the provisioning. Neither
changed where a single turn runs — this is the phase where the column starts being read and an
agent could first see the difference, so every test here observes the **spawned process's `cwd`**
rather than a return value. That is the only fact an agent can act on, and the failure this change
exists to prevent (F58) is precisely a turn running somewhere other than where the product's own
documentation says it does.

`_spawn` raises after capturing `cwd` on purpose: the workspace decision is complete by then, the
run is recorded as failed, and no test here has to fake a runner's output to reach the one line it
is about. The pattern is `test_task_resolved_before_workspace.py`'s.

**The suite's defaults are off for these tests, and both have to be restored.**
`_no_real_worktree_provision` stubs `resolve_agent_workspace` *and* `ensure_task_worktree` to
return the project root, so a test that restores only one of them would find both schemes resolving
to the same directory and pass without discriminating anything.
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub import task_workspace, worktrees
from hub.api.v1 import agent_trigger
from hub.api.v1.agent_trigger import trigger_agent_directly
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import (
    EvidenceFootprint,
    Project,
    RequirementEvidence,
    Run,
    Task,
    TaskDependency,
    TaskRequirementLink,
)

_REAL_RESOLVE_AGENT_WORKSPACE = worktrees.resolve_agent_workspace
_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree

#: Valid task ids, in the shape `short_id` mints and `validate_task_id` accepts: `task-` plus hex.
BOUND_TASK = "task-a1b2c3d4e5f6"
OTHER_TASK = "task-0f0f0f0f0f0f"


def _git(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(path), capture_output=True, text=True, check=False
    )


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "README.md").write_text("base\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "base")
    return path


def _rev(path: Path, ref: str) -> str:
    return _git(path, "rev-parse", ref).stdout.strip()


def _real_worktrees(monkeypatch) -> None:
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    monkeypatch.setattr(worktrees, "ensure_task_worktree", _REAL_ENSURE_TASK_WORKTREE)


async def _agent(app, auth_headers, bind_runner, name, config=None):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude", **(config or {})}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(name, cli="claude")


async def _conversation(agent: str) -> str:
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent=agent, origin="operator")
        session.add(conversation)
        await session.commit()
        return conversation.id


async def _task(task_id: str, *, scheme: Optional[str] = None) -> None:
    """A task row. *scheme* is only ever passed as `'agent'`, to stand in for migration `0095`.

    Nothing in the product may write this column (design D4, and `test_task_workspace_scheme.py`
    scans the source to enforce it), so a test that needs a grandfathered task has to create one
    that way — which is exactly what the migration does, once.
    """
    async with async_session_factory() as session:
        task = Task(id=task_id, project_id="proj-test", title=task_id, status="in_progress")
        if scheme is not None:
            task.workspace_scheme = scheme
        session.add(task)
        await session.commit()


async def _set_main_branch(branch: Optional[str]) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.main_branch = branch
        await session.commit()


async def _turn(app_session_factory, *, agent: str, **kwargs) -> Optional[str]:
    """Run one turn far enough to decide its workspace, and return the `cwd` it was spawned with.

    Killing the spawn leaves two things behind that are artifacts of the harness rather than of the
    behaviour, and both are cleared here so a test can take a *second* turn — which three of the
    tests below have to, since a follow-up, a grandfathered comparison and a read-only agent are
    each a statement about two turns and not one:

    - the background task the trigger started, which ends in the `RuntimeError` above;
    - the `Run` row, still `running`, which `agent_trigger.py:439-445` refuses the next turn over.
    """
    captured = {}

    def _spawn(cmd, cwd=None, env=None, **rest):
        captured["cwd"] = cwd
        raise RuntimeError("stop here: the workspace decision is what this test is about")

    async with app_session_factory() as session:
        with patch("hub.api.v1.agent_trigger.PtySession.spawn", _spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                await trigger_agent_directly(session=session, agent=agent, **kwargs)

    # Wait for the *fact this function returns*, not for a proxy of it. Waiting on
    # `_background_runs` alone is a race: `trigger_agent_directly` returns as soon as it has
    # scheduled `_execute_run`, and on a loaded machine that task has not yet been registered when
    # the drain below looks — so the drain finds nothing, returns immediately, and `cwd` is `None`
    # for a turn that was about to resolve perfectly well. Measured: both two-turn tests failed
    # exactly this way in a full-suite run and neither ever failed alone.
    for _ in range(1000):
        if "cwd" in captured:
            break
        await asyncio.sleep(0.01)
    while agent_trigger._background_runs:
        await asyncio.gather(*list(agent_trigger._background_runs), return_exceptions=True)
    async with app_session_factory() as session:
        for run in (
            (await session.execute(select(Run).where(Run.agent == agent, Run.status == "running")))
            .scalars()
            .all()
        ):
            run.status = "failed"
        await session.commit()
    return captured.get("cwd")


@pytest.mark.asyncio
async def test_a_writing_turn_bound_to_a_task_runs_in_the_tasks_own_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """4.1 — the whole point of the change, observed at the one place an agent can see it.

    The agent's own worktree must *not* exist: a turn that provisioned both and ran in the task one
    would satisfy a `cwd` assertion alone while still leaving the shared branch that F58 rides on.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")
    await _task(BOUND_TASK)

    cwd = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="work on it",
        conversation_id=conversation_id,
        task_id=BOUND_TASK,
    )

    expected = worktrees.task_worktree_path(repo, BOUND_TASK)
    assert Path(cwd) == expected
    assert expected.is_dir()
    assert _rev(expected, "HEAD") == _rev(repo, "main")
    assert _git(expected, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == (
        worktrees.task_branch_name(BOUND_TASK)
    )
    assert not worktrees.worktree_path(repo, "writer").exists()
    assert _git(repo, "rev-parse", "--verify", "--quiet", "agentweave/writer").returncode != 0


@pytest.mark.asyncio
async def test_a_writing_turn_with_no_task_still_runs_in_the_agents_own_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """4.2 — the per-agent workspace is not legacy (design D3).

    Chat, exploration, questions and scheduled work are unbound and permanent, so this is the
    control the other tests are read against: if it ever fails, per-task isolation has been made
    unconditional rather than keyed by what the turn is about.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")

    cwd = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="just thinking out loud",
        conversation_id=conversation_id,
    )

    expected = worktrees.worktree_path(repo, "writer")
    assert Path(cwd) == expected
    assert expected.is_dir()
    assert _git(expected, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "agentweave/writer"
    assert not worktrees.task_root(repo).exists()


@pytest.mark.asyncio
async def test_a_follow_up_naming_no_task_stays_in_the_tasks_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """4.3 — the conversation binding is what stops two schemes coexisting by accident.

    A follow-up typed into the composer sends no task id. Without the inherited binding it would
    resolve to the agent's own workspace mid-task, and the agent's second turn would not be able to
    see its own first turn's work — which is the continuity failure D4 refuses to inflict on
    grandfathered tasks, arriving instead on every ordinary one.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")
    await _task(BOUND_TASK)

    first = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="start it",
        conversation_id=conversation_id,
        task_id=BOUND_TASK,
    )
    follow_up = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="carry on",
        conversation_id=conversation_id,
    )

    assert Path(first) == worktrees.task_worktree_path(repo, BOUND_TASK)
    assert Path(follow_up) == Path(first)
    assert not worktrees.worktree_path(repo, "writer").exists()


@pytest.mark.asyncio
async def test_a_grandfathered_task_keeps_the_per_agent_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """4.4 — the stamp is read, never recomputed (design D4).

    Both halves in one test on purpose: a resolver that ignored the column entirely would fail the
    first assertion, and one that sent *everything* to the per-agent checkout would fail the
    second. Separately they are each satisfiable by a broken implementation.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    grandfathered_conversation = await _conversation("writer")
    fresh_conversation = await _conversation("writer")
    await _task(OTHER_TASK, scheme="agent")
    await _task(BOUND_TASK)

    grandfathered = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="carry on with the old one",
        conversation_id=grandfathered_conversation,
        task_id=OTHER_TASK,
    )
    fresh = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="start the new one",
        conversation_id=fresh_conversation,
        task_id=BOUND_TASK,
    )

    assert Path(grandfathered) == worktrees.worktree_path(repo, "writer")
    assert Path(fresh) == worktrees.task_worktree_path(repo, BOUND_TASK)
    # No task branch is created for a grandfathered task — not merely an unused one.
    assert (
        _git(repo, "rev-parse", "--verify", "--quiet", worktrees.task_branch_name(OTHER_TASK))
    ).returncode != 0
    assert not worktrees.task_worktree_path(repo, OTHER_TASK).exists()


@pytest.mark.asyncio
async def test_the_base_is_the_projects_main_branch_when_it_is_set(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """4.6 — a task branch is cut from the branch its approval will merge into (design D1).

    The project checkout is deliberately left on a *different* branch carrying a commit `main` does
    not have. Cutting from `HEAD` would pick that up, and the assertion below would see it: the two
    refs are distinguishable only because the fixture made them so.
    """
    repo = _init_repo(tmp_path / "repo")
    _git(repo, "checkout", "-q", "-b", "sidetrack")
    (repo / "sidetrack.txt").write_text("not on main\n")
    _git(repo, "add", "sidetrack.txt")
    _git(repo, "commit", "-q", "-m", "sidetrack")
    await bind_project_workspace(repo)
    await _set_main_branch("main")
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")
    await _task(BOUND_TASK)

    cwd = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="work on it",
        conversation_id=conversation_id,
        task_id=BOUND_TASK,
    )

    assert _rev(Path(cwd), "HEAD") == _rev(repo, "main")
    assert _rev(Path(cwd), "HEAD") != _rev(repo, "sidetrack")
    assert not (Path(cwd) / "sidetrack.txt").exists()


@pytest.mark.asyncio
async def test_the_base_is_head_when_no_main_branch_is_set(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """4.6 — and the fallback, which is today's behaviour for a project with nothing named.

    The `cwd` assertion is not redundant with the ref one: an agent branch is cut from `HEAD` too,
    so without it this test is equally satisfied by a resolver that ignored the binding entirely,
    which is the one mutation the rest of this file exists to catch.
    """
    repo = _init_repo(tmp_path / "repo")
    _git(repo, "checkout", "-q", "-b", "sidetrack")
    (repo / "sidetrack.txt").write_text("not on main\n")
    _git(repo, "add", "sidetrack.txt")
    _git(repo, "commit", "-q", "-m", "sidetrack")
    await bind_project_workspace(repo)
    await _set_main_branch(None)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")
    await _task(BOUND_TASK)

    cwd = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="work on it",
        conversation_id=conversation_id,
        task_id=BOUND_TASK,
    )

    assert Path(cwd) == worktrees.task_worktree_path(repo, BOUND_TASK)
    assert _rev(Path(cwd), "HEAD") == _rev(repo, "sidetrack")
    assert (Path(cwd) / "sidetrack.txt").exists()


@pytest.mark.asyncio
async def test_a_main_branch_that_does_not_resolve_falls_back_to_head(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Design D1 says "set **and resolves**", and 4.6 named only "set" — so this is the half the
    task text left implicit, asserted rather than left to be discovered.

    A `main_branch` naming a ref this repository does not have is an ordinary stale setting: the
    branch was renamed, or the project was relocated. Passing it to `worktree add` would turn that
    into a refused turn, where running on `HEAD` is available, harmless, and exactly what a project
    with nothing named already gets.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _set_main_branch("trunk-that-was-renamed")
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")
    await _task(BOUND_TASK)

    cwd = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="work on it",
        conversation_id=conversation_id,
        task_id=BOUND_TASK,
    )

    assert cwd is not None
    assert Path(cwd) == worktrees.task_worktree_path(repo, BOUND_TASK)
    assert _rev(Path(cwd), "HEAD") == _rev(repo, "HEAD")


@pytest.mark.asyncio
async def test_a_read_only_agent_shares_the_project_checkout_bound_to_a_task_or_not(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """4.7 — `is_writing_agent` keeps precedence over the binding.

    A read-only agent given a checkout it may not write to gains nothing and loses the project
    directory it was reading. Asserted in both directions in one test because the point is that the
    binding makes no difference here at all.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "reader", {"read_only": True})
    bound_conversation = await _conversation("reader")
    unbound_conversation = await _conversation("reader")
    await _task(BOUND_TASK)

    bound = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="reader",
        message="read it",
        conversation_id=bound_conversation,
        task_id=BOUND_TASK,
    )
    unbound = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="reader",
        message="read something else",
        conversation_id=unbound_conversation,
    )

    assert Path(bound) == repo
    assert Path(unbound) == repo
    assert not worktrees.task_root(repo).exists()
    assert not worktrees.worktree_root(repo).exists()


@pytest.mark.asyncio
async def test_a_project_that_is_not_a_repository_runs_the_turn_in_place(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """4.8 — absence of a repository is a degradation, not an error, for a task as for an agent.

    `resolve_agent_workspace` already states this posture for the unbound case. Extending per-task
    isolation without extending it would refuse every turn on a supported project shape — the
    directory has no branch to cut from, no primary checkout at risk, and nothing the Hub could do
    differently.
    """
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    await bind_project_workspace(plain)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")
    await _task(BOUND_TASK)

    cwd = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="work on it",
        conversation_id=conversation_id,
        task_id=BOUND_TASK,
    )

    assert Path(cwd) == plain
    assert not worktrees.task_root(plain).exists()


@pytest.mark.asyncio
async def test_a_task_id_the_product_could_not_have_minted_keeps_the_per_agent_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Not in 4.9's text, and it had to be decided anyway — so it is decided here rather than in
    whichever production database first contains such a row.

    `validate_task_id` accepts `task-` followed by hex, which is what `short_id` mints; nothing in
    the schema enforces it. A row that arrived another way cannot be given a branch and a directory
    named after it, and the two available answers are "refuse every turn on this task" and "run it
    where it ran before". The second is chosen: the first is an outage on data the Hub cannot fix,
    and the second is what grandfathering already means. It is logged, because unlike an unbound
    turn or a stamped one this is not a shape the product expects to see.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")
    await _task("task-Not-Hex")

    # Asserted against the module's own logger rather than through `caplog`, which this file
    # measured to be unreliable in a full-suite run: it captured the warning when the file ran
    # alone and captured nothing when it ran after 3,000 siblings, so the test failed for a reason
    # that had nothing to do with the behaviour. `test_migrations.py:545` already records the same
    # unreliability and *drops* its log assertion; patching the logger keeps the assertion instead,
    # which matters here because "it is logged rather than silent" is half of the decision.
    with patch.object(task_workspace.logger, "warning") as warned:
        cwd = await _turn(
            async_session_factory,
            project_id="proj-test",
            agent="writer",
            message="work on it",
            conversation_id=conversation_id,
            task_id="task-Not-Hex",
        )

    assert Path(cwd) == worktrees.worktree_path(repo, "writer")
    assert not worktrees.task_root(repo).exists()
    assert warned.call_count == 1
    assert "task-Not-Hex" in (warned.call_args.args[0] % warned.call_args.args[1:])


@pytest.mark.asyncio
async def test_a_prerequisites_accepted_commits_are_in_the_task_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """4.10 — the Hub layer actually finds the prerequisite commits, rather than passing none.

    Phase 2 proved `ensure_task_worktree` merges the commits it is *given*; nothing until here
    proves anything is given. A `_prerequisite_commits` that always returned `()` passes every
    other test in this file and every test in `test_task_worktrees.py`, which is exactly the shape
    F58 had: a guarantee stated in a docstring with no test able to fail on it.

    The commit is deliberately on a branch that `main` cannot reach, so its file appearing in the
    dependent task's checkout can only have come through the merge.
    """
    repo = _init_repo(tmp_path / "repo")
    _git(repo, "checkout", "-q", "-b", "agentweave/builder")
    (repo / "prerequisite.txt").write_text("groundwork\n")
    _git(repo, "add", "prerequisite.txt")
    _git(repo, "commit", "-q", "-m", "the prerequisite's work")
    prerequisite_commit = _rev(repo, "HEAD")
    _git(repo, "checkout", "-q", "main")
    await bind_project_workspace(repo)
    await _set_main_branch("main")
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")
    await _task(OTHER_TASK)
    await _task(BOUND_TASK)
    async with async_session_factory() as session:
        session.add(
            TaskDependency(
                id="dep-1",
                project_id="proj-test",
                task_id=BOUND_TASK,
                depends_on_task_id=OTHER_TASK,
            )
        )
        session.add(
            TaskRequirementLink(
                id="link-1",
                project_id="proj-test",
                task_id=OTHER_TASK,
                requirement_id="req-1",
            )
        )
        session.add(
            RequirementEvidence(
                id="ev-1",
                project_id="proj-test",
                requirement_id="req-1",
                task_id=OTHER_TASK,
                digest="d" * 64,
                kind="commit",
                actor_kind="agent",
                actor="writer",
                summary="groundwork done",
                review_state="accepted",
            )
        )
        session.add(
            EvidenceFootprint(
                id="fp-1",
                project_id="proj-test",
                evidence_id="ev-1",
                kind="git",
                commit_sha=prerequisite_commit,
                branch="agentweave/builder",
            )
        )
        await session.commit()

    cwd = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="work on it",
        conversation_id=conversation_id,
        task_id=BOUND_TASK,
    )

    assert Path(cwd) == worktrees.task_worktree_path(repo, BOUND_TASK)
    assert (Path(cwd) / "prerequisite.txt").read_text() == "groundwork\n"
    assert not (repo / "prerequisite.txt").exists()
