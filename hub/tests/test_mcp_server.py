"""Unit tests for the canonical Hub-owned, identity-bound MCP surface."""

import json
import urllib.error
from unittest.mock import MagicMock

import pytest


def _response(body=b"{}"):
    response = MagicMock()
    response.read.return_value = body
    response.__enter__ = lambda value: value
    response.__exit__ = MagicMock(return_value=False)
    return response


@pytest.fixture
def hub(monkeypatch):
    calls = []
    responses = []

    def urlopen(request, timeout=10):
        calls.append(request)
        result = responses.pop(0) if responses else b"{}"
        if isinstance(result, Exception):
            raise result
        return _response(result)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setenv("HUB_URL", "http://localhost:8000")
    monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_test-key")
    return calls, responses


def _body(request):
    return json.loads(request.data) if request.data else None


def test_hub_request_binds_run_token_without_identity_headers(hub):
    from hub.mcp_server import _hub_request

    calls, responses = hub
    responses.append(b'{"ok": true}')
    assert _hub_request("POST", "/tasks", {"title": "T"}) == {"ok": True}
    request = calls[0]
    assert request.get_header("Authorization") == "Bearer aw_run_test-key"
    assert request.get_header("X-agentweave-agent") is None
    assert request.get_header("X-agentweave-run") is None
    assert request.full_url.endswith("/api/v1/agent-actions/tasks")
    assert _body(request) == {"title": "T"}


def test_send_message_payload_contains_no_identity_or_run(hub):
    from hub.mcp_server import send_message

    calls, responses = hub
    responses.append(b'{"id": "msg-1"}')
    assert send_message("worker", "Subject", "Content") == {
        "success": True,
        "message_id": "msg-1",
    }
    assert _body(calls[0]) == {
        "recipient": "worker",
        "subject": "Subject",
        "content": "Content",
        "type": "message",
        "task_id": None,
    }


def test_effect_refuses_unbound_run_credential(hub, monkeypatch):
    from hub.mcp_server import send_message

    calls, _ = hub
    monkeypatch.delenv("AW_RUN_TOKEN")
    with pytest.raises(RuntimeError, match="No bound run credential"):
        send_message("worker", "Subject", "Content")
    assert calls == []


def test_task_tools_use_agent_ledger_endpoints_without_assigner(hub):
    from hub.mcp_server import create_task, get_task, list_tasks, update_task

    calls, responses = hub
    responses.extend(
        [
            b'{"id":"task-1"}',
            b'[{"id":"task-1"}]',
            b'{"id":"task-1"}',
            b'{"id":"task-1","status":"completed"}',
        ]
    )
    assert create_task("Build", assignee="worker")["id"] == "task-1"
    assert "assigner" not in _body(calls[0])
    assert list_tasks("worker")[0]["id"] == "task-1"
    assert "agent=worker" in calls[1].full_url
    assert get_task("task-1")["id"] == "task-1"
    assert update_task("task-1", "completed")["status"] == "completed"
    assert _body(calls[3]) == {"status": "completed"}


def test_question_tools_bind_asker_and_return_answer(hub, monkeypatch):
    """`ask_user` now waits and returns the answer itself, so it consumes the poll response its
    own wait makes. `get_answer` remains for an agent that deliberately did not block."""
    from hub import mcp_server
    from hub.mcp_server import ask_user, get_answer

    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    calls, responses = hub
    responses.extend(
        [
            b'{"id":"q-1"}',
            b'{"answered":true,"answer":"yes"}',  # consumed by ask_user's own wait
            b'{"answered":true,"answer":"yes"}',  # for the explicit get_answer below
        ]
    )
    answered = ask_user("Proceed?")
    assert answered["question_id"] == "q-1"
    assert answered["answered"] is True
    assert answered["answer"] == "yes"
    # `options` is always sent, empty for an open question — the column is a list, and a null
    # would come back as None rather than []. `header`/`multi_select` are sent unconditionally
    # too, so the Hub never has to distinguish "absent" from "not wanted".
    assert _body(calls[0]) == {
        "question": "Proceed?",
        "blocking": True,
        "options": [],
        "header": None,
        "multi_select": False,
    }
    assert get_answer("q-1") == {"answered": True, "answer": "yes", "pending": False}


def test_request_agent_uses_bound_run_without_requester_field(hub):
    from hub.mcp_server import request_agent

    calls, responses = hub
    responses.append(b'{"agent":"worker-2","status":"queued"}')
    assert request_agent("worker-2", "worker-template", "Implement it")["status"] == "queued"
    assert _body(calls[0]) == {
        "name": "worker-2",
        "template": "worker-template",
        "task": "Implement it",
    }


@pytest.mark.parametrize(
    ("call", "method", "path", "body"),
    [
        (
            lambda module: module.create_job("N", "worker", "M", "0 2 * * *"),
            "POST",
            "/api/v1/agent-actions/jobs",
            {
                "name": "N",
                "agent": "worker",
                "message": "M",
                "cron": "0 2 * * *",
                "session_mode": "new",
            },
        ),
        (
            lambda module: module.toggle_job("job-1", True),
            "PATCH",
            "/api/v1/agent-actions/jobs/job-1",
            {"enabled": True},
        ),
        (
            lambda module: module.run_job("job-1"),
            "POST",
            "/api/v1/agent-actions/jobs/job-1/run",
            None,
        ),
        (
            lambda module: module.delete_job("job-1"),
            "DELETE",
            "/api/v1/agent-actions/jobs/job-1",
            None,
        ),
    ],
)
def test_job_mutations_reach_only_governed_api(call, method, path, body, hub):
    from hub import mcp_server

    calls, responses = hub
    responses.append(b'{"ok":true}')
    assert call(mcp_server)["ok"] is True
    assert calls[0].method == method
    assert calls[0].full_url.endswith(path)
    assert _body(calls[0]) == body


def test_job_mutation_preserves_forbidden_failure(hub):
    from hub.mcp_server import HubAPIError, run_job

    _, responses = hub
    responses.append(
        urllib.error.HTTPError(
            "http://localhost/api/v1/projects/proj-test/jobs/job-1/run",
            403,
            "Forbidden",
            {},
            MagicMock(read=lambda: b'{"detail":"operator approval required"}'),
        )
    )
    with pytest.raises(HubAPIError) as raised:
        run_job("job-1")
    assert raised.value.status_code == 403
    assert "operator approval required" in raised.value.detail


@pytest.mark.parametrize("status_code", [403, 404, 409, 422])
def test_mcp_adapter_preserves_typed_application_failures(hub, status_code):
    from hub.mcp_server import HubAPIError, _hub_request

    _, responses = hub
    responses.append(
        urllib.error.HTTPError(
            "http://localhost/api/v1/agent-actions/tasks/x",
            status_code,
            "application failure",
            {},
            MagicMock(read=lambda: b'{"detail":"typed failure"}'),
        )
    )

    with pytest.raises(HubAPIError) as raised:
        _hub_request("GET", "/tasks/x")
    assert raised.value.status_code == status_code
    assert raised.value.detail == "typed failure"


def test_hub_request_timeout_is_ten_seconds(monkeypatch):
    from hub.mcp_server import _hub_request

    captured = {}

    def urlopen(request, timeout=None):
        captured["timeout"] = timeout
        return _response(b"{}")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_test")
    _hub_request("GET", "/tasks")
    assert captured["timeout"] == 10


def test_rejected_request_names_the_attempted_endpoint(hub):
    """Task 5.1/5.4: a request the Hub reached and rejected must name which endpoint was
    attempted, not just the bare status code and detail."""
    from hub.mcp_server import HubAPIError, _hub_request

    _, responses = hub
    responses.append(
        urllib.error.HTTPError(
            "http://localhost/api/v1/agent-actions/messages",
            404,
            "Not Found",
            {},
            MagicMock(read=lambda: b'{"detail":"Unknown recipient \'ghost\'"}'),
        )
    )

    with pytest.raises(HubAPIError) as raised:
        _hub_request("POST", "/messages")

    assert raised.value.method == "POST"
    assert raised.value.path == "/messages"
    assert "POST /messages" in str(raised.value)
    assert "Unknown recipient" in str(raised.value)


def test_unreachable_hub_is_distinguishable_from_a_rejected_request(hub):
    """Task 5.2: an unreachable destination (no Hub answered at all) must be
    distinguishable, by exception type and by message, from a reached-and-rejected
    request — the two point at different problems (network/misconfiguration vs. a
    validation or policy failure the Hub itself raised)."""
    from hub.mcp_server import HubAPIError, HubUnreachableError, _hub_request

    _, responses = hub
    responses.append(urllib.error.URLError("Connection refused"))

    with pytest.raises(HubUnreachableError) as raised:
        _hub_request("POST", "/messages")

    assert not isinstance(raised.value, HubAPIError)
    assert "Cannot reach the Hub" in str(raised.value)
    assert "POST /messages" in str(raised.value)
    assert "HUB_URL" in str(raised.value)
    # Distinguishable phrasing from the rejected case, not just a distinguishable type.
    assert "rejected" not in str(raised.value)
