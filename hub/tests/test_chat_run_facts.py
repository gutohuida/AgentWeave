"""The chat responses carry facts for the runs their own entries name (F274).

A turn's terminal label and its "Worked for Ns" line are drawn from a `runs` map. That map used
to be read from the agent timeline route, which answers about a fixed window of the fifty most
recent events — and a conversation is not that window. Runs age out of it while their turns are
still on screen, and every such turn renders outcomeless.

So the map is now built by the route that returns the turns, off the run ids **those entries**
name. These tests pin the two properties that follow: the map cannot be evicted by traffic the
response does not contain, and it cannot describe a list other than the one returned.

Every test uses a UNIQUE agent name — the Hub's engine is a module-level singleton and in-memory
SQLite data persists across tests in the same pytest run.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput, Conversation, EventLog, InboundQueueEntry, Run

# The agent timeline route caps its EventLog read at fifty rows (`agents.py:748-752`). Phase 0
# measured the defect by pushing past that; these fixtures do the same, in rows rather than in
# live turns.
TIMELINE_EVENT_WINDOW = 50


async def _project_id(app, auth_headers) -> str:
    resp = await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()["project_id"]


async def _conversation(session, project_id: str, agent: str, conversation_id: str) -> None:
    if await get_conversation_by_id(session, conversation_id) is None:
        session.add(
            Conversation(
                id=conversation_id,
                project_id=project_id,
                agent=agent,
                provider_session_id=conversation_id,
                lifecycle="open",
            )
        )


async def _add_run(
    project_id: str,
    *,
    run_id: str,
    agent: str,
    conversation_id: str,
    status: str = "completed",
    exit_code: int | None = 0,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    outside_workspace_writes: list | None = None,
) -> None:
    async with async_session_factory() as session:
        await _conversation(session, project_id, agent, conversation_id)
        session.add(
            Run(
                id=run_id,
                project_id=project_id,
                agent=agent,
                session_id=conversation_id,
                conversation_id=conversation_id,
                status=status,
                exit_code=exit_code,
                started_at=started_at or datetime.now(timezone.utc),
                ended_at=ended_at,
                outside_workspace_writes=outside_workspace_writes,
                turn_depth=0,
            )
        )
        await session.commit()


async def _add_output(
    project_id: str,
    *,
    out_id: str,
    agent: str,
    conversation_id: str,
    run_id: str | None,
    content: str = "output",
    timestamp: datetime | None = None,
) -> None:
    async with async_session_factory() as session:
        await _conversation(session, project_id, agent, conversation_id)
        session.add(
            AgentOutput(
                id=out_id,
                project_id=project_id,
                agent=agent,
                content=content,
                session_id=conversation_id,
                conversation_id=conversation_id,
                run_id=run_id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _add_delivered_entry(
    project_id: str,
    *,
    entry_id: str,
    agent: str,
    conversation_id: str,
    run_id: str,
    content: str = "go",
    timestamp: datetime | None = None,
) -> None:
    when = timestamp or datetime.now(timezone.utc)
    async with async_session_factory() as session:
        await _conversation(session, project_id, agent, conversation_id)
        session.add(
            InboundQueueEntry(
                id=entry_id,
                project_id=project_id,
                agent=agent,
                origin_type="operator",
                content=content,
                arrived_at=when,
                hop_depth=0,
                state="delivered",
                delivered_in_run_id=run_id,
                delivered_at=when,
                conversation_id=conversation_id,
            )
        )
        await session.commit()


async def _add_lifecycle_events(project_id: str, *, agent: str, run_id: str, count: int) -> None:
    """EventLog rows of the kind that fill the agent timeline's fifty-row window."""
    async with async_session_factory() as session:
        now = datetime.now(timezone.utc)
        for i in range(count):
            session.add(
                EventLog(
                    id=f"ev-{run_id}-{i}",
                    project_id=project_id,
                    agent=agent,
                    event_type="run_started" if i % 2 else "run_completed",
                    timestamp=now + timedelta(milliseconds=i),
                    data={"run_id": run_id, "agent": agent},
                )
            )
        await session.commit()


# ---------------------------------------------------------------------------
# 4.1 — the map is there, and it is the run's own row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_response_carries_facts_for_every_run_its_entries_name(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_rf1"
    started = datetime(2026, 9, 9, 5, 0, 0, tzinfo=timezone.utc)
    await _add_run(
        project_id,
        run_id="run-rf1",
        agent=agent,
        conversation_id="conv-rf1",
        status="stopped",
        exit_code=2,
        started_at=started,
        ended_at=started + timedelta(seconds=8),
    )
    await _add_delivered_entry(
        project_id, entry_id="e-rf1", agent=agent, conversation_id="conv-rf1", run_id="run-rf1"
    )
    await _add_output(
        project_id, out_id="o-rf1", agent=agent, conversation_id="conv-rf1", run_id="run-rf1"
    )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/conv-rf1", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    runs = resp.json()["runs"]
    assert "run-rf1" in runs, f"the response named the run in its entries but not in runs: {runs}"
    facts = runs["run-rf1"]
    assert facts["status"] == "stopped"
    assert facts["exit_code"] == 2
    assert facts["started_at"] is not None
    assert facts["ended_at"] is not None


@pytest.mark.asyncio
async def test_running_is_renamed_started_at_the_boundary(app, auth_headers):
    """`Run.status` says `running`; the client's vocabulary says `started` (design D5)."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_rf1b"
    await _add_run(
        project_id,
        run_id="run-rf1b",
        agent=agent,
        conversation_id="conv-rf1b",
        status="running",
        exit_code=None,
    )
    await _add_output(
        project_id, out_id="o-rf1b", agent=agent, conversation_id="conv-rf1b", run_id="run-rf1b"
    )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/conv-rf1b", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["runs"]["run-rf1b"]["status"] == "started"


@pytest.mark.asyncio
async def test_outside_workspace_writes_never_none_becomes_empty_list(app, auth_headers):
    """`None` is *never observed*, `[]` is *observed and clean*; a default would merge them."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_rf1c"
    await _add_run(
        project_id,
        run_id="run-rf1c-unseen",
        agent=agent,
        conversation_id="conv-rf1c",
        outside_workspace_writes=None,
    )
    await _add_run(
        project_id,
        run_id="run-rf1c-clean",
        agent=agent,
        conversation_id="conv-rf1c",
        outside_workspace_writes=[],
    )
    await _add_output(
        project_id,
        out_id="o-rf1c-1",
        agent=agent,
        conversation_id="conv-rf1c",
        run_id="run-rf1c-unseen",
    )
    await _add_output(
        project_id,
        out_id="o-rf1c-2",
        agent=agent,
        conversation_id="conv-rf1c",
        run_id="run-rf1c-clean",
    )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/conv-rf1c", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    runs = resp.json()["runs"]
    assert runs["run-rf1c-unseen"]["outside_workspace_writes"] is None
    assert runs["run-rf1c-clean"]["outside_workspace_writes"] == []


# ---------------------------------------------------------------------------
# 4.2 — the one that would have caught F274
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_other_conversations_traffic_cannot_evict_this_conversations_run(app, auth_headers):
    """Phase 0's headline, as rows: one conversation's finished run, then enough traffic on
    OTHER conversations of the same agent to overrun any fixed event window. The conversation's
    own response must still say how its turn ended.

    Asserted on the chat response alone — reading the timeline route here would let the test
    pass for the wrong reason.
    """
    project_id = await _project_id(app, auth_headers)
    agent = "agent_rf2"
    await _add_run(
        project_id, run_id="run-rf2-a", agent=agent, conversation_id="conv-rf2-a", status="stopped"
    )
    await _add_output(
        project_id, out_id="o-rf2-a", agent=agent, conversation_id="conv-rf2-a", run_id="run-rf2-a"
    )

    # Eight ordinary turns in other conversations — phase 0's count — each contributing its own
    # run, its own output and seven lifecycle events. Well past fifty events in total.
    for i in range(8):
        other_run = f"run-rf2-filler-{i}"
        other_conv = f"conv-rf2-filler-{i}"
        await _add_run(project_id, run_id=other_run, agent=agent, conversation_id=other_conv)
        await _add_output(
            project_id,
            out_id=f"o-rf2-filler-{i}",
            agent=agent,
            conversation_id=other_conv,
            run_id=other_run,
        )
        await _add_lifecycle_events(project_id, agent=agent, run_id=other_run, count=7)

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/conv-rf2-a", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [e["id"] for e in body["entries"]] == ["o-rf2-a"]
    assert "run-rf2-a" in body["runs"], "the conversation's own run was evicted by other traffic"
    assert body["runs"]["run-rf2-a"]["status"] == "stopped"
    # And nothing it does not name: the map is bounded by this response's entries.
    assert set(body["runs"]) == {"run-rf2-a"}


# ---------------------------------------------------------------------------
# 4.3 — one conversation can overrun the window on its own
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_conversation_naming_more_runs_than_a_window_holds(app, auth_headers):
    """The half that proves widening the event window is not the fix."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_rf3"
    run_count = TIMELINE_EVENT_WINDOW + 10
    base = datetime(2026, 9, 9, 4, 0, 0, tzinfo=timezone.utc)
    for i in range(run_count):
        run_id = f"run-rf3-{i:03d}"
        await _add_run(
            project_id,
            run_id=run_id,
            agent=agent,
            conversation_id="conv-rf3",
            started_at=base + timedelta(seconds=i),
        )
        await _add_output(
            project_id,
            out_id=f"o-rf3-{i:03d}",
            agent=agent,
            conversation_id="conv-rf3",
            run_id=run_id,
            timestamp=base + timedelta(seconds=i),
        )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/conv-rf3", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    named = {e["run_id"] for e in body["entries"] if e["run_id"]}
    assert len(named) == run_count
    assert named == set(body["runs"]), "the response named runs it could not describe"


# ---------------------------------------------------------------------------
# 4.4 — the recent route describes what it returns, not what it read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recent_chat_map_is_taken_after_the_limit_truncation(app, auth_headers):
    """`get_recent_chat` reads `limit` rows per source and then truncates the merge to `limit`.

    A run named only by an entry the truncation removed is not this response's business. Built
    from two sources so the merge really does exceed `limit` — each query's own `.limit()` alone
    would not create the case.
    """
    project_id = await _project_id(app, auth_headers)
    agent = "agent_rf4"
    base = datetime(2026, 9, 9, 3, 0, 0, tzinfo=timezone.utc)
    await _add_run(project_id, run_id="run-rf4-old", agent=agent, conversation_id="conv-rf4")
    await _add_run(project_id, run_id="run-rf4-new", agent=agent, conversation_id="conv-rf4")
    # The two oldest entries in the merge, and the only ones naming `run-rf4-old`.
    for i in range(2):
        await _add_delivered_entry(
            project_id,
            entry_id=f"e-rf4-{i}",
            agent=agent,
            conversation_id="conv-rf4",
            run_id="run-rf4-old",
            timestamp=base + timedelta(seconds=i),
        )
    for i in range(2):
        await _add_output(
            project_id,
            out_id=f"o-rf4-{i}",
            agent=agent,
            conversation_id="conv-rf4",
            run_id="run-rf4-new",
            timestamp=base + timedelta(seconds=10 + i),
        )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat?limit=2", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    returned = {e["run_id"] for e in body["entries"] if e["run_id"]}
    assert returned == {"run-rf4-new"}, f"fixture did not truncate as intended: {body['entries']}"
    assert "run-rf4-new" in body["runs"]
    assert "run-rf4-old" not in body["runs"], "the map described entries the response dropped"


@pytest.mark.asyncio
async def test_recent_chat_carries_facts_for_the_runs_it_returns(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_rf4b"
    await _add_run(
        project_id,
        run_id="run-rf4b",
        agent=agent,
        conversation_id="conv-rf4b",
        status="failed",
        exit_code=1,
    )
    await _add_output(
        project_id, out_id="o-rf4b", agent=agent, conversation_id="conv-rf4b", run_id="run-rf4b"
    )

    resp = await app.get(f"/api/v1/projects/proj-test/agent/{agent}/chat", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["runs"]["run-rf4b"]["status"] == "failed"


# ---------------------------------------------------------------------------
# 4.5 — a run id with no row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entry_naming_an_absent_run_leaves_the_key_absent(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_rf5"
    await _add_run(project_id, run_id="run-rf5-real", agent=agent, conversation_id="conv-rf5")
    await _add_output(
        project_id, out_id="o-rf5-1", agent=agent, conversation_id="conv-rf5", run_id="run-rf5-real"
    )
    await _add_output(
        project_id, out_id="o-rf5-2", agent=agent, conversation_id="conv-rf5", run_id="run-rf5-gone"
    )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/conv-rf5", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    runs = resp.json()["runs"]
    assert "run-rf5-real" in runs
    assert "run-rf5-gone" not in runs


@pytest.mark.asyncio
async def test_a_conversation_naming_no_run_gets_an_empty_map(app, auth_headers):
    """And empty means empty: the agent's runs elsewhere are not this conversation's."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_rf5b"
    await _add_output(
        project_id, out_id="o-rf5b", agent=agent, conversation_id="conv-rf5b", run_id=None
    )
    await _add_run(project_id, run_id="run-rf5b-other", agent=agent, conversation_id="conv-rf5b-2")
    await _add_output(
        project_id,
        out_id="o-rf5b-2",
        agent=agent,
        conversation_id="conv-rf5b-2",
        run_id="run-rf5b-other",
    )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/conv-rf5b", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["runs"] == {}
