"""Per-conversation runtime overrides on POST /agent/trigger
(2026-08-04-hub-model-control-and-provisioning)."""

import json
from unittest.mock import patch

import pytest

from hub.sse import sse_manager
from tests.test_agent_trigger import _await_background_run, _fake_pty


@pytest.mark.asyncio
async def test_an_invalid_override_refuses_the_turn_and_starts_no_process(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"override-invalid": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("override-invalid", cli="claude")

    fake_spawn = _fake_pty([])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={
                "agent": "override-invalid",
                "message": "hi",
                "session_mode": "new",
                "overrides": {"effort": "not-a-real-value"},
            },
            headers=auth_headers,
        )
    assert response.status_code == 400
    assert "not-a-real-value" in response.json()["detail"]
    fake_spawn.assert_not_called()


@pytest.mark.asyncio
async def test_an_effort_value_valid_for_the_other_provider_is_refused(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"override-cross": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("override-cross", cli="codex")

    fake_spawn = _fake_pty([])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={
                "agent": "override-cross",
                "message": "hi",
                "session_mode": "new",
                # "max" is a valid Claude effort value but not one Codex's catalog declares.
                "overrides": {"effort": "max"},
            },
            headers=auth_headers,
        )
    assert response.status_code == 400
    fake_spawn.assert_not_called()


@pytest.mark.asyncio
async def test_a_valid_override_is_applied_to_the_spawned_command(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"override-valid": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("override-valid", cli="claude", model="claude-sonnet-5")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={
                    "agent": "override-valid",
                    "message": "hi",
                    "session_mode": "new",
                    "overrides": {"model": "claude-opus-5", "effort": "high"},
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            await _await_background_run()

    command = fake_spawn.call_args.args[0]
    assert command[command.index("--model") + 1] == "claude-opus-5"
    assert command[command.index("--effort") + 1] == "high"


@pytest.mark.asyncio
async def test_an_override_persists_on_the_conversation_and_survives_reload(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"override-persist": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("override-persist", cli="claude")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={
                    "agent": "override-persist",
                    "message": "hi",
                    "session_mode": "new",
                    "overrides": {"effort": "high"},
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            await _await_background_run()

    conversations = await app.get(
        "/api/v1/projects/proj-test/agent/override-persist/conversations", headers=auth_headers
    )
    assert conversations.status_code == 200
    body = conversations.json()
    assert len(body) == 1
    assert body[0]["runtime_overrides"] == {"effort": "high"}


@pytest.mark.asyncio
async def test_a_new_conversation_does_not_inherit_a_previous_conversations_overrides(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"override-fresh": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("override-fresh", cli="claude")

    # Two separate PtySession.spawn mocks — each returns its own session object, so the
    # second call's read loop doesn't hit the first call's already-exhausted side_effect
    # iterator (a shared fake session across two real spawns hangs the second one).
    first_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", first_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            first = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={
                    "agent": "override-fresh",
                    "message": "hi",
                    "session_mode": "new",
                    "overrides": {"effort": "high"},
                },
                headers=auth_headers,
            )
            assert first.status_code == 200
            await _await_background_run()

    second_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s2"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", second_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            second = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "override-fresh", "message": "hi again", "session_mode": "new"},
                headers=auth_headers,
            )
            assert second.status_code == 200
            await _await_background_run()

    conversations = await app.get(
        "/api/v1/projects/proj-test/agent/override-fresh/conversations", headers=auth_headers
    )
    body = conversations.json()
    assert len(body) == 2
    overrides_by_id = {c["id"]: c["runtime_overrides"] for c in body}
    assert overrides_by_id[first.json()["conversation_id"]] == {"effort": "high"}
    assert overrides_by_id[second.json()["conversation_id"]] in (None, {})


@pytest.mark.asyncio
async def test_a_conversation_whose_model_changed_attributes_usage_per_turn(
    app, auth_headers, bind_runner
):
    """agent-context-usage: 'Usage SHALL be attributed to the model that ran each turn.'"""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"model-switch": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("model-switch", cli="codex")

    status = await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)
    project_id = status.json()["project_id"]
    queue = sse_manager.subscribe(project_id)
    try:
        first_spawn = _fake_pty(
            [
                '{"type":"thread.started","thread_id":"thread-1"}\n',
                '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}\n',
            ]
        )
        with patch("hub.api.v1.agent_trigger.PipeSession.spawn", first_spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
                first = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={
                        "agent": "model-switch",
                        "message": "hi",
                        "session_mode": "new",
                        "overrides": {"model": "gpt-5.6-sol"},
                    },
                    headers=auth_headers,
                )
                assert first.status_code == 200
                await _await_background_run()

        conversation_id = first.json()["conversation_id"]
        second_spawn = _fake_pty(
            [
                '{"type":"thread.started","thread_id":"thread-1"}\n',
                '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}\n',
            ]
        )
        with patch("hub.api.v1.agent_trigger.PipeSession.spawn", second_spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
                second = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={
                        "agent": "model-switch",
                        "message": "hi again",
                        "conversation_id": conversation_id,
                        "overrides": {"model": "gpt-5.4-mini"},
                    },
                    headers=auth_headers,
                )
                assert second.status_code == 200
                await _await_background_run()

        models_seen = []
        while not queue.empty():
            event = queue.get_nowait()
            if event.event == "context_warning":
                models_seen.append(json.loads(event.data)["model"])
        assert models_seen == ["gpt-5.6-sol", "gpt-5.4-mini"]
    finally:
        sse_manager.unsubscribe(project_id, queue)
