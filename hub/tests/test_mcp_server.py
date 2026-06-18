"""Tests for hub.mcp_server — the 20+ MCP tools + the _hub_request helper.

Per PR 12, every MCP tool gets at least one test that pins:
  - The (method, path, body, params) it sends to the Hub REST API
  - How it transforms a successful response
  - How it handles a Hub RuntimeError (HTTP error)

The earlier 3 tests in this file (M23 urlopen timeout, M17 update_task
without agent param) are preserved at the bottom for regression.

Approach: monkeypatch urllib.request.urlopen with a scripted function
that records every call and returns a configurable sequence of
responses. The Hub env vars (HUB_URL/HUB_API_KEY/HUB_PROJECT_ID) are
set in the test; the MCP tool reads them on each call.
"""

import json
import urllib.error
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_response(body=b'{"ok": true}'):
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class _HubScript:
    """Programmable stub for urllib.request.urlopen.

    Use set_response(...) to script the next call's return body.
    Use set_error(...) to script an HTTPError or URLError on the next call.
    Every call appends (method, path, body, headers) to .calls for assertion.
    """

    def __init__(self):
        self.calls: list = []
        self._responses: list = []
        self._errors: list = []
        self._response_iter = None
        self._error_iter = None

    def set_response(self, body):
        """Queue a body for the next call."""
        self._responses.append(body)
        self._response_iter = iter(self._responses)
        self._error_iter = iter(self._errors)

    def set_responses(self, *bodies):
        """Queue multiple bodies in order (one per call)."""
        self._responses.extend(bodies)
        self._response_iter = iter(self._responses)
        self._error_iter = iter(self._errors)

    def set_error(self, exc):
        """Queue an exception for the next call."""
        self._errors.append(exc)
        self._error_iter = iter(self._errors)
        self._response_iter = iter(self._responses)

    def __call__(self, req, timeout=None, data=None):
        # Capture headers AFTER _hub_request has added them (it calls
        # add_header() on the request between construction and urlopen).
        headers = dict(req.header_items())
        self.calls.append(
            {
                "method": req.method,
                "url": req.full_url,
                "body": req.data,
                "headers": headers,
            }
        )
        # Errors take precedence.
        try:
            err = next(self._error_iter)
            raise err
        except StopIteration:
            pass
        try:
            body = next(self._response_iter)
        except StopIteration:
            body = b"{}"
        return _ok_response(body)


@pytest.fixture
def hub(monkeypatch):
    """Wire up a fresh _HubScript and the Hub env vars; return the script.

    Each test that uses this fixture gets a clean script and clean env.
    """
    monkeypatch.setenv("HUB_URL", "http://localhost:8000")
    monkeypatch.setenv("HUB_API_KEY", "test-key")
    monkeypatch.setenv("HUB_PROJECT_ID", "proj-test")
    script = _HubScript()
    monkeypatch.setattr("urllib.request.urlopen", script)
    return script


def _parse_body(call):
    """Parse the JSON body of a recorded call (or {} if no body)."""
    if call["body"] is None:
        return {}
    return json.loads(call["body"].decode("utf-8"))


# ---------------------------------------------------------------------------
# _hub_request helper (the spine of every tool)
# ---------------------------------------------------------------------------


def test_hub_request_adds_bearer_and_content_type(hub):
    """Every request must carry Authorization: Bearer <key> and Content-Type."""
    from hub.mcp_server import _hub_request

    hub.set_response(b'{"ok": true}')
    _hub_request("GET", "/agents")
    headers = hub.calls[0]["headers"]
    assert headers.get("Authorization") == "Bearer test-key"
    assert headers.get("Content-type") == "application/json"


def test_hub_request_injects_project_id_into_body(hub):
    """If a body is provided and lacks 'project_id', inject it from env."""
    from hub.mcp_server import _hub_request

    hub.set_response(b'{"id": "x"}')
    _hub_request("POST", "/messages", body={"from": "a", "to": "b", "subject": "s", "content": "c"})
    body = _parse_body(hub.calls[0])
    assert body.get("project_id") == "proj-test"


def test_hub_request_preserves_existing_project_id(hub):
    """If the body already has 'project_id', don't overwrite it."""
    from hub.mcp_server import _hub_request

    hub.set_response(b'{"ok": true}')
    _hub_request("POST", "/messages", body={"from": "a", "to": "b", "project_id": "custom"})
    body = _parse_body(hub.calls[0])
    assert body.get("project_id") == "custom"


def test_hub_request_raises_runtimeerror_on_http_error(hub):
    """An HTTPError from urlopen must be re-raised as RuntimeError."""
    from hub.mcp_server import _hub_request

    err = urllib.error.HTTPError(
        url="http://test/api/v1/x",
        code=500,
        msg="Server Error",
        hdrs={},
        fp=MagicMock(read=MagicMock(return_value=b"boom")),
    )
    hub.set_error(err)
    with pytest.raises(RuntimeError, match="Hub API error"):
        _hub_request("GET", "/agents")


def test_hub_request_appends_query_params(hub):
    """params={...} must be urlencoded onto the request URL."""
    from hub.mcp_server import _hub_request

    hub.set_response(b'[]')
    _hub_request("GET", "/messages", params={"agent": "alice", "limit": 10})
    url = hub.calls[0]["url"]
    assert "agent=alice" in url
    assert "limit=10" in url


# ---------------------------------------------------------------------------
# Messaging tools
# ---------------------------------------------------------------------------


def test_send_message_posts_to_messages(hub):
    """send_message must POST /messages with from/to/subject/content/type/task_id."""
    from hub.mcp_server import send_message

    hub.set_response(b'{"id": "msg-1"}')
    result = send_message("claude", "kimi", "Hi", "Hello", "message", None)
    assert result == {"success": True, "message_id": "msg-1"}
    call = hub.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/api/v1/messages")
    body = _parse_body(call)
    assert body["from"] == "claude"
    assert body["to"] == "kimi"
    assert body["subject"] == "Hi"
    assert body["content"] == "Hello"
    assert body["type"] == "message"


def test_send_message_returns_error_dict_on_hub_failure(hub):
    """A Hub RuntimeError surfaces as {success: False, error: ...}."""
    from hub.mcp_server import send_message

    err = urllib.error.HTTPError(
        url="x", code=500, msg="err", hdrs={}, fp=MagicMock(read=lambda: b"boom")
    )
    hub.set_error(err)
    result = send_message("a", "b", "s", "c")
    assert result["success"] is False
    assert "error" in result


def test_get_inbox_calls_get_then_patches_each_message(hub):
    """get_inbox must GET /messages, then PATCH /messages/{id}/read for each."""
    from hub.mcp_server import get_inbox

    hub.set_responses(
        b'[{"id": "m-1"}, {"id": "m-2"}, {"id": "m-3"}]',
        b"{}",
        b"{}",
        b"{}",
    )
    msgs = get_inbox("kimi")
    assert len(msgs) == 3
    # First call: GET /messages?agent=kimi
    assert hub.calls[0]["method"] == "GET"
    assert "agent=kimi" in hub.calls[0]["url"]
    # Next three calls: PATCH /messages/{id}/read
    for i, expected_id in enumerate(["m-1", "m-2", "m-3"]):
        assert hub.calls[i + 1]["method"] == "PATCH"
        assert f"/messages/{expected_id}/read" in hub.calls[i + 1]["url"]


def test_get_inbox_returns_empty_list_on_hub_failure(hub):
    """A Hub failure on the GET returns [ ] (no PATCH calls attempted)."""
    from hub.mcp_server import get_inbox

    err = urllib.error.HTTPError(
        url="x", code=500, msg="err", hdrs={}, fp=MagicMock(read=lambda: b"boom")
    )
    hub.set_error(err)
    assert get_inbox("kimi") == []


def test_mark_read_patches_message_id(hub):
    """mark_read must PATCH /messages/{id}/read."""
    from hub.mcp_server import mark_read

    hub.set_response(b"{}")
    result = mark_read("msg-1")
    assert result == {"success": True}
    assert hub.calls[0]["method"] == "PATCH"
    assert "/messages/msg-1/read" in hub.calls[0]["url"]


def test_mark_read_returns_error_dict_on_failure(hub):
    """A Hub failure on mark_read returns {success: False, error: ...}."""
    from hub.mcp_server import mark_read

    err = urllib.error.HTTPError(
        url="x", code=404, msg="nf", hdrs={}, fp=MagicMock(read=lambda: b"nf")
    )
    hub.set_error(err)
    result = mark_read("msg-1")
    assert result["success"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# Task tools
# ---------------------------------------------------------------------------


def test_create_task_posts_with_all_fields(hub):
    """create_task must POST /tasks with every provided field."""
    from hub.mcp_server import create_task

    hub.set_response(b'{"id": "task-1"}')
    result = create_task(
        title="Build feature",
        description="Full desc",
        assignee="kimi",
        assigner="claude",
        priority="high",
        requirements=["req1"],
        acceptance_criteria=["ac1"],
    )
    assert result["id"] == "task-1"
    body = _parse_body(hub.calls[0])
    assert body["title"] == "Build feature"
    assert body["description"] == "Full desc"
    assert body["assignee"] == "kimi"
    assert body["assigner"] == "claude"
    assert body["priority"] == "high"
    assert body["requirements"] == ["req1"]
    assert body["acceptance_criteria"] == ["ac1"]


def test_create_task_returns_error_dict_on_failure(hub):
    """A Hub failure on create_task returns {error: ...}."""
    from hub.mcp_server import create_task

    err = urllib.error.HTTPError(
        url="x", code=422, msg="bad", hdrs={}, fp=MagicMock(read=lambda: b"bad")
    )
    hub.set_error(err)
    result = create_task("title", "desc")
    assert "error" in result


def test_list_tasks_calls_with_agent_param(hub):
    """list_tasks must GET /tasks?agent=<name> when agent is provided."""
    from hub.mcp_server import list_tasks

    hub.set_response(b'[{"id": "task-1"}]')
    tasks = list_tasks("kimi")
    assert len(tasks) == 1
    assert "agent=kimi" in hub.calls[0]["url"]


def test_list_tasks_no_agent_no_filter(hub):
    """list_tasks with no agent must call GET /tasks (no agent filter)."""
    from hub.mcp_server import list_tasks

    hub.set_response(b"[]")
    list_tasks()
    url = hub.calls[0]["url"]
    assert "/api/v1/tasks" in url
    # No agent= param when not provided.
    assert "agent=" not in url


def test_list_tasks_returns_empty_list_on_failure(hub):
    """A Hub failure on list_tasks returns [ ]."""
    from hub.mcp_server import list_tasks

    err = urllib.error.HTTPError(
        url="x", code=500, msg="err", hdrs={}, fp=MagicMock(read=lambda: b"err")
    )
    hub.set_error(err)
    assert list_tasks("kimi") == []


def test_get_task_gets_by_id(hub):
    """get_task must GET /tasks/{id} and return the task dict."""
    from hub.mcp_server import get_task

    hub.set_response(b'{"id": "task-1", "status": "in_progress"}')
    result = get_task("task-1")
    assert result["status"] == "in_progress"
    assert hub.calls[0]["method"] == "GET"
    assert "/tasks/task-1" in hub.calls[0]["url"]


def test_get_task_returns_error_dict_on_failure(hub):
    """A 404 on get_task returns {error: ...}."""
    from hub.mcp_server import get_task

    err = urllib.error.HTTPError(
        url="x", code=404, msg="nf", hdrs={}, fp=MagicMock(read=lambda: b"nf")
    )
    hub.set_error(err)
    result = get_task("task-1")
    assert "error" in result


def test_get_status_returns_status_dict(hub):
    """get_status must GET /status and return the response body."""
    from hub.mcp_server import get_status

    hub.set_response(b'{"message_counts": {"total": 5}, "task_counts": {}}')
    result = get_status()
    assert result["message_counts"]["total"] == 5


def test_list_agents_maps_response(hub):
    """list_agents must map Hub's 'role' -> MCP 'session_role' and flag principal."""
    from hub.mcp_server import list_agents

    hub.set_response(
        b'[{"name": "alice", "role": "principal", "runner": "native", "dev_roles": ["backend_dev"]},'
        b' {"name": "bob", "role": "delegate", "runner": "claude_proxy", "dev_roles": []}]'
    )
    result = list_agents()
    assert "agents" in result
    assert len(result["agents"]) == 2
    alice = result["agents"][0]
    assert alice["name"] == "alice"
    assert alice["session_role"] == "principal"
    assert alice["runner"] == "native"
    assert alice["dev_roles"] == ["backend_dev"]
    assert alice["is_principal"] is True
    bob = result["agents"][1]
    assert bob["is_principal"] is False
    assert bob["session_role"] == "delegate"


# ---------------------------------------------------------------------------
# Agent configuration tools
# ---------------------------------------------------------------------------


def test_get_agent_config_for_native_agent(hub):
    """get_agent_config for a native agent returns {name, runner: native}."""
    from hub.mcp_server import get_agent_config

    hub.set_response(b'[{"name": "alice", "runner": "native", "role": "principal"}]')
    result = get_agent_config("alice")
    assert result["name"] == "alice"
    assert result["runner"] == "native"


def test_get_agent_config_for_claude_proxy_agent(hub):
    """get_agent_config for a claude_proxy agent includes base_url and api_key_var
    (but never the actual key)."""
    from hub.mcp_server import get_agent_config

    # Two scripted calls:
    #   1) GET /agents              -> list with the minimax agent
    #   2) GET /session/sync        -> dict with the agent's env_vars
    agents_body = b'[{"name": "minimax", "runner": "claude_proxy", "role": "principal"}]'
    session_body = (
        b'{"data": {"agents": {"minimax": {"env_vars": {'
        b'"ANTHROPIC_BASE_URL": "https://api.minimaxi.com",'
        b'"ANTHROPIC_API_KEY_VAR": "MINIMAX_API_KEY"'
        b'}}}}}'
    )
    hub.set_responses(agents_body, session_body)
    result = get_agent_config("minimax")
    assert result["runner"] == "claude_proxy"
    assert result["base_url"] == "https://api.minimaxi.com"
    assert result["api_key_var"] == "MINIMAX_API_KEY"
    # The actual key value must NEVER be returned.
    assert "api_key" not in result
    assert "ANTHROPIC_API_KEY" not in result


def test_get_agent_config_for_unknown_agent(hub):
    """An unknown agent name returns {error: ...}."""
    from hub.mcp_server import get_agent_config

    hub.set_response(b'[{"name": "alice", "runner": "native"}]')
    result = get_agent_config("ghost")
    assert "error" in result
    assert "ghost" in result["error"]


def test_register_session_posts_session_id(hub):
    """register_session must POST /agents/{agent}/register-session."""
    from hub.mcp_server import register_session

    hub.set_response(b'{"success": true, "launch_command": "claude --resume sess-1"}')
    result = register_session("claude", "sess-1")
    assert result["success"] is True
    body = _parse_body(hub.calls[0])
    assert body["session_id"] == "sess-1"
    assert hub.calls[0]["url"].endswith("/api/v1/agents/claude/register-session")


def test_register_session_returns_error_dict_on_failure(hub):
    """A Hub failure on register_session returns {success: False, error: ...}."""
    from hub.mcp_server import register_session

    err = urllib.error.HTTPError(
        url="x", code=409, msg="conflict", hdrs={}, fp=MagicMock(read=lambda: b"conflict")
    )
    hub.set_error(err)
    result = register_session("claude", "sess-1")
    assert result["success"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# Human-interaction tools
# ---------------------------------------------------------------------------


def test_ask_user_posts_question(hub):
    """ask_user must POST /questions with from_agent, question, blocking."""
    from hub.mcp_server import ask_user

    hub.set_response(b'{"id": "q-1"}')
    result = ask_user("claude", "Ready?", blocking=True)
    assert result == {"success": True, "question_id": "q-1"}
    body = _parse_body(hub.calls[0])
    assert body["from_agent"] == "claude"
    assert body["question"] == "Ready?"
    assert body["blocking"] is True


def test_ask_user_returns_error_dict_on_failure(hub):
    """A Hub failure on ask_user returns {success: False, error: ...}."""
    from hub.mcp_server import ask_user

    err = urllib.error.HTTPError(
        url="x", code=500, msg="err", hdrs={}, fp=MagicMock(read=lambda: b"err")
    )
    hub.set_error(err)
    result = ask_user("claude", "Ready?")
    assert result["success"] is False


def test_get_answer_answered(hub):
    """get_answer for an answered question returns {answered: True, answer: ...}."""
    from hub.mcp_server import get_answer

    hub.set_response(b'{"id": "q-1", "answered": true, "answer": "yes"}')
    result = get_answer("q-1")
    assert result["answered"] is True
    assert result["answer"] == "yes"
    assert result["pending"] is False


def test_get_answer_pending(hub):
    """get_answer for a pending question returns {answered: False, pending: True}."""
    from hub.mcp_server import get_answer

    hub.set_response(b'{"id": "q-1", "answered": false, "answer": null}')
    result = get_answer("q-1")
    assert result["answered"] is False
    assert result["pending"] is True


# ---------------------------------------------------------------------------
# Self-registration tools
# ---------------------------------------------------------------------------


def test_register_agent_posts_all_fields(hub):
    """register_agent must POST /agents/register with every provided field."""
    from hub.mcp_server import register_agent

    hub.set_response(b'{"role": "delegate", "context": "hi"}')
    result = register_agent(
        name="bob",
        contact_mode="mcp-push",
        role_request="backend_dev",
        mcp_endpoint="http://bob.local:9000/mcp",
        spawn_cmd=["bob", "--mode", "watch"],
        config={"model": "sonnet"},
    )
    body = _parse_body(hub.calls[0])
    assert body["name"] == "bob"
    assert body["contact_mode"] == "mcp-push"
    assert body["role_request"] == "backend_dev"
    assert body["mcp_endpoint"] == "http://bob.local:9000/mcp"
    assert body["spawn_cmd"] == ["bob", "--mode", "watch"]
    assert body["config"] == {"model": "sonnet"}


def test_update_agent_config_patches_partial_body(hub):
    """update_agent_config must PATCH /agents/{name} with only the provided fields."""
    from hub.mcp_server import update_agent_config

    hub.set_response(b'{"name": "bob"}')
    update_agent_config(name="bob", contact_mode="mcp-push")
    assert hub.calls[0]["method"] == "PATCH"
    assert "/agents/bob" in hub.calls[0]["url"]
    body = _parse_body(hub.calls[0])
    assert body["contact_mode"] == "mcp-push"
    # Unset fields are not in the body.
    assert "config" not in body
    assert "mcp_endpoint" not in body
    assert "spawn_cmd" not in body


def test_get_context_returns_content(hub):
    """get_context must GET /agents/context?role=... and return {success, content}."""
    from hub.mcp_server import get_context

    hub.set_response(b'{"content": "ROLE GUIDE"}')
    result = get_context("backend_dev")
    assert result == {"success": True, "content": "ROLE GUIDE"}
    assert "role=backend_dev" in hub.calls[0]["url"]


def test_get_agent_context_returns_full_payload(hub):
    """get_agent_context must GET /agents/agent-context?agent=... and unwrap."""
    from hub.mcp_server import get_agent_context

    hub.set_response(b'{"status": "active", "context_md": "hi"}')
    result = get_agent_context("alice")
    assert result["success"] is True
    assert result["status"] == "active"
    assert result["context_md"] == "hi"


def test_heartbeat_posts_active_status(hub):
    """heartbeat must POST /agents/{name}/heartbeat with {status: 'active'}."""
    from hub.mcp_server import heartbeat

    hub.set_response(b"{}")
    result = heartbeat("alice")
    assert result == {"ok": True}
    body = _parse_body(hub.calls[0])
    assert body["status"] == "active"
    assert hub.calls[0]["url"].endswith("/api/v1/agents/alice/heartbeat")


# ---------------------------------------------------------------------------
# AI Jobs tools
# ---------------------------------------------------------------------------


def test_create_job_posts_required_fields(hub):
    """create_job must POST /jobs with name, agent, message, cron, session_mode."""
    from hub.mcp_server import create_job

    hub.set_response(b'{"id": "job-1"}')
    result = create_job("Daily", "kimi", "Run me", "0 9 * * *", "new")
    assert result == {"success": True, "job_id": "job-1", "message": "Job created"}
    body = _parse_body(hub.calls[0])
    assert body["name"] == "Daily"
    assert body["agent"] == "kimi"
    assert body["message"] == "Run me"
    assert body["cron"] == "0 9 * * *"
    assert body["session_mode"] == "new"


def test_list_jobs_with_agent_filter(hub):
    """list_jobs must GET /jobs?agent=<name> when agent is provided."""
    from hub.mcp_server import list_jobs

    hub.set_response(b'[{"id": "job-1"}]')
    jobs = list_jobs("kimi")
    assert len(jobs) == 1
    assert "agent=kimi" in hub.calls[0]["url"]


def test_list_jobs_no_agent_returns_all(hub):
    """list_jobs with no agent must call GET /jobs (no agent filter)."""
    from hub.mcp_server import list_jobs

    hub.set_response(b"[]")
    list_jobs()
    assert "agent=" not in hub.calls[0]["url"]


def test_get_job_by_id(hub):
    """get_job must GET /jobs/{id} and return the job dict."""
    from hub.mcp_server import get_job

    hub.set_response(b'{"id": "job-1", "name": "Daily", "history": []}')
    result = get_job("job-1")
    assert result["id"] == "job-1"
    assert hub.calls[0]["url"].endswith("/api/v1/jobs/job-1")


def test_delete_job_calls_delete(hub):
    """delete_job must DELETE /jobs/{id}."""
    from hub.mcp_server import delete_job

    hub.set_response(b"{}")
    result = delete_job("job-1")
    assert result["success"] is True
    assert "deleted" in result["message"]
    assert hub.calls[0]["method"] == "DELETE"
    assert hub.calls[0]["url"].endswith("/api/v1/jobs/job-1")


def test_toggle_job_enabled(hub):
    """toggle_job(enabled=True) must PATCH /jobs/{id} with {enabled: true}."""
    from hub.mcp_server import toggle_job

    hub.set_response(b"{}")
    result = toggle_job("job-1", True)
    assert result["success"] is True
    assert "enabled" in result["message"]
    body = _parse_body(hub.calls[0])
    assert body["enabled"] is True


def test_toggle_job_disabled(hub):
    """toggle_job(enabled=False) must PATCH /jobs/{id} with {enabled: false}."""
    from hub.mcp_server import toggle_job

    hub.set_response(b"{}")
    result = toggle_job("job-1", False)
    assert result["success"] is True
    assert "disabled" in result["message"]
    body = _parse_body(hub.calls[0])
    assert body["enabled"] is False


def test_run_job_returns_run_id(hub):
    """run_job must POST /jobs/{id}/run and return the run_id."""
    from hub.mcp_server import run_job

    hub.set_response(b'{"run_id": "run-1"}')
    result = run_job("job-1")
    assert result["success"] is True
    assert result["run_id"] == "run-1"
    assert hub.calls[0]["method"] == "POST"
    assert hub.calls[0]["url"].endswith("/api/v1/jobs/job-1/run")


# ---------------------------------------------------------------------------
# Legacy tests (M23, M17) — preserved at the bottom for regression
# ---------------------------------------------------------------------------


def test_hub_request_passes_timeout_10_to_urlopen(monkeypatch):
    """M23: every urlopen call from _hub_request must use timeout=10."""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["timeout"] = timeout
        return _ok_response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("HUB_URL", "http://localhost:8000")
    monkeypatch.setenv("HUB_API_KEY", "test-key")
    monkeypatch.setenv("HUB_PROJECT_ID", "proj-test")

    from hub.mcp_server import _hub_request

    _hub_request("GET", "/agents")
    assert captured.get("timeout") == 10


def test_hub_request_passes_timeout_on_post(monkeypatch):
    """The timeout must also apply on POST."""
    captured = {}

    def fake_urlopen(req, timeout=None, data=None):
        captured["timeout"] = timeout
        return _ok_response(b'{"id": "x"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("HUB_URL", "http://localhost:8000")
    monkeypatch.setenv("HUB_API_KEY", "test-key")
    monkeypatch.setenv("HUB_PROJECT_ID", "proj-test")

    from hub.mcp_server import _hub_request

    _hub_request("POST", "/messages", body={"from": "a", "to": "b", "subject": "s", "content": "c"})
    assert captured.get("timeout") == 10


def test_update_task_tool_does_not_send_dead_agent_param(monkeypatch):
    """M17: update_task must not send the unused 'agent' field to the REST API."""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = req.data
        return _ok_response(b'{"id": "task-1", "status": "in_progress"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("HUB_URL", "http://localhost:8000")
    monkeypatch.setenv("HUB_API_KEY", "test-key")
    monkeypatch.setenv("HUB_PROJECT_ID", "proj-test")

    from hub.mcp_server import update_task

    result = update_task("task-1", "in_progress")
    assert result.get("status") == "in_progress"
    body = json.loads(captured["body"])
    assert "agent" not in body
