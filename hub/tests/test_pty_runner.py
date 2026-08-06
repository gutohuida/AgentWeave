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
import subprocess
import sys
import time
from unittest.mock import MagicMock

import pytest

from hub.pty_runner import (
    IS_WINDOWS,
    STRUCTURED_OUTPUT_DIMENSIONS,
    PipeSession,
    PtySession,
    pid_alive,
    resolve_executable,
    strip_ansi_escapes,
    terminate_process_tree,
)


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


class TestCmdShimUnwrapping:
    """A `.cmd` shim runs under cmd.exe, which truncates its command line at the first raw
    newline — so a multi-line `-p` prompt loses everything after line one. `claude` installs
    from npm as `claude.CMD`, so every Claude run on Windows received only the prompt's first
    line and agents reported having been given no task
    (2026-08-06-hub-collaboration-and-conversation-fixes).
    """

    def _shim(self, tmp_path, body, name="tool.cmd"):
        shim = tmp_path / name
        shim.write_text(body, encoding="utf-8")
        return shim

    def test_npm_shim_resolves_to_its_real_executable(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hub.pty_runner.IS_WINDOWS", True)
        target_dir = tmp_path / "node_modules" / "pkg" / "bin"
        target_dir.mkdir(parents=True)
        target = target_dir / "tool.exe"
        target.write_text("")
        shim = self._shim(
            tmp_path,
            '@ECHO off\r\nSETLOCAL\r\n"%dp0%\\node_modules\\pkg\\bin\\tool.exe"   %*\r\n',
        )

        resolved = resolve_executable([str(shim), "-p", "line one\nline two"])
        assert resolved[0] == str(target.resolve())
        # Arguments are untouched — only argv[0] is rewritten.
        assert resolved[1:] == ["-p", "line one\nline two"]

    def test_shim_that_bakes_in_its_own_arguments_is_left_alone(self, tmp_path, monkeypatch):
        """A JS shim runs `node.exe script.js %*`; dropping the script would break the launch."""
        monkeypatch.setattr("hub.pty_runner.IS_WINDOWS", True)
        (tmp_path / "node.exe").write_text("")
        shim = self._shim(
            tmp_path,
            '@ECHO off\r\n"%dp0%\\node.exe" "%dp0%\\..\\cli.js" %*\r\n',
        )
        assert resolve_executable([str(shim)])[0] == str(shim)

    def test_shim_whose_target_is_missing_is_left_alone(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hub.pty_runner.IS_WINDOWS", True)
        shim = self._shim(tmp_path, '@ECHO off\r\n"%dp0%\\gone.exe" %*\r\n')
        assert resolve_executable([str(shim)])[0] == str(shim)

    def test_non_windows_never_unwraps(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hub.pty_runner.IS_WINDOWS", False)
        (tmp_path / "tool.exe").write_text("")
        shim = self._shim(tmp_path, '@ECHO off\r\n"%dp0%\\tool.exe" %*\r\n')
        assert resolve_executable([str(shim)])[0] == str(shim)

    @pytest.mark.skipif(not IS_WINDOWS, reason="cmd.exe truncation is Windows-only")
    def test_a_multiline_argument_survives_the_unwrapped_spawn(self, tmp_path):
        """End-to-end proof, against a real shim and a real spawn, that the newline survives."""
        echo = tmp_path / "echoargv.py"
        echo.write_text(
            "import sys, json\n"
            "print('START' + json.dumps(sys.argv[1:]) + 'END', flush=True)\n",
            encoding="utf-8",
        )
        # Same shape as the real npm shim: one executable, `%*`, no baked-in arguments. The
        # script path is supplied by the caller's own argv, as claude's prompt is.
        shim = self._shim(tmp_path, f'@ECHO off\r\n"{sys.executable}" %*\r\n')

        session = PtySession.spawn([str(shim), str(echo), "-p", "first line\nSECOND_LINE_MARKER"])
        out = ""
        for _ in range(400):
            chunk = session.read()
            if chunk:
                out += chunk
            if "END" in out:
                break
            time.sleep(0.05)
        assert "SECOND_LINE_MARKER" in out, f"prompt was truncated: {out[:400]!r}"


class TestPtySessionSpawn:
    @pytest.mark.skipif(not IS_WINDOWS, reason="pywinpty socket polling is Windows-only")
    def test_delayed_output_is_not_mistaken_for_eof(self):
        session = PtySession.spawn(
            [sys.executable, "-c", "import time; time.sleep(0.2); print('delayed output')"]
        )
        try:
            captured = ""
            while True:
                chunk = session.read()
                if not chunk:
                    break
                captured += chunk
            assert "delayed output" in captured
            assert session.wait() == 0
        finally:
            if session.isalive():
                session.terminate(force=True)


class TestProcessSessionSpawn:
    def test_captures_stdout_stderr_and_exit_code(self):
        session = PipeSession.spawn(
            [
                sys.executable,
                "-c",
                "import sys; print('stdout line'); print('stderr line', file=sys.stderr)",
            ]
        )
        try:
            captured = ""
            while True:
                chunk = session.read()
                if not chunk:
                    break
                captured += chunk
            assert "stdout line" in captured
            assert "stderr line" in captured
            assert session.wait() == 0
        finally:
            if session.isalive():
                session.terminate(force=True)

    @pytest.mark.skipif(not IS_WINDOWS, reason="CREATE_NO_WINDOW is Windows-only")
    def test_windows_spawn_is_hidden_and_noninteractive(self, monkeypatch):
        fake_process = MagicMock()
        fake_process.stdout = MagicMock()
        fake_process.pid = 1234
        popen = MagicMock(return_value=fake_process)
        monkeypatch.setattr("hub.pty_runner.subprocess.Popen", popen)

        PipeSession.spawn([sys.executable, "-c", "pass"])

        kwargs = popen.call_args.kwargs
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stdout"] is subprocess.PIPE
        assert kwargs["stderr"] is subprocess.STDOUT

    @pytest.mark.skipif(not IS_WINDOWS, reason="ConPTY materializes terminal-width wrapping")
    def test_structured_output_width_does_not_split_long_json_record(self):
        payload = '{"type":"result","content":"' + ("x" * 2_000) + '"}'
        session = PtySession.spawn(
            [sys.executable, "-c", f"print({payload!r})"],
            dimensions=STRUCTURED_OUTPUT_DIMENSIONS,
        )
        try:
            captured = ""
            while True:
                chunk = session.read()
                if not chunk:
                    break
                captured += chunk
            assert strip_ansi_escapes(captured).strip() == payload
            assert session.wait() == 0
        finally:
            if session.isalive():
                session.terminate(force=True)

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


class TestTerminateProcessTree:
    def test_kills_a_long_running_process(self):
        session = PtySession.spawn([sys.executable, "-c", "import time; time.sleep(30)"])
        pid = session.pid
        try:
            assert pid_alive(pid) is True
            terminate_process_tree(pid, force=True)
            for _ in range(50):
                if not pid_alive(pid):
                    break
                time.sleep(0.1)
            assert pid_alive(pid) is False
        finally:
            if session.isalive():
                session.terminate(force=True)

    def test_already_dead_pid_does_not_raise(self):
        session = PtySession.spawn([sys.executable, "-c", "pass"])
        pid = session.pid
        session.wait()
        for _ in range(50):
            if not session.isalive():
                break
            time.sleep(0.1)
        terminate_process_tree(pid, force=True)  # must not raise


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

    def test_pipe_session_runs_cmd_shim_without_visible_console(self, tmp_path, monkeypatch):
        shim = tmp_path / "fakepipecli.cmd"
        shim.write_text("@echo off\necho pipe-arg=%1\nexit /b 4\n")
        monkeypatch.setenv("PATH", str(tmp_path) + ";" + os.environ["PATH"])

        session = PipeSession.spawn(["fakepipecli", "value"])
        try:
            captured = ""
            while True:
                chunk = session.read()
                if not chunk:
                    break
                captured += chunk
            assert "pipe-arg=value" in captured
            assert session.wait() == 4
        finally:
            if session.isalive():
                session.terminate(force=True)
