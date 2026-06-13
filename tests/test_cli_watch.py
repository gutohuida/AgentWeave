"""Tests for the cmd_start watchdog invocation (H8)."""

import argparse
import os
import platform
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import agentweave.constants as const


@pytest.mark.skipif(platform.system() == "Windows", reason="POSIX-only /proc-based test")
def test_cmd_start_does_not_leak_fd_on_posix(tmp_path, monkeypatch):
    """H8 regression: cmd_start (the watchdog launcher) must not open
    WATCHDOG_LOG_FILE in the parent process. Each invocation previously
    leaked one fd in the parent shell; on POSIX we can count fds via
    /proc/<pid>/fd.
    """
    from agentweave.cli import cmd_start

    monkeypatch.chdir(tmp_path)
    # The cmd_start function imports WATCHDOG_LOG_FILE and WATCHDOG_PID_FILE
    # from .constants inside the function, so monkeypatching the constants
    # module is sufficient. AGENTWEAVE_DIR is module-level in cli.py so we
    # patch it there.
    monkeypatch.setattr(const, "WATCHDOG_LOG_FILE", tmp_path / "wd.log")
    monkeypatch.setattr(const, "WATCHDOG_PID_FILE", tmp_path / "wd.pid")
    import agentweave.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AGENTWEAVE_DIR", tmp_path)

    # Stub subprocess.Popen to a no-op so we don't spawn a real daemon
    fake_proc = MagicMock(pid=99999)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: fake_proc)
    # Skip the diagnostics and stale-killer paths
    monkeypatch.setattr(cli_mod, "_kill_stale_watchdogs", lambda: [])

    before = set(os.listdir(f"/proc/{os.getpid()}/fd"))

    args = argparse.Namespace(retry_after=60)
    result = cmd_start(args)
    assert result == 0

    after = set(os.listdir(f"/proc/{os.getpid()}/fd"))
    # No new fds should be open in the parent after cmd_start returns
    assert before == after, (
        f"fd leak: opened={after - before}, closed={before - after}"
    )


def test_cmd_start_source_does_not_open_watchdog_log_in_parent():
    """Universal H8 check (works on any platform): the source must not
    call open() on WATCHDOG_LOG_FILE in the parent. The fix is for the
    child to open its own log.
    """
    src = Path("src/agentweave/cli.py").read_text(encoding="utf-8")
    # The buggy line was:
    #   log_fh = open(WATCHDOG_LOG_FILE, "a", encoding="utf-8")
    # The fix removes this. Check that the substring is gone.
    assert "log_fh = open(WATCHDOG_LOG_FILE" not in src, (
        "H8 regression: cmd_start must not open WATCHDOG_LOG_FILE in the parent"
    )


def test_cmd_start_passes_devnull_to_popen(tmp_path, monkeypatch):
    """cmd_start should pass DEVNULL to Popen for stdout/stderr/stdin
    now that the parent no longer hands off an fd. Verify by capturing
    the kwargs.
    """
    from agentweave.cli import cmd_start

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(const, "WATCHDOG_LOG_FILE", tmp_path / "wd.log")
    monkeypatch.setattr(const, "WATCHDOG_PID_FILE", tmp_path / "wd.pid")
    import agentweave.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AGENTWEAVE_DIR", tmp_path)

    captured = {}

    class FakeProc:
        pid = 99999

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli_mod, "_kill_stale_watchdogs", lambda: [])

    args = argparse.Namespace(retry_after=60)
    cmd_start(args)

    kw = captured.get("kwargs", {})
    # The child should not receive a parent-owned log fd
    assert kw.get("stdout") is subprocess.DEVNULL, (
        f"stdout should be DEVNULL, got {kw.get('stdout')!r}"
    )
    assert kw.get("stderr") is subprocess.DEVNULL
    assert kw.get("stdin") is subprocess.DEVNULL
