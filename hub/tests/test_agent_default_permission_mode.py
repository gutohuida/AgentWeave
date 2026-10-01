"""An agent's default permission posture — task 3.2 of 2026-08-08-agent-configuration-page.

The posture sits between the conversation's own choice and the built-in fallback, and it is the
editable home of what `Agent.config["yolo"]` has been expressing as a boolean all along. These
tests pin both halves: that the two spellings cannot disagree, and that the default actually
reaches the spawned command for a run nobody was at a composer for.
"""

from unittest.mock import patch

import pytest

from tests.test_agent_trigger import _await_background_run, _fake_pty


async def _set_posture(app, auth_headers, name, mode):
    return await app.patch(
        f"/api/v1/projects/proj-test/agents/{name}",
        json={"default_permission_mode": mode},
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_the_posture_and_the_legacy_yolo_flag_cannot_disagree(app, auth_headers, add_agent):
    """`yolo` is the older two-valued spelling of this setting, not a second setting.

    `runner_commands`, `codex_appserver` and the collaboration-readiness check all read the flag.
    Letting the two drift produces the specific incoherence of a run under "Ask me" whose `yolo`
    suppresses the `--allowedTools` allowlist its own MCP tools need.
    """
    await add_agent("posture-sync")

    resp = await _set_posture(app, auth_headers, "posture-sync", "bypassPermissions")
    assert resp.status_code == 200
    assert resp.json()["default_permission_mode"] == "bypassPermissions"
    assert resp.json()["config"]["yolo"] is True

    resp = await _set_posture(app, auth_headers, "posture-sync", "manual")
    assert resp.status_code == 200
    assert resp.json()["config"]["yolo"] is False

    # Clearing means the built-in default, which is what the settings row says. An agent that
    # silently stayed at full access after the operator cleared full access would be the worst
    # available reading of "cleared".
    resp = await _set_posture(app, auth_headers, "posture-sync", None)
    assert resp.status_code == 200
    assert resp.json()["default_permission_mode"] is None
    assert resp.json()["config"]["yolo"] is False


@pytest.mark.asyncio
async def test_a_body_setting_both_ends_with_them_agreeing(app, auth_headers, add_agent):
    """The posture is applied after the config merge, so it wins — one choice, one answer."""
    await add_agent("posture-both")

    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/posture-both",
        json={"config": {"yolo": True}, "default_permission_mode": "acceptEdits"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["default_permission_mode"] == "acceptEdits"
    assert resp.json()["config"]["yolo"] is False


@pytest.mark.asyncio
async def test_an_unknown_posture_is_refused_and_stores_nothing(app, auth_headers, add_agent):
    await add_agent("posture-invalid")

    resp = await _set_posture(app, auth_headers, "posture-invalid", "yolo-please")
    assert resp.status_code == 400
    assert "acceptEdits" in resp.json()["detail"]

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    row = next(a for a in resp.json() if a["name"] == "posture-invalid")
    assert row["default_permission_mode"] is None


@pytest.mark.asyncio
async def test_the_posture_is_settable_without_a_runner_bound(app, auth_headers, add_agent):
    """Validated against the catalog, not against the agent's provider.

    An agent may have no runner bound, and rebinding one must not invalidate a default the
    operator already chose.
    """
    await add_agent("posture-unbound")

    resp = await _set_posture(app, auth_headers, "posture-unbound", "manual")
    assert resp.status_code == 200

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    row = next(a for a in resp.json() if a["name"] == "posture-unbound")
    assert row["default_permission_mode"] == "manual"
    assert row["runner_id"] is None


@pytest.mark.asyncio
async def test_the_agents_default_reaches_a_run_that_states_no_posture(
    app, auth_headers, bind_runner
):
    """The point of the setting: a run nobody was at a composer for still has an answer."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"posture-applied": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("posture-applied", cli="claude")
    assert (await _set_posture(app, auth_headers, "posture-applied", "manual")).status_code == 200

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "posture-applied", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200, resp.text
            await _await_background_run()

    command = fake_spawn.call_args.args[0]
    assert command[command.index("--permission-mode") + 1] == "manual"
    # The default posture the operator did not choose must not also be appended — two
    # `--permission-mode` flags is the failure mode where the pill appears to work and does not.
    assert command.count("--permission-mode") == 1
    assert "--dangerously-skip-permissions" not in command


@pytest.mark.asyncio
async def test_a_conversations_own_choice_beats_the_agents_default(app, auth_headers, bind_runner):
    """`default` means what a run starts from, not what it is held to."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"posture-beaten": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("posture-beaten", cli="claude")
    assert (await _set_posture(app, auth_headers, "posture-beaten", "manual")).status_code == 200

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={
                    "agent": "posture-beaten",
                    "message": "hi",
                    "session_mode": "new",
                    "overrides": {"permission_mode": "acceptEdits"},
                },
                headers=auth_headers,
            )
            assert resp.status_code == 200, resp.text
            await _await_background_run()

    command = fake_spawn.call_args.args[0]
    # Stated on the conversation, so it wins over both the agent's default and the Hub's.
    assert command[command.index("--permission-mode") + 1] == "acceptEdits"
    assert "--permission-prompt-tool" not in command
    assert command.count("--permission-mode") == 1


@pytest.mark.asyncio
async def test_an_agent_with_no_default_is_unchanged(app, auth_headers, bind_runner):
    """The migration adds no backfill, so every existing agent has to behave exactly as before."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"posture-none": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("posture-none", cli="claude")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "posture-none", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200, resp.text
            await _await_background_run()

    command = fake_spawn.call_args.args[0]
    # The Hub's default, which since 2026-08-13 is the workspace posture — `manual` plus an
    # approver — so an agent given no configuration can still run what it wrote.
    assert command[command.index("--permission-mode") + 1] == "manual"
    assert "--permission-prompt-tool" in command


# --- What the roster says a run gets at rest (F283) ----------------------------------------------
# `the-permissions-pill-shows-the-posture-the-run-gets`, design D2/D3/D5. The pills and the settings
# select read these two fields, so each row below is the posture the spawn would really use.


async def _roster_postures(app, auth_headers):
    listed = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return {
        row["name"]: (row["permission_mode_at_rest"], row["permission_mode_built_in"])
        for row in listed.json()
    }


@pytest.mark.asyncio
async def test_the_roster_states_the_posture_each_agent_gets_at_rest(
    app, auth_headers, add_agent, bind_runner
):
    await add_agent("plain")
    await bind_runner("plain", cli="claude")
    await add_agent("no-server", config={"hub_client": "cli"})
    await bind_runner("no-server", cli="claude")
    await add_agent("autonomous", config={"yolo": True})
    await bind_runner("autonomous", cli="claude")
    await add_agent("codexer")
    await bind_runner("codexer", cli="codex")
    await add_agent("copiloter")
    await bind_runner("copiloter", cli="copilot")
    await add_agent("unbound")

    postures = await _roster_postures(app, auth_headers)

    assert postures["plain"] == ("workspace", "workspace")
    assert postures["no-server"] == ("acceptEdits", "acceptEdits")
    # Clearing the default clears the flag too, so the blank option names the non-yolo posture.
    assert postures["autonomous"] == ("bypassPermissions", "workspace")
    assert postures["codexer"] == ("acceptEdits", "acceptEdits")
    assert postures["copiloter"] == ("workspace", "workspace")
    # No runner, no run to describe.
    assert postures["unbound"] == (None, None)


@pytest.mark.asyncio
async def test_the_roster_reads_hub_client_the_way_the_spawn_does(
    app, auth_headers, add_agent, bind_runner
):
    """The spawn reads `get_agent_config`, where a session-wide `hub_client` fills in the session's
    per-agent entry *before* that entry is laid over `Agent.config`, so it beats a `hub_client`
    stored on the row (design D2, R2 and R3). A roster that merged in another order would say
    "Workspace only" for a run spawned under "Edit files"."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"hub_client": "cli", "agents": {}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await add_agent("inherits")
    await bind_runner("inherits", cli="claude")
    await add_agent("overridden", config={"hub_client": "mcp"})
    await bind_runner("overridden", cli="claude")

    postures = await _roster_postures(app, auth_headers)

    assert postures["inherits"] == ("acceptEdits", "acceptEdits")
    assert postures["overridden"] == ("acceptEdits", "acceptEdits")
