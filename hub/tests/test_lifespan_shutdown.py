"""Task 3.9: does the real ASGI lifespan shutdown actually terminate a tracked run's
process, not just the unit-tested pieces in isolation.

`conftest.py`'s `app` fixture uses `httpx.ASGITransport`, which deliberately does not
trigger FastAPI's `lifespan()` (see its own comment) — every other test in this suite
exercises `reconcile_interrupted_runs()`/`terminate_all_active_runs()` directly rather than
through a real app boot/shutdown cycle. This file uses Starlette's `TestClient` instead,
which does run `lifespan()` on `__enter__`/`__exit__`, against a real spawned OS
subprocess — the only test in the suite that goes through the actual startup/shutdown path
`main.py` wires these into.
"""

import contextlib
import sys
import time

from starlette.testclient import TestClient

from hub import run_liveness
from hub.main import create_app
from hub.pty_runner import PtySession, pid_alive


def test_hub_shutdown_kills_a_real_tracked_process():
    # Populates run_liveness.active_ptys directly with a real long-running OS subprocess, bypassing the
    # HTTP trigger endpoint — this test's only concern is whether the ASGI lifespan's
    # shutdown event reaches terminate_all_active_runs() and it actually kills what it
    # finds, not the trigger endpoint's own request handling (covered elsewhere).
    # Far longer than the wait below, so only the shutdown can be what ends it.
    session = PtySession.spawn([sys.executable, "-c", "import time; time.sleep(600)"])
    pid = session.pid
    run_liveness.active_ptys["run-lifespan-test"] = session
    try:
        assert pid_alive(pid) is True

        app = create_app()
        with TestClient(app):
            pass  # lifespan startup runs on __enter__, shutdown runs on __exit__

        # Until it is gone, not for a fixed time: a loaded machine can take seconds to end a process.
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            # `session.isalive()` first, and it is load-bearing on POSIX: a SIGKILLed child
            # stays a **zombie** until its parent reaps it, and `pid_alive()` uses
            # `os.kill(pid, 0)`, which succeeds for a zombie. This process is the parent, so
            # nothing reaps it unless the test does. ptyprocess's `isalive()` calls
            # `waitpid(WNOHANG)` and reaps. The product never occupies this window — its only
            # `pid_alive` caller runs at boot against pids from a *previous* Hub, long since
            # re-parented to init and reaped — so this is the test's problem, not the code's.
            session.isalive()
            if not pid_alive(pid):
                break
            time.sleep(0.1)
        assert pid_alive(pid) is False
    finally:
        run_liveness.active_ptys.pop("run-lifespan-test", None)
        # Only a process still running is ended here. The pty's own `isalive()` can still say yes
        # for a child the shutdown has already killed, and Windows refuses to terminate a process
        # that is exiting with "Access is denied" (AW-44): that one is already going.
        if pid_alive(pid) and session.isalive():
            with contextlib.suppress(PermissionError):
                session.terminate(force=True)
