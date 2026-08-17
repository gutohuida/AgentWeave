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
