"""Tests for AgentWeave MCP server tools."""

import json
from unittest.mock import MagicMock, patch

import pytest

try:
    import fastmcp  # noqa: F401
except ImportError:
    pytest.skip("fastmcp not available", allow_module_level=True)


class TestRegisterAgent:
    @patch("agentweave.mcp.server.get_transport")
    @patch("agentweave.session.Session.load")
    @patch("urllib.request.urlopen")
    def test_register_agent_success(
        self, mock_urlopen, mock_session_load, mock_get_transport, tmp_path, monkeypatch
    ):
        from agentweave.mcp.server import register_agent

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "http"
        mock_get_transport.return_value = mock_transport
        mock_session_load.return_value = None

        monkeypatch.chdir(tmp_path)
        transport_config = tmp_path / ".agentweave" / "transport.json"
        transport_config.parent.mkdir(parents=True, exist_ok=True)
        transport_config.write_text(
            json.dumps({"type": "http", "url": "http://localhost:8000", "api_key": "aw_live_test"}),
            encoding="utf-8",
        )

        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {"role": "backend_dev", "context": "# Backend Dev"}
        ).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = register_agent(name="hermes", contact_mode="poll", role_request="backend_dev")

        assert result["success"] is True
        assert result["role"] == "backend_dev"
        assert result["context"] == "# Backend Dev"

    @patch("agentweave.mcp.server.get_transport")
    def test_register_agent_non_http_transport(self, mock_get_transport):
        from agentweave.mcp.server import register_agent

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "local"
        mock_get_transport.return_value = mock_transport

        result = register_agent(name="hermes", contact_mode="poll")

        assert "error" in result
        assert "HTTP transport" in result["error"]

    @patch("agentweave.mcp.server.get_transport")
    def test_register_agent_invalid_contact_mode(self, mock_get_transport):
        from agentweave.mcp.server import register_agent

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "http"
        mock_get_transport.return_value = mock_transport

        result = register_agent(name="hermes", contact_mode="invalid-mode")

        assert "error" in result
        assert "Invalid contact_mode" in result["error"]

    @patch("agentweave.mcp.server.get_transport")
    @patch("agentweave.session.Session.load")
    def test_register_agent_name_collision(self, mock_session_load, mock_get_transport):
        from agentweave.mcp.server import register_agent

        session = MagicMock()
        session.agent_names = ["claude", "kimi"]
        mock_session_load.return_value = session

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "http"
        mock_get_transport.return_value = mock_transport

        result = register_agent(name="claude", contact_mode="poll")

        assert "error" in result
        assert "reserved for a configured agent" in result["error"]

    @patch("agentweave.mcp.server.get_transport")
    @patch("agentweave.session.Session.load")
    @patch("urllib.request.urlopen")
    def test_register_agent_re_registration(
        self, mock_urlopen, mock_session_load, mock_get_transport, tmp_path, monkeypatch
    ):
        from agentweave.mcp.server import register_agent

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "http"
        mock_get_transport.return_value = mock_transport
        mock_session_load.return_value = None

        monkeypatch.chdir(tmp_path)
        transport_config = tmp_path / ".agentweave" / "transport.json"
        transport_config.parent.mkdir(parents=True, exist_ok=True)
        transport_config.write_text(
            json.dumps({"type": "http", "url": "http://localhost:8000", "api_key": "aw_live_test"}),
            encoding="utf-8",
        )

        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {"role": "collaborator", "context": "# Collaborator"}
        ).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result1 = register_agent(name="hermes", contact_mode="poll")
        result2 = register_agent(name="hermes", contact_mode="poll")

        assert result1["success"] is True
        assert result2["success"] is True
        assert mock_urlopen.call_count == 2

    @patch("agentweave.mcp.server.get_transport")
    @patch("agentweave.session.Session.load")
    @patch("urllib.request.urlopen")
    def test_register_agent_with_config(
        self, mock_urlopen, mock_session_load, mock_get_transport, tmp_path, monkeypatch
    ):
        from agentweave.mcp.server import register_agent

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "http"
        mock_get_transport.return_value = mock_transport
        mock_session_load.return_value = None

        monkeypatch.chdir(tmp_path)
        transport_config = tmp_path / ".agentweave" / "transport.json"
        transport_config.parent.mkdir(parents=True, exist_ok=True)
        transport_config.write_text(
            json.dumps({"type": "http", "url": "http://localhost:8000", "api_key": "aw_live_test"}),
            encoding="utf-8",
        )

        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {"role": "backend_dev", "context": "# Backend Dev"}
        ).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = register_agent(
            name="hermes",
            contact_mode="poll",
            role_request="backend_dev",
            config={"runner": "kimi", "model": "kimi-k2", "yolo": True, "roles": ["backend_dev"]},
        )

        assert result["success"] is True
        # Verify the request body included config
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        import urllib.request

        assert isinstance(request, urllib.request.Request)
        body = json.loads(request.data)
        assert body["config"]["runner"] == "kimi"
        assert body["config"]["yolo"] is True


class TestUpdateAgentConfig:
    @patch("agentweave.mcp.server.get_transport")
    @patch("urllib.request.urlopen")
    def test_update_agent_config_success(
        self, mock_urlopen, mock_get_transport, tmp_path, monkeypatch
    ):
        from agentweave.mcp.server import update_agent_config

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "http"
        mock_get_transport.return_value = mock_transport

        monkeypatch.chdir(tmp_path)
        transport_config = tmp_path / ".agentweave" / "transport.json"
        transport_config.parent.mkdir(parents=True, exist_ok=True)
        transport_config.write_text(
            json.dumps({"type": "http", "url": "http://localhost:8000", "api_key": "aw_live_test"}),
            encoding="utf-8",
        )

        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {"name": "hermes", "config": {"runner": "kimi", "yolo": True}}
        ).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = update_agent_config(name="hermes", config={"yolo": True})

        assert result["success"] is True
        assert result["name"] == "hermes"
        # Verify PATCH method was used
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.method == "PATCH"
        body = json.loads(request.data)
        assert body["config"]["yolo"] is True

    @patch("agentweave.mcp.server.get_transport")
    def test_update_agent_config_non_http_transport(self, mock_get_transport):
        from agentweave.mcp.server import update_agent_config

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "local"
        mock_get_transport.return_value = mock_transport

        result = update_agent_config(name="hermes", config={"yolo": True})

        assert "error" in result
        assert "HTTP transport" in result["error"]


class TestGetContext:
    @patch("agentweave.mcp.server.get_transport")
    @patch("urllib.request.urlopen")
    def test_get_context_valid_role(self, mock_urlopen, mock_get_transport, tmp_path, monkeypatch):
        from agentweave.mcp.server import get_context

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "http"
        mock_get_transport.return_value = mock_transport

        monkeypatch.chdir(tmp_path)
        transport_config = tmp_path / ".agentweave" / "transport.json"
        transport_config.parent.mkdir(parents=True, exist_ok=True)
        transport_config.write_text(
            json.dumps({"type": "http", "url": "http://localhost:8000", "api_key": "aw_live_test"}),
            encoding="utf-8",
        )

        resp = MagicMock()
        resp.read.return_value = json.dumps({"content": "# Backend Developer Guide"}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = get_context(role="backend_dev")

        assert result["success"] is True
        assert result["content"] == "# Backend Developer Guide"

    @patch("agentweave.mcp.server.get_transport")
    @patch("urllib.request.urlopen")
    def test_get_context_unknown_role(
        self, mock_urlopen, mock_get_transport, tmp_path, monkeypatch
    ):
        import urllib.error

        from agentweave.mcp.server import get_context

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "http"
        mock_get_transport.return_value = mock_transport

        monkeypatch.chdir(tmp_path)
        transport_config = tmp_path / ".agentweave" / "transport.json"
        transport_config.parent.mkdir(parents=True, exist_ok=True)
        transport_config.write_text(
            json.dumps({"type": "http", "url": "http://localhost:8000", "api_key": "aw_live_test"}),
            encoding="utf-8",
        )

        err_resp = MagicMock()
        err_resp.read.return_value = json.dumps(
            {"detail": "Role template not found: unknown_role"}
        ).encode()
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=404, msg="Not Found", hdrs={}, fp=err_resp
        )

        result = get_context(role="unknown_role")

        assert "error" in result
        assert "not found" in result["error"].lower()

    @patch("agentweave.mcp.server.get_transport")
    def test_get_context_non_http_transport(self, mock_get_transport):
        from agentweave.mcp.server import get_context

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "local"
        mock_get_transport.return_value = mock_transport

        result = get_context(role="backend_dev")

        assert "error" in result
        assert "HTTP transport" in result["error"]


class TestGetAgentContext:
    @patch("agentweave.mcp.server.get_transport")
    @patch("urllib.request.urlopen")
    def test_get_agent_context_success(
        self, mock_urlopen, mock_get_transport, tmp_path, monkeypatch
    ):
        from agentweave.mcp.server import get_agent_context

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "http"
        mock_get_transport.return_value = mock_transport

        monkeypatch.chdir(tmp_path)
        transport_config = tmp_path / ".agentweave" / "transport.json"
        transport_config.parent.mkdir(parents=True, exist_ok=True)
        transport_config.write_text(
            json.dumps({"type": "http", "url": "http://localhost:8000", "api_key": "aw_live_test"}),
            encoding="utf-8",
        )

        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {
                "agent": "hermes",
                "known": True,
                "declared": False,
                "registered": True,
                "provisional": True,
                "roles": ["backend_dev"],
                "missing": [],
                "metadata": {"context_path": None},
                "context": "# hermes - AgentWeave Onboarding Context",
            }
        ).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = get_agent_context(agent="hermes")

        assert result["success"] is True
        assert result["agent"] == "hermes"
        assert result["registered"] is True
        assert "Onboarding Context" in result["context"]

    @patch("agentweave.mcp.server.get_transport")
    def test_get_agent_context_non_http_transport(self, mock_get_transport):
        from agentweave.mcp.server import get_agent_context

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "local"
        mock_get_transport.return_value = mock_transport

        result = get_agent_context(agent="hermes")

        assert "error" in result
        assert "HTTP transport" in result["error"]


class TestHeartbeat:
    @patch("agentweave.mcp.server.get_transport")
    @patch("urllib.request.urlopen")
    def test_heartbeat_success(self, mock_urlopen, mock_get_transport, tmp_path, monkeypatch):
        from agentweave.mcp.server import heartbeat

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "http"
        mock_transport.is_agent_registered.return_value = True
        mock_get_transport.return_value = mock_transport

        monkeypatch.chdir(tmp_path)
        transport_config = tmp_path / ".agentweave" / "transport.json"
        transport_config.parent.mkdir(parents=True, exist_ok=True)
        transport_config.write_text(
            json.dumps({"type": "http", "url": "http://localhost:8000", "api_key": "aw_live_test"}),
            encoding="utf-8",
        )

        resp = MagicMock()
        resp.read.return_value = json.dumps({"id": "hb-123"}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = heartbeat(agent="hermes")

        assert result["ok"] is True

    @patch("agentweave.mcp.server.get_transport")
    def test_heartbeat_unknown_agent(self, mock_get_transport):
        from agentweave.mcp.server import heartbeat

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "http"
        mock_transport.is_agent_registered.return_value = False
        mock_get_transport.return_value = mock_transport

        result = heartbeat(agent="unknown-agent")

        assert "error" in result
        assert "not registered" in result["error"].lower()

    @patch("agentweave.mcp.server.get_transport")
    def test_heartbeat_non_http_transport(self, mock_get_transport):
        from agentweave.mcp.server import heartbeat

        mock_transport = MagicMock()
        mock_transport.get_transport_type.return_value = "local"
        mock_get_transport.return_value = mock_transport

        result = heartbeat(agent="hermes")

        assert "error" in result
        assert "HTTP transport" in result["error"]


class TestDatetimeIsTzAware:
    """M3 — datetime.utcnow() is deprecated in Python 3.12+. Standardize
    on datetime.now(timezone.utc) in mcp/server.py.

    The two callsites are:
    - save_checkpoint (filename and body display)
    - register_session (registered_at field)
    """

    def test_mcp_server_does_not_use_datetime_utcnow(self):
        from pathlib import Path

        src = Path("src/agentweave/mcp/server.py").read_text(encoding="utf-8")
        assert "datetime.utcnow()" not in src, (
            "M3 regression: datetime.utcnow() is deprecated (Python 3.12+). "
            "Use datetime.now(timezone.utc) instead."
        )

    def test_mcp_server_uses_timezone_aware_now(self):
        from pathlib import Path

        src = Path("src/agentweave/mcp/server.py").read_text(encoding="utf-8")
        assert "datetime.now(timezone.utc)" in src, (
            "Expected datetime.now(timezone.utc) somewhere in mcp/server.py"
        )

    def test_mcp_server_imports_timezone(self):
        from pathlib import Path

        src = Path("src/agentweave/mcp/server.py").read_text(encoding="utf-8")
        # Need the timezone symbol to be imported
        assert "from datetime import datetime, timezone" in src or (
            "from datetime import" in src and "timezone" in src
        ), "mcp/server.py must import timezone from datetime"

