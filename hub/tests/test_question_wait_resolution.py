"""The Hub's own resolution of how long a run waits for an answer, and the tool's agreement.

`a-task-waits-while-its-run-waits`, design D3. The Hub stamps `Question.wait_expires_at` while
serving the ask, and `POST /questions/wait-ended` refuses a report that arrives before it. That
refusal is only worth anything if the deadline describes the wait the tool actually performs — so
this module asserts the two agree, in the same idiom `mcp_server.py` already uses for
`MIN_WAITING_SECONDS`/`MAX_WAITING_SECONDS`: the constant is restated because the module may import
only stdlib and fastmcp, and a test is what makes the restatement safe.

The ask carries no `wait_seconds`, deliberately. It would arrive over the run's own credential, so
the guard's threshold would come from the guarded party.
"""

from __future__ import annotations

import pytest

from hub import mcp_server
from hub.api.v1.agent_trigger import (
    QUESTION_WAIT_DEFAULT,
    QUESTION_WAIT_ENV,
    QUESTION_WAIT_MAX,
    QUESTION_WAIT_MIN,
    effective_question_wait,
)
from hub.db.models import Agent


def _agent(**columns) -> Agent:
    return Agent(id="ag-w", project_id="proj-test", name="worker", **columns)


def test_the_restated_bounds_and_default_agree_with_the_tool():
    """4.3. The whole reason the restatement is allowed."""
    assert QUESTION_WAIT_MIN == mcp_server.MIN_WAITING_SECONDS
    assert QUESTION_WAIT_MAX == mcp_server.MAX_WAITING_SECONDS
    assert QUESTION_WAIT_ENV == "AW_QUESTION_TIMEOUT"
    # The tool's default, read from the module that owns it rather than restated a third time here.
    assert mcp_server._configured_wait("AW_NO_SUCH_VAR", 240) == QUESTION_WAIT_DEFAULT


def test_the_agents_own_column_wins(monkeypatch):
    """4.3b. `agent_trigger` writes it into the child environment *last*, overwriting anything the
    Hub's own environment or the agent's `env_vars` put there — so it wins here too."""
    monkeypatch.setenv(QUESTION_WAIT_ENV, "300")
    agent = _agent(question_timeout_seconds=90, config={"env_vars": {QUESTION_WAIT_ENV: "500"}})
    assert effective_question_wait(agent) == 90


def test_the_agents_env_vars_win_over_the_hubs_own_environment(monkeypatch):
    """`resolve_agent_env` merges the agent's `env_vars` *over* `os.environ`, so an agent that sets
    the variable directly is what the tool will read. Resolved in the order the spawn writes it,
    which is the only way the two can be made to agree rather than merely look alike."""
    monkeypatch.setenv(QUESTION_WAIT_ENV, "300")
    agent = _agent(config={"env_vars": {QUESTION_WAIT_ENV: "120"}})
    assert effective_question_wait(agent) == 120


def test_the_hubs_own_environment_is_used_when_nothing_else_is_set(monkeypatch):
    monkeypatch.setenv(QUESTION_WAIT_ENV, "300")
    assert effective_question_wait(_agent()) == 300


def test_nothing_configured_is_the_default(monkeypatch):
    monkeypatch.delenv(QUESTION_WAIT_ENV, raising=False)
    assert effective_question_wait(_agent()) == 240
    # And an agent row that could not be resolved at all is the same answer, not a crash: the ask
    # must not fail because the roster row is missing.
    assert effective_question_wait(None) == 240


@pytest.mark.parametrize("raw", ["", "abc", "0", "9", "601", "-30", "12.5"])
def test_an_unusable_value_falls_back_exactly_as_the_tool_does(monkeypatch, raw):
    """4.3b. Out of range and unparseable both fall back to 240, which is what
    `_configured_wait` does — so the recorded deadline describes the wait the tool performs, not
    the one the setting intended."""
    monkeypatch.setenv(QUESTION_WAIT_ENV, raw)
    assert effective_question_wait(_agent()) == 240
    assert mcp_server._configured_wait(QUESTION_WAIT_ENV, 240) == 240


@pytest.mark.parametrize("raw", ["10", "240", "600"])
def test_a_usable_value_is_taken_by_both(monkeypatch, raw):
    monkeypatch.setenv(QUESTION_WAIT_ENV, raw)
    assert effective_question_wait(_agent()) == int(raw)
    assert mcp_server._configured_wait(QUESTION_WAIT_ENV, 240) == int(raw)
