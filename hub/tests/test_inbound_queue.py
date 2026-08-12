from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Run
from hub.inbound_queue import (
    can_start,
    deliver_entries_with_run,
    format_turn_prompt,
    new_entry,
    queued_entries,
    return_run_entries,
)
from hub.turn_scheduler import schedule_agent


@pytest.mark.asyncio
async def test_operator_and_agent_entries_share_ordered_typed_queue(app):
    async with async_session_factory() as db:
        operator = new_entry(
            project_id="proj-test",
            agent="queue-order-target",
            origin_type="operator",
            content="first",
            hop_depth=0,
        )
        peer = new_entry(
            project_id="proj-test",
            agent="queue-order-target",
            origin_type="agent",
            origin_agent="user",
            content="second",
            hop_depth=1,
        )
        db.add_all([operator, peer])
        await db.commit()
        rows = await queued_entries(db, "proj-test", "queue-order-target")

    assert [row.content for row in rows] == ["first", "second"]
    assert [(row.origin_type, row.origin_agent) for row in rows] == [
        ("operator", None),
        ("agent", "user"),
    ]


@pytest.mark.asyncio
async def test_delivery_and_run_creation_are_one_commit(app):
    async with async_session_factory() as db:
        entries = [
            new_entry(
                project_id="proj-test",
                agent="atomic-target",
                origin_type="operator",
                content=str(i),
                hop_depth=i,
            )
            for i in range(3)
        ]
        db.add_all(entries)
        await db.commit()
        run = Run(
            id="run-atomic",
            project_id="proj-test",
            agent="atomic-target",
            status="running",
            turn_depth=0,
        )
        delivered = await deliver_entries_with_run(
            db,
            project_id="proj-test",
            agent="atomic-target",
            entry_ids=[entry.id for entry in entries[:2]],
            run=run,
        )

    assert [entry.content for entry in delivered] == ["0", "1"]
    async with async_session_factory() as db:
        assert await db.get(Run, "run-atomic") is not None
        waiting = await queued_entries(db, "proj-test", "atomic-target")
        assert [entry.content for entry in waiting] == ["2"]


@pytest.mark.asyncio
async def test_interrupted_run_returns_delivered_entries(app):
    async with async_session_factory() as db:
        entry = new_entry(
            project_id="proj-test",
            agent="retry-target",
            origin_type="operator",
            content="retry",
            hop_depth=0,
        )
        db.add(entry)
        await db.commit()
        run = Run(
            id="run-retry",
            project_id="proj-test",
            agent="retry-target",
            status="running",
            turn_depth=0,
        )
        await deliver_entries_with_run(
            db,
            project_id="proj-test",
            agent="retry-target",
            entry_ids=[entry.id],
            run=run,
        )
        returned = await return_run_entries(db, run.id)
        await db.commit()
        waiting = await queued_entries(db, "proj-test", "retry-target")

    assert returned == [entry.id]
    assert [row.id for row in waiting] == [entry.id]


def test_hop_budget_and_inline_prompt_use_typed_origin():
    deep = new_entry(
        project_id="p",
        agent="a",
        origin_type="agent",
        origin_agent="user",
        content="peer",
        hop_depth=7,
    )
    operator = new_entry(
        project_id="p", agent="a", origin_type="operator", content="reset", hop_depth=0
    )
    assert can_start([deep], 6) is False
    assert can_start([deep, operator], 6) is True
    prompt = format_turn_prompt([deep, operator])
    assert 'Agent "user" (hop 7):\npeer' in prompt
    assert "Operator (hop 0):\nreset" in prompt


def test_scheduled_job_origin_is_typed_and_has_no_origin_agent():
    job = new_entry(
        project_id="p",
        agent="a",
        origin_type="job",
        content="scheduled",
        hop_depth=0,
    )
    assert format_turn_prompt([job]) == (
        "[AgentWeave inbound queue — delivered inline in arrival order]\n\n"
        "Scheduled job (hop 0):\nscheduled"
    )
    with pytest.raises(ValueError, match="origin_agent"):
        new_entry(
            project_id="p",
            agent="a",
            origin_type="job",
            origin_agent="fake",
            content="invalid",
            hop_depth=0,
        )


@pytest.mark.asyncio
async def test_queue_settings_defaults_update_and_reject_invalid(app, auth_headers):
    defaults = await app.get("/api/v1/projects/proj-test/queue/settings", headers=auth_headers)
    assert defaults.status_code == 200
    assert defaults.json() == {
        "hop_budget": 6,
        "turn_delivery_cap": 10,
        "agent_budget": 8,
        "allow_agent_jobs": False,
    }

    updated = await app.patch(
        "/api/v1/projects/proj-test/queue/settings",
        json={"hop_budget": 4, "turn_delivery_cap": 2},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json() == {
        "hop_budget": 4,
        "turn_delivery_cap": 2,
        "agent_budget": 8,
        "allow_agent_jobs": False,
    }

    invalid = await app.patch(
        "/api/v1/projects/proj-test/queue/settings",
        json={"hop_budget": 0, "turn_delivery_cap": "many"},
        headers=auth_headers,
    )
    assert invalid.status_code == 422

    await app.patch(
        "/api/v1/projects/proj-test/queue/settings",
        json={"hop_budget": 6, "turn_delivery_cap": 10},
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_undelivered_entry_can_be_withdrawn(app, auth_headers):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"withdraw-manual": {"runner": "manual"}}}},
        headers=auth_headers,
    )
    trigger = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "withdraw-manual", "message": "cancel me"},
        headers=auth_headers,
    )
    entry_id = trigger.json()["queue_entry_id"]
    queue_status = await app.get(
        "/api/v1/projects/proj-test/queue/withdraw-manual/status", headers=auth_headers
    )
    assert queue_status.json()["waiting_count"] == 1
    assert "manual" in queue_status.json()["waiting_reason"].lower()

    withdrawn = await app.delete(
        f"/api/v1/projects/proj-test/queue/entries/{entry_id}", headers=auth_headers
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["state"] == "withdrawn"
    second = await app.delete(
        f"/api/v1/projects/proj-test/queue/entries/{entry_id}", headers=auth_headers
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_operator_input_does_not_drain_another_conversation(app, auth_headers, bind_runner):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={
            "data": {
                "agents": {
                    "hop-source": {"runner": "claude"},
                    "hop-target": {"runner": "claude"},
                }
            }
        },
        headers=auth_headers,
    )
    await bind_runner("hop-target", cli="claude")
    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-hop-source",
                project_id="proj-test",
                agent="hop-source",
                status="running",
                turn_depth=6,
            )
        )
        await db.commit()

    with patch("hub.api.v1.agent_trigger.PtySession.spawn") as spawn:
        peer = await app.post(
            "/api/v1/projects/proj-test/messages",
            json={
                "from": "hop-source",
                "to": "hop-target",
                "content": "deep peer work",
                "run_id": "run-hop-source",
            },
            headers=auth_headers,
        )
        assert peer.status_code == 201
        spawn.assert_not_called()

    queued = await app.get(
        "/api/v1/projects/proj-test/queue/hop-target?state=queued", headers=auth_headers
    )
    assert [(row["content"], row["hop_depth"]) for row in queued.json()] == [("deep peer work", 7)]
    queue_status = await app.get(
        "/api/v1/projects/proj-test/queue/hop-target/status", headers=auth_headers
    )
    assert queue_status.json()["waiting_reason"] == "hop budget exhausted"

    fake_session = MagicMock()
    fake_session.pid = 6001
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"hop-session"}\n',
        "",
    ]
    fake_session.wait.return_value = 0
    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            reset = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "hop-target", "message": "operator reset"},
                headers=auth_headers,
            )
            assert reset.status_code == 200
            assert reset.json()["status"] == "running"
            tasks = list(agent_trigger._background_runs)
            for task in tasks:
                await task

    async with async_session_factory() as db:
        run = await db.get(Run, reset.json()["run_id"])
        assert run.turn_depth == 0
        result = await db.execute(
            select(InboundQueueEntry).where(InboundQueueEntry.agent == "hop-target")
        )
        entries = list(result.scalars().all())
    assert [entry.state for entry in entries] == ["queued", "delivered"]
    assert entries[0].conversation_id != entries[1].conversation_id


@pytest.mark.asyncio
async def test_delivery_cap_defers_entries_to_following_turns(app, auth_headers, bind_runner):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"cap-target": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner("cap-target", cli="claude")
    from hub.db.models import Project

    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.turn_delivery_cap = 2
        conversation = Conversation(
            id="conv-cap-target",
            project_id="proj-test",
            agent="cap-target",
            lifecycle="open",
        )
        db.add_all(
            [conversation]
            + [
                new_entry(
                    project_id="proj-test",
                    agent="cap-target",
                    origin_type="operator",
                    content=f"item {index}",
                    hop_depth=0,
                    session_mode="new",
                    conversation_id=conversation.id,
                )
                for index in range(3)
            ]
        )
        await db.commit()

    def completed_session(pid, session_id):
        session = MagicMock()
        session.pid = pid
        session.read.side_effect = [
            '{"type":"result","subtype":"success","is_error":false,'
            f'"session_id":"{session_id}"}}\n',
            "",
        ]
        session.wait.return_value = 0
        return session

    spawn = MagicMock(
        side_effect=[completed_session(7001, "cap-1"), completed_session(7002, "cap-2")]
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            result = await schedule_agent("proj-test", "cap-target")
            assert result.response is not None
            while agent_trigger._background_runs:
                for task in list(agent_trigger._background_runs):
                    await task

    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.agent == "cap-target")
                    .order_by(InboundQueueEntry.sequence)
                )
            )
            .scalars()
            .all()
        )
        project = await db.get(Project, "proj-test")
        project.turn_delivery_cap = 10
        await db.commit()

    run_ids = [entry.delivered_in_run_id for entry in rows]
    assert run_ids[0] == run_ids[1]
    assert run_ids[2] != run_ids[1]
    assert spawn.call_count == 2


@pytest.mark.asyncio
async def test_queue_status_probes_the_bound_runner_not_the_agent_name(
    app, auth_headers, bind_runner
):
    """The reported reason must come from the runner the agent is bound to.

    Probing without the Runner overlay falls through to `RUNNER_CLI["native"] is
    None`, whose fallback is the agent's own name — so an agent called
    `codex-spec` bound to the `codex` runner was reported as
    "Runner CLI 'codex-spec' was not found in PATH". It was launchable. The
    false reason masked the real one, which at the time was that its project
    had no git repository for an isolated worktree — no longer a blocker, but
    the masking is the defect this test pins.
    """
    # The agent row must exist before a runner can be bound to it.
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"codex-spec": {}}}},
        headers=auth_headers,
    )
    await bind_runner("codex-spec", cli="codex")

    await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "codex-spec", "message": "hello"},
        headers=auth_headers,
    )

    status = await app.get(
        "/api/v1/projects/proj-test/queue/codex-spec/status", headers=auth_headers
    )

    assert status.status_code == 200
    assert "codex-spec' was not found" not in (status.json().get("waiting_reason") or "")


@pytest.mark.asyncio
async def test_queue_status_does_not_report_a_missing_repository_as_a_blocker(
    app, auth_headers, bind_runner
):
    """A project with no git repository stops nothing, so nothing may say it does.

    This reason existed while a writing agent was refused in a non-repository
    project. It runs in the project directory now, so naming the repository
    would describe a state that blocks no turn — and send the operator to fix
    something that is not broken.

    The entry is queued directly rather than through the trigger, because the
    suite stubs worktree provisioning away: a triggered turn starts, and then
    there is nothing waiting to explain.
    """
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"needs-a-repo": {}}}},
        headers=auth_headers,
    )
    await bind_runner("needs-a-repo", cli="claude")

    async with async_session_factory() as session:
        session.add(
            InboundQueueEntry(
                id="entry-needs-a-repo",
                project_id="proj-test",
                agent="needs-a-repo",
                origin_type="operator",
                content="hello",
                hop_depth=0,
                state="queued",
            )
        )
        await session.commit()

    status = await app.get(
        "/api/v1/projects/proj-test/queue/needs-a-repo/status", headers=auth_headers
    )

    assert status.status_code == 200
    # The project root under the autouse workspace fixture is a bare tmp_path, not a repo.
    reason = status.json()["waiting_reason"] or ""
    assert "git" not in reason.lower(), reason
    assert "repository" not in reason.lower(), reason
