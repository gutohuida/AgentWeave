"""The coverage upload must not be able to fail a CI run.

`fail_ci_if_error: false` only covers errors the codecov action handles itself. On 2026-10-12 the
action died on `getaddrinfo ENOTFOUND cli.codecov.io` before reaching that logic, and the run
went red on a commit that changed no code while every test job passed. `continue-on-error` is
what actually makes the step advisory.
"""

from __future__ import annotations

import re
from pathlib import Path

CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def test_codecov_upload_steps_are_advisory() -> None:
    text = CI.read_text(encoding="utf-8")
    steps = re.split(r"(?m)^\s*- name: ", text)
    uploads = [s for s in steps if "codecov/codecov-action" in s]
    assert uploads, "ci.yml no longer uploads coverage; delete this test with it"
    for step in uploads:
        assert re.search(r"(?m)^\s*continue-on-error:\s*true\s*$", step), step
