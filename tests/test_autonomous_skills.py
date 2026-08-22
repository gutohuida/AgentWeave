"""Checks for the repo's cross-agent autonomous development skills."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"
SESSION_ROOT = SKILLS_ROOT / "autonomous-session"
INSTALLER = SESSION_ROOT / "scripts" / "install-driver.ps1"
ITERATION = SESSION_ROOT / "scripts" / "run-iteration.ps1"


def test_driver_scripts_remain_ascii_for_windows_powershell_51():
    for script in (INSTALLER, ITERATION):
        script.read_bytes().decode("ascii")


def test_skills_declare_codex_and_shared_state_contract():
    prep = (SKILLS_ROOT / "autonomous-prep" / "SKILL.md").read_text(encoding="utf-8")
    session = (SESSION_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "`runner` — exactly `claude` or `codex`" in prep
    assert "`permission_mode`" in prep
    assert '"runner": "codex"' in session
    assert '"permission_mode": "unattended-full-access"' in session


def test_installer_passes_custom_task_and_resolved_runner_to_iteration():
    installer = INSTALLER.read_text(encoding="ascii")

    assert "$runner = join-path" not in installer.lower()
    assert '-TaskName `"$TaskName`"' in installer
    assert '-Runner `"$resolvedRunner`"' in installer
    assert '-PermissionMode `"$resolvedPermissionMode`"' in installer
    assert '-AgentExecutable `"$agentExecutable`"' in installer


def test_iteration_has_zero_prompt_codex_modes():
    iteration = ITERATION.read_text(encoding="ascii")

    assert "--dangerously-bypass-approvals-and-sandbox" in iteration
    assert "--ask-for-approval never" in iteration
    assert "--sandbox workspace-write" in iteration
    assert "--ephemeral" in iteration
    assert "$prompt | & $AgentExecutable" in iteration
    assert '$ErrorActionPreference = "Continue"' in iteration
    assert "STATE.json has no next_action" in iteration


@pytest.mark.skipif(os.name != "nt", reason="Windows Scheduled Task driver")
@pytest.mark.parametrize(
    ("runner", "permission_mode", "expected"),
    [
        ("claude", "unattended-full-access", {"-p", "--permission-mode", "bypassPermissions"}),
        (
            "codex",
            "unattended-full-access",
            {"exec", "--ephemeral", "--dangerously-bypass-approvals-and-sandbox"},
        ),
        (
            "codex",
            "workspace-contained",
            {"--ask-for-approval", "never", "exec", "--sandbox", "workspace-write"},
        ),
    ],
)
def test_iteration_dispatches_expected_agent_arguments(
    tmp_path: Path, runner: str, permission_mode: str, expected: set[str]
):
    if not shutil.which("powershell") or not shutil.which("git"):
        pytest.skip("PowerShell and Git are required")

    repo = tmp_path / "repo"
    state_dir = repo / ".claude" / "autonomous"
    state_dir.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "autonomous/test"], check=True)

    state = {
        "branch": "autonomous/test",
        "runner": runner,
        "permission_mode": permission_mode,
        "last_heartbeat": None,
        "next_action": "Do one harmless test action.",
    }
    (state_dir / "STATE.json").write_text(json.dumps(state), encoding="utf-8")

    fake_agent = tmp_path / "fake-agent.ps1"
    fake_agent.write_text(
        "[System.IO.File]::WriteAllLines((Join-Path (Get-Location) 'agent-args.txt'), "
        "[string[]]$args)\nexit 0\n",
        encoding="ascii",
    )
    stop_at = (datetime.now().astimezone() + timedelta(minutes=10)).isoformat()

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ITERATION),
            "-Repo",
            str(repo),
            "-StopAt",
            stop_at,
            "-TaskName",
            "AgentWeaveAutonomousTest",
            "-Runner",
            runner,
            "-PermissionMode",
            permission_mode,
            "-AgentExecutable",
            str(fake_agent),
            "-HeartbeatGraceMinutes",
            "0",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    args = set((repo / "agent-args.txt").read_text(encoding="utf-8-sig").splitlines())
    assert expected <= args


@pytest.mark.skipif(os.name != "nt", reason="Windows Scheduled Task driver")
def test_completed_queue_stops_before_launching_agent(tmp_path: Path):
    if not shutil.which("powershell") or not shutil.which("git"):
        pytest.skip("PowerShell and Git are required")

    repo = tmp_path / "repo"
    state_dir = repo / ".claude" / "autonomous"
    state_dir.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "autonomous/test"], check=True)
    state = {
        "branch": "autonomous/test",
        "runner": "codex",
        "permission_mode": "unattended-full-access",
        "last_heartbeat": None,
        "next_action": None,
    }
    (state_dir / "STATE.json").write_text(json.dumps(state), encoding="utf-8")

    fake_agent = tmp_path / "fake-agent.ps1"
    launched = repo / "agent-launched.txt"
    fake_agent.write_text(
        f"Set-Content -LiteralPath '{launched}' -Value launched\nexit 0\n", encoding="ascii"
    )
    stop_at = (datetime.now().astimezone() + timedelta(minutes=10)).isoformat()
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ITERATION),
            "-Repo",
            str(repo),
            "-StopAt",
            stop_at,
            "-TaskName",
            "AgentWeaveAutonomousMissingTestTask",
            "-Runner",
            "codex",
            "-PermissionMode",
            "unattended-full-access",
            "-AgentExecutable",
            str(fake_agent),
            "-HeartbeatGraceMinutes",
            "0",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not launched.exists()
    assert "queue complete" in (state_dir / "driver.log").read_text(encoding="utf-8")
