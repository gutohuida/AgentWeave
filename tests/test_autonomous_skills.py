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


POLICY = REPO_ROOT / ".claude" / "loops" / "usage-policy.json"


def _run_routed_iteration(
    tmp_path: Path,
    state: dict,
    *,
    stdout_json: dict | None = None,
    with_policy: bool = True,
) -> tuple[subprocess.CompletedProcess, Path, Path]:
    """Run run-iteration.ps1 once against a fake Claude that records its args and env.

    Returns (process, repo, fake-agent work dir). The fake prints `stdout_json` as the
    `--output-format json` result line when given.
    """
    if not shutil.which("powershell") or not shutil.which("git"):
        pytest.skip("PowerShell and Git are required")

    repo = tmp_path / "repo"
    state_dir = repo / ".claude" / "autonomous"
    if not state_dir.exists():
        state_dir.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "-q", "-b", "autonomous/test"], check=True
        )
    if with_policy:
        (repo / ".claude" / "loops").mkdir(parents=True, exist_ok=True)
        shutil.copy(POLICY, repo / ".claude" / "loops" / "usage-policy.json")
    state = {
        "branch": "autonomous/test",
        "runner": "claude",
        "permission_mode": "unattended-full-access",
        "next_action": "Do one harmless test action.",
        **state,
    }
    (state_dir / "STATE-night.json").write_text(json.dumps(state), encoding="utf-8")

    work = tmp_path / "fake"
    work.mkdir(exist_ok=True)
    result_file = work / "result.json"
    if stdout_json is not None:
        result_file.write_text(json.dumps(stdout_json), encoding="utf-8")
    fake_agent = tmp_path / "fake-claude.ps1"
    fake_agent.write_text(
        f"[System.IO.File]::WriteAllLines('{work / 'args.txt'}', [string[]]$args)\n"
        f"Set-Content -LiteralPath '{work / 'env.txt'}' -Value "
        '("AW_AUTONOMOUS=$env:AW_AUTONOMOUS", '
        '"DISABLE_AUTOUPDATER=$env:DISABLE_AUTOUPDATER", '
        '"BG=$env:CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS")\n'
        f"if (Test-Path '{result_file}') {{ Get-Content -Raw '{result_file}' }}\n"
        "exit 0\n",
        encoding="ascii",
    )
    stop_at = (datetime.now().astimezone() + timedelta(minutes=10)).isoformat()
    proc = subprocess.run(
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
            "AgentWeaveAutonomousRoutingTest",
            "-Runner",
            "claude",
            "-PermissionMode",
            "unattended-full-access",
            "-AgentExecutable",
            str(fake_agent),
            "-HeartbeatGraceMinutes",
            "0",
            "-StateFile",
            ".claude\\autonomous\\STATE-night.json",
            "-LogFile",
            ".claude\\autonomous\\driver-night.log",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc, repo, work


def _flag_value(args: list[str], flag: str) -> str | None:
    return args[args.index(flag) + 1] if flag in args else None


@pytest.mark.skipif(os.name != "nt", reason="Windows Scheduled Task driver")
@pytest.mark.parametrize(
    ("item", "expected_model", "expected_effort"),
    [
        ({"id": "a-change-r2"}, "opus", "high"),
        ({"id": "a-change-rev"}, "opus", "high"),
        ({"id": "a-change-impl"}, "sonnet", "high"),
        ({"id": "a-change-drive"}, "sonnet", "medium"),
        ({"id": "ledger-conflicts"}, "sonnet", "medium"),
        ({"id": "compose"}, "sonnet", "medium"),
        ({"id": "c3-guard"}, "opus", "high"),
        ({"id": "a-change-impl", "model": "opus"}, "opus", "high"),
        ({"id": "a-change-r1", "effort": "xhigh"}, "opus", "xhigh"),
    ],
)
def test_iteration_routes_the_current_item_through_the_usage_policy(
    tmp_path: Path, item: dict, expected_model: str, expected_effort: str
):
    proc, _, work = _run_routed_iteration(
        tmp_path, {"model": "opus", "current": item["id"], "queue": [item]}
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    args = (work / "args.txt").read_text(encoding="utf-8-sig").splitlines()
    assert _flag_value(args, "--model") == expected_model
    assert _flag_value(args, "--effort") == expected_effort
    assert _flag_value(args, "--output-format") == "json"
    assert _flag_value(args, "--max-budget-usd") == "40"
    assert "--strict-mcp-config" in args
    env = (work / "env.txt").read_text(encoding="utf-8-sig")
    assert "AW_AUTONOMOUS=1" in env
    assert "DISABLE_AUTOUPDATER=1" in env
    assert "BG=3600000" in env


@pytest.mark.skipif(os.name != "nt", reason="Windows Scheduled Task driver")
def test_iteration_without_a_policy_keeps_the_state_model_and_no_effort(tmp_path: Path):
    proc, _, work = _run_routed_iteration(
        tmp_path,
        {"model": "opus", "current": "a-change-impl", "queue": [{"id": "a-change-impl"}]},
        with_policy=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    args = (work / "args.txt").read_text(encoding="utf-8-sig").splitlines()
    assert _flag_value(args, "--model") == "opus"
    assert "--effort" not in args
    assert "--max-budget-usd" not in args


RESULT_OK = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "num_turns": 57,
    "duration_ms": 612000,
    "total_cost_usd": 4.5,
    "result": "Did the thing.\nSecond line.",
    "subagent_stats": {"spawned": 1},
    "modelUsage": {
        "claude-sonnet-5": {
            "inputTokens": 10,
            "outputTokens": 2000,
            "cacheReadInputTokens": 900000,
            "cacheCreationInputTokens": 40000,
            "costUSD": 4.25,
        },
        "claude-haiku-4-5-20251001": {
            "inputTokens": 900,
            "outputTokens": 12,
            "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0,
            "costUSD": 0.25,
        },
    },
}


@pytest.mark.skipif(os.name != "nt", reason="Windows Scheduled Task driver")
def test_iteration_meters_itself_into_the_ledger_and_logs_the_result_text(tmp_path: Path):
    proc, repo, _ = _run_routed_iteration(
        tmp_path,
        {"current": "a-change-impl", "iteration": 7, "queue": [{"id": "a-change-impl"}]},
        stdout_json=RESULT_OK,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    state_dir = repo / ".claude" / "autonomous"
    rows = (state_dir / "usage-ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    row = json.loads(rows[0])
    assert row["window"] == "night"
    assert row["item"] == "a-change-impl"
    assert (row["model"], row["model_from"]) == ("sonnet", "rule")
    assert (row["effort"], row["effort_from"]) == ("high", "rule")
    assert row["parsed"] is True
    assert row["total_cost_usd"] == 4.5
    assert row["num_turns"] == 57
    assert row["iteration"] == 7
    assert row["subagents"] == 1
    assert row["model_usage"]["claude-sonnet-5"]["cache_read"] == 900000
    log = (state_dir / "driver-night.log").read_text(encoding="utf-8")
    assert "Did the thing." in log and "Second line." in log
    assert "$4.50 list" in log
    assert "item=a-change-impl" in log


@pytest.mark.skipif(os.name != "nt", reason="Windows Scheduled Task driver")
def test_a_usage_limit_pauses_the_window_instead_of_firing_into_it(tmp_path: Path):
    limited = {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "num_turns": 1,
        "total_cost_usd": 0,
        "result": "You've hit your weekly limit - resets Mon 9am",
    }
    proc, repo, work = _run_routed_iteration(
        tmp_path,
        {"current": "a-change-impl", "queue": [{"id": "a-change-impl"}]},
        stdout_json=limited,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    state_dir = repo / ".claude" / "autonomous"
    assert (state_dir / ".limit-hit-night").exists()
    assert "USAGE LIMIT HIT" in (state_dir / "driver-night.log").read_text(encoding="utf-8")

    (work / "args.txt").unlink()
    proc, _, work = _run_routed_iteration(
        tmp_path,
        {"current": "a-change-impl", "queue": [{"id": "a-change-impl"}]},
        stdout_json=RESULT_OK,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (work / "args.txt").exists(), "a firing inside the cool-down launched the agent"
    assert "cool-down" in (state_dir / "driver-night.log").read_text(encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="Windows Scheduled Task driver")
def test_a_model_that_writes_about_limits_does_not_trip_the_cool_down(tmp_path: Path):
    chatty = {**RESULT_OK, "result": "Noted that the :8000 Hub said you've hit your session limit."}
    proc, repo, _ = _run_routed_iteration(
        tmp_path,
        {"current": "a-change-impl", "queue": [{"id": "a-change-impl"}]},
        stdout_json=chatty,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (repo / ".claude" / "autonomous" / ".limit-hit-night").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows Scheduled Task driver")
def test_an_unparseable_policy_refuses_to_launch(tmp_path: Path):
    proc, repo, work = _run_routed_iteration(
        tmp_path, {"current": "a-change-impl", "queue": [{"id": "a-change-impl"}]}
    )
    (repo / ".claude" / "loops" / "usage-policy.json").write_text("{not json", encoding="utf-8")
    (work / "args.txt").unlink()
    proc = subprocess.run(
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
            (datetime.now().astimezone() + timedelta(minutes=10)).isoformat(),
            "-TaskName",
            "AgentWeaveAutonomousRoutingTest",
            "-Runner",
            "claude",
            "-PermissionMode",
            "unattended-full-access",
            "-AgentExecutable",
            str(tmp_path / "fake-claude.ps1"),
            "-HeartbeatGraceMinutes",
            "0",
            "-StateFile",
            ".claude\\autonomous\\STATE-night.json",
            "-LogFile",
            ".claude\\autonomous\\driver-night.log",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 2
    assert not (work / "args.txt").exists()
