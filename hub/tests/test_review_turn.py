"""A review turn end to end — `2026-08-23-a-reviewer-can-see-the-work`, task groups 3 and 4.

The assertion this whole change exists for is `test_a_reviewer_reads_a_file_that_is_not_on_main`:
before it, a reviewing agent was refused at the author's worktree and had to ask the author what
had changed (`scripts/drive/FINDINGS.md`, F10).

Helpers are reused from `test_agent_trigger` rather than duplicated: `hub/tests` is a package, and
two copies of the pty fake drift.
"""

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from hub import review_turn, worktrees
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    EvidenceFootprint,
    InboundQueueEntry,
    RequirementEvidence,
    SpecDocument,
    SpecRequirement,
    Task,
)
from hub.spec_payload import SCHEMA_VERSION, embed_payload

from .test_agent_trigger import _await_background_run, _fake_pty, _init_repo

NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)

_REAL_ENSURE_REVIEW_CHECKOUT = worktrees.ensure_review_checkout


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result


def _author_commit(repo: Path, *, filename: str, body: str, branch="agentweave/builder") -> str:
    """Work that exists on the author's branch and not on main — the interesting case."""
    _git(repo, "checkout", "-q", "-b", branch)
    (repo / filename).write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "author's work")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-q", "main")
    return sha


async def _reviewable_task(
    *,
    commit: str,
    branch: str = "agentweave/builder",
    task_id: str = "task-1",
    reviewer_declaration: str = None,
    document_path: str = "spec/ledger.html",
):
    """A completed task carrying evidence that names *commit*."""
    async with async_session_factory() as session:
        session.add(
            SpecDocument(
                id="doc-1",
                project_id="proj-test",
                path=document_path,
                title="Ledger",
                phase="current",
                kind="capability",
            )
        )
        session.add(
            SpecRequirement(
                id="req-1",
                project_id="proj-test",
                document_id="doc-1",
                identifier="FR-1",
                key="fr-1",
                digest="d" * 64,
            )
        )
        session.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title="Balance the ledger",
                status="completed",
                spec_document_id="doc-1" if reviewer_declaration is not None else None,
                spec_task_key="t1" if reviewer_declaration is not None else None,
            )
        )
        session.add(
            RequirementEvidence(
                id="ev-1",
                project_id="proj-test",
                requirement_id="req-1",
                task_id=task_id,
                digest="d" * 64,
                kind="commit",
                actor_kind="agent",
                actor="builder",
                summary="all green",
                produced_at=NOW - timedelta(minutes=5),
            )
        )
        session.add(
            EvidenceFootprint(
                id="fp-1",
                project_id="proj-test",
                evidence_id="ev-1",
                kind="git",
                commit_sha=commit,
                branch=branch,
                observed_at=NOW - timedelta(minutes=5),
            )
        )
        await session.commit()


async def _trigger_review(app, auth_headers, *, agent="critic", task_id="task-1", message="review"):
    return await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": agent, "message": message, "review_task_id": task_id},
        headers=auth_headers,
    )


async def _roster(app, auth_headers, bind_runner, *names):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"} for name in names}}},
        headers=auth_headers,
    )
    for name in names:
        await bind_runner(name, cli="claude")


# ---------------------------------------------------------------------------
# task 3.5 — the workspace is the review checkout, and the author's is outside it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_reviewer_reads_a_file_that_is_not_on_main(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """The assertion that distinguishes this change from doing nothing."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="def balance():\n    return 0\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, "critic")
    await _reviewable_task(commit=sha)

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            response = await _trigger_review(app, auth_headers)
            assert response.status_code == 200, response.text
            await _await_background_run()

    cwd = Path(fake_spawn.call_args.kwargs["cwd"])
    assert cwd == worktrees.review_path(repo, "critic")
    # Not on main, and readable here. This is what `critic` could not do before.
    assert not (repo / "ledger.py").exists()
    assert (cwd / "ledger.py").read_text() == "def balance():\n    return 0\n"


@pytest.mark.asyncio
async def test_the_boundary_moves_with_the_workspace(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Task 3.2: the value the agent is told and the value that is enforced stay one value."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, "critic")
    await _reviewable_task(commit=sha)

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            await _trigger_review(app, auth_headers)
            await _await_background_run()

    env = fake_spawn.call_args.kwargs["env"]
    cwd = fake_spawn.call_args.kwargs["cwd"]
    assert env["AW_WORKSPACE_DIR"] == cwd
    assert Path(env["AW_WORKSPACE_DIR"]) == worktrees.review_path(repo, "critic")


@pytest.mark.asyncio
async def test_the_reviewers_own_worktree_is_outside_the_turns_boundary(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Design D4: exactly one workspace per review turn, so the wrong place is *outside* it."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, "critic")
    await _reviewable_task(commit=sha)
    own = worktrees.ensure_worktree(repo, "critic")

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            await _trigger_review(app, auth_headers)
            await _await_background_run()

    boundary = Path(fake_spawn.call_args.kwargs["env"]["AW_WORKSPACE_DIR"]).resolve()
    assert own.resolve() != boundary
    assert boundary not in own.resolve().parents
    assert own.resolve() not in boundary.parents


@pytest.mark.asyncio
async def test_the_turn_context_says_this_is_a_review_and_names_the_task_and_commit(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Task 3.3. The boundary enforces *where*; this is the half that states *what*."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, "critic")
    await _reviewable_task(commit=sha)

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            await _trigger_review(app, auth_headers)
            await _await_background_run()

    cwd = Path(fake_spawn.call_args.kwargs["cwd"])
    context = (cwd / ".agentweave" / "context" / "critic.md").read_text(encoding="utf-8")
    assert "This is a review turn" in context
    assert "task `task-1`" in context
    assert sha in context
    assert "Balance the ledger" in context
    assert "HEAD detached" in context
    # It must also say what NOT to do, or a reviewer helpfully fixes the bug and calls it verified.
    assert "Do not fix what you find" in context
    assert "run its test suite" in context.lower()


@pytest.mark.asyncio
async def test_the_context_says_when_earlier_evidence_named_a_different_commit(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Design D5: told, not silently handed the newest."""
    repo = _init_repo(tmp_path / "repo")
    first = _author_commit(repo, filename="one.py", body="x = 1\n", branch="agentweave/b1")
    second = _author_commit(repo, filename="two.py", body="y = 2\n", branch="agentweave/b2")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, "critic")
    await _reviewable_task(commit=first)
    async with async_session_factory() as session:
        session.add(
            RequirementEvidence(
                id="ev-2",
                project_id="proj-test",
                requirement_id="req-1",
                task_id="task-1",
                digest="d" * 64,
                kind="commit",
                actor_kind="agent",
                actor="builder",
                summary="moved",
                produced_at=NOW,
            )
        )
        session.add(
            EvidenceFootprint(
                id="fp-2",
                project_id="proj-test",
                evidence_id="ev-2",
                kind="git",
                commit_sha=second,
                branch="agentweave/b2",
                observed_at=NOW,
            )
        )
        await session.commit()

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            await _trigger_review(app, auth_headers)
            await _await_background_run()

    cwd = Path(fake_spawn.call_args.kwargs["cwd"])
    context = (cwd / ".agentweave" / "context" / "critic.md").read_text(encoding="utf-8")
    assert "Earlier evidence for this task named a different commit" in context
    assert first in context
    assert "ev-1" in context
    # The newer one is what was checked out.
    assert (cwd / "two.py").exists()
    assert not (cwd / "one.py").exists()


# ---------------------------------------------------------------------------
# task 3.4 — refusals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_task_with_no_evidence_is_refused_before_anything_spawns(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, "critic")
    async with async_session_factory() as session:
        session.add(
            Task(id="task-1", project_id="proj-test", title="Nothing done", status="completed")
        )
        await session.commit()

    response = await _trigger_review(app, auth_headers)

    assert response.status_code == 409
    assert "no recorded evidence" in response.json()["detail"]
    assert not worktrees.review_path(repo, "critic").exists()


@pytest.mark.asyncio
async def test_a_task_the_project_does_not_have_is_refused(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, "critic")

    response = await _trigger_review(app, auth_headers, task_id="task-nonexistent")

    assert response.status_code in (404, 409)


@pytest.mark.asyncio
async def test_a_commit_the_repository_does_not_contain_is_refused_not_approximated(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Putting the reviewer on a *nearby* commit would produce a verdict about code nobody wrote."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, "critic")
    await _reviewable_task(commit="0" * 40)

    async with async_session_factory() as session:
        with pytest.raises(review_turn.ReviewTurnRefused) as excinfo:
            await review_turn.prepare_review_turn(
                session,
                project_id="proj-test",
                reviewer="critic",
                task_id="task-1",
                repo_root=repo,
            )

    assert "not present in this repository" in str(excinfo.value)
    assert not worktrees.review_path(repo, "critic").exists()


@pytest.mark.asyncio
async def test_work_dir_cannot_be_combined_with_a_review_turn(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, "critic")

    async with async_session_factory() as session:
        from hub.api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly
        from hub.conversations import new_conversation

        conversation = new_conversation(project_id="proj-test", agent="critic", origin="operator")
        session.add(conversation)
        session.add(Task(id="task-1", project_id="proj-test", title="A task", status="completed"))
        await session.commit()

        with pytest.raises(TriggerAgentError) as excinfo:
            await trigger_agent_directly(
                project_id="proj-test",
                agent="critic",
                message="review",
                conversation_id=conversation.id,
                work_dir="somewhere",
                session=session,
                review_task_id="task-1",
            )

    assert "cannot be combined with a review turn" in excinfo.value.detail


@pytest.mark.asyncio
async def test_a_batch_naming_two_review_tasks_is_refused(app):
    """A review turn has one workspace, so "review both" is not a thing this can mean."""
    from hub.api.v1.agent_trigger import TriggerAgentError, _review_task_from_entries

    async with async_session_factory() as session:
        for entry_id, task_id in (("entry-a", "task-1"), ("entry-b", "task-2")):
            session.add(
                InboundQueueEntry(
                    id=entry_id,
                    project_id="proj-test",
                    agent="critic",
                    origin_type="operator",
                    content="review",
                    hop_depth=0,
                    state="queued",
                    review_task_id=task_id,
                )
            )
        await session.commit()

        with pytest.raises(TriggerAgentError) as excinfo:
            await _review_task_from_entries(session, ["entry-a", "entry-b"])

    assert "more than one task" in excinfo.value.detail


@pytest.mark.asyncio
async def test_entries_agreeing_on_one_review_task_resolve_to_it(app):
    from hub.api.v1.agent_trigger import _review_task_from_entries

    async with async_session_factory() as session:
        session.add(
            InboundQueueEntry(
                id="entry-a",
                project_id="proj-test",
                agent="critic",
                origin_type="operator",
                content="review",
                hop_depth=0,
                state="queued",
                review_task_id="task-1",
            )
        )
        session.add(
            InboundQueueEntry(
                id="entry-b",
                project_id="proj-test",
                agent="critic",
                origin_type="operator",
                content="and also",
                hop_depth=0,
                state="queued",
            )
        )
        await session.commit()

        assert await _review_task_from_entries(session, ["entry-a", "entry-b"]) == "task-1"
        assert await _review_task_from_entries(session, ["entry-b"]) is None
        assert await _review_task_from_entries(session, None) is None


# ---------------------------------------------------------------------------
# task 4.2 — an archived reviewer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_archived_reviewer_is_refused(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, "critic")
    await _reviewable_task(commit=sha)
    async with async_session_factory() as session:
        from sqlalchemy import update

        await session.execute(
            update(Agent)
            .where(Agent.project_id == "proj-test", Agent.name == "critic")
            .values(lifecycle="archived")
        )
        await session.commit()

    response = await _trigger_review(app, auth_headers)

    assert response.status_code == 409
    assert "archived" in response.json()["detail"]
    assert not worktrees.review_path(repo, "critic").exists()


# ---------------------------------------------------------------------------
# task 4.3 — a declared reviewer that does not resolve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_task_declaring_no_reviewer_falls_back_to_the_operator(app):
    async with async_session_factory() as session:
        task = Task(id="task-1", project_id="proj-test", title="A task", status="completed")
        session.add(task)
        await session.commit()

        resolution = await review_turn.resolve_declared_reviewer(
            session, project_id="proj-test", task=task
        )

    assert resolution.declared is None
    assert resolution.agent is None
    assert resolution.unresolved is None
    assert resolution.falls_back_to_operator is True


@pytest.mark.asyncio
async def test_a_declared_reviewer_not_on_the_roster_is_surfaced_never_substituted(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    # A roster with a plausible near-miss on it. The point is that `auditor` is NOT chosen.
    await _roster(app, auth_headers, bind_runner, "auditor")
    document = repo / "spec" / "ledger.html"
    document.parent.mkdir(parents=True, exist_ok=True)
    # The real embedder, not a hand-written tag: a fixture that fakes the envelope stops testing
    # the thing that reads it the moment the envelope changes.
    document.write_text(
        embed_payload(
            {"schema_version": SCHEMA_VERSION, "tasks": [{"key": "t1", "reviewer": "critic"}]}
        ),
        encoding="utf-8",
    )

    async with async_session_factory() as session:
        session.add(
            SpecDocument(
                id="doc-1",
                project_id="proj-test",
                path="spec/ledger.html",
                title="Ledger",
                phase="current",
                kind="capability",
            )
        )
        task = Task(
            id="task-1",
            project_id="proj-test",
            title="A task",
            status="completed",
            spec_document_id="doc-1",
            spec_task_key="t1",
        )
        session.add(task)
        await session.commit()

        resolution = await review_turn.resolve_declared_reviewer(
            session, project_id="proj-test", task=task
        )

    assert resolution.declared == "critic"
    assert resolution.agent is None
    assert resolution.agent != "auditor"
    assert "no agent by that name is on this project's roster" in resolution.unresolved
    assert "falls back to you" in resolution.unresolved
    assert resolution.falls_back_to_operator is True


@pytest.mark.asyncio
async def test_a_declared_reviewer_that_is_archived_falls_back_rather_than_being_used(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """Nothing runs an archived agent, so naming one is the same as naming nobody available."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, "critic")
    document = repo / "spec" / "ledger.html"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(
        embed_payload(
            {"schema_version": SCHEMA_VERSION, "tasks": [{"key": "t1", "reviewer": "critic"}]}
        ),
        encoding="utf-8",
    )

    async with async_session_factory() as session:
        from sqlalchemy import update

        session.add(
            SpecDocument(
                id="doc-1",
                project_id="proj-test",
                path="spec/ledger.html",
                title="Ledger",
                phase="current",
                kind="capability",
            )
        )
        task = Task(
            id="task-1",
            project_id="proj-test",
            title="A task",
            status="completed",
            spec_document_id="doc-1",
            spec_task_key="t1",
        )
        session.add(task)
        await session.execute(
            update(Agent)
            .where(Agent.project_id == "proj-test", Agent.name == "critic")
            .values(lifecycle="archived")
        )
        await session.commit()

        resolution = await review_turn.resolve_declared_reviewer(
            session, project_id="proj-test", task=task
        )

    assert resolution.declared == "critic"
    assert resolution.agent is None
    assert "archived" in resolution.unresolved


@pytest.mark.asyncio
async def test_a_declared_reviewer_on_the_roster_resolves_to_itself(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, "critic")
    document = repo / "spec" / "ledger.html"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(
        embed_payload(
            {"schema_version": SCHEMA_VERSION, "tasks": [{"key": "t1", "reviewer": "critic"}]}
        ),
        encoding="utf-8",
    )

    async with async_session_factory() as session:
        session.add(
            SpecDocument(
                id="doc-1",
                project_id="proj-test",
                path="spec/ledger.html",
                title="Ledger",
                phase="current",
                kind="capability",
            )
        )
        task = Task(
            id="task-1",
            project_id="proj-test",
            title="A task",
            status="completed",
            spec_document_id="doc-1",
            spec_task_key="t1",
        )
        session.add(task)
        await session.commit()

        resolution = await review_turn.resolve_declared_reviewer(
            session, project_id="proj-test", task=task
        )

    assert resolution.agent == "critic"
    assert resolution.unresolved is None
    assert resolution.falls_back_to_operator is False
