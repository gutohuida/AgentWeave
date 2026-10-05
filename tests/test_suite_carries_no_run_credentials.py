"""F493 for the CLI suite: run inside an agent's run, it must not reach the Hub that started it.

Measured 2026-10-05 before the fix: the whole suite under a run-shaped environment sent four
`POST /api/v1/agent-actions/session/sync` requests to the run's `HUB_URL` and failed ten transport
tests. The acceptance test runs the probe in a child pytest under such an environment, pointed at
a listener in this process, and the listener must hear nothing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from agentweave.transport.config import get_transport
from tests.conftest import RUN_ENVIRONMENT_NAMES

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_a_run_transport_is_not_reached_from_inside_the_suite():
    """The probe. Runs in every suite run; the acceptance test below runs it under a fake run."""
    # The path `Session.save()` takes: with a run credential present, `get_transport` returns the
    # run's HTTP transport (it reads no transport.json), and `push_session` posts to the run's Hub.
    if os.environ.get("AW_RUN_TOKEN", "").strip():
        get_transport().push_session({})
    leaked = sorted(name for name in RUN_ENVIRONMENT_NAMES if name in os.environ)
    assert leaked == [], f"run variables reached a test: {leaked}"


def test_a_suite_run_inside_an_agent_run_writes_nothing_to_its_hub():
    received: list[str] = []

    class Listener(BaseHTTPRequestHandler):
        def _record(self) -> None:
            received.append(f"{self.command} {self.path}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _record  # noqa: N815 - http.server names

        def log_message(self, *args) -> None:  # noqa: ANN002
            pass

    server = HTTPServer(("127.0.0.1", 0), Listener)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = dict(os.environ)
        env.update(
            {
                "AW_RUN_TOKEN": "aw_run_f493probe",
                "AW_RUN_ID": "run-f493probe",
                "AW_AGENT_IDENTITY": "cp5",
                "HUB_URL": f"http://127.0.0.1:{server.server_port}",
            }
        )
        child = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/test_suite_carries_no_run_credentials.py"
                "::test_a_run_transport_is_not_reached_from_inside_the_suite",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert received == [], f"the suite reached the run's Hub: {received}"
    assert child.returncode == 0, child.stdout[-3000:] + child.stderr[-3000:]
