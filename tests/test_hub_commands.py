"""Tests for agentweave hub CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from agentweave.cli import (
    _docker_available,
    _fetch_setup_token,
    _hub_health_check,
    _hub_native_start,
    _hub_open_project,
    _hub_project_app_url,
    _hub_project_status_summary,
    _hub_resolve_launch_url,
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
            mock_native.assert_called_once_with(
                port=args.port, detach=True, app=False, cwd=Path.cwd()
            )

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
        # Kept nested rather than combined: SIM117 is disabled for this suite because
        # rewriting hundreds of stacked blocks would be churn with no reader benefit.
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
            mock_native.assert_called_once_with(
                port=args.port, detach=True, app=True, cwd=Path.cwd()
            )

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

        # Kept nested rather than combined: SIM117 is disabled for this suite because
        # rewriting hundreds of stacked blocks would be churn with no reader benefit.
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

    def test_status_running(self, capsys):
        """Test that status reports running when Hub is healthy."""
        import json

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"status": "ok", "version": "0.1.0"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with patch(
            "agentweave.cli.urllib.request.urlopen", return_value=mock_response
        ):  # noqa: SIM117
            with patch(
                "agentweave.cli._hub_project_status_summary",
                return_value="2 registered (most recent: Default Project)",
            ):
                result = cmd_status(MagicMock())
        assert result == 0
        captured = capsys.readouterr()
        assert "running" in captured.out.lower()
        assert "2 registered (most recent: Default Project)" in captured.out

    def test_status_stopped(self, capsys):
        """Test that status reports stopped when Hub is not responding."""
        with patch(
            "agentweave.cli.urllib.request.urlopen", side_effect=Exception("Connection refused")
        ):
            cmd_status(MagicMock())
            captured = capsys.readouterr()
            assert "stopped" in captured.out.lower()

    def test_status_shows_zero_projects_for_fresh_instance(self, capsys):
        """A directly started Hub with no registered projects still reports status."""
        import json

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"status": "ok"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with patch(
            "agentweave.cli.urllib.request.urlopen", return_value=mock_response
        ):  # noqa: SIM117
            with patch("agentweave.cli._hub_project_status_summary", return_value="0 registered"):
                cmd_status(MagicMock())
        captured = capsys.readouterr()
        assert "0 registered" in captured.out


class TestProjectStatusSummary:
    """Tests for _hub_project_status_summary (task 2.1: status counts)."""

    def test_reports_count_and_most_recent(self):
        """The collection endpoint orders by last_opened_at desc; the first entry
        is the most recently opened project."""
        import json

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            [{"id": "proj-a", "name": "Alpha"}, {"id": "proj-b", "name": "Beta"}]
        ).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with patch(
            "agentweave.cli._fetch_setup_token", return_value="aw_live_test"
        ):  # noqa: SIM117
            with patch("agentweave.cli.urllib.request.urlopen", return_value=mock_response):
                summary = _hub_project_status_summary(8000)
        assert summary == "2 registered (most recent: Alpha)"

    def test_reports_zero_when_no_projects_registered(self):
        import json

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([]).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with patch(
            "agentweave.cli._fetch_setup_token", return_value="aw_live_test"
        ):  # noqa: SIM117
            with patch("agentweave.cli.urllib.request.urlopen", return_value=mock_response):
                summary = _hub_project_status_summary(8000)
        assert summary == "0 registered"

    def test_returns_none_without_a_token(self):
        """No operator token available (e.g. Hub not yet bootstrapped) is non-fatal."""
        with patch("agentweave.cli._fetch_setup_token", return_value=None):
            assert _hub_project_status_summary(8000) is None

    def test_returns_none_on_request_failure(self):
        with patch(
            "agentweave.cli._fetch_setup_token", return_value="aw_live_test"
        ):  # noqa: SIM117
            with patch(
                "agentweave.cli.urllib.request.urlopen", side_effect=Exception("connection reset")
            ):
                assert _hub_project_status_summary(8000) is None


class TestOpenProjectCall:
    """Tests for _hub_open_project and the launch-URL resolution it feeds (task 2.1:
    open failure, and the plumbing behind legacy `proj-default` binding)."""

    def test_open_project_posts_path_and_returns_summary(self, tmp_path):
        import json

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"id": "proj-abc", "name": "Demo"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        captured_request = {}

        def _fake_urlopen(request, timeout=None):
            captured_request["url"] = request.full_url
            captured_request["method"] = request.get_method()
            captured_request["headers"] = dict(request.header_items())
            captured_request["body"] = request.data
            return mock_response

        with patch("agentweave.cli.urllib.request.urlopen", side_effect=_fake_urlopen):
            result = _hub_open_project(8000, tmp_path, "aw_live_test")

        assert result == {"id": "proj-abc", "name": "Demo"}
        assert captured_request["url"] == "http://localhost:8000/api/v1/projects/open"
        assert captured_request["method"] == "POST"
        assert captured_request["headers"]["Authorization"] == "Bearer aw_live_test"
        assert json.loads(captured_request["body"]) == {"path": str(tmp_path)}

    def test_open_project_returns_none_without_a_token(self, tmp_path):
        assert _hub_open_project(8000, tmp_path, None) is None

    def test_open_project_returns_none_on_failure(self, tmp_path):
        """A network error or Hub-side rejection (e.g. identity conflict) must not
        raise — the caller falls back to opening the app without a project."""
        with patch(
            "agentweave.cli.urllib.request.urlopen", side_effect=Exception("connection refused")
        ):
            assert _hub_open_project(8000, tmp_path, "aw_live_test") is None

    def test_project_app_url_includes_project_id(self):
        url = _hub_project_app_url(8000, {"id": "proj-abc", "name": "Demo"})
        assert url == "http://localhost:8000/?project=proj-abc&view=overview"

    def test_project_app_url_falls_back_to_bare_url_when_no_project(self):
        assert _hub_project_app_url(8000, None) == "http://localhost:8000"

    def test_resolve_launch_url_falls_back_when_open_fails(self, tmp_path, capsys):
        """Open failure (task 2.1) must not block launch: it prints a warning and
        opens the bare Hub URL instead of a project-scoped one."""
        with patch(
            "agentweave.cli._fetch_setup_token", return_value="aw_live_test"
        ):  # noqa: SIM117
            with patch("agentweave.cli._hub_open_project", return_value=None):
                url = _hub_resolve_launch_url(8000, tmp_path)
        assert url == "http://localhost:8000"
        captured = capsys.readouterr()
        assert "could not open" in captured.out.lower()

    def test_resolve_launch_url_none_cwd_skips_open_call(self):
        """No invocation directory (e.g. a Docker-only start) means no open call at
        all — not even an attempt — and no project-scoped URL."""
        with patch("agentweave.cli._hub_open_project") as mock_open:
            url = _hub_resolve_launch_url(8000, None)
        mock_open.assert_not_called()
        assert url == "http://localhost:8000"

    def test_resolve_launch_url_uses_project_summary_on_success(self, tmp_path):
        with patch(
            "agentweave.cli._fetch_setup_token", return_value="aw_live_test"
        ):  # noqa: SIM117
            with patch(
                "agentweave.cli._hub_open_project",
                return_value={"id": "proj-abc", "name": "Demo"},
            ):
                url = _hub_resolve_launch_url(8000, tmp_path)
        assert url == "http://localhost:8000/?project=proj-abc&view=overview"


class TestNativeStartProjectLifecycle:
    """Tests for _hub_native_start's phase-2 scenarios (task 2.1): first start,
    already-running instance, foreground start, and zero-project direct Hub start."""

    def _health_response(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)
        return mock_response

    def _stub_hub_main(self, monkeypatch, tmp_path):
        """Stub `sys.modules["hub.main"]` so `import hub.main` and `find_spec`
        resolve deterministically inside the test.

        This repo's own `hub/` source directory has no top-level `__init__.py`
        (only `hub/hub/` does); when the process cwd is the repo root, Python can
        resolve bare `import hub` to that directory as an implicit namespace
        package instead of the real editable-installed `agentweave-hub`, which
        then fails with `ImportError: cannot import name '__version__'`. Stubbing
        sys.modules directly sidesteps that cwd-dependent shadowing rather than
        depending on which package a bare `import hub` happens to resolve to.
        """
        import sys
        import types

        fake_main = types.ModuleType("hub.main")
        fake_main.__file__ = str(tmp_path / "hub_pkg" / "main.py")
        fake_main.__spec__ = MagicMock()
        fake_pkg = types.ModuleType("hub")
        fake_pkg.main = fake_main
        fake_pkg.__path__ = [str(tmp_path / "hub_pkg")]
        monkeypatch.setitem(sys.modules, "hub", fake_pkg)
        monkeypatch.setitem(sys.modules, "hub.main", fake_main)

    def test_first_start_opens_the_invocation_directory(self, tmp_path, monkeypatch):
        """A fresh detached start captures its cwd and opens it as a project after
        the health check passes, then opens the app window at the project URL."""
        self._stub_hub_main(monkeypatch, tmp_path)
        monkeypatch.setattr("agentweave.cli.HUB_DIR", tmp_path / "hub")
        env_path = tmp_path / "hub" / ".env"
        env_path.parent.mkdir(parents=True)
        env_path.write_text("AW_BOOTSTRAP_API_KEY=aw_live_test\n", encoding="utf-8")

        calls = {"n": 0}

        def _urlopen_side_effect(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise Exception("not running yet")
            return self._health_response()

        fake_proc = MagicMock()
        fake_proc.pid = 4242

        with patch(
            "agentweave.cli.urllib.request.urlopen", side_effect=_urlopen_side_effect
        ):  # noqa: SIM117
            with patch("agentweave.cli._hub_pid_running", return_value=None):
                with patch(
                    "agentweave.cli._hub_native_scaffold",
                    return_value=(env_path, "aw_live_test", True),
                ):
                    with patch("agentweave.cli._hub_run_migrations", return_value=True):
                        with patch("agentweave.cli.subprocess.Popen", return_value=fake_proc):
                            with patch(
                                "agentweave.cli._hub_resolve_launch_url",
                                return_value="resolved-url",
                            ) as mock_resolve:
                                with patch("agentweave.cli._open_app_window") as mock_open_window:
                                    result = _hub_native_start(
                                        port=8000, detach=True, app=True, cwd=tmp_path
                                    )

        assert result == 0
        mock_resolve.assert_called_once_with(8000, tmp_path)
        mock_open_window.assert_called_once_with("resolved-url")

    def test_already_running_instance_still_opens_the_directory(self, tmp_path):
        """Design decision 6: whether the instance was already running or was just
        started, bare invocation opens/registers its directory the same way."""
        with patch(
            "agentweave.cli.urllib.request.urlopen", return_value=self._health_response()
        ):  # noqa: SIM117
            with patch(
                "agentweave.cli._hub_resolve_launch_url", return_value="resolved-url"
            ) as mock_resolve:
                with patch("agentweave.cli._open_app_window") as mock_open_window:
                    result = _hub_native_start(port=8000, detach=True, app=True, cwd=tmp_path)
        assert result == 0
        mock_resolve.assert_called_once_with(8000, tmp_path)
        mock_open_window.assert_called_once_with("resolved-url")

    def test_already_running_without_app_flag_still_registers_project(self, tmp_path):
        """The open call is unconditional; only opening a browser window is gated
        by --app. A bare status-style check must still register the directory."""
        with patch(
            "agentweave.cli.urllib.request.urlopen", return_value=self._health_response()
        ):  # noqa: SIM117
            with patch(
                "agentweave.cli._hub_resolve_launch_url", return_value="resolved-url"
            ) as mock_resolve:
                with patch("agentweave.cli._open_app_window") as mock_open_window:
                    result = _hub_native_start(port=8000, detach=True, app=False, cwd=tmp_path)
        assert result == 0
        mock_resolve.assert_called_once_with(8000, tmp_path)
        mock_open_window.assert_not_called()

    def test_foreground_start_threads_cwd_into_wait_and_open_app(self, tmp_path, monkeypatch):
        """--no-detach (foreground) must still open the invocation directory once
        Hub answers healthy, via the same threaded app-window helper.

        `threading.Thread`/`uvicorn.run` are patched via their real dotted paths
        (both are imported locally inside the function under test, not as
        `agentweave.cli` module attributes) since `uvicorn` is a real
        dependency here and there is no need to fake it away.
        """
        self._stub_hub_main(monkeypatch, tmp_path)
        monkeypatch.setattr("agentweave.cli.HUB_DIR", tmp_path / "hub")
        env_path = tmp_path / "hub" / ".env"
        env_path.parent.mkdir(parents=True)
        env_path.write_text("", encoding="utf-8")

        with patch(
            "agentweave.cli.urllib.request.urlopen", side_effect=Exception("not running")
        ):  # noqa: SIM117
            with patch("agentweave.cli._hub_pid_running", return_value=None):
                with patch(
                    "agentweave.cli._hub_native_scaffold",
                    return_value=(env_path, None, False),
                ):
                    with patch("agentweave.cli._hub_run_migrations", return_value=True):
                        with patch("threading.Thread") as mock_thread:
                            with patch("uvicorn.run"):
                                _hub_native_start(port=8000, detach=False, app=True, cwd=tmp_path)
        mock_thread.assert_called_once()
        _, kwargs = mock_thread.call_args
        assert kwargs["target"].__name__ == "_wait_and_open_app"
        assert kwargs["args"] == (8000, tmp_path)

    def test_zero_project_direct_hub_start_opens_without_a_project(self, tmp_path):
        """A directly started Hub (e.g. Docker, or native with no invocation
        directory) opens with no project selected rather than guessing one."""
        with patch("agentweave.cli.urllib.request.urlopen", return_value=self._health_response()):
            with patch("agentweave.cli._hub_open_project") as mock_open_project:
                with patch("agentweave.cli._open_app_window") as mock_open_window:
                    result = _hub_native_start(port=8000, detach=True, app=True, cwd=None)
        assert result == 0
        mock_open_project.assert_not_called()
        mock_open_window.assert_called_once_with("http://localhost:8000")
