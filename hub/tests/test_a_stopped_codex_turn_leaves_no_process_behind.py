"""F1162 -- stopping a Codex app-server turn ends every process the turn started.

Driven 2026-11-11: a Codex turn running `py -3.11 -c "...sleep..."` was stopped. The run row read
`stopped`, and 12 s later `py.exe` and its `python.exe` child were still alive, their PowerShell
parent gone. A stop sends `turn/interrupt` and then kills the app-server (`close(force=True)`), and
the kill reached only the app-server itself. Walking the tree (`taskkill /T`) is not enough here:
the orphan's parent had already exited, so no walk from the app-server finds it.

The fake app-server below starts a shell-like middle process, which starts a long sleeper and then
exits -- the shape the live turn left. A forced close must end the sleeper; an ordinary close (a
turn that finished) leaves alone what the agent started on purpose, as it always has.
"""

import asyncio
import sys
import time

import pytest

from hub.codex_appserver import AppServerProcess
from hub.pty_runner import pid_alive

SLEEPER = "import time\nfor _ in range(600): time.sleep(0.1)\n"


def _fake_app_server(tmp_path):
    """An 'app-server' that leaves an orphaned grandchild and writes its pid to a file."""
    pid_file = tmp_path / "sleeper.pid"
    (tmp_path / "sleeper.py").write_text(SLEEPER, encoding="utf-8")
    (tmp_path / "middle.py").write_text(
        "import subprocess, sys\n"
        f"child = subprocess.Popen([sys.executable, {str(tmp_path / 'sleeper.py')!r}])\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n",
        encoding="utf-8",
    )
    (tmp_path / "server.py").write_text(
        "import subprocess, sys, time\n"
        f"subprocess.run([sys.executable, {str(tmp_path / 'middle.py')!r}])\n"
        "for _ in range(600): time.sleep(0.1)\n",
        encoding="utf-8",
    )
    return [sys.executable, str(tmp_path / "server.py")], pid_file


async def _spawn_and_wait_for_sleeper(tmp_path):
    cmd, pid_file = _fake_app_server(tmp_path)
    session = await AppServerProcess.spawn(cmd, cwd=str(tmp_path))
    deadline = time.monotonic() + 30
    while not (pid_file.exists() and pid_file.read_text().strip()):
        assert time.monotonic() < deadline, "the fake app-server never started its sleeper"
        await asyncio.sleep(0.05)
    sleeper = int(pid_file.read_text())
    assert pid_alive(sleeper)
    return session, sleeper


async def _gone(pid, seconds=10.0):
    deadline = time.monotonic() + seconds
    while pid_alive(pid):
        if time.monotonic() > deadline:
            return False
        await asyncio.sleep(0.1)
    return True


@pytest.mark.timeout(120)
async def test_a_forced_close_ends_an_orphaned_grandchild(tmp_path):
    session, sleeper = await _spawn_and_wait_for_sleeper(tmp_path)
    try:
        await session.close(force=True)
        assert await _gone(sleeper), "the turn's orphaned command outlived the stop"
    finally:
        if pid_alive(sleeper):
            from hub.pty_runner import terminate_process_tree

            terminate_process_tree(sleeper)


@pytest.mark.timeout(120)
async def test_an_ordinary_close_leaves_what_the_agent_started(tmp_path):
    """The control: a turn that finished is not a stop. A server an agent started in the
    background survives its turn, as it does today on every transport."""
    session, sleeper = await _spawn_and_wait_for_sleeper(tmp_path)
    try:
        await session.close()
        await asyncio.sleep(1.0)
        assert pid_alive(sleeper)
    finally:
        from hub.pty_runner import terminate_process_tree

        terminate_process_tree(sleeper)


def _tree_script(tmp_path):
    """A root that stays up, a child that stays up, and the child's long grandchild."""
    pids = tmp_path / "pids.txt"
    (tmp_path / "leaf.py").write_text(SLEEPER, encoding="utf-8")
    (tmp_path / "branch.py").write_text(
        "import subprocess, sys, time\n"
        f"leaf = subprocess.Popen([sys.executable, {str(tmp_path / 'leaf.py')!r}])\n"
        f"open({str(pids)!r}, 'w').write(f'{{__import__(\"os\").getpid()}} {{leaf.pid}}')\n"
        "for _ in range(600): time.sleep(0.1)\n",
        encoding="utf-8",
    )
    (tmp_path / "root.py").write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(tmp_path / 'branch.py')!r}])\n"
        "for _ in range(600): time.sleep(0.1)\n",
        encoding="utf-8",
    )
    return [sys.executable, str(tmp_path / "root.py")], pids


@pytest.mark.skipif(sys.platform != "win32", reason="POSIX ends the process group at close")
@pytest.mark.timeout(120)
async def test_ending_the_commands_leaves_the_app_server_to_answer(tmp_path):
    """Measured live: `py.exe` left the job at creation, so the stop must end the app-server's
    descendants before `turn/interrupt` lets Codex end the shell and orphan them."""
    cmd, pids = _tree_script(tmp_path)
    session = await AppServerProcess.spawn(cmd, cwd=str(tmp_path))
    deadline = time.monotonic() + 30
    while not (pids.exists() and len(pids.read_text().split()) == 2):
        assert time.monotonic() < deadline, "the tree never started"
        await asyncio.sleep(0.05)
    branch, leaf = (int(p) for p in pids.read_text().split())
    try:
        await session.end_commands()

        assert await _gone(branch) and await _gone(leaf)
        assert session.is_running()
    finally:
        await session.close(force=True)
        for pid in (branch, leaf):
            if pid_alive(pid):
                from hub.pty_runner import terminate_process_tree

                terminate_process_tree(pid)
