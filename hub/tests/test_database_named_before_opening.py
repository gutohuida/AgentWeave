"""Group 2 of `a-hub-that-was-not-told-which-database-refuses-to-open-one`: the Hub
names its database before it opens it (F388).

`TestLogDatabaseBeforeOpeningUnit` is the fast check on the text and the level (2.6).
`TestGroup2LineOrderingRealProcess` and `TestRefusalIsAutomated` launch a real `uvicorn
hub.main:app` subprocess (2.7, 2.8) — a unit-level proxy cannot fail here: pytest's own
logging plugin holds the root logger at WARNING regardless of what `alembic.ini`
configures, so an assertion against `isEnabledFor` inside the suite passes whether or
not the feature exists (the F190 shape this change's own R4 review found).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest


class TestLogDatabaseBeforeOpeningUnit:
    def test_sqlite_url_logs_absolute_path_existence_and_pid(self, tmp_path, monkeypatch, caplog):
        from hub.config import settings
        from hub.main import _log_database_before_opening

        db_path = tmp_path / "sub" / "agentweave.db"
        assert not db_path.exists()
        monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
        monkeypatch.setattr(settings, "aw_port", 59321)

        with caplog.at_level(logging.WARNING, logger="hub.main"):
            _log_database_before_opening()

        records = [r for r in caplog.records if r.name == "hub.main"]
        assert len(records) == 1, records
        record = records[0]
        assert record.levelno >= logging.WARNING

        # Self-identifying against the raw message alone -- not `caplog.text`, which
        # interpolates a level/logger-name prefix this site does not carry (2.2/2.6).
        message = record.getMessage()
        assert "Hub database" in message
        assert str(db_path.resolve()) in message
        assert "existed before this process opened it: False" in message
        assert str(os.getpid()) in message
        assert "59321" not in message  # D6: no port

    def test_pre_existing_sqlite_file_logs_existed_true(self, tmp_path, monkeypatch, caplog):
        from hub.config import settings
        from hub.main import _log_database_before_opening

        db_path = tmp_path / "agentweave.db"
        db_path.write_bytes(b"")
        monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")

        with caplog.at_level(logging.WARNING, logger="hub.main"):
            _log_database_before_opening()

        message = caplog.records[-1].getMessage()
        assert "existed before this process opened it: True" in message

    def test_non_sqlite_url_strips_credentials(self, monkeypatch, caplog):
        from hub.config import settings
        from hub.main import _log_database_before_opening

        monkeypatch.setattr(
            settings, "database_url", "postgresql://opuser:hunter2@dbhost:5432/agentweave"
        )

        with caplog.at_level(logging.WARNING, logger="hub.main"):
            _log_database_before_opening()

        message = caplog.records[-1].getMessage()
        assert "hunter2" not in message
        assert "opuser" not in message
        assert "dbhost:5432/agentweave" in message


def _drain_stderr(proc: subprocess.Popen, buffer: list) -> None:
    """Runs on a daemon thread. `readline()` has no timeout, so the deadline lives in
    the polling loop that reads `buffer` from the main thread (2.7's implementation
    note) -- this thread just unblocks that loop from ever having to call `readline()`
    itself. It ends naturally once the child closes stderr (kill, in the caller's
    `finally`, or normal exit).
    """
    try:
        for line in proc.stderr:
            buffer.append(line)
    except ValueError:
        pass  # stream closed under us while reading


def _spawn_hub(*, cwd: Path, env: dict) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "hub.main:app", "--host", "127.0.0.1", "--port", "0"],
        cwd=str(cwd),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class TestGroup2LineOrderingRealProcess:
    def test_line_precedes_first_migration_and_names_the_child_pid(self, tmp_path):
        """R4's replacement for 2.7. R1's version asserted
        `logging.getLogger("hub.main").isEnabledFor(logging.INFO) is False` "under the
        alembic-configured root" -- but no such root exists inside pytest, so that
        assertion held whether or not the feature was built. This launches a real
        `uvicorn hub.main:app` subprocess and reads its actual stderr.

        Mutation-checked (recorded, not automated -- both revert cleanly by hand):
        - `hub/hub/main.py`'s `_log_database_before_opening`, `logger.warning` ->
          `logger.info`: this test fails (the line stops appearing on stderr, since
          pytest's root-level assertion above cannot be reused here -- this is a real
          process, and `logging.lastResort` is WARNING-only).
        - moving the `_log_database_before_opening()` call after `await init_db()` in
          `lifespan()`: this test fails (the ordering assertion below flips).
        """
        db_file = tmp_path / "x.db"
        assert not db_file.exists()
        env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_file.as_posix()}"}

        proc = _spawn_hub(cwd=tmp_path, env=env)
        lines: list = []
        reader = threading.Thread(target=_drain_stderr, args=(proc, lines), daemon=True)
        reader.start()

        deadline = time.monotonic() + 30
        try:
            while time.monotonic() < deadline:
                if any("Application startup complete" in ln for ln in lines):
                    break
                if proc.poll() is not None:
                    pytest.fail(
                        "uvicorn exited before reporting startup complete:\n" + "".join(lines)
                    )
                time.sleep(0.05)
            else:
                pytest.fail(
                    "uvicorn did not report startup complete within 30s:\n" + "".join(lines)
                )
        finally:
            proc.kill()
            proc.wait(timeout=10)

        group2_idx = next((i for i, ln in enumerate(lines) if "Hub database: opening" in ln), None)
        assert group2_idx is not None, "".join(lines)
        upgrade_idx = next((i for i, ln in enumerate(lines) if "Running upgrade" in ln), None)
        # A fresh database always emits the alembic chain; zero lines would make the
        # ordering assertion below prove nothing (R4's own note on this task).
        assert upgrade_idx is not None, "no 'Running upgrade' line seen:\n" + "".join(lines)
        assert group2_idx < upgrade_idx, "".join(lines)

        group2_line = lines[group2_idx]
        assert "existed before this process opened it: False" in group2_line
        # `proc.pid` is the listening PID only when `sys.executable` is a real
        # interpreter (not a venv launcher stub that spawns a further child) -- true
        # here, since this test process itself was started under `py -3.11`, so
        # `sys.executable` already names the resolved interpreter, not a launcher.
        assert str(proc.pid) in group2_line, group2_line


class TestRefusalIsAutomated:
    def test_missing_database_url_refuses_and_leaves_no_home_directory(self, tmp_path):
        """2.8 (R4): automates what 6.1's manual drive checked -- the one thing the
        change said no unit test could make. `Path.home()` reads `USERPROFILE` on
        Windows and `HOME` on POSIX, so pointing both at a throwaway directory makes
        the path the refusal declines a fake one; the operator's real home is never
        named.
        """
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        cwd = tmp_path / "cwd"
        cwd.mkdir()  # no .env reachable from here

        env = dict(os.environ)
        env.pop("DATABASE_URL", None)  # conftest.py exports :memory: into os.environ
        env["USERPROFILE"] = str(fake_home)
        env["HOME"] = str(fake_home)

        proc = _spawn_hub(cwd=cwd, env=env)
        try:
            _, stderr = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=10)
            pytest.fail("a broken refusal left the server running instead of exiting")

        assert proc.returncode != 0, stderr
        default_db_path = fake_home / ".agentweave" / "hub" / "data" / "agentweave.db"
        expected_default_url = f"sqlite+aiosqlite:///{default_db_path.as_posix()}"
        assert expected_default_url in stderr, stderr  # 1.4's fact 1: the declined path
        assert "DATABASE_URL" in stderr, stderr  # 1.4's fact 2
        assert "agentweave" in stderr, stderr  # 1.4's fact 3
        assert not (fake_home / ".agentweave").exists()
