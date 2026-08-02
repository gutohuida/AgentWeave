"""Command-path parity for Phase 7 when no tool-protocol server is available."""

import argparse
import json
from unittest.mock import MagicMock


class _HttpTransport:
    def __init__(self):
        self.calls = []

    def get_transport_type(self):
        return "http"

    def _request(self, method, path, body):
        self.calls.append((method, path, body))
        return {"agent": body["name"], "queue_entry_id": "queue-1", "status": "queued"}


def test_agent_request_command_uses_same_budgeted_endpoint(monkeypatch, capsys):
    from agentweave.cli import cmd_agent_request

    transport = _HttpTransport()
    monkeypatch.setenv("AW_AGENT_IDENTITY", "lead")
    monkeypatch.setenv("AW_RUN_ID", "run-1")
    monkeypatch.setattr("agentweave.transport.get_transport", lambda: transport)
    args = argparse.Namespace(
        agent_name="worker-2", template="worker-template", task="Implement it", json=True
    )
    assert cmd_agent_request(args) == 0
    assert transport.calls == [
        (
            "POST",
            "/agents/request",
            {
                "name": "worker-2",
                "template": "worker-template",
                "task": "Implement it",
                "run_id": "run-1",
            },
        )
    ]
    assert json.loads(capsys.readouterr().out)["status"] == "queued"


def test_agent_request_command_refuses_unbound_or_non_hub(monkeypatch, capsys):
    from agentweave.cli import cmd_agent_request

    args = argparse.Namespace(agent_name="worker", template="template", task="work", json=True)
    monkeypatch.delenv("AW_AGENT_IDENTITY", raising=False)
    monkeypatch.delenv("AW_RUN_ID", raising=False)
    assert cmd_agent_request(args) == 1
    assert "No bound agent identity" in capsys.readouterr().out


def test_watchdog_path_is_command_only_without_global_mcp_registration():
    from agentweave.tool_surface import access_path_notice, resolve_access_path

    assert resolve_access_path("claude", "claude", override="mcp") == "cli"
    notice = access_path_notice("cli")
    assert "agentweave msg send" in notice
    assert "agentweave agent request" in notice
    assert "no retrieval command is needed" in notice


def test_legacy_mcp_setup_is_a_non_mutating_compatibility_notice(monkeypatch, capsys):
    from agentweave.cli import cmd_mcp_setup

    monkeypatch.setattr(
        "subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no spawn"))
    )
    assert cmd_mcp_setup(argparse.Namespace()) == 0
    assert "automatic" in capsys.readouterr().out.lower()


def test_http_command_path_forwards_bound_agent_and_run_headers(monkeypatch):
    from agentweave.transport.http import HttpTransport

    captured = {}
    response = MagicMock()
    response.read.return_value = b"{}"
    response.__enter__ = lambda value: value
    response.__exit__ = MagicMock(return_value=False)

    def urlopen(request, timeout=10):
        captured["headers"] = dict(request.header_items())
        return response

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setenv("AW_AGENT_IDENTITY", "lead")
    monkeypatch.setenv("AW_RUN_ID", "run-1")
    transport = HttpTransport("http://localhost:8000", "key", "proj")
    transport._request("POST", "/tasks", {"title": "T"})
    assert captured["headers"]["X-agentweave-agent"] == "lead"
    assert captured["headers"]["X-agentweave-run"] == "run-1"
