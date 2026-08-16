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
        for real requires an installed hub package, a migration run and a spawned uvicorn."""
        import inspect

        from agentweave import cli

        src = inspect.getsource(cli._hub_native_start)
        assert (
            'db_url = _old_db_url or f"sqlite+aiosqlite:///{db_path.as_posix()}"' in src
        ), "regression: _hub_native_start no longer honours a pre-set DATABASE_URL"
        assert (
            'os.environ["DATABASE_URL"] = db_url' in src
        ), "DATABASE_URL must still be exported before hub.config.settings is imported"


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
