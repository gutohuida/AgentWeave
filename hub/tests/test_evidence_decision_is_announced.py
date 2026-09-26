# ruff: noqa: F811  (the `world` fixture is imported, then named as a test argument)
"""`the-coverage-bar-takes-the-evidence-decision-it-asks-for`, backend half: a decided piece and the
end of a run that recorded evidence are each announced as `spec_updated`, so an open coverage bar
refetches. Reuses the F358 change's world (a repository, a document, a task, a recording run).
"""

import inspect
import re

import pytest
from sqlalchemy import select

from hub import run_liveness
from hub.api.v1 import agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import RequirementEvidence

from .test_conflict_refusal_names_what_clears_it import record_as_agent
from .test_evidence_waits_for_its_run import (  # noqa: F401  (world is a fixture)
    BUILDER,
    RECORDING,
    agent_decides,
    operator_decides,
    world,
)


@pytest.fixture
def broadcasts(monkeypatch):
    sent = []

    async def capture(project_id, event_type, data=None, *args, **kwargs):
        sent.append((project_id, event_type, data))

    from hub.api.v1 import agent_actions, spec

    monkeypatch.setattr(spec.sse_manager, "broadcast", capture)
    monkeypatch.setattr(agent_actions.sse_manager, "broadcast", capture)
    monkeypatch.setattr(agent_trigger.sse_manager, "broadcast", capture)
    return sent


def decided(sent, evidence_id):
    return [
        data
        for _, kind, data in sent
        if kind == "spec_updated" and (data or {}).get("evidence") == evidence_id
    ]


@pytest.mark.asyncio
async def test_operator_decision_is_announced(app, auth_headers, world, broadcasts):
    """1.1: one `spec_updated` naming the piece and its requirement."""
    evidence_id = await record_as_agent(app, BUILDER)
    broadcasts.clear()
    response = await operator_decides(app, auth_headers, evidence_id)
    assert response.status_code == 200, response.text
    assert decided(broadcasts, evidence_id) == [{"evidence": evidence_id, "requirement": "FR-1"}]


@pytest.mark.asyncio
async def test_a_refused_decision_announces_nothing(app, auth_headers, world, broadcasts):
    evidence_id = await record_as_agent(app, BUILDER)
    run_liveness.active_ptys[RECORDING] = object()
    broadcasts.clear()
    held = await operator_decides(app, auth_headers, evidence_id)
    assert held.status_code == 409
    assert decided(broadcasts, evidence_id) == []


@pytest.mark.asyncio
async def test_a_granted_agents_decision_is_announced(app, auth_headers, world, broadcasts):
    """1.1, agent plane."""
    evidence_id = await record_as_agent(app, BUILDER)
    broadcasts.clear()
    response = await agent_decides(app, evidence_id)
    assert response.status_code == 200, response.text
    assert decided(broadcasts, evidence_id) == [{"evidence": evidence_id, "requirement": "FR-1"}]


@pytest.mark.asyncio
async def test_the_announcement_survives_a_merge_that_raises(
    app, auth_headers, world, broadcasts, monkeypatch
):
    """1.1a: the id is read before integration rolls back, so the broadcast cannot 500 the route."""
    from hub import task_integration
    from hub.db.models import Task

    async def loading(session, *args, **kwargs):
        await session.execute(select(Task))
        raise RuntimeError("merge failed")

    monkeypatch.setattr(task_integration, "tasks_awaiting_this_commit", loading, raising=False)
    evidence_id = await record_as_agent(app, BUILDER)
    broadcasts.clear()
    response = await operator_decides(app, auth_headers, evidence_id)
    assert response.status_code == 200, response.text
    assert decided(broadcasts, evidence_id) == [{"evidence": evidence_id, "requirement": "FR-1"}]
    async with async_session_factory() as session:
        assert (await session.execute(select(RequirementEvidence))).scalars().all()[
            0
        ].review_state == "accepted"


@pytest.mark.asyncio
async def test_recording_through_the_agent_plane_marks_the_run(app, auth_headers, world):
    """1.9 (record half); 1.9a control: the operator's record route names no run."""
    run_liveness.runs_that_recorded_evidence.discard(RECORDING)
    await record_as_agent(app, BUILDER)
    assert RECORDING in run_liveness.runs_that_recorded_evidence
    run_liveness.runs_that_recorded_evidence.discard(RECORDING)


@pytest.mark.asyncio
async def test_a_run_end_announces_only_for_a_run_that_recorded(broadcasts):
    """1.9 (announce half)."""
    await agent_trigger._announce_run_end_to_open_views("proj-test", "run-x")
    assert broadcasts == [("proj-test", "spec_updated", {"run_ended": "run-x"})]


@pytest.mark.asyncio
async def test_a_failing_announcement_never_raises_into_a_finished_run(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("stream gone")

    monkeypatch.setattr(agent_trigger.sse_manager, "broadcast", boom)
    await agent_trigger._announce_run_end_to_open_views("proj-test", "run-x")


def test_both_run_ends_announce_after_the_flush_and_only_when_recorded():
    """1.9: after the registry release, after `outside_writes.flush()`, guarded by the set."""
    source = inspect.getsource(agent_trigger)
    for release in (
        "run_liveness.active_ptys.pop(run_id",
        "run_liveness.active_app_server_runs.discard(run_id",
    ):
        at = source.index(release)
        block = source[at : at + 900]
        assert re.search(
            r"recorded_evidence = run_id in run_liveness\.runs_that_recorded_evidence", block
        ), release
        assert "runs_that_recorded_evidence.discard(run_id)" in block, release
        flush = block.index("await outside_writes.flush()")
        assert "if recorded_evidence:" in block[flush:], release
        assert block.index("recorded_evidence =") < flush, release
