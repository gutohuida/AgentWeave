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
    monkeypatch.setenv("HUB_API_KEY", "test-key")
    monkeypatch.setenv("AW_AGENT_IDENTITY", "lead")
    monkeypatch.setenv("AW_RUN_ID", "run-1")
    return calls, responses


def _body(request):
    return json.loads(request.data) if request.data else None


def test_hub_request_binds_headers_and_does_not_inject_project_body(hub):
    from hub.mcp_server import _hub_request

    calls, responses = hub
    responses.append(b'{"ok": true}')
    assert _hub_request("POST", "/tasks", {"title": "T"}) == {"ok": True}
    request = calls[0]
    assert request.get_header("Authorization") == "Bearer test-key"
    assert request.get_header("X-agentweave-agent") == "lead"
    assert request.get_header("X-agentweave-run") == "run-1"
    assert _body(request) == {"title": "T"}


def test_send_message_uses_bound_identity_and_run(hub):
    from hub.mcp_server import send_message

    calls, responses = hub
    responses.append(b'{"id": "msg-1"}')
    assert send_message("worker", "Subject", "Content") == {
        "success": True,
        "message_id": "msg-1",
    }
    assert _body(calls[0]) == {
        "from": "lead",
        "to": "worker",
        "subject": "Subject",
        "content": "Content",
        "type": "message",
        "task_id": None,
        "run_id": "run-1",
    }


def test_effect_refuses_unbound_identity(hub, monkeypatch):
    from hub.mcp_server import send_message

    calls, _ = hub
    monkeypatch.delenv("AW_AGENT_IDENTITY")
    result = send_message("worker", "Subject", "Content")
    assert result["success"] is False
    assert "No bound agent identity" in result["error"]
    assert calls == []


def test_task_tools_use_ledger_endpoints_and_bound_assigner(hub):
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
    assert _body(calls[0])["assigner"] == "lead"
    assert list_tasks("worker")[0]["id"] == "task-1"
    assert "agent=worker" in calls[1].full_url
    assert get_task("task-1")["id"] == "task-1"
    assert update_task("task-1", "completed")["status"] == "completed"
    assert _body(calls[3]) == {"status": "completed"}


def test_question_tools_bind_asker_and_return_answer(hub):
    from hub.mcp_server import ask_user, get_answer

    calls, responses = hub
    responses.extend([b'{"id":"q-1"}', b'{"answered":true,"answer":"yes"}'])
    assert ask_user("Proceed?", blocking=True)["question_id"] == "q-1"
    assert _body(calls[0]) == {
        "from_agent": "lead",
        "question": "Proceed?",
        "blocking": True,
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
        "run_id": "run-1",
    }


@pytest.mark.parametrize(
    ("call", "method", "path", "body"),
    [
        (
            lambda module: module.create_job("N", "worker", "M", "0 2 * * *"),
            "POST",
            "/api/v1/jobs",
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
            "/api/v1/jobs/job-1",
            {"enabled": True},
        ),
        (lambda module: module.run_job("job-1"), "POST", "/api/v1/jobs/job-1/run", None),
        (lambda module: module.delete_job("job-1"), "DELETE", "/api/v1/jobs/job-1", None),
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


def test_job_mutation_reports_approval_required_on_gate_rejection(hub):
    from hub.mcp_server import run_job

    _, responses = hub
    responses.append(
        urllib.error.HTTPError(
            "http://localhost/api/v1/jobs/job-1/run",
            403,
            "Forbidden",
            {},
            MagicMock(read=lambda: b'{"detail":"operator approval required"}'),
        )
    )
    result = run_job("job-1")
    assert result["success"] is False
    assert result["approval_required"] is True


def test_hub_request_timeout_is_ten_seconds(monkeypatch):
    from hub.mcp_server import _hub_request

    captured = {}

    def urlopen(request, timeout=None):
        captured["timeout"] = timeout
        return _response(b"{}")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    _hub_request("GET", "/tasks")
    assert captured["timeout"] == 10
