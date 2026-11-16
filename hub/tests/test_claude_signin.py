"""F1183: an expired Claude sign-in that cannot be renewed is reported as not runnable."""

from __future__ import annotations

import json
import time

import pytest

from hub import claude_signin
from hub.launchability import probe_agent
from hub.runner_parsing import parse_claude_line

DEAD_TEXT = (
    "Failed to authenticate: this login reached its time limit and cannot be renewed. "
    "Run `claude auth login`"
)


@pytest.fixture(autouse=True)
def _claude_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        "hub.runner_adapters.claude.probe_binary", lambda *a: ("claude", True, None)
    )
    claude_signin.forget()
    yield tmp_path
    claude_signin.forget()


def _write(home, **oauth):
    (home / ".credentials.json").write_text(json.dumps({"claudeAiOauth": oauth}))


def _verdict():
    return probe_agent("a", {"runner": "claude"})


def test_expired_access_token_with_refresh_token_is_still_runnable(_claude_home):
    _write(_claude_home, accessToken="x", refreshToken="r", expiresAt=int(time.time() * 1000) - 1)
    v = _verdict()
    assert v["runnable"] and v["authorized"] and v["reason"] is None


def test_expired_with_no_refresh_token_is_not_runnable(_claude_home):
    _write(_claude_home, accessToken="x", expiresAt=int(time.time() * 1000) - 1)
    v = _verdict()
    assert not v["runnable"] and not v["authorized"]
    assert "claude auth login" in v["reason"]


def test_failed_run_marks_unrenewable_until_credentials_change(_claude_home):
    _write(_claude_home, accessToken="x", refreshToken="r", expiresAt=1)
    line = json.dumps(
        {"type": "result", "subtype": "success", "is_error": True, "result": DEAD_TEXT}
    )
    parsed = parse_claude_line(line)
    assert parsed.auth_failure and parsed.login_unrenewable
    assert "claude auth login" in parsed.events[0].content
    claude_signin.mark_unrenewable()
    v = _verdict()
    assert not v["runnable"] and "claude auth login" in v["reason"]
    # `claude auth login` rewrites the file: the verdict follows.
    _write(
        _claude_home,
        accessToken="new",
        refreshToken="r2",
        expiresAt=int(time.time() * 1000) + 10**7,
    )
    assert _verdict()["runnable"]


def test_no_credentials_file_is_left_alone(_claude_home):
    assert _verdict()["runnable"]
