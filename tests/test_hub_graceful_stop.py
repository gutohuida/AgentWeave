"""F297: `agentweave stop` on Windows asks the Hub to shut down before it forces it.

`taskkill /F` is `TerminateProcess`, so the Hub's lifespan teardown -- which terminates active runs
and stops the scheduler -- never ran on Windows, against `app-lifecycle`'s *Status, stop, and reset
act on the local instance* ("active runs across projects are terminated through normal shutdown").
"""

import os
import subprocess
import sys
import textwrap
import time
import urllib.request
from unittest.mock import patch

import pytest

from agentweave import cli


def test_windows_stop_does_not_force_a_hub_that_shut_down_gracefully():
    with patch.object(cli.sys, "platform", "win32"):
        with patch.object(cli, "_hub_break_windows", return_value=True) as graceful:
            with patch("subprocess.run") as run:
                cli._hub_kill_pid(4242)
    graceful.assert_called_once_with(4242)
    run.assert_not_called()


def test_windows_stop_forces_a_hub_that_did_not_shut_down():
    with patch.object(cli.sys, "platform", "win32"):
        with patch.object(cli, "_hub_break_windows", return_value=False):
            with patch("subprocess.run") as run:
                cli._hub_kill_pid(4242)
    run.assert_called_once()
    assert run.call_args.args[0] == ["taskkill", "/PID", "4242", "/F"]


PROBE = textwrap.dedent("""
    import os
    from pathlib import Path

    MARKER = Path(os.environ["F297_MARKER"])

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    MARKER.write_text("lifespan shutdown ran")
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        elif scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
    """)


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows stop path")
def test_a_hub_detached_as_cmd_start_does_it_runs_its_shutdown_when_stopped(tmp_path):
    """Real processes, launched with `cmd_start`'s exact creation flags."""
    pytest.importorskip("uvicorn")
    (tmp_path / "probe_app.py").write_text(PROBE, encoding="utf-8")
    marker = tmp_path / "marker.txt"
    port = 18097
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "probe_app:app", "--port", str(port)],
        cwd=tmp_path,
        env={**os.environ, "F297_MARKER": str(marker)},
        creationflags=0x08000000 | 0x00000200,  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("the probe Hub never came up")

        # What `cmd_stop` calls, so this also shows the old `taskkill /F` skipping the teardown.
        cli._hub_kill_pid(proc.pid)
        proc.wait(timeout=5)
        assert marker.exists(), "the Hub was stopped without running its lifespan shutdown"
    finally:
        if proc.poll() is None:
            proc.kill()
