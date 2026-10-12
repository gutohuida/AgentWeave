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
import time

import pytest


def _drain(proc: subprocess.Popen, buffer: list) -> None:
    try:
        for line in proc.stderr:
            buffer.append(line)
    except ValueError:
        pass


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
    threading.Thread(target=_drain, args=(proc, lines), daemon=True).start()
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            if any("Application startup complete" in ln for ln in lines):
                break
            if proc.poll() is not None:
                pytest.fail("uvicorn exited before startup:\n" + "".join(lines))
            time.sleep(0.05)
        else:
            pytest.fail("uvicorn did not finish starting within 30s:\n" + "".join(lines))
    finally:
        proc.kill()
        proc.wait(timeout=10)

    pinned = [ln for ln in lines if "Tool server pinned at" in ln]
    assert pinned, "".join(lines)
    assert str(fake_home / ".agentweave" / "hub" / "tool-server") in pinned[0], pinned[0]
