"""Group B, tasks 1.11, 1.12, 4.1 and 4.2 of `a-copilot-agent-uses-hooks-and-its-own-agents`
(design D8): a Copilot reviewer may be told to consult Copilot's own built-in review agents
before recording its verdict.

Two things are checked separately because they can drift apart on their own:

* **`<base>`.** `review_turn.prepare_review_turn` computes `ReviewContext.base_sha` as the merge
  base of the reviewed commit and `Project.main_branch`, before the review checkout is
  provisioned, and never raises for it.
* **The bullet.** `_render_hub_agent_context` adds one bullet, after the verdict line and before
  the evidence gate, only for a Copilot agent whose `config.copilot_review_agents` names at least
  one agent from the closed vocabulary. The PATCH route validates that setting before the merge;
  the renderer filters the stored value again at render time, so a value another writer put there
  without going through the PATCH check can only narrow the bullet, never inject into it
  (review 2026-09-28, finding 14).
"""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import review_turn, worktrees
from hub.api.v1.agents import _render_hub_agent_context
from hub.db.engine import async_session_factory
from hub.db.models import Agent

from .test_agent_trigger import _init_repo
from .test_review_turn import _author_commit, _git, _reviewable_task
from .test_task_integration import set_main_branch

PROJECT = "proj-test"
P = f"/api/v1/projects/{PROJECT}"
VERDICT = "**End the review with a verdict, using `update_task`.** The task is `under_review`"


def _review(*, commit_sha="c" * 40, base_sha=None):
    return review_turn.ReviewContext(
        task_id="task-1",
        task_title="Balance the ledger",
        reviewer="critic",
        commit_sha=commit_sha,
        evidence_id="ev-1",
        workspace=Path("/does/not/matter"),
        base_sha=base_sha,
    )


async def _context(name, *, runner, review):
    async with async_session_factory() as session:
        agent_row = (
            await session.execute(
                select(Agent).where(Agent.project_id == PROJECT, Agent.name == name)
            )
        ).scalar_one()
        rendered = await _render_hub_agent_context(
            agent=name,
            project_id=PROJECT,
            db=session,
            session_data=None,
            agent_row=agent_row,
            work_dir="/work",
            review=review,
            runner=runner,
        )
    return rendered["context"]


# ---------------------------------------------------------------------------
# Test 1.11 — the bullet
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_copilot_reviewer_with_one_review_agent_gets_the_d8_bullet(
    app, auth_headers, add_agent
):
    await add_agent("critic", config={"copilot_review_agents": ["code-review"]})
    context = await _context(
        "critic", runner="copilot", review=_review(commit_sha="c" * 40, base_sha="b" * 40)
    )
    assert "`code-review`" in context
    assert "b" * 40 in context
    assert "c" * 40 in context
    assert "recorded only by `update_task`" in context


@pytest.mark.asyncio
async def test_two_review_agents_are_named_together(app, auth_headers, add_agent):
    await add_agent("critic", config={"copilot_review_agents": ["code-review", "security-review"]})
    context = await _context("critic", runner="copilot", review=_review())
    # D8a (F484) writes the several-agents sentence out exactly (`test_review_agents_report.py`).
    assert "run Copilot's `code-review`, `security-review` agents as subagents" in context


@pytest.mark.asyncio
async def test_the_verdict_line_is_byte_identical_to_the_no_setting_render(
    app, auth_headers, add_agent
):
    await add_agent("critic", config={})
    without = await _context("critic", runner="copilot", review=_review())

    await add_agent("critic", config={"copilot_review_agents": ["code-review"]})
    with_setting = await _context("critic", runner="copilot", review=_review())

    assert VERDICT in without and VERDICT in with_setting
    without_head = without[: without.index(VERDICT) + len(VERDICT)]
    with_head = with_setting[: with_setting.index(VERDICT) + len(VERDICT)]
    assert without_head == with_head
    assert without != with_setting


@pytest.mark.asyncio
async def test_an_ordinary_turn_gets_no_bullet(app, auth_headers, add_agent):
    await add_agent("critic", config={"copilot_review_agents": ["code-review"]})
    async with async_session_factory() as session:
        agent_row = (
            await session.execute(
                select(Agent).where(Agent.project_id == PROJECT, Agent.name == "critic")
            )
        ).scalar_one()
        rendered = await _render_hub_agent_context(
            agent="critic",
            project_id=PROJECT,
            db=session,
            session_data=None,
            agent_row=agent_row,
            work_dir="/work",
            review=None,
            runner="copilot",
        )
    assert "code-review" not in rendered["context"]


@pytest.mark.asyncio
async def test_a_claude_agent_with_the_same_config_gets_no_bullet(app, auth_headers, add_agent):
    await add_agent("critic", config={"copilot_review_agents": ["code-review"]})
    context = await _context("critic", runner="claude", review=_review())
    assert "code-review" not in context


@pytest.mark.asyncio
async def test_an_empty_list_gets_no_bullet(app, auth_headers, add_agent):
    await add_agent("critic", config={"copilot_review_agents": []})
    context = await _context("critic", runner="copilot", review=_review())
    assert "Before your verdict, run Copilot" not in context


@pytest.mark.asyncio
async def test_with_no_base_the_bullet_names_the_commit_alone(app, auth_headers, add_agent):
    await add_agent("critic", config={"copilot_review_agents": ["code-review"]})
    context = await _context(
        "critic", runner="copilot", review=_review(commit_sha="c" * 40, base_sha=None)
    )
    assert "the changes from" not in context
    assert f"`{'c' * 40}`'s own changes" in context


# ---------------------------------------------------------------------------
# Test 1.12 — the PATCH validation, and the renderer's own defensive filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unknown_vocabulary_entry_is_refused_and_stored_config_is_unchanged(
    app, auth_headers, add_agent, bind_runner
):
    await add_agent("critic")
    await bind_runner("critic", cli="copilot")
    seed = await app.patch(
        f"{P}/agents/critic",
        json={"config": {"copilot_review_agents": ["code-review"]}},
        headers=auth_headers,
    )
    assert seed.status_code == 200, seed.text

    for bad in (["research"], ["x"], "code-review"):
        refused = await app.patch(
            f"{P}/agents/critic",
            json={"config": {"copilot_review_agents": bad}},
            headers=auth_headers,
        )
        assert refused.status_code == 400, refused.text

    roster = await app.get(f"{P}/agents", headers=auth_headers)
    [critic] = [row for row in roster.json() if row["name"] == "critic"]
    assert critic["config"]["copilot_review_agents"] == ["code-review"]


@pytest.mark.asyncio
async def test_an_accepted_list_round_trips_through_the_roster(
    app, auth_headers, add_agent, bind_runner
):
    await add_agent("critic")
    await bind_runner("critic", cli="copilot")
    accepted = await app.patch(
        f"{P}/agents/critic",
        json={"config": {"copilot_review_agents": ["code-review", "security-review"]}},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text

    roster = await app.get(f"{P}/agents", headers=auth_headers)
    [critic] = [row for row in roster.json() if row["name"] == "critic"]
    assert critic["config"]["copilot_review_agents"] == ["code-review", "security-review"]


@pytest.mark.asyncio
async def test_a_value_stored_by_another_writer_can_only_narrow_the_bullet(
    app, auth_headers, add_agent
):
    """Finding 14: nothing but the PATCH route is required to agree with the vocabulary."""
    await add_agent("critic", config={"copilot_review_agents": ["code-review", "research"]})
    context = await _context("critic", runner="copilot", review=_review())
    assert "`code-review`" in context
    assert "research" not in context


@pytest.mark.asyncio
async def test_a_non_list_value_stored_by_another_writer_renders_no_bullet(
    app, auth_headers, add_agent
):
    await add_agent("critic", config={"copilot_review_agents": "code-review"})
    context = await _context("critic", runner="copilot", review=_review())
    assert "Before your verdict, run Copilot" not in context


# ---------------------------------------------------------------------------
# Tasks 4.1 / 1.11 — `<base>`, computed by `prepare_review_turn`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_sha_is_none_with_no_main_branch_set(
    app, auth_headers, tmp_path, bind_project_workspace
):
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="x.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await _reviewable_task(commit=sha)

    async with async_session_factory() as session:
        context = await review_turn.prepare_review_turn(
            session, project_id=PROJECT, reviewer="critic", task_id="task-1", repo_root=repo
        )
    assert context.base_sha is None


@pytest.mark.asyncio
async def test_base_sha_is_none_when_main_branch_does_not_exist(
    app, auth_headers, tmp_path, bind_project_workspace
):
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="x.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await set_main_branch("does-not-exist")
    await _reviewable_task(commit=sha)

    async with async_session_factory() as session:
        context = await review_turn.prepare_review_turn(
            session, project_id=PROJECT, reviewer="critic", task_id="task-1", repo_root=repo
        )
    assert context.base_sha is None


@pytest.mark.asyncio
async def test_base_sha_is_none_when_the_commit_is_already_on_main(
    app, auth_headers, tmp_path, bind_project_workspace
):
    repo = _init_repo(tmp_path / "repo")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    await bind_project_workspace(repo)
    await set_main_branch("main")
    await _reviewable_task(commit=sha, branch="main")

    async with async_session_factory() as session:
        context = await review_turn.prepare_review_turn(
            session, project_id=PROJECT, reviewer="critic", task_id="task-1", repo_root=repo
        )
    assert context.base_sha is None


@pytest.mark.asyncio
async def test_base_sha_is_the_merge_base_of_the_commit_and_main(
    app, auth_headers, tmp_path, bind_project_workspace
):
    repo = _init_repo(tmp_path / "repo")
    main_tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
    sha = _author_commit(repo, filename="x.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await set_main_branch("main")
    await _reviewable_task(commit=sha)

    async with async_session_factory() as session:
        context = await review_turn.prepare_review_turn(
            session, project_id=PROJECT, reviewer="critic", task_id="task-1", repo_root=repo
        )
    assert context.base_sha == main_tip


@pytest.mark.asyncio
async def test_a_raising_merge_base_check_runs_before_the_checkout_is_provisioned(
    app, auth_headers, tmp_path, bind_project_workspace, monkeypatch
):
    """Design D8, R3: an escaping `TimeoutExpired` must not leave a provisioned checkout
    unclaimed, so the merge-base check runs first and never raises."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="x.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await set_main_branch("main")
    await _reviewable_task(commit=sha)

    order = []
    real_checkout = worktrees.ensure_review_checkout

    def _raising_git(root, *args):
        order.append("git")
        raise subprocess.TimeoutExpired(cmd=["git", *args], timeout=60)

    def _tracked_checkout(*args, **kwargs):
        order.append("checkout")
        return real_checkout(*args, **kwargs)

    monkeypatch.setattr(review_turn, "_git", _raising_git)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _tracked_checkout)

    async with async_session_factory() as session:
        context = await review_turn.prepare_review_turn(
            session, project_id=PROJECT, reviewer="critic", task_id="task-1", repo_root=repo
        )

    assert context.base_sha is None
    assert order == ["git", "checkout"]
