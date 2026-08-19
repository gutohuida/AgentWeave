"""Tests for CLI helpers."""

from pathlib import Path


class TestTransportJsonAtomicWrite:
    """S8 — transport.json must be written via write_json_atomic so the
    0600 chmod and os.replace atomicity from PR 3 are inherited.

    The two call sites (cmd_transport_setup for git, cmd_transport_setup
    for http, and a third in the http cluster update path) all funnel
    through utils.save_json. PR 3 turned save_json into a thin wrapper
    around write_json_atomic, so the call sites are already correct.
    This test is the regression guard: if anyone ever calls
    Path.write_text() directly to write transport.json, it fails.
    """

    def test_save_json_is_thin_wrapper_around_write_json_atomic(self):
        """Regression guard: utils.save_json must remain a thin wrapper
        around write_json_atomic so the 0600 + atomic semantics are
        inherited by every call site (S8)."""
        # Inspect the source of save_json
        import inspect

        from agentweave import utils

        src = inspect.getsource(utils.save_json)
        assert (
            "write_json_atomic" in src
        ), f"utils.save_json no longer delegates to write_json_atomic: {src!r}"


class TestSubprocessRunHasTimeout:
    """M12 — every subprocess.run call in cli.py must pass timeout= so a
    hung child (e.g. git push, docker compose up, claude proxy) cannot
    freeze the user's terminal.

    This is a source-level regression guard. The PR 2 fix added
    timeouts to the GitTransport git calls but not to the higher-level
    CLI plumbing. After PR 4, no subprocess.run in cli.py may be
    called without a timeout.
    """

    def _find_undefined_subprocess_runs(self):
        from pathlib import Path

        src = Path("src/agentweave/cli.py").read_text(encoding="utf-8")
        # Match all subprocess.run( ... ) calls. We can't perfectly
        # parse Python, but we can find lines that have
        # `subprocess.run(` or `._sp.run(` (the aliased form) but
        # don't have `timeout=` on a reasonable near-by continuation.
        # A simpler heuristic: any line that starts a
        # subprocess.run call should have `timeout=` in the visible
        # portion of that call (within 200 chars).
        issues = []
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.lstrip()
            if "subprocess.run(" in stripped or "._sp.run(" in stripped:
                # Look ahead 200 chars (allow wrapped calls)
                look_ahead = "\n".join(src.splitlines()[i - 1 : i + 8])
                if "timeout=" not in look_ahead:
                    issues.append((i, line.rstrip()))
        return issues

    def test_no_subprocess_run_without_timeout(self):
        issues = self._find_undefined_subprocess_runs()
        assert (
            not issues
        ), "M12 regression: subprocess.run calls in cli.py without timeout=:\n" + "\n".join(
            f"  cli.py:{ln}: {line}" for ln, line in issues
        )


class TestTwoInstancesDoNotCollide:
    """One machine may run more than one Hub — the instance you work in, and a throwaway one
    on another port and another database that you test against.

    `--port` has existed all along, but two singletons made it a trap: a single shared
    `hub.pid`, so the second start erased the first's record, and an unconditional overwrite
    of `DATABASE_URL`, so both processes opened the same SQLite file. These guard both.
    """

    def test_pid_file_is_per_port_and_the_default_port_keeps_its_historic_name(self):
        from agentweave.cli import DEFAULT_HUB_PORT, HUB_DIR, _hub_pid_file

        # The default keeps the unsuffixed name, so a Hub started by an older build is still
        # found, reported and stopped by this one.
        assert _hub_pid_file() == HUB_DIR / "hub.pid"
        assert _hub_pid_file(DEFAULT_HUB_PORT) == HUB_DIR / "hub.pid"

        # Any other port gets its own file, so two instances never overwrite each other.
        assert _hub_pid_file(8010) == HUB_DIR / "hub-8010.pid"
        assert _hub_pid_file(8010) != _hub_pid_file(DEFAULT_HUB_PORT)

    def test_native_start_prefers_an_explicit_database_url(self, monkeypatch):
        """The source-level guard: `db_url` must fall back to the computed path rather than
        replace an explicit one. Asserted against the source because reaching the assignment
        for real requires an installed hub package, a migration run and a spawned uvicorn.

        The decision itself moved into `_hub_resolve_database_source` (D6, so `--profile` has a
        single place to name which of DATABASE_URL/profile won) — this guard now checks
        `_hub_native_start` still delegates to it and still exports the result, and
        `TestProfileFlag` below tests the helper's actual precedence behaviour directly.
        """
        import inspect

        from agentweave import cli

        src = inspect.getsource(cli._hub_native_start)
        assert (
            "db_url, _db_source_message = _hub_resolve_database_source(_old_db_url, profile, db_path)"
            in src
        ), "regression: _hub_native_start no longer delegates the DATABASE_URL decision"
        assert (
            'os.environ["DATABASE_URL"] = db_url' in src
        ), "DATABASE_URL must still be exported before hub.config.settings is imported"


class TestProfileFlag:
    """D6 — `--profile <name>` isolates a database, PID file and (with `--port`) a port together.

    The default profile must stay byte-identical to the pre-D6 paths; a named profile must never
    collide with the default profile's or with another named profile's.
    """

    def test_default_profile_data_dir_is_byte_identical_to_pre_profile_path(self):
        from agentweave.cli import HUB_DIR, _hub_profile_data_dir

        assert _hub_profile_data_dir() == HUB_DIR / "data"
        assert _hub_profile_data_dir("default") == HUB_DIR / "data"

    def test_default_profile_pid_file_is_byte_identical_to_pre_profile_path(self):
        from agentweave.cli import HUB_DIR, _hub_pid_file

        assert _hub_pid_file() == HUB_DIR / "hub.pid"
        assert _hub_pid_file(profile="default") == HUB_DIR / "hub.pid"
        assert _hub_pid_file(8010, "default") == HUB_DIR / "hub-8010.pid"

    def test_two_named_profiles_resolve_to_distinct_db_paths_and_pid_files(self):
        from agentweave.cli import HUB_DIR, _hub_pid_file, _hub_profile_data_dir

        assert _hub_profile_data_dir("a") == HUB_DIR / "profiles" / "a"
        assert _hub_profile_data_dir("b") == HUB_DIR / "profiles" / "b"
        assert _hub_profile_data_dir("a") != _hub_profile_data_dir("b")

        # Even at DEFAULT_HUB_PORT, a named profile's PID file is unconditionally namespaced,
        # so it can never collide with the default profile's file at the same port.
        assert _hub_pid_file(8000, "a") == HUB_DIR / "hub-a-8000.pid"
        assert _hub_pid_file(8010, "a") == HUB_DIR / "hub-a-8010.pid"
        assert _hub_pid_file(8010, "b") == HUB_DIR / "hub-b-8010.pid"
        assert _hub_pid_file(8010, "a") != _hub_pid_file(8010, "b")
        assert _hub_pid_file(8000, "a") != _hub_pid_file(8000, "default")

    def test_explicit_database_url_overrides_profile_and_names_which_won(self, tmp_path):
        from agentweave.cli import _hub_resolve_database_source

        db_path = tmp_path / "profiles" / "dev" / "agentweave.db"
        explicit = "sqlite+aiosqlite:///explicit.db"

        # DATABASE_URL set + named profile -> DATABASE_URL wins, message names both.
        db_url, message = _hub_resolve_database_source(explicit, "dev", db_path)
        assert db_url == explicit
        assert message is not None
        assert "DATABASE_URL" in message
        assert "dev" in message

        # DATABASE_URL set + default profile -> DATABASE_URL wins silently, unchanged from
        # before profiles existed.
        db_url, message = _hub_resolve_database_source(explicit, "default", db_path)
        assert db_url == explicit
        assert message is None

        # No DATABASE_URL + named profile -> the computed profile path wins, named in the message.
        db_url, message = _hub_resolve_database_source(None, "dev", db_path)
        assert db_url == f"sqlite+aiosqlite:///{db_path.as_posix()}"
        assert message is not None
        assert "dev" in message

        # No DATABASE_URL + default profile -> computed path wins silently, unchanged.
        db_url, message = _hub_resolve_database_source(None, "default", db_path)
        assert db_url == f"sqlite+aiosqlite:///{db_path.as_posix()}"
        assert message is None


class TestPortRequiredForNamedProfile:
    """D6 "Port" (round-2 cold review), task 1.8/2.9 — a named profile with no explicit `--port`
    must error rather than silently resolve to `DEFAULT_HUB_PORT`, since a named profile's
    database and PID-file namespacing do nothing to prevent a TCP-level bind collision with the
    default profile's own instance.

    `--port` defaults to `None` (not `DEFAULT_HUB_PORT`) on every subparser that carries it,
    specifically so "not passed" and "passed and happens to equal 8000" are distinguishable —
    the parser-level tests below guard that sentinel directly, since a plain `default=8000`
    would make the whole check unreachable.
    """

    def test_named_profile_without_port_is_an_error(self):
        from agentweave.cli import DEFAULT_HUB_PORT, _hub_require_port_for_named_profile

        message = _hub_require_port_for_named_profile("dev", None)
        assert message is not None
        assert "--profile" in message
        assert "--port" in message
        assert "dev" in message
        assert str(DEFAULT_HUB_PORT) in message

    def test_default_profile_without_port_is_fine(self):
        from agentweave.cli import _hub_require_port_for_named_profile

        assert _hub_require_port_for_named_profile("default", None) is None
        assert _hub_require_port_for_named_profile("", None) is None

    def test_named_profile_with_explicit_port_is_fine(self):
        from agentweave.cli import _hub_require_port_for_named_profile

        assert _hub_require_port_for_named_profile("dev", 8010) is None

    def test_parser_port_default_is_none_not_8000(self):
        """Guards the sentinel itself: if `--port` ever regresses to `default=8000` on any of
        these three subparsers, the passed-vs-default distinction above becomes unreachable and
        this whole check goes silently dead."""
        from agentweave.cli import create_parser

        parser = create_parser()
        assert parser.parse_args([]).port is None
        assert parser.parse_args(["status"]).port is None
        assert parser.parse_args(["stop"]).port is None
        # reset has no --port at all (design.md D6) — nothing to check there.

        assert parser.parse_args(["--port", "8010"]).port == 8010
        assert parser.parse_args(["status", "--port", "8010"]).port == 8010
        assert parser.parse_args(["stop", "--port", "8010"]).port == 8010

    def test_cmd_hub_start_rejects_named_profile_without_port(self, capsys):
        import argparse

        from agentweave.cli import cmd_hub_start

        args = argparse.Namespace(
            port=None, profile="dev", local=False, docker=False, no_detach=False, app=True
        )
        assert cmd_hub_start(args) == 1
        captured = capsys.readouterr()
        assert "--port" in captured.out

    def test_cmd_status_rejects_named_profile_without_port(self, capsys):
        import argparse

        from agentweave.cli import cmd_status

        args = argparse.Namespace(port=None, profile="dev")
        assert cmd_status(args) == 1
        captured = capsys.readouterr()
        assert "--port" in captured.out

    def test_cmd_stop_rejects_named_profile_without_port(self, capsys):
        import argparse

        from agentweave.cli import cmd_stop

        args = argparse.Namespace(port=None, profile="dev", local=False)
        assert cmd_stop(args) == 1
        captured = capsys.readouterr()
        assert "--port" in captured.out


class TestAppModeNativeWindow:
    """D3/D5, tasks 3.2-3.3, 4.1-4.3 — pywebview opens a native OS window when it is
    installed and a backend is available; otherwise app mode is byte-identical to the
    pre-existing chromeless-browser-or-tab behavior (`_open_app_window`).

    `_open_app_window_native` does `import webview` inside the function body (never at
    module load, per CLAUDE.md's stdlib-only stance on the CLI's own code), so it is
    tested here by injecting a fake module into `sys.modules` rather than requiring a
    real pywebview install — the same trick used to force an ImportError deterministically
    regardless of whether pywebview happens to be present in the test environment.

    Design.md D3's amendment A2 already settled that no Playwright test can drive
    pywebview's actual window, so these tests exercise `_open_app_window_native` and its
    call sites' wiring in isolation, not a real window.
    """

    def test_pywebview_not_installed_returns_false(self, monkeypatch):
        """4.1 — with pywebview unimportable, the function reports it can't run the
        native path so the caller falls back to `_open_app_window` unchanged."""
        import sys

        from agentweave.cli import _open_app_window_native

        # sys.modules[name] = None is the documented way to force `import name` to raise
        # ImportError, regardless of whether the real package happens to be installed.
        monkeypatch.setitem(sys.modules, "webview", None)
        assert _open_app_window_native("http://127.0.0.1:8000") is False

    def test_pywebview_installed_opens_window_with_resolved_url(self, monkeypatch):
        """4.2 — create_window/start receive the exact title and URL
        `_hub_resolve_launch_url` already resolves, `start` also receives the packaged
        mark's path as `icon=`, and the function reports True (the caller's signal not
        to also call `_open_app_window`)."""
        import sys
        import types

        from agentweave.cli import _open_app_window_native

        calls = []
        fake_webview = types.SimpleNamespace(
            create_window=lambda title, url: calls.append(("create_window", title, url)),
            start=lambda **kwargs: calls.append(("start", kwargs.get("icon"))),
        )
        monkeypatch.setitem(sys.modules, "webview", fake_webview)

        result = _open_app_window_native("http://127.0.0.1:8010/?project=proj-1")
        assert result is True
        assert calls[0] == (
            "create_window",
            "AgentWeave",
            "http://127.0.0.1:8010/?project=proj-1",
        )
        assert calls[1][0] == "start"
        icon_path = calls[1][1]
        assert icon_path is not None, "packaged icon.ico should resolve in this dev install"
        assert Path(icon_path).name == "icon.ico"
        assert Path(icon_path).is_file()

    def test_webview_start_exception_falls_back(self, monkeypatch, capsys):
        """4.3 — a broken backend (e.g. no WebView2/WebKitGTK/Qt) must not crash the
        invocation. It's caught, a message naming what happened is printed, and the
        function reports False so the caller opens the browser fallback instead."""
        import sys
        import types

        from agentweave.cli import _open_app_window_native

        def _boom(**kwargs):
            raise RuntimeError("no WebView2 runtime found")

        fake_webview = types.SimpleNamespace(create_window=lambda title, url: None, start=_boom)
        monkeypatch.setitem(sys.modules, "webview", fake_webview)

        assert _open_app_window_native("http://127.0.0.1:8000") is False
        assert "WebView2" in capsys.readouterr().out

    def test_open_app_window_native_sets_windows_app_user_model_id_first(self, monkeypatch):
        """Confirmed empirically (see the Q7 log entry): `webview.start(icon=...)`
        alone sets the window's own icon but not the taskbar button's — Windows
        keeps showing python.exe's icon there until the process claims an explicit
        AppUserModelID. That claim must happen before `create_window`, not after,
        so assert both the call and its ordering relative to the two webview calls."""
        import sys
        import types

        from agentweave import cli

        calls = []
        monkeypatch.setattr(
            cli,
            "_set_windows_app_user_model_id",
            lambda: calls.append("aumid"),
        )
        fake_webview = types.SimpleNamespace(
            create_window=lambda title, url: calls.append("create_window"),
            start=lambda **kwargs: calls.append("start"),
        )
        monkeypatch.setitem(sys.modules, "webview", fake_webview)

        assert cli._open_app_window_native("http://127.0.0.1:8000") is True
        assert calls == ["aumid", "create_window", "start"]

    def test_set_windows_app_user_model_id_noop_off_windows(self, monkeypatch):
        """The AUMID call is a ctypes.windll shell32 call, which only exists on
        Windows — must not even attempt it, let alone raise, on other platforms."""
        from agentweave import cli

        monkeypatch.setattr(cli.sys, "platform", "darwin")
        cli._set_windows_app_user_model_id()  # must not raise

    def test_set_windows_app_user_model_id_swallows_shell_errors(self, monkeypatch):
        """A shell32 call that fails (old Windows, sandboxed process, whatever) must
        not take down window opening — same swallow-and-continue posture as the
        pywebview backend exception handling right next to this call site."""
        import ctypes
        import types

        from agentweave import cli

        monkeypatch.setattr(cli.sys, "platform", "win32")

        class _BoomShell32:
            # Mirrors the real Windows API's PascalCase name — noqa: N802.
            def SetCurrentProcessExplicitAppUserModelID(self, *_a, **_k):  # noqa: N802
                raise OSError("no shell32 in this sandbox")

        monkeypatch.setattr(
            ctypes, "windll", types.SimpleNamespace(shell32=_BoomShell32()), raising=False
        )
        cli._set_windows_app_user_model_id()  # must not raise

    def test_app_icon_path_resolves_to_a_real_multi_size_ico(self):
        """The mark ships as a real asset, not a stub — resolve it once via the same
        importlib.resources path `_open_app_window_native` uses, and confirm the file
        it finds is a genuine multi-size .ico rather than a placeholder."""
        from PIL import Image

        from agentweave.cli import _app_icon_path

        path = _app_icon_path()
        assert path is not None
        assert Path(path).is_file()
        with Image.open(path) as img:
            assert img.format == "ICO"
            sizes = set(img.info.get("sizes", []))
            assert (256, 256) in sizes
            assert (16, 16) in sizes

    def test_app_icon_path_missing_asset_returns_none(self, monkeypatch):
        """A stripped-down install without the asset must not crash the window
        open — `webview.start(icon=None)` is exactly today's un-iconed behaviour."""
        import importlib.resources as resources_mod

        from agentweave import cli

        class _MissingIcon:
            def joinpath(self, *parts):
                return self

            def is_file(self):
                return False

        class _FakeTraversable:
            def joinpath(self, *parts):
                return _MissingIcon()

        monkeypatch.setattr(resources_mod, "files", lambda pkg: _FakeTraversable())
        assert cli._app_icon_path() is None

    def test_hub_native_start_already_running_prefers_native_window(self, monkeypatch):
        """Exercises a real call site (task 3.3's first of four): `_hub_native_start`'s
        already-running branch tries `_open_app_window_native` before `_open_app_window`,
        and does not call the fallback when the native path reports success."""
        import urllib.request

        from agentweave import cli

        class FakeResp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeResp())

        calls = []
        monkeypatch.setattr(
            cli, "_open_app_window_native", lambda url: calls.append(("native", url)) or True
        )
        monkeypatch.setattr(cli, "_open_app_window", lambda url: calls.append(("fallback", url)))

        result = cli._hub_native_start(
            port=8000, detach=True, app=True, cwd=None, profile="default"
        )
        assert result == 0
        assert calls == [("native", cli._hub_url(8000))]

    def test_hub_native_start_already_running_falls_back_when_native_unavailable(self, monkeypatch):
        """4.1's byte-identical claim, exercised at the real call site rather than just the
        helper in isolation: when `_open_app_window_native` reports it couldn't run (e.g.
        pywebview absent), the exact same `_open_app_window(url)` call fires as it always
        has — same URL, no new branch."""
        import urllib.request

        from agentweave import cli

        class FakeResp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeResp())

        calls = []
        monkeypatch.setattr(cli, "_open_app_window_native", lambda url: False)
        monkeypatch.setattr(cli, "_open_app_window", lambda url: calls.append(("fallback", url)))

        result = cli._hub_native_start(
            port=8000, detach=True, app=True, cwd=None, profile="default"
        )
        assert result == 0
        assert calls == [("fallback", cli._hub_url(8000))]

    def test_call_sites_fall_back_through_the_native_helper_first(self):
        """4.4 / source-level regression guard for task 3.3's wiring as a whole: both real
        functions with app-mode call sites (`_hub_native_start`'s two, `cmd_hub_start`'s
        Docker branch's two) must try `_open_app_window_native` before falling back. The
        fifth site, `_wait_and_open_app` (the `--no-detach` foreground path), is a
        deliberate, named exception (design.md D3) and must keep calling
        `_open_app_window` unconditionally — pywebview requires the main thread, which
        `_wait_and_open_app`'s worker thread is not.
        """
        import inspect

        from agentweave import cli

        for fn in (cli._hub_native_start, cli.cmd_hub_start):
            src = inspect.getsource(fn)
            assert src.count("_open_app_window_native(") == 2, (
                f"{fn.__name__} should wire exactly two call sites through "
                "_open_app_window_native (task 3.3)"
            )

        wait_src = inspect.getsource(cli._wait_and_open_app)
        assert "_open_app_window_native" not in wait_src, (
            "_wait_and_open_app must keep the unconditional browser fallback (design.md D3's "
            "named exception) — it must not be wired through _open_app_window_native"
        )
        assert "_open_app_window(" in wait_src


class TestDesktopShortcut:
    """APP1 — a Desktop shortcut (`AgentWeave.lnk`) is created on first native-mode run
    so the app can be launched without a terminal. Windows only for now; a macOS/Linux
    equivalent is an unresearched follow-up, recorded in the log rather than attempted
    here. Built via PowerShell's `WScript.Shell` COM object, invoked as a subprocess, so
    it adds no new pip dependency (CLAUDE.md: the CLI's own code stays stdlib-only)."""

    def test_noop_off_windows(self, monkeypatch):
        from agentweave import cli

        monkeypatch.setattr(cli.sys, "platform", "darwin")
        calls = []
        monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: calls.append(a) or None)
        assert cli._create_desktop_shortcut() is False
        assert calls == []

    def test_skips_when_shortcut_already_exists(self, tmp_path, monkeypatch):
        """Idempotent: a second call (e.g. a second `agentweave` install, or a future
        re-run) must not clobber a shortcut the operator may have moved or customized."""
        from agentweave import cli

        monkeypatch.setattr(cli.sys, "platform", "win32")
        monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
        desktop = tmp_path / "Desktop"
        desktop.mkdir()
        (desktop / "AgentWeave.lnk").write_text("existing", encoding="utf-8")

        calls = []
        monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: calls.append(a) or None)
        assert cli._create_desktop_shortcut() is False
        assert calls == []

    def test_swallows_subprocess_errors(self, tmp_path, monkeypatch):
        """A failure here (no PowerShell, a sandboxed process, whatever) must not raise —
        this is convenience, not a requirement for the Hub to start."""
        from agentweave import cli

        monkeypatch.setattr(cli.sys, "platform", "win32")
        monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)

        def _boom(*a, **k):
            raise OSError("powershell not found")

        monkeypatch.setattr(cli.subprocess, "run", _boom)
        assert cli._create_desktop_shortcut() is False

    def test_builds_powershell_script_targeting_pythonw_with_icon(self, tmp_path, monkeypatch):
        """When a `pythonw.exe` sibling exists next to the running interpreter, the
        shortcut targets it with `-m agentweave` (no console window flashes behind the
        app window) rather than the console-mode `agentweave.exe`, and passes the
        packaged icon through `IconLocation`."""
        from agentweave import cli

        monkeypatch.setattr(cli.sys, "platform", "win32")
        monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "_app_icon_path", lambda: r"C:\fake\icon.ico")

        pythonw = tmp_path / "pythonw.exe"
        pythonw.write_bytes(b"")
        monkeypatch.setattr(cli.sys, "executable", str(tmp_path / "python.exe"))

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)

            class _Result:
                returncode = 0

            return _Result()

        monkeypatch.setattr(cli.subprocess, "run", fake_run)
        assert cli._create_desktop_shortcut() is True
        assert len(calls) == 1
        cmd = calls[0]
        assert cmd[0] == "powershell"
        script = cmd[-1]
        assert "AgentWeave.lnk" in script
        assert str(pythonw) in script
        assert "-m agentweave" in script
        assert r"C:\fake\icon.ico" in script

    def test_falls_back_to_console_script_without_pythonw(self, tmp_path, monkeypatch):
        """No `pythonw.exe` sibling (e.g. a venv layout that doesn't ship one) -> falls
        back to `shutil.which("agentweave")`, the installed console-script entry point,
        with no `-m agentweave` arguments (the exe itself is the entry point)."""
        from agentweave import cli

        monkeypatch.setattr(cli.sys, "platform", "win32")
        monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
        monkeypatch.setattr(cli, "_app_icon_path", lambda: None)
        monkeypatch.setattr(cli.sys, "executable", str(tmp_path / "python.exe"))
        monkeypatch.setattr(cli.shutil, "which", lambda name: r"C:\fake\Scripts\agentweave.exe")

        calls = []
        monkeypatch.setattr(
            cli.subprocess,
            "run",
            lambda cmd, **k: calls.append(cmd) or type("R", (), {"returncode": 0})(),
        )
        assert cli._create_desktop_shortcut() is True
        script = calls[0][-1]
        assert r"C:\fake\Scripts\agentweave.exe" in script
        assert "-m agentweave" not in script
        # No icon patched in this case — IconLocation must not appear.
        assert "IconLocation" not in script

    def test_hub_native_start_calls_create_shortcut_gated_on_first_run(self):
        """Regression guard for the call site inside `_hub_native_start`: the shortcut
        must be attempted exactly once, gated on `is_first_run`, not on every start."""
        import inspect

        from agentweave import cli

        src = inspect.getsource(cli._hub_native_start)
        assert src.count("_create_desktop_shortcut()") == 1
        assert "if is_first_run and _create_desktop_shortcut():" in src

    def test_real_powershell_creates_a_valid_lnk_file_on_windows(self, tmp_path, monkeypatch):
        """Live verification, not only a mocked subprocess call: on a real Windows
        environment (this dev box, and CI's windows-latest matrix leg) actually invoke
        PowerShell and confirm a genuine shell-link file lands on Desktop. `.lnk` files
        begin with a fixed 4-byte header (ShellLinkHeader's HeaderSize field, always
        0x0000004C little-endian) — checking it is a cheap, real structural assertion
        that this is a shortcut, not an empty or garbage file."""
        import sys as _sys

        if _sys.platform != "win32":
            import pytest

            pytest.skip("PowerShell shortcut creation only runs on Windows")

        from agentweave import cli

        monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)

        assert cli._create_desktop_shortcut() is True
        lnk_path = tmp_path / "Desktop" / "AgentWeave.lnk"
        assert lnk_path.is_file()
        assert lnk_path.read_bytes()[:4] == b"\x4c\x00\x00\x00"


class TestDownloadWithSha256:
    """S9 — verify SHA256 of downloaded Hub docker-compose.yml and .env
    via a new _download_with_sha256 helper.

    The helper downloads the file, optionally fetches a sidecar
    `<url>.sha256` and compares. If the sidecar is missing, it logs a
    WARN and continues (the file is still saved). If the sidecar is
    present but the checksum does not match, the file is deleted and
    an error is returned.
    """

    def test_downloads_file_when_no_sha256_url(self, tmp_path, monkeypatch):
        """No sha256 URL configured -> download proceeds, no verification."""
        import urllib.request

        from agentweave.cli import _download_with_sha256

        dest = tmp_path / "out.txt"

        # The helper will be called with a fake URL; we patch urlretrieve
        # at the urllib.request module level (the helper imports urllib.request
        # as _req inside the function, so the module attribute is the right
        # target).
        def fake_urlretrieve(url, path):
            Path(path).write_text("hello world", encoding="utf-8")

        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        result = _download_with_sha256(
            url="https://example.com/file.txt",
            dest=dest,
            sha256_url=None,
        )
        assert result is True
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == "hello world"

    def test_verifies_sha256_when_provided_and_matches(self, tmp_path, monkeypatch):
        """sha256 URL configured and checksum matches -> success."""
        import urllib.request

        from agentweave.cli import _download_with_sha256

        dest = tmp_path / "out.txt"
        # SHA256 of "hello world"
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

        def fake_urlretrieve(url, path):
            Path(path).write_text("hello world", encoding="utf-8")

        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        result = _download_with_sha256(
            url="https://example.com/file.txt",
            dest=dest,
            sha256_url="https://example.com/file.txt.sha256",
            expected_sha256=expected,
        )
        assert result is True
        assert dest.exists()

    def test_fails_loud_on_sha256_mismatch(self, tmp_path, monkeypatch, capsys):
        """sha256 URL configured and checksum does NOT match -> error,
        destination file is removed (no partial download left behind)."""
        import urllib.request

        from agentweave.cli import _download_with_sha256

        dest = tmp_path / "out.txt"
        # Wrong checksum
        wrong = "0000000000000000000000000000000000000000000000000000000000000000"

        def fake_urlretrieve(url, path):
            Path(path).write_text("hello world", encoding="utf-8")

        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        result = _download_with_sha256(
            url="https://example.com/file.txt",
            dest=dest,
            sha256_url="https://example.com/file.txt.sha256",
            expected_sha256=wrong,
        )
        assert result is False
        # Destination should not exist — the corrupted file must be cleaned up
        assert not dest.exists()
