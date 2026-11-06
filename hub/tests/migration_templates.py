"""Prepared databases for the migration tests.

Most migration tests start by migrating a file up to some revision, and many then downgrade it a long
way and climb back; each of those moves replays every revision in between. The result of a move is a
function of the starting file's bytes, the direction and the target revision, so the first request
for a given move runs the real migrations and every later request for the same move gets a copy of
the result. A test that seeds its own rows first starts from a file nobody else has, so it misses and
runs the real revisions; so does the first test to reach any move. Every revision's `upgrade` and
`downgrade` is therefore still executed, and a migration that raises leaves nothing behind.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import sqlite3
from pathlib import Path

from sqlalchemy.engine import make_url

from hub.config import settings


def _file_of(url: str) -> "Path | None":
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite") or not parsed.database:
        return None
    if parsed.database == ":memory:":
        return None
    return Path(parsed.database)


def _settle(target: Path) -> bool:
    """Fold a database's write-ahead log into its file, so the file alone is the whole database.

    The journal mode is a property of the file and a migrated database is in WAL, which leaves
    `-wal` and `-shm` beside it for as long as any connection has it open. Returns whether it
    stands alone now; a file that cannot be settled is simply not copied or served from a copy.
    """
    if target.exists():
        try:
            with contextlib.closing(sqlite3.connect(target, timeout=2)) as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            return False
    return not any(Path(str(target) + s).exists() for s in ("-wal", "-shm"))


def _revision_order(config) -> "list[str]":  # noqa: ANN001
    """The numbered revisions in chain order, read from the file names (the chain is linear)."""
    versions = Path(config.get_main_option("script_location")) / "versions"
    return sorted(m.group(1) for f in versions.glob("*.py") if (m := re.match(r"(\d{4})_", f.name)))


def _earlier_climb(config, directory, start, direction, revision):  # noqa: ANN001, ANN202
    """The longest prepared climb from an empty file that stops short of *revision*, if any.

    A climb to 0120 is the climb to 0059 followed by the revisions 0060..0120, so the second can start
    from a copy of the first and run only the revisions it has not already been through. Those still
    run for real, here, the first time anyone reaches them.
    """
    if direction != "up" or start:
        return None
    order = _revision_order(config)
    wanted = order[-1] if revision == "head" else revision
    if wanted not in order:
        return None
    best = None
    for candidate in directory.glob(f"{hashlib.sha256(b'').hexdigest()[:24]}-up-*.db"):
        reached = candidate.stem.rsplit("-", 1)[1]
        reached = order[-1] if reached == "head" else reached
        if reached in order and reached < wanted and (best is None or reached > best[0]):
            best = (reached, candidate)
    return best[1] if best else None


def _cached(real, directory: Path, direction: str):  # noqa: ANN001, ANN202
    """Wrap `alembic.command.upgrade` / `downgrade` so a given move of a given starting file runs once.

    The directory is shared by every worker and nobody waits on anybody: two workers that reach an
    unprepared move together both run it, and the second `os.replace` lands an identical file.

    The result is a function of the starting file's bytes, the direction and the target revision, so
    that triple names the prepared copy. A start nobody else has used (a test that seeds its own rows
    first) misses and runs the real migrations, then leaves its result for any identical start. A
    migration that raises leaves nothing behind, so a broken one fails in every test that reaches it.
    """

    def move(config, revision, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        target = _file_of(settings.database_url)
        if args or kwargs or not isinstance(revision, str) or target is None or not _settle(target):
            return real(config, revision, *args, **kwargs)
        start = target.read_bytes() if target.exists() else b""
        key = f"{hashlib.sha256(start).hexdigest()[:24]}-{direction}-{revision}"
        template = directory / f"{key}.db"
        if template.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(template, target)
            return None
        head_start = _earlier_climb(config, directory, start, direction, revision)
        if head_start is not None:
            shutil.copyfile(head_start, target)
        real(config, revision)
        if _settle(target):
            building = directory / f"{key}.{os.getpid()}.building"
            shutil.copyfile(target, building)
            try:
                os.replace(building, template)
            except PermissionError:
                # Windows refuses to replace a file another worker has open, which happens when
                # that worker landed the same template first and is copying it out. Its copy is
                # this one's identical twin, so it counts as landed; anything else is a real fault.
                building.unlink(missing_ok=True)
                if not template.exists():
                    raise
        return None

    return move


def caching_upgrade(real_upgrade, directory: Path):  # noqa: ANN001, ANN201
    return _cached(real_upgrade, directory, "up")


def caching_downgrade(real_downgrade, directory: Path):  # noqa: ANN001, ANN201
    return _cached(real_downgrade, directory, "down")


def remembering_revision_files(real_load):  # noqa: ANN001, ANN201
    """Wrap `alembic.util.load_python_file` so each revision file is executed once per process.

    Every alembic command builds a fresh `ScriptDirectory`, which executes all of the revision files
    again (well over a hundred of them) before it does anything to the database; that was most of a
    command's time. A revision file only defines its identifiers and its `upgrade`/`downgrade`
    functions, so the module can be shared between commands. `env.py` is not one of them: it reads
    the invocation's own configuration when it runs, so it is executed afresh every time.
    """
    loaded: dict[tuple[str, str], object] = {}

    def load_python_file(dir_, filename):  # noqa: ANN001, ANN202
        if filename == "env.py":
            return real_load(dir_, filename)
        key = (str(dir_), str(filename))
        if key not in loaded:
            loaded[key] = real_load(dir_, filename)
        return loaded[key]

    return load_python_file


def without_fsync(real_apply):  # noqa: ANN001, ANN201
    """Wrap `sqlite_pragmas.apply_pragmas` so a migration test's connections do not wait on the disk.

    The Hub asks for `synchronous=FULL` so an acknowledged commit survives power loss, which costs an
    fsync per commit; a migration commits per revision and per batch step, and a test database is
    deleted when the test ends. The journal mode is still asked for and still returned.
    """

    def apply_pragmas(dbapi_connection):  # noqa: ANN001, ANN202
        mode = real_apply(dbapi_connection)
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA synchronous=OFF")
        finally:
            cursor.close()
        return mode

    return apply_pragmas


def copying_create_all(real_create_all, directory: Path):  # noqa: ANN001, ANN201
    """Wrap a test module's `_create_all_at(db_url)` so the models' schema is built once per *directory*.

    `Base.metadata.create_all` on a fresh file is the same file every time (the key below includes
    the models' table names, so a change to them cannot be served from an older copy).
    """
    from hub.db.models import Base

    template = (
        directory
        / f"create-all-{hashlib.sha256(','.join(sorted(Base.metadata.tables)).encode()).hexdigest()[:12]}.db"
    )

    async def create_all_at(db_url: str) -> None:
        target = _file_of(db_url)
        if target is None or (target.exists() and target.stat().st_size):
            return await real_create_all(db_url)
        if not template.exists():
            building = directory / f"create-all.{os.getpid()}.building"
            await real_create_all(f"sqlite+aiosqlite:///{building.as_posix()}")
            os.replace(building, template)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template, target)

    return create_all_at
