"""F767 -- a flow that names a reviewer must not offer that reviewer fresh work.

Found in the tasks sweep (2026-10-19): `delivery: {mode: flow, agent: builder, reviewer: rev}` and
two independent tasks, `builder` and `rev` both free. The first firing started `t-clamp` on builder
and `t-sub` on `rev`, because `_agents_a_loop_may_staff` returned every free agent for a flow. The
review ladder then refused to substitute for a named reviewer, so `rev`, having built `t-sub`, was
the one agent that could never review it: `review_unstaffed`, and the task waited for the operator.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, SpecDocument, Task
from hub.scheduler import decide_firing
from hub.spec_payload import SCHEMA_VERSION

from ._spec_files import stored_text
from .test_agent_trigger import _init_repo
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio


async def _flow(db, repo, *, delivery):
    document = repo / "spec" / "changes" / "c" / "spec.json"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(
        stored_text(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "tasks": [{"key": "t-clamp"}, {"key": "t-sub"}],
                "delivery": {"mode": "flow", "agent": "builder", **delivery},
            },
            phase="approved",
        ),
        encoding="utf-8",
    )
    db.add(
        SpecDocument(
            id="doc-f767",
            project_id="proj-test",
            path="spec/changes/c/spec.json",
            title="F767",
            phase="approved",
            kind="change-spec",
        )
    )
    db.add(
        AIJob(
            id="job-f767",
            project_id="proj-test",
            name="F767",
            agent="builder",
            message="work the queue",
            cron="*/5 * * * *",
            session_mode="new",
            enabled=True,
        )
    )
    await db.commit()
    db.add(
        Loop(
            id="loop-f767",
            project_id="proj-test",
            job_id="job-f767",
            purpose="f767",
            spec_document_id="doc-f767",
        )
    )
    await db.commit()
    for key in ("t-clamp", "t-sub"):
        db.add(
            Task(
                id=f"task-f767-{key}",
                project_id="proj-test",
                title=key,
                status="pending",
                loop_id="loop-f767",
                spec_document_id="doc-f767",
                spec_task_key=key,
            )
        )
    await db.commit()
    return (await db.execute(select(Loop).where(Loop.id == "loop-f767"))).scalar_one()


async def _fire(app, auth_headers, bind_runner, bind_project_workspace, tmp_path, delivery):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, "builder", "rev")
    async with async_session_factory() as db:
        loop = await _flow(db, repo, delivery=delivery)
        return await decide_firing(db, loop, default_agent="builder")


async def test_the_named_reviewer_is_not_offered_fresh_work(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    decision = await _fire(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, {"reviewer": "rev"}
    )
    assert [s.agent for s in decision.selections] == ["builder"]


async def test_the_named_tester_is_not_offered_fresh_work(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    decision = await _fire(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, {"tester": "rev"}
    )
    assert [s.agent for s in decision.selections] == ["builder"]


async def test_a_flow_naming_no_reviewer_still_runs_two_builds(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    decision = await _fire(app, auth_headers, bind_runner, bind_project_workspace, tmp_path, {})
    assert sorted(s.agent for s in decision.selections) == ["builder", "rev"]


async def test_a_flow_whose_only_other_agent_is_the_reviewer_still_runs_its_builder(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """Narrowing must never leave the flow with nobody: the reviewer is withheld only while
    somebody else can build."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, "rev")
    async with async_session_factory() as db:
        loop = await _flow(db, repo, delivery={"reviewer": "rev", "agent": "rev"})
        decision = await decide_firing(db, loop, default_agent="rev")
    assert [s.agent for s in decision.selections] == ["rev"]


async def test_the_flows_own_agent_is_not_offered_fresh_work_when_it_is_also_the_reviewer(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """F864 -- the default-agent arm is the other way a named reviewer reached fresh work: with
    `agent` and `reviewer` the same agent, both tasks were built, and the one alpha built could
    never be reviewed by alpha. Beta is free, so beta builds and alpha is kept for review."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, "alpha", "beta")
    async with async_session_factory() as db:
        loop = await _flow(db, repo, delivery={"agent": "alpha", "reviewer": "alpha"})
        decision = await decide_firing(db, loop, default_agent="alpha")
    assert [s.agent for s in decision.selections] == ["beta"]
