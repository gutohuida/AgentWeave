"""Tests for the PTY process spawn/output-capture prototype (Phase 3 task 3.4).

`hub.pty_runner` wraps `pywinpty` on Windows and `ptyprocess` on POSIX behind one
interface. CI's `hub-test` job runs on `ubuntu-latest` only (see
`.github/workflows/ci.yml`), so it only ever exercises the POSIX/ptyprocess path — the
Windows/pywinpty path was validated by hand against this repo's actual Windows dev
environment (see the task's tasks.md entry for the live-verification transcript). These
tests are written to run meaningfully on whichever platform executes them.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

from hub.pty_runner import IS_WINDOWS, PtySession, pid_alive, resolve_executable, strip_ansi_escapes


class TestStripAnsiEscapes:
    def test_leading_osc_title_sequence_is_removed(self):
        # Live-captured: ConPTY emits this before a spawned claude process's first output.
        line = '\x1b]0;claude\x1b\\{"type":"system","subtype":"init"}'
        assert strip_ansi_escapes(line) == '{"type":"system","subtype":"init"}'

    def test_leading_csi_handshake_sequences_are_removed(self):
        line = "\x1b[1t\x1b[c\x1b[?1004h\x1b[?9001h" + '{"type":"assistant"}'
        assert strip_ansi_escapes(line) == '{"type":"assistant"}'

    def test_trailing_cursor_restore_is_removed_to_empty(self):
        assert strip_ansi_escapes("\x1b[?25h") == ""

    def test_plain_text_is_unaffected(self):
        assert strip_ansi_escapes("hello world") == "hello world"

    def test_escape_sequences_inside_the_line_are_also_removed(self):
        line = "before\x1b[?7ltext\x1b[?7hafter"
        assert strip_ansi_escapes(line) == "beforetextafter"


class TestResolveExecutable:
    def test_absolute_path_passes_through_unchanged(self, tmp_path):
        fake_binary = tmp_path / ("fake.exe" if IS_WINDOWS else "fake")
        fake_binary.write_text("")
        result = resolve_executable([str(fake_binary), "--flag"])
        assert result == [str(fake_binary), "--flag"]

    def test_bare_name_resolves_via_path(self, monkeypatch):
        monkeypatch.setattr(
            "hub.pty_runner.shutil.which", lambda name: f"/resolved/{name}" if name else None
        )
        result = resolve_executable(["mycli", "arg"])
        assert result == ["/resolved/mycli", "arg"]

    def test_missing_binary_raises_file_not_found(self, monkeypatch):
        monkeypatch.setattr("hub.pty_runner.shutil.which", lambda name: None)
        with pytest.raises(FileNotFoundError, match="not found in PATH"):
            resolve_executable(["does-not-exist"])

    def test_empty_cmd_raises_value_error(self):
        with pytest.raises(ValueError):
            resolve_executable([])


class TestPtySessionSpawn:
    def test_captures_stdout_and_exit_code(self):
        session = PtySession.spawn([sys.executable, "-c", "print('hello from pty')"])
        try:
            output = []
            while True:
                chunk = session.read()
                if not chunk:
                    break
                output.append(chunk)
            captured = "".join(output)
            assert "hello from pty" in captured
            assert session.wait() == 0
            assert session.isalive() is False
        finally:
            if session.isalive():
                session.terminate(force=True)

    def test_nonzero_exit_code_is_captured(self):
        session = PtySession.spawn([sys.executable, "-c", "import sys; sys.exit(7)"])
        try:
            while session.read():
                pass
            assert session.wait() == 7
        finally:
            if session.isalive():
                session.terminate(force=True)

    def test_pid_is_a_positive_integer(self):
        session = PtySession.spawn([sys.executable, "-c", "pass"])
        try:
            assert isinstance(session.pid, int)
            assert session.pid > 0
            session.wait()
        finally:
            if session.isalive():
                session.terminate(force=True)

    def test_terminate_stops_a_long_running_process(self):
        session = PtySession.spawn([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            assert session.isalive() is True
            session.terminate(force=True)
            # Give the OS a moment to reap the process.
            for _ in range(50):
                if not session.isalive():
                    break
                time.sleep(0.1)
            assert session.isalive() is False
        finally:
            if session.isalive():
                session.terminate(force=True)

    def test_missing_executable_raises_before_spawning(self):
        with pytest.raises(FileNotFoundError):
            PtySession.spawn(["definitely-not-a-real-cli-xyz"])


class TestPidAlive:
    def test_current_process_is_alive(self):
        assert pid_alive(os.getpid()) is True

    def test_exited_and_reaped_process_is_not_alive(self):
        session = PtySession.spawn([sys.executable, "-c", "pass"])
        pid = session.pid
        session.wait()
        for _ in range(50):
            if not session.isalive():
                break
            time.sleep(0.1)
        assert pid_alive(pid) is False


@pytest.mark.skipif(not IS_WINDOWS, reason="Windows .cmd shim resolution only applies on Windows")
class TestWindowsCmdShim:
    def test_resolves_and_spawns_a_cmd_shim_by_bare_name(self, tmp_path, monkeypatch):
        # Reproduces the exact concern flagged at cli.py:2341 — agent CLIs installed via
        # npm are `.cmd` shims, and a bare name must resolve through PATHEXT to find them.
        shim = tmp_path / "fakecli.cmd"
        shim.write_text("@echo off\necho hello from fakecli.cmd\necho arg1=%1\nexit /b 3\n")

        monkeypatch.setenv("PATH", str(tmp_path) + ";" + os.environ["PATH"])

        session = PtySession.spawn(["fakecli", "x"])
        try:
            output = []
            while True:
                chunk = session.read()
                if not chunk:
                    break
                output.append(chunk)
            captured = "".join(output)
            assert "hello from fakecli.cmd" in captured
            assert "arg1=x" in captured
            assert session.wait() == 3
        finally:
            if session.isalive():
                session.terminate(force=True)
