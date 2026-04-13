"""Tests for agentweave hub CLI commands."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from agentweave.cli import (
    HUB_DIR,
    _docker_available,
    _fetch_setup_token,
    _hub_health_check,
    cmd_hub_start,
    cmd_hub_status,
    cmd_hub_stop,
)


class TestDockerAvailability:
    """Tests for Docker availability detection."""

    def test_docker_not_available(self):
        """Test that _docker_available returns False when docker is not in PATH."""
        with patch("agentweave.cli.shutil.which", return_value=None):
            assert _docker_available() is False

    def test_docker_available_with_compose_v2(self):
        """Test that _docker_available returns True with docker compose (v2)."""
        with patch("agentweave.cli.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/docker"
            with patch("agentweave.cli.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="Docker Compose v2")
                assert _docker_available() is True

    def test_docker_available_with_compose_v1(self):
        """Test that _docker_available returns True with docker-compose (v1)."""
        with patch("agentweave.cli.shutil.which") as mock_which:
            # First call for docker returns path, second for docker-compose returns path
            mock_which.side_effect = ["/usr/bin/docker", "/usr/bin/docker-compose"]
            with patch("agentweave.cli.subprocess.run") as mock_run:
                # docker compose fails (v2 not available)
                mock_run.return_value = MagicMock(returncode=1, stderr="unknown command")
                assert _docker_available() is True


class TestHubHealthCheck:
    """Tests for Hub health check polling."""

    def test_health_check_success(self):
        """Test that _hub_health_check returns True when Hub is healthy."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with patch("agentweave.cli.urllib.request.urlopen", return_value=mock_response):
            assert _hub_health_check(timeout=1) is True

    def test_health_check_failure(self):
        """Test that _hub_health_check returns False when Hub is not responding."""
        with patch("agentweave.cli.urllib.request.urlopen", side_effect=Exception("Connection refused")):
            assert _hub_health_check(timeout=1) is False


class TestFetchSetupToken:
    """Tests for fetching setup token from Hub."""

    def test_fetch_token_success(self):
        """Test that _fetch_setup_token returns API key on success."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"api_key": "aw_live_test123"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with patch("agentweave.cli.urllib.request.urlopen", return_value=mock_response):
            assert _fetch_setup_token() == "aw_live_test123"

    def test_fetch_token_failure(self):
        """Test that _fetch_setup_token returns None on failure."""
        with patch("agentweave.cli.urllib.request.urlopen", side_effect=Exception("Connection refused")):
            assert _fetch_setup_token() is None


class TestHubStartCommand:
    """Tests for cmd_hub_start."""

    def test_hub_start_no_docker(self, capsys):
        """Test that hub start fails gracefully when Docker is not available."""
        with patch("agentweave.cli._docker_available", return_value=False):
            result = cmd_hub_start(MagicMock())
            assert result == 1
            captured = capsys.readouterr()
            assert "Docker is not available" in captured.out

    def test_hub_start_already_running(self, capsys):
        """Test that hub start reports success when Hub is already running."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with patch("agentweave.cli._docker_available", return_value=True):
            with patch("agentweave.cli.urllib.request.urlopen", return_value=mock_response):
                result = cmd_hub_start(MagicMock())
                assert result == 0
                captured = capsys.readouterr()
                assert "already running" in captured.out


class TestHubStopCommand:
    """Tests for cmd_hub_stop."""

    def test_hub_stop_not_running(self, capsys):
        """Test that hub stop reports success when Hub is not running."""
        with patch("agentweave.cli.urllib.request.urlopen", side_effect=Exception("Connection refused")):
            result = cmd_hub_stop(MagicMock())
            assert result == 0
            captured = capsys.readouterr()
            assert "not running" in captured.out.lower()


class TestHubStatusCommand:
    """Tests for cmd_hub_status."""

    def test_hub_status_running(self, capsys):
        """Test that hub status reports running when Hub is healthy."""
        import json

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"status": "ok", "version": "0.1.0"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with patch("agentweave.cli.urllib.request.urlopen", return_value=mock_response):
            result = cmd_hub_status(MagicMock())
            assert result == 0
            captured = capsys.readouterr()
            assert "running" in captured.out.lower()

    def test_hub_status_stopped(self, capsys):
        """Test that hub status reports stopped when Hub is not responding."""
        with patch("agentweave.cli.urllib.request.urlopen", side_effect=Exception("Connection refused")):
            result = cmd_hub_status(MagicMock())
            captured = capsys.readouterr()
            assert "stopped" in captured.out.lower()
