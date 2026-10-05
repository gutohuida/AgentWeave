"""F493: the Hub suite, run inside an agent's run, must not reach the Hub that started the run.

A run's environment carries its bound credential (`AW_RUN_TOKEN`) and the Hub's address
(`HUB_URL`), and this repository's instructions tell an agent to run `pytest hub/tests/`. Before
`conftest.py` stripped them, any test that reached a reporting path (`mcp_server._report_decision`
under a test's fake operator answer) posted a decision that never happened to the live Hub,
attributed to the real run: drive task 7.7 of slice 5 found one such `permission_denied` row in the
trial Hub, reason `"the operator was asked"`, the fixture value of `test_hub_own_call.py`.

The acceptance test reproduces the seam end to end: a child pytest runs the probe below under a
run-shaped environment whose `HUB_URL` is a listener in this process, and the listener must hear
nothing. The probe is an ordinary test, so in the normal suite it also checks the strip directly.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from hub import mcp_server
from tests.conftest import RUN_ENVIRONMENT_NAMES

HUB_ROOT = Path(__file__).resolve().parents[1]


def test_reporting_from_inside_the_suite_reaches_no_hub():
    """The probe. Runs in every suite run; the acceptance test below runs it under a fake run."""
    # The real reporting path a test's fake denial goes through. With the run's credential gone it
    # raises before any request is made, and the raise is swallowed by design.
    mcp_server._report_decision(
        "PowerShell", {"allow": False, "reason": "the operator was asked"}, "tu"
    )
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
        # What `trigger_agent` gives a run (hub/hub/api/v1/agent_trigger.py), pointed at the
        # listener instead of a Hub.
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
                f"{Path(__file__).name}::test_reporting_from_inside_the_suite_reaches_no_hub",
            ],
            cwd=HUB_ROOT / "tests",
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


def test_every_variable_the_hub_gives_a_run_is_stripped():
    """Drift guard: a run variable `trigger_agent` starts writing is stripped by the suite too."""
    source = (HUB_ROOT / "hub" / "api" / "v1" / "agent_trigger.py").read_text(encoding="utf-8")
    written = set(re.findall(r'env\["((?:AW|HUB)_[A-Z_]+)"\] =', source))
    assert written, "no run variables found; the pattern no longer matches trigger_agent"
    assert written <= set(RUN_ENVIRONMENT_NAMES), sorted(written - set(RUN_ENVIRONMENT_NAMES))


def test_the_cli_suite_strips_the_same_variables():
    """`tests/conftest.py` (the CLI suite) cannot import this suite's list, so it restates it."""
    tree = ast.parse((HUB_ROOT.parent / "tests" / "conftest.py").read_text(encoding="utf-8"))
    declared = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "RUN_ENVIRONMENT_NAMES" for t in node.targets)
    )
    assert set(declared) == set(RUN_ENVIRONMENT_NAMES)
