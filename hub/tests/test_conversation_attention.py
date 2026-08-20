"""A conversation says whether it needs the operator, without being opened.

This is the expensive half of the navigation problem. `Question` and `PermissionRequest` each
block a run pending an answer, and today none of them are visible anywhere except inside the
conversation that raised them — so with three agents working, a run that stopped to ask
something is found by clicking through agents one at a time while
`Agent.question_timeout_seconds` counts down.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import PermissionRequest, Question, Run
from hub.utils import short_id


async def _sync_agents(app, auth_headers, *names):
    response = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "manual"} for name in names}}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _attention(app, auth_headers, agent="offline"):
    response = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/conversations", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return {row["id"]: row["attention"] for row in response.json()}


async def _conversation(app, auth_headers, message="Check the build", agent="offline") -> str:
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": agent, "message": message},
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    return created.json()["conversation_id"]


async def _run_for(conversation_id: str, agent: str = "offline", status: str = "running") -> str:
    run_id = f"run-{short_id()}"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                conversation_id=conversation_id,
                status=status,
            )
        )
        await session.commit()
    return run_id


@pytest.mark.asyncio
async def test_a_quiet_conversation_is_idle(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "offline")
    conversation_id = await _conversation(app, auth_headers)
    assert (await _attention(app, auth_headers))[conversation_id] == "idle"


@pytest.mark.asyncio
async def test_a_live_run_reads_as_running(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "offline")
    conversation_id = await _conversation(app, auth_headers)
    await _run_for(conversation_id)
    assert (await _attention(app, auth_headers))[conversation_id] == "running"


@pytest.mark.asyncio
async def test_an_unanswered_question_reads_as_waiting(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "offline")
    conversation_id = await _conversation(app, auth_headers)
    run_id = await _run_for(conversation_id)

    async with async_session_factory() as session:
        session.add(
            Question(
                id=f"q-{short_id()}",
                project_id="proj-test",
                from_agent="offline",
                question="Which database should this use?",
                created_by_run_id=run_id,
                conversation_id=conversation_id,
            )
        )
        await session.commit()

    # Waiting outranks running: the run is alive, but it stopped for the operator.
    assert (await _attention(app, auth_headers))[conversation_id] == "waiting"


@pytest.mark.asyncio
async def test_a_pending_permission_request_reads_as_waiting(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "offline")
    conversation_id = await _conversation(app, auth_headers)
    run_id = await _run_for(conversation_id)

    async with async_session_factory() as session:
        session.add(
            PermissionRequest(
                id=f"perm-{short_id()}",
                project_id="proj-test",
                agent="offline",
                run_id=run_id,
                conversation_id=conversation_id,
                tool_name="Bash",
                tool_input={"command": "rm -rf build"},
                status="pending",
            )
        )
        await session.commit()

    assert (await _attention(app, auth_headers))[conversation_id] == "waiting"


@pytest.mark.asyncio
async def test_answering_clears_the_waiting_state(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "offline")
    conversation_id = await _conversation(app, auth_headers)
    run_id = await _run_for(conversation_id, status="completed")
    question_id = f"q-{short_id()}"

    async with async_session_factory() as session:
        session.add(
            Question(
                id=question_id,
                project_id="proj-test",
                from_agent="offline",
                question="Which database should this use?",
                created_by_run_id=run_id,
                conversation_id=conversation_id,
            )
        )
        await session.commit()

    assert (await _attention(app, auth_headers))[conversation_id] == "waiting"

    answered = await app.patch(
        f"/api/v1/projects/proj-test/questions/{question_id}",
        json={"answer": "Postgres"},
        headers=auth_headers,
    )
    assert answered.status_code == 200, answered.text

    assert (await _attention(app, auth_headers))[conversation_id] == "idle"


@pytest.mark.asyncio
async def test_a_question_in_one_conversation_does_not_mark_another(app, auth_headers) -> None:
    """The whole point: a blocked background conversation is visible while a different one is
    open, and the open one is not falsely flagged."""
    await _sync_agents(app, auth_headers, "offline")
    blocked = await _conversation(app, auth_headers, message="Blocked thread")
    quiet = await _conversation(app, auth_headers, message="Quiet thread")
    assert blocked != quiet
    run_id = await _run_for(blocked, status="completed")

    async with async_session_factory() as session:
        session.add(
            Question(
                id=f"q-{short_id()}",
                project_id="proj-test",
                from_agent="offline",
                question="Which database should this use?",
                created_by_run_id=run_id,
                conversation_id=blocked,
            )
        )
        await session.commit()

    attention = await _attention(app, auth_headers)
    assert attention[blocked] == "waiting"
    assert attention[quiet] == "idle"


@pytest.mark.asyncio
async def test_a_question_created_through_the_api_records_its_conversation(
    app, auth_headers
) -> None:
    """2.11 end to end: the denormalised column is populated by the real creation path, not
    only by tests that set it by hand."""
    await _sync_agents(app, auth_headers, "offline")
    conversation_id = await _conversation(app, auth_headers)
    run_id = await _run_for(conversation_id)

    async with async_session_factory() as session:
        from hub.api.v1.questions import ask_question_for_actor
        from hub.schemas.questions import QuestionCreate, QuestionOption

        question = await ask_question_for_actor(
            QuestionCreate(
                from_agent="offline",
                question="Which database?",
                blocking=False,
                options=[QuestionOption(label="Postgres"), QuestionOption(label="SQLite")],
                header="Database",
                multi_select=False,
            ),
            project_id="proj-test",
            from_agent="offline",
            created_by_run_id=run_id,
            session=session,
        )
        assert question.conversation_id == conversation_id

    assert (await _attention(app, auth_headers))[conversation_id] == "waiting"
