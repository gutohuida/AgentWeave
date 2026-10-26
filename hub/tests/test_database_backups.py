"""Every backup of a running Hub's database is consistent under WAL (`backups-consistent`, D3).

Under WAL the newest commits may live in `agentweave.db-wal` until a checkpoint, so a copy of the
`.db` file alone silently omits them. The methods this repository prescribes -- SQLite's backup API
from a read-only connection (the restart runbook, `scripts/drive/terra_replica.py`,
`scripts/drive/perf_database.py`) and `VACUUM INTO` -- read through the WAL. These tests take each
while the Hub's own engine is committing, and guard that no file copy of a database comes back into
`hub/hub`, `src/` or `scripts/`.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from hub.db import sqlite_pragmas

REPO = Path(__file__).resolve().parents[2]


def _writer(path: Path, stop: threading.Event, committed: list) -> None:
    """Commit continuously through an engine opened the way the Hub opens its database."""
    eng = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"timeout": 30})
    sqlite_pragmas.install(eng)
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE marks (n INTEGER PRIMARY KEY, pad TEXT)"))
    n = 0
    try:
        while not stop.is_set():
            n += 1
            with eng.begin() as conn:
                conn.execute(text("INSERT INTO marks VALUES (:n, :p)"), {"n": n, "p": "y" * 2000})
            committed.append(n)
            time.sleep(0.001)
    finally:
        eng.dispose()


def _backup_api(source: Path, target: Path) -> None:
    src = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    src.backup(dst)
    src.close()
    dst.close()


def _vacuum_into(source: Path, target: Path) -> None:
    src = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    src.execute("VACUUM INTO ?", (str(target),))
    src.close()


def _file_copy(source: Path, target: Path) -> None:
    target.write_bytes(source.read_bytes())


def _take_mid_write(tmp_path: Path, take) -> tuple:  # noqa: ANN001
    live = tmp_path / "live.db"
    stop, committed = threading.Event(), []
    thread = threading.Thread(target=_writer, args=(live, stop, committed))
    thread.start()
    try:
        deadline = time.time() + 30
        while len(committed) < 200 and time.time() < deadline:
            time.sleep(0.01)
        assert committed, "the writer never committed"
        before = committed[-1]
        target = tmp_path / "backup.db"
        take(live, target)
    finally:
        stop.set()
        thread.join(timeout=60)
    c = sqlite3.connect(live)
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    c.close()
    restored = sqlite3.connect(target)
    try:
        integrity = restored.execute("PRAGMA integrity_check").fetchone()[0]
        try:
            present = restored.execute(
                "SELECT count(*) FROM marks WHERE n <= ?", (before,)
            ).fetchone()[0]
        except sqlite3.OperationalError:
            present = 0
    finally:
        restored.close()
    return integrity, present, before


@pytest.mark.parametrize("take", [_backup_api, _vacuum_into], ids=["backup-api", "vacuum-into"])
def test_a_backup_taken_mid_write_restores_every_committed_row(
    tmp_path, take
) -> None:  # noqa: ANN001
    integrity, present, before = _take_mid_write(tmp_path, take)
    assert integrity == "ok"
    assert present == before


def test_a_file_copy_of_a_wal_database_omits_committed_rows(tmp_path) -> None:
    """Why D3 exists: the commits not yet checkpointed are not in the `.db` file."""
    integrity, present, before = _take_mid_write(tmp_path, _file_copy)
    assert present < before


_FILE_COPY = re.compile(
    r"(shutil\.copy\w*\(|copyfile\(|Copy-Item\s|^\s*cp\s+[^=\s]|robocopy\s|read_bytes\(\))"
    r"[^\n]*(\.db\b|agentweave\.db|\bDB\b|_db\b)",
    re.IGNORECASE,
)


def test_no_file_copy_of_a_database_in_the_product_cli_or_scripts() -> None:
    hits = []
    for top in ("hub/hub", "src", "scripts"):
        for path in (REPO / top).rglob("*"):
            if path.suffix not in (".py", ".ps1", ".sh", ".cs") or not path.is_file():
                continue
            if "static" in path.parts:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for number, line in enumerate(lines, 1):
                if _FILE_COPY.search(line):
                    hits.append(f"{path.relative_to(REPO).as_posix()}:{number}: {line.strip()}")
    assert (
        not hits
    ), "a file copy of a database misses WAL commits; use sqlite backup:\n" + "\n".join(hits)


def test_the_guard_recognises_a_file_copy() -> None:
    assert _FILE_COPY.search('shutil.copy2(DB, "backup-before-0140/agentweave.db")')
    assert _FILE_COPY.search("Copy-Item $env:USERPROFILE\\.agentweave\\hub\\data\\agentweave.db x")
    assert not _FILE_COPY.search("cp = await add_checkpoint(db, conv, title)")
    assert not _FILE_COPY.search("shutil.copytree(src, root / 'spec')")
