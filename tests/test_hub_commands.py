"""Tests for agentweave hub CLI commands."""

from unittest.mock import MagicMock, patch

from agentweave.cli import (
    _docker_available,
    _fetch_setup_token,
    _hub_health_check,
    cmd_hub_start,
    cmd_status,
    cmd_stop,
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
        with patch(
            "agentweave.cli.urllib.request.urlopen", side_effect=Exception("Connection refused")
        ):
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
        with patch(
            "agentweave.cli.urllib.request.urlopen", side_effect=Exception("Connection refused")
        ):
            assert _fetch_setup_token() is None


class TestHubStartCommand:
    """Tests for cmd_hub_start."""

    def test_hub_start_defaults_to_native(self, capsys):
        """Test that hub start with no flags dispatches to the native path, not Docker."""
        args = MagicMock()
        args.docker = False
        args.local = False
        args.no_detach = False
        args.app = False
        with patch("agentweave.cli._hub_native_start", return_value=0) as mock_native:
            result = cmd_hub_start(args)
            assert result == 0
            mock_native.assert_called_once_with(port=args.port, detach=True, app=False)

    def test_hub_start_docker_flag_no_docker(self, capsys):
        """Test that hub start --docker fails gracefully when Docker is not available."""
        args = MagicMock()
        args.docker = True
        args.local = False
        args.no_detach = False
        args.app = False
        with patch("agentweave.cli._docker_available", return_value=False):
            result = cmd_hub_start(args)
            assert result == 1
            captured = capsys.readouterr()
            assert "Docker is not available" in captured.out

    def test_hub_start_docker_already_running(self, capsys):
        """Test that hub start --docker reports success when Hub is already running."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        args = MagicMock()
        args.docker = True
        args.local = False
        args.no_detach = False
        args.app = False
        # Kept nested: parenthesized multi-context `with` is a syntax error on
        # Python 3.8/3.9, which this suite still runs against in CI.
        with patch("agentweave.cli._docker_available", return_value=True):  # noqa: SIM117
            with patch("agentweave.cli.urllib.request.urlopen", return_value=mock_response):
                result = cmd_hub_start(args)
                assert result == 0
                captured = capsys.readouterr()
                assert "already running" in captured.out

    def test_hub_start_local_implies_docker(self, capsys):
        """Test that --local (without --docker) still takes the Docker path."""
        args = MagicMock()
        args.docker = False
        args.local = True
        args.no_detach = False
        args.app = False
        with patch("agentweave.cli._docker_available", return_value=False):
            result = cmd_hub_start(args)
            assert result == 1
            captured = capsys.readouterr()
            assert "Docker is not available" in captured.out

    def test_hub_start_app_flag_passed_to_native(self, capsys):
        """Test that --app is forwarded to the native start path."""
        args = MagicMock()
        args.docker = False
        args.local = False
        args.no_detach = False
        args.app = True
        with patch("agentweave.cli._hub_native_start", return_value=0) as mock_native:
            result = cmd_hub_start(args)
            assert result == 0
            mock_native.assert_called_once_with(port=args.port, detach=True, app=True)

    def test_hub_start_docker_already_running_opens_app(self, capsys):
        """Test that --app opens the app window even when the Hub is already running."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        args = MagicMock()
        args.docker = True
        args.local = False
        args.no_detach = False
        args.app = True
        with patch("agentweave.cli._docker_available", return_value=True):  # noqa: SIM117
            with patch("agentweave.cli.urllib.request.urlopen", return_value=mock_response):
                with patch("agentweave.cli._open_app_window") as mock_open:
                    result = cmd_hub_start(args)
                    assert result == 0
                    mock_open.assert_called_once()


class TestAppModeBrowser:
    """Tests for the --app chromeless browser window helper."""

    def test_find_app_mode_browser_none_found(self):
        """Test that no candidate path existing returns None."""
        from agentweave.cli import _find_app_mode_browser

        # Kept nested: parenthesized multi-context `with` is a syntax error on
        # Python 3.8/3.9, which this suite still runs against in CI.
        with patch("agentweave.cli.Path.exists", return_value=False):  # noqa: SIM117
            with patch("agentweave.cli.shutil.which", return_value=None):
                assert _find_app_mode_browser() is None

    def test_open_app_window_launches_found_browser(self):
        """Test that a found browser is launched with --app=<url>."""
        from agentweave.cli import _open_app_window

        with patch(  # noqa: SIM117
            "agentweave.cli._find_app_mode_browser", return_value="/usr/bin/chromium"
        ):
            with patch("agentweave.cli.subprocess.Popen") as mock_popen:
                _open_app_window("http://localhost:8000")
                mock_popen.assert_called_once()
                call_args = mock_popen.call_args[0][0]
                assert call_args[0] == "/usr/bin/chromium"
                assert call_args[1] == "--app=http://localhost:8000"

    def test_open_app_window_falls_back_to_webbrowser(self):
        """Test that no browser found falls back to the stdlib webbrowser module."""
        from agentweave.cli import _open_app_window

        with patch("agentweave.cli._find_app_mode_browser", return_value=None):  # noqa: SIM117
            with patch("webbrowser.open") as mock_open:
                _open_app_window("http://localhost:8000")
                mock_open.assert_called_once_with("http://localhost:8000")


class TestStopCommand:
    """Tests for cmd_stop."""

    def test_stop_not_running(self, capsys):
        """Test that stop reports success when Hub is not running."""
        with patch(
            "agentweave.cli.urllib.request.urlopen", side_effect=Exception("Connection refused")
        ):
            result = cmd_stop(MagicMock())
            assert result == 0
            captured = capsys.readouterr()
            assert "not running" in captured.out.lower()


class TestStatusCommand:
    """Tests for cmd_status."""

    def test_status_running(self, tmp_path, capsys):
        """Test that status reports running when Hub is healthy."""
        import json

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"status": "ok", "version": "0.1.0"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        (tmp_path / ".env").write_text(
            "AW_BOOTSTRAP_PROJECT_ID=proj-default\n" "AW_BOOTSTRAP_PROJECT_NAME=Default Project\n",
            encoding="utf-8",
        )
        with patch("agentweave.cli.HUB_DIR", tmp_path):  # noqa: SIM117
            with patch("agentweave.cli.urllib.request.urlopen", return_value=mock_response):
                result = cmd_status(MagicMock())
            assert result == 0
            captured = capsys.readouterr()
            assert "running" in captured.out.lower()
            assert "Default Project (proj-default)" in captured.out

    def test_status_stopped(self, capsys):
        """Test that status reports stopped when Hub is not responding."""
        with patch(
            "agentweave.cli.urllib.request.urlopen", side_effect=Exception("Connection refused")
        ):
            cmd_status(MagicMock())
            captured = capsys.readouterr()
            assert "stopped" in captured.out.lower()
