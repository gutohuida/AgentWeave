"""A runner's flags cannot override its model or the posture (F599, F600).

`spec/changes/a-runner-s-flags-cannot-override-the-posture`. The command builder appends a runner's
`flags` after the Hub's own `--model` and posture flags, so a `--dangerously-skip-permissions`
runner wrote outside the workspace while the roster said `workspace`; and Add-agent bound such a
runner because it matched cli and model. The live drive is `scripts/drive/d1015_f599_runner_flags.py`.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Agent, Runner
from hub.runner_flag_rules import posture_flags_problem

BASE = "/api/v1/projects/proj-test"


@pytest.mark.parametrize(
    "cli, flags, owner",
    [
        ("claude", ["--dangerously-skip-permissions"], "posture"),
        ("claude", ["--permission-mode", "bypassPermissions"], "posture"),
        ("claude", ["--permission-mode=acceptEdits"], "posture"),
        ("claude", ["--model=opus"], "model"),
        ("claude", ["--allowedTools", "Bash"], "posture"),
        ("claude", ["--settings", "s.json"], "posture"),
        ("codex", ["-m", "o3"], "model"),
        ("codex", ["--sandbox=danger-full-access"], "posture"),
        ("codex", ["-c", "sandbox_mode=danger-full-access"], "posture"),
        ("codex", ["--config=approval_policy=never"], "posture"),
        ("copilot", ["--model", "gpt-5"], "model"),
    ],
)
def test_an_override_flag_is_named_with_its_owner(cli, flags, owner):
    problem = posture_flags_problem(cli, flags)
    assert problem is not None and owner in problem
    assert flags[0].split("=")[0] in problem


@pytest.mark.parametrize(
    "cli, flags",
    [
        ("claude", ["--mcp-config", "extra.json"]),
        ("claude", ["--verbose"]),
        ("codex", ["-c", "model_reasoning_summary=detailed"]),
        ("codex", ["--no-app-server"]),
        ("copilot", ["--allow-all-tools"]),
        ("claude", None),
    ],
)
def test_other_flags_may_stand(cli, flags):
    assert posture_flags_problem(cli, flags) is None


@pytest.mark.asyncio
async def test_create_and_patch_refuse_an_override_flag(app, auth_headers):
    refused = await app.post(
        f"{BASE}/runners",
        json={"name": "bypass", "cli": "claude", "flags": ["--dangerously-skip-permissions"]},
        headers=auth_headers,
    )
    assert refused.status_code == 400
    assert "--dangerously-skip-permissions" in refused.json()["detail"]

    plain = await app.post(
        f"{BASE}/runners", json={"name": "plain", "cli": "claude"}, headers=auth_headers
    )
    assert plain.status_code == 201
    runner_id = plain.json()["id"]
    patched = await app.patch(
        f"{BASE}/runners/{runner_id}", json={"flags": ["--model", "opus"]}, headers=auth_headers
    )
    assert patched.status_code == 400
    assert "model" in patched.json()["detail"]
    async with async_session_factory() as db:
        assert (await db.get(Runner, runner_id)).flags is None


async def _stored_flagged_runner(agent):
    """A runner row from before this change, bound to an agent."""
    async with async_session_factory() as db:
        db.add(
            Runner(
                id="runner-f599-old",
                project_id="proj-test",
                name="old bypass",
                cli="claude",
                flags=["--dangerously-skip-permissions"],
            )
        )
        db.add(
            Agent(id=f"ag-{agent}", project_id="proj-test", name=agent, runner_id="runner-f599-old")
        )
        await db.commit()


@pytest.mark.asyncio
async def test_a_stored_override_flag_makes_the_runner_not_launchable(app, auth_headers):
    await _stored_flagged_runner("old599")

    verdicts = (await app.get(f"{BASE}/runners/launchability", headers=auth_headers)).json()
    verdict = verdicts["runners"]["runner-f599-old"]
    assert verdict["runnable"] is False
    assert "--dangerously-skip-permissions" in verdict["reason"]

    with patch("hub.api.v1.agent_trigger.PtySession.spawn") as spawn:  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            sent = await app.post(
                f"{BASE}/agent/trigger",
                json={"agent": "old599", "message": "write outside"},
                headers=auth_headers,
            )
    spawn.assert_not_called()
    assert "--dangerously-skip-permissions" in sent.text


@pytest.mark.asyncio
async def test_a_stored_runner_can_still_be_repaired_by_patch(app, auth_headers):
    await _stored_flagged_runner("fix599")
    renamed = await app.patch(
        f"{BASE}/runners/runner-f599-old", json={"name": "renamed"}, headers=auth_headers
    )
    assert renamed.status_code == 200
    fixed = await app.patch(
        f"{BASE}/runners/runner-f599-old", json={"flags": []}, headers=auth_headers
    )
    assert fixed.status_code == 200
    verdicts = (await app.get(f"{BASE}/runners/launchability", headers=auth_headers)).json()
    assert "dangerously" not in (verdicts["runners"]["runner-f599-old"]["reason"] or "")


@pytest.mark.asyncio
async def test_add_agent_binds_only_a_plain_runner(app, auth_headers):
    """F600: a flagged and a provider runner of the same cli and model, created first."""
    async with async_session_factory() as db:
        db.add(
            Runner(
                id="runner-f600-flagged",
                project_id="proj-test",
                name="flagged",
                cli="claude",
                model="haiku",
                flags=["--mcp-config", "x.json"],
            )
        )
        await db.commit()
    created = await app.post(
        f"{BASE}/agents",
        json={"name": "plain600", "provider": "claude", "model": "haiku"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    async with async_session_factory() as db:
        runner = await db.get(Runner, created.json()["runner_id"])
    assert runner.id != "runner-f600-flagged"
    assert not runner.flags

    again = await app.post(
        f"{BASE}/agents",
        json={"name": "plain600b", "provider": "claude", "model": "haiku"},
        headers=auth_headers,
    )
    assert again.json()["runner_id"] == runner.id, "the plain runner is reused, not duplicated"
    async with async_session_factory() as db:
        count = len(
            (await db.execute(select(Runner).where(Runner.model == "haiku"))).scalars().all()
        )
    assert count == 2


def test_a_runner_cannot_bring_back_the_operators_setting_sources():
    """F454: the Hub passes `--setting-sources project,local`; a runner flag after it would win."""
    problem = posture_flags_problem("claude", ["--setting-sources", "user,project,local"])
    assert problem is not None and "--setting-sources" in problem


def test_every_claude_agent_run_loads_only_the_projects_setting_sources():
    """F454, at the builder: one occurrence, project and local only, in every Claude argv."""
    from hub.runner_adapters import build_command

    for kwargs in ({}, {"yolo": True}, {"session_id": "s-1"}):
        cmd = build_command(runner="claude", cli="claude", prompt="hi", **kwargs)
        assert cmd.count("--setting-sources") == 1
        assert cmd[cmd.index("--setting-sources") + 1] == "project,local"
