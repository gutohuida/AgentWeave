"""F449: the Hub names the tool-server copy it pinned, on the operator's stderr.

`main.py`'s lifespan logged the pin at INFO, and the root logger is WARN after `init_db()`'s
alembic `fileConfig` (`migrations/env.py:28`), so the line was never printed. pytest's own logging
plugin holds the root at WARNING too, so a unit-level `caplog` check cannot tell the two apart;
this launches a real `uvicorn hub.main:app` and reads what it prints.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading

import pytest

#: Only a hang guard, never the expected wait: a fresh database migrates every revision before the
#: pin is logged, and on a gate machine running two Hub suites at once that ran past the 30s this
#: test once allowed (2026-10-25: gate runs chk-f047489cd56a and chk-7658cc2ac9f7 on the operator's
#: Hub failed here; the second's run on main passed it).
STARTUP_HANG_GUARD_SECONDS = 600
#: The lines that settle the question: the pin is named, or could not be made, or startup ended.
_SETTLING = (
    "Tool server pinned at",
    "Could not pin the tool server",
    "Application startup complete",
)


def _drain(proc: subprocess.Popen, buffer: list, settled: threading.Event) -> None:
    try:
        for line in proc.stderr:
            buffer.append(line)
            if any(marker in line for marker in _SETTLING):
                settled.set()
    except ValueError:
        pass
    finally:
        settled.set()  # stderr closed: the process exited, and waiting longer would prove nothing


def test_a_started_hub_prints_the_path_of_the_tool_server_it_pinned(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    db_file = tmp_path / "x.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_file.as_posix()}",
        # `Path.home()` reads these; the pin lands under the fake home, not the operator's.
        "USERPROFILE": str(fake_home),
        "HOME": str(fake_home),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "hub.main:app", "--host", "127.0.0.1", "--port", "0"],
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lines: list = []
    settled = threading.Event()
    threading.Thread(target=_drain, args=(proc, lines, settled), daemon=True).start()
    try:
        # Wait for the line itself, however long the migrations before it take on this machine.
        if not settled.wait(timeout=STARTUP_HANG_GUARD_SECONDS):
            pytest.fail(
                f"uvicorn printed neither the pin nor startup in {STARTUP_HANG_GUARD_SECONDS}s:\n"
                + "".join(lines)
            )
    finally:
        proc.kill()
        proc.wait(timeout=60)

    pinned = [ln for ln in lines if "Tool server pinned at" in ln]
    assert pinned, "".join(lines)
    assert str(fake_home / ".agentweave" / "hub" / "tool-server") in pinned[0], pinned[0]
