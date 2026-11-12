"""F1160 -- a Hub started inside an agent's run never hands that run's variables to its own runs.

Driven 2026-11-11: a scratch Hub on :8030, started from inside an :8000 run, inherited the run's
`HUB_URL` (:8000) and `AW_RUN_TOKEN`. `trigger_agent` prefers an explicit `HUB_URL`, so the Codex
agent it launched sent every `aw-tool` call to :8000 and was refused as an invalid run credential.

Held at `lifespan()` (the variables are gone before the startup re-drain can start a run) and at the
real `POST /agent/trigger` (a run is told the Hub that started it). The control: a `HUB_URL` the
Hub was given on purpose, with no run credential beside it, still wins (`task 3.5`).
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from hub.inherited_run_env import RUN_ENVIRONMENT_NAMES, drop_inherited_run_environment
from tests.conftest import RUN_ENVIRONMENT_NAMES as SUITE_STRIPS
from tests.test_agent_trigger import _await_background_run, _fake_pty

PARENT = {
    "HUB_URL": "http://127.0.0.1:8000",
    "AW_RUN_TOKEN": "aw_run_parent-secret",
    "AW_RUN_ID": "run-parent",
    "AW_AGENT_IDENTITY": "QA",
    "AW_TURN_DEPTH": "3",
    "AW_PERMISSION_POSTURE": "operator",
    "AW_DECISION_TIMEOUT": "17",
    "AW_QUESTION_TIMEOUT": "19",
    "AW_CAN_ADMIN_SPECS": "1",
    "AW_REACH_GRANTS": "C:/elsewhere",
    "AW_WORKSPACE_DIR": "C:/parent/worktree",
}


def test_a_parent_runs_variables_are_dropped():
    environ = {**PARENT, "PATH": "/bin", "DATABASE_URL": "sqlite:///x.db"}

    removed = drop_inherited_run_environment(environ)

    assert environ == {"PATH": "/bin", "DATABASE_URL": "sqlite:///x.db"}
    assert set(removed) == set(PARENT)


def test_a_hub_url_given_on_purpose_is_kept():
    """No run credential beside it: the operator's override (Docker, a reverse proxy)."""
    environ = {"HUB_URL": "http://hub.example.internal:443", "PATH": "/bin"}

    assert drop_inherited_run_environment(environ) == []
    assert environ["HUB_URL"] == "http://hub.example.internal:443"


def test_the_suite_strips_every_name_the_product_drops():
    assert set(RUN_ENVIRONMENT_NAMES) - set(SUITE_STRIPS) <= {"AW_REACH_GRANTS"}


async def test_lifespan_drops_them_before_the_startup_redrain(monkeypatch):
    import hub.main as main

    for name, value in PARENT.items():
        monkeypatch.setenv(name, value)
    seen_at_redrain = {}

    async def _reconcile(*args, **kwargs):
        seen_at_redrain.update({n: os.environ.get(n) for n in PARENT})

    async def _noop(*args, **kwargs):
        return None

    for name in (
        "init_db",
        "log_journal_mode",
        "reconcile_stale_job_runs",
        "init_scheduler",
        "arm_held_queues",
        "terminate_all_active_runs",
        "shutdown_scheduler",
        "_settle_background_runs",
    ):
        monkeypatch.setattr(main, name, _noop, raising=False)
    monkeypatch.setattr(main, "reconcile_interrupted_runs", _reconcile)
    monkeypatch.setattr(main.instance_identity, "load_or_create", lambda: None)
    monkeypatch.setattr(main, "_ui_staleness_warning", lambda: None)
    monkeypatch.setattr(main, "engine", SimpleNamespace(dispose=AsyncMock()))

    try:
        async with main.lifespan(None):
            pass
    except Exception:  # noqa: BLE001 -- only what the re-drain saw is under test
        pass

    assert seen_at_redrain, "lifespan never reached the startup re-drain"
    assert {n: v for n, v in seen_at_redrain.items() if v is not None} == {}


@pytest.mark.asyncio
async def test_a_run_is_told_the_hub_that_started_it(app, auth_headers, bind_runner, monkeypatch):
    for name, value in PARENT.items():
        monkeypatch.setenv(name, value)
    drop_inherited_run_environment()

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"child-agent": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner("child-agent", cli="claude")

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            with patch("hub.bound_address.get", return_value=("127.0.0.1", 8030)):
                response = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "child-agent", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert response.status_code == 200, response.text
                await _await_background_run()

    env = fake_spawn.call_args.kwargs["env"]
    assert env["HUB_URL"] == "http://127.0.0.1:8030"
    assert env["AW_RUN_TOKEN"] != PARENT["AW_RUN_TOKEN"]
    assert env["AW_RUN_ID"] != PARENT["AW_RUN_ID"]
    assert env["AW_AGENT_IDENTITY"] == "child-agent"
    # The ones a run is given only sometimes: none of the parent's may stand in for them.
    for name in ("AW_TURN_DEPTH", "AW_PERMISSION_POSTURE", "AW_DECISION_TIMEOUT"):
        assert env.get(name) != PARENT[name], name
    assert "AW_CAN_ADMIN_SPECS" not in env
    assert env.get("AW_REACH_GRANTS") != PARENT["AW_REACH_GRANTS"]
