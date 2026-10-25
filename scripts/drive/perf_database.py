"""Acceptance drive for `the-database-stays-fast-as-history-grows` (performance overhaul, slice 2).

Tier 2. Written, run and failing before the build. Every check runs against a scratch database or a
copy, never the operator's database and never `:8000` or `:8010`:

  wal-on              the Hub's engine opens every pooled connection in WAL, synchronous=FULL, with a
                      positive journal_size_limit -- on a scratch file, and on a rollback-journal copy
  wal-fallback        an engine whose WAL request is refused still serves, and the startup line names
                      the journal mode it runs in
  reads-under-writes  one writer commits output rows flat out while four readers replay the /agents
                      route's own statements for 30s, through the Hub's engine: read p90 < 500ms
  durable             a task answered 201 survives the Hub process being killed and restarted
  backups-consistent  each backup path in hub/, src/ and scripts/ (none may be a file copy) taken while
                      a writer commits passes integrity_check and holds every row committed before it
  trace-retention     the Hub's sweep removes every span older than the project's window and keeps
                      every newer one; changing the window in the trace settings moves the next sweep
  retention-no-stall  the first sweep over a copy whose spans are all expired never makes a GET /agents
                      slower than its idle time plus 100ms
  stats-current       the Hub's statistics refresh leaves sqlite_stat1 rows for agent_outputs and
                      event_logs -- on a copy, and on a running Hub's first maintenance pass
  hot-read-indexes    the newest-context-reading query uses an index on event_logs led by (project,
                      event type, agent), and no agent_outputs index is a leading prefix of another

A Hub on a copy of real data runs with its lifespan OFF (the copy's queued input would spawn a real
agent run); only scratch databases with no projects of their own get a lifespan.

    py -3.11 scripts/drive/perf_database.py [--source C:/Users/huida/aw-perf/real-D.db] [--only a,b]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import pathlib
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
HUB_DIR = REPO / "hub"
OPERATOR_DB = (pathlib.Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db").resolve()
DEFAULT_SOURCE = pathlib.Path(r"C:\Users\huida\aw-perf\real-D.db")
PROJECT = "proj-d85a82bf4216"
READ_P90_BOUND_MS = 500.0
STALL_SLACK_MS = 100.0
results: list[tuple[str, str, bool, str]] = []


def check(requirement: str, name: str, ok: bool, detail: str = "") -> bool:
    results.append((requirement, name, bool(ok), detail))
    print(
        f"{'PASS' if ok else 'FAIL'} [{requirement}] {name}" + (f" -- {detail}" if detail else "")
    )
    sys.stdout.flush()
    return bool(ok)


def refuse_operator_db(path: pathlib.Path) -> None:
    if pathlib.Path(path).resolve() == OPERATOR_DB:
        sys.exit(f"refusing to touch the operator's database {OPERATOR_DB}")


def url_for(path: pathlib.Path) -> str:
    return f"sqlite+aiosqlite:///{pathlib.Path(path).as_posix()}"


def copy_of(source: pathlib.Path, target: pathlib.Path) -> pathlib.Path:
    """A consistent copy: the SQLite backup API from a read-only connection (never a file copy)."""
    refuse_operator_db(target)
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = pathlib.Path(str(target) + suffix)
        if p.exists():
            p.unlink()
    src = sqlite3.connect(pathlib.Path(source).resolve().as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    src.backup(dst)
    src.close()
    # The copy is the operator's file as it is: their journal mode, not whatever the backup set.
    dst.execute("PRAGMA journal_mode=DELETE")
    dst.close()
    return target


def child(mode: str, db: pathlib.Path, *extra: str, timeout: float = 600) -> dict:
    """Run one check in a fresh interpreter whose Hub settings name *db*."""
    refuse_operator_db(db)
    env = dict(os.environ)
    env["DATABASE_URL"] = url_for(db)
    env["PYTHONPATH"] = str(HUB_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(pathlib.Path(__file__).resolve()), "--child", mode, str(db), *extra],
        cwd=str(HUB_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT ") :])
    return {"error": f"child {mode} exited {proc.returncode}", "tail": (proc.stderr or "")[-1500:]}


def emit(payload: dict) -> None:
    print("RESULT " + json.dumps(payload, default=str), flush=True)


# ---------------------------------------------------------------------------------------------
# Children: each runs inside one interpreter whose DATABASE_URL names its database.


def _drive_key(db: str) -> str:
    """A credential of the drive's own, written into the copy, so no real key is read or used."""
    key = "aw_live_" + secrets.token_hex(16)
    c = sqlite3.connect(db, timeout=30)
    c.execute(
        "INSERT INTO operator_credentials (id, label, revoked, created_at) VALUES (?, ?, 0, ?)",
        (key, "perf-database-drive", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")),
    )
    c.commit()
    c.close()
    return key


async def _child_pragmas(db: str) -> dict:
    from sqlalchemy import text

    from hub.db.engine import engine

    readings = []
    conns = [await engine.connect() for _ in range(4)]
    try:
        for conn in conns:
            row = {}
            for pragma in ("journal_mode", "synchronous", "journal_size_limit", "busy_timeout"):
                row[pragma] = (await conn.execute(text(f"PRAGMA {pragma}"))).scalar()
            readings.append(row)
    finally:
        for conn in conns:
            await conn.close()
        await engine.dispose()
    return {"connections": readings}


async def _child_fallback(db: str) -> dict:
    """An engine whose connect-time WAL request is refused: every connection opens with `nolock=1`,
    for which SQLite answers `PRAGMA journal_mode=WAL` with the journal it keeps (measured: delete).
    The listener is on the Engine class, so the migration engine is refused too."""
    import logging

    import httpx
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "do_connect")
    def _refuse_wal(dialect, record, cargs, cparams):  # noqa: ANN001
        cargs[0] = pathlib.Path(cargs[0]).resolve().as_uri() + "?nolock=1"
        cparams["uri"] = True

    lines: list[str] = []

    class Grab(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(record.getMessage())

    grab = Grab(level=logging.WARNING)
    logging.getLogger("hub").addHandler(grab)

    from hub.main import create_app, lifespan

    app = create_app()
    status = None
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://drive") as client:
            status = (await client.get("/health")).status_code
    journal_lines = [line for line in lines if "journal" in line.lower()]
    return {"health": status, "journal_lines": journal_lines, "lines": lines[-12:]}


async def _capture_agents_statements(client, project: str) -> list:  # noqa: ANN001
    from sqlalchemy import event

    from hub.db.engine import engine

    captured: list = []

    def grab(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if statement.lstrip().upper().startswith("SELECT"):
            captured.append((statement, tuple(parameters or ())))

    await client.get(f"/api/v1/projects/{project}/agents")
    event.listen(engine.sync_engine, "before_cursor_execute", grab)
    response = await client.get(f"/api/v1/projects/{project}/agents")
    event.remove(engine.sync_engine, "before_cursor_execute", grab)
    assert response.status_code == 200, (response.status_code, response.text[:300])
    return captured


def _pct(values: list, q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


async def _child_reads(db: str, seconds: str) -> dict:
    import httpx
    from sqlalchemy import text

    from hub.db.engine import async_session_factory, engine
    from hub.main import create_app

    await _migrate()
    key = _drive_key(db)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://drive",
        headers={"Authorization": f"Bearer {key}"},
        timeout=120,
    ) as client:
        statements = await _capture_agents_statements(client, PROJECT)
    duration = float(seconds)
    stop = asyncio.Event()
    commits: list = []
    reads: list = []
    errors: list = []
    content = "x" * 1400

    async def writer() -> None:
        sequence = 0
        while not stop.is_set():
            sequence += 1
            started = time.perf_counter()
            try:
                async with async_session_factory() as session:
                    await session.execute(
                        text(
                            "INSERT INTO agent_outputs (id, project_id, agent, session_id, "
                            "conversation_id, content, kind, payload, run_id, sequence, timestamp) "
                            "VALUES (:id, :p, 'Architect', 'sess-drive', 'conv-drive', :c, 'text', "
                            "'{}', 'run-drive', :s, :t)"
                        ),
                        {
                            "id": "out-" + uuid.uuid4().hex[:12],
                            "p": PROJECT,
                            "c": content,
                            "s": sequence,
                            "t": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
                        },
                    )
                    await session.commit()
                commits.append(time.perf_counter() - started)
            except Exception as exc:  # noqa: BLE001 -- counted and reported
                errors.append(f"write: {exc}"[:160])
            await asyncio.sleep(0)

    async def reader() -> None:
        while not stop.is_set():
            started = time.perf_counter()
            try:
                async with engine.connect() as conn:
                    for statement, params in statements:
                        (await conn.exec_driver_sql(statement, params)).fetchall()
                reads.append(time.perf_counter() - started)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"read: {exc}"[:160])
            await asyncio.sleep(0.05)

    tasks = [asyncio.create_task(writer())] + [asyncio.create_task(reader()) for _ in range(4)]
    await asyncio.sleep(duration)
    stop.set()
    await asyncio.gather(*tasks)
    async with engine.connect() as conn:
        mode = (await conn.exec_driver_sql("PRAGMA journal_mode")).scalar()
    await engine.dispose()
    ms = [r * 1000 for r in reads]
    cs = [c * 1000 for c in commits]
    return {
        "journal_mode": mode,
        "statements": len(statements),
        "reads": len(ms),
        "read_p50_ms": round(_pct(ms, 0.5), 1),
        "read_p90_ms": round(_pct(ms, 0.9), 1),
        "read_max_ms": round(max(ms), 1) if ms else None,
        "commits": len(cs),
        "commit_p50_ms": round(_pct(cs, 0.5), 2),
        "commit_p99_ms": round(_pct(cs, 0.99), 2),
        "errors": errors[:5],
        "error_count": len(errors),
    }


async def _child_backups(db: str, scratch: str) -> dict:
    """A writer commits through the Hub's engine; every backup path is taken mid-write."""
    from sqlalchemy import text

    from hub.db.engine import async_session_factory, engine, init_db

    await init_db()
    async with engine.connect() as conn:
        mode = (await conn.exec_driver_sql("PRAGMA journal_mode")).scalar()
    async with async_session_factory() as session:
        await session.execute(
            text("CREATE TABLE IF NOT EXISTS drive_marks (n INTEGER PRIMARY KEY, pad TEXT)")
        )
        await session.commit()
    committed = {"n": 0}
    stop = threading.Event()

    async def writer() -> None:
        n = 0
        while not stop.is_set():
            n += 1
            async with async_session_factory() as session:
                await session.execute(
                    text("INSERT INTO drive_marks (n, pad) VALUES (:n, :p)"),
                    {"n": n, "p": "y" * 2000},
                )
                await session.commit()
            committed["n"] = n
            await asyncio.sleep(0.002)

    sys.path.insert(0, str(REPO / "scripts" / "drive"))
    out_dir = pathlib.Path(scratch)

    def backup_api_ro(target: pathlib.Path) -> None:
        # The runbook's and the drive scripts' method: sqlite backup from a read-only connection.
        src = sqlite3.connect(pathlib.Path(db).resolve().as_uri() + "?mode=ro", uri=True)
        dst = sqlite3.connect(target)
        src.backup(dst)
        src.close()
        dst.close()

    def vacuum_into(target: pathlib.Path) -> None:
        src = sqlite3.connect(pathlib.Path(db).resolve().as_uri() + "?mode=ro", uri=True)
        src.execute("VACUUM INTO ?", (str(target),))
        src.close()

    def terra_replica_copy(target: pathlib.Path) -> None:
        import terra_replica  # scripts/drive/terra_replica.py

        terra_replica.SOURCE_DB = pathlib.Path(db)
        terra_replica.PROFILE = target.parent / "terra-profile"
        terra_replica.DB = terra_replica.PROFILE / "agentweave.db"
        terra_replica.copy_database().close()
        os.replace(terra_replica.DB, target)

    def raw_file_copy(target: pathlib.Path) -> None:
        # Control, not a product path: what a file copy of the .db alone takes under this journal.
        target.write_bytes(pathlib.Path(db).read_bytes())

    paths = {
        "sqlite-backup-api (runbook, drive scripts)": backup_api_ro,
        "VACUUM INTO": vacuum_into,
        "scripts/drive/terra_replica.py copy_database": terra_replica_copy,
        "CONTROL raw .db file copy": raw_file_copy,
    }
    task = asyncio.create_task(writer())
    await asyncio.sleep(1.0)
    outcomes = {}
    for index, (name, take) in enumerate(paths.items()):
        target = out_dir / f"backup-{index}.db"
        for suffix in ("", "-wal", "-shm"):
            p = pathlib.Path(str(target) + suffix)
            if p.exists():
                p.unlink()
        before = committed["n"]
        try:
            await asyncio.to_thread(take, target)
            c = sqlite3.connect(target)
            integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
            try:
                present = c.execute(
                    "SELECT count(*) FROM drive_marks WHERE n <= ?", (before,)
                ).fetchone()[0]
            except sqlite3.Error as exc:
                present = f"error: {exc}"
            c.close()
            outcomes[name] = {
                "integrity": integrity,
                "committed_before": before,
                "present": present,
            }
        except Exception as exc:  # noqa: BLE001
            outcomes[name] = {"error": str(exc)[:300]}
        await asyncio.sleep(0.5)
    stop.set()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await engine.dispose()
    return {"journal_mode": mode, "paths": outcomes}


def _stored(at: datetime) -> str:
    """A datetime as `UTCDateTime` stores it: naive UTC text, comparable as a string."""
    if at.tzinfo is not None:
        at = at.astimezone(timezone.utc).replace(tzinfo=None)
    return at.strftime("%Y-%m-%d %H:%M:%S.%f")


async def _migrate() -> None:
    """Bring the copy to this tree's head, as the Hub's restart would (lifespan stays off)."""
    from hub.db.engine import _run_alembic_upgrade

    await _run_alembic_upgrade()


async def _child_retention(db: str) -> dict:
    import httpx

    await _migrate()
    key = _drive_key(db)
    from hub.main import create_app

    app = create_app()
    out: dict = {}

    def spans() -> dict:
        c = sqlite3.connect(f"file:{pathlib.Path(db).as_posix()}?mode=ro", uri=True)
        rows = c.execute("SELECT span_id, project_id, start_time FROM trace_spans").fetchall()
        c.close()
        return {r[0]: (r[1], r[2]) for r in rows}

    def verdict(before: dict, after: dict, cutoffs: dict) -> dict:
        wrong_kept, wrong_gone = 0, 0
        for span_id, (project, start) in before.items():
            cutoff = cutoffs.get(project)
            expired = cutoff is not None and start < cutoff
            if expired and span_id in after:
                wrong_kept += 1
            if not expired and span_id not in after:
                wrong_gone += 1
        return {
            "before": len(before),
            "after": len(after),
            "older_remaining": wrong_kept,
            "newer_removed": wrong_gone,
        }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://drive",
        headers={"Authorization": f"Bearer {key}"},
    ) as client:
        base = f"/api/v1/projects/{PROJECT}/traces/settings"
        for days, label in ((2, "first"), (1, "changed")):
            response = await client.put(base, json={"retention_days": days})
            got = (await client.get(base)).json()
            out[f"{label}_put"] = response.status_code
            out[f"{label}_setting"] = got.get("retention_days")
            if response.status_code != 200:
                out[f"{label}_body"] = response.text[:300]
                return out
            try:
                from hub import trace_retention
            except ImportError as exc:
                out["sweep"] = f"no sweep: {exc}"
                return out
            before = spans()
            report = await trace_retention.sweep()
            cutoffs = {project: _stored(entry["cutoff"]) for project, entry in report.items()}
            out[label] = {"window_days": days, **verdict(before, spans(), cutoffs)}
            out[label]["cutoff"] = cutoffs.get(PROJECT)
    return out


async def _child_stall(db: str) -> dict:
    import httpx

    await _migrate()
    c = sqlite3.connect(db, timeout=30)
    c.execute(
        "UPDATE trace_spans SET start_time = datetime(start_time, '-60 days'), "
        "trace_started_at = datetime(trace_started_at, '-60 days'), "
        "end_time = CASE WHEN end_time IS NULL THEN NULL ELSE datetime(end_time, '-60 days') END"
    )
    c.commit()
    total = c.execute("SELECT count(*) FROM trace_spans").fetchone()[0]
    c.close()
    key = _drive_key(db)
    from hub.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    out: dict = {"spans_expired": total}
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://drive",
        headers={"Authorization": f"Bearer {key}"},
        timeout=120,
    ) as client:
        url = f"/api/v1/projects/{PROJECT}/agents"

        async def timed() -> float:
            started = time.perf_counter()
            r = await client.get(url)
            assert r.status_code == 200, r.status_code
            return (time.perf_counter() - started) * 1000

        await timed()
        idle = []
        for _ in range(20):
            idle.append(await timed())
            await asyncio.sleep(0.1)
        out["idle_max_ms"] = round(max(idle), 1)
        out["idle_p50_ms"] = round(_pct(idle, 0.5), 1)
        try:
            from hub import trace_retention
        except ImportError as exc:
            out["sweep"] = f"no sweep: {exc}"
            return out
        started = time.perf_counter()
        sweeping = asyncio.create_task(trace_retention.sweep())
        during = []
        while not sweeping.done():
            during.append(await timed())
            await asyncio.sleep(0.1)
        report = sweeping.result()
        out["sweep_seconds"] = round(time.perf_counter() - started, 2)
        out["deleted"] = sum(entry["deleted"] for entry in report.values())
        out["gets_during_sweep"] = len(during)
        out["during_max_ms"] = round(max(during), 1) if during else None
    c = sqlite3.connect(f"file:{pathlib.Path(db).as_posix()}?mode=ro", uri=True)
    out["spans_left"] = c.execute("SELECT count(*) FROM trace_spans").fetchone()[0]
    c.close()
    return out


async def _child_stats(db: str) -> dict:
    def stat_tables() -> list:
        c = sqlite3.connect(f"file:{pathlib.Path(db).as_posix()}?mode=ro", uri=True)
        try:
            return sorted({r[0] for r in c.execute("SELECT tbl FROM sqlite_stat1")})
        except sqlite3.Error:
            return []
        finally:
            c.close()

    await _migrate()
    out = {"before": stat_tables()}
    try:
        from hub import db_maintenance
    except ImportError as exc:
        out["refresh"] = f"no statistics refresh: {exc}"
        return out
    started = time.perf_counter()
    await db_maintenance.refresh_statistics()
    out["refresh_seconds"] = round(time.perf_counter() - started, 3)
    out["after"] = stat_tables()
    return out


async def _child_indexes(db: str, how: str) -> dict:
    from sqlalchemy import select

    from hub.db.engine import engine, init_db
    from hub.db.models import EventLog

    if how == "fresh":
        await init_db()
    else:
        from hub.db.engine import _run_alembic_upgrade

        await _run_alembic_upgrade()
    await engine.dispose()
    statement = (
        select(EventLog)
        .where(
            EventLog.project_id == PROJECT,
            EventLog.event_type == "context_warning",
            EventLog.agent == "Architect",
        )
        .order_by(EventLog.timestamp.desc())
        .limit(1)
    )
    compiled = statement.compile(engine.sync_engine, compile_kwargs={"literal_binds": True})
    c = sqlite3.connect(f"file:{pathlib.Path(db).as_posix()}?mode=ro", uri=True)
    version = c.execute("SELECT version_num FROM alembic_version").fetchone()
    plan = [r[3] for r in c.execute("EXPLAIN QUERY PLAN " + str(compiled))]
    used = None
    for line in plan:
        m = re.search(r"USING (?:COVERING )?INDEX (\w+)", line)
        if m:
            used = m.group(1)
    used_columns = [r[2] for r in c.execute(f"PRAGMA index_info({used})")] if used else []
    used_sql = (
        c.execute("SELECT sql FROM sqlite_master WHERE name = ?", (used,)).fetchone()[0]
        if used
        else ""
    )
    # Covers project, event type and agent: as three leading columns, or as (project, agent, ...)
    # in a partial index restricted to `context_warning` rows (`0144`, slice 1's).
    covers = used_columns[:3] == ["project_id", "event_type", "agent"] or (
        used_columns[:2] == ["project_id", "agent"] and "event_type = 'context_warning'" in used_sql
    )
    outputs = {}
    for _, name, *_rest in c.execute("PRAGMA index_list(agent_outputs)"):
        outputs[name] = [r[2] for r in c.execute(f"PRAGMA index_info({name})")]
    c.close()
    prefixes = [
        f"{a}{outputs[a]} prefixes {b}{outputs[b]}"
        for a in outputs
        for b in outputs
        if a != b and outputs[a] and outputs[b][: len(outputs[a])] == outputs[a]
    ]
    return {
        "version": version[0] if version else None,
        "plan": plan,
        "index": used,
        "index_columns": used_columns,
        "index_sql": used_sql,
        "covers": covers,
        "agent_outputs_indexes": outputs,
        "prefix_pairs": prefixes,
    }


CHILDREN = {
    "pragmas": _child_pragmas,
    "fallback": _child_fallback,
    "reads": _child_reads,
    "backups": _child_backups,
    "retention": _child_retention,
    "stall": _child_stall,
    "stats": _child_stats,
    "indexes": _child_indexes,
}


def run_child(argv: list) -> None:
    mode, db, *extra = argv
    refuse_operator_db(pathlib.Path(db))
    try:
        emit(asyncio.run(CHILDREN[mode](db, *extra)))
    except Exception as exc:  # noqa: BLE001 -- the parent reports it as the check's failure
        import traceback

        traceback.print_exc()
        emit({"error": f"{type(exc).__name__}: {exc}"[:600]})


# ---------------------------------------------------------------------------------------------
# A real Hub process on a scratch database (no projects of its own: safe to run its lifespan).


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Hub:
    def __init__(self, db: pathlib.Path, log: pathlib.Path):
        refuse_operator_db(db)
        self.db, self.log = db, log
        self.key = "aw_live_" + secrets.token_hex(16)
        self.port = free_port()
        assert self.port not in (8000, 8010)
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        env = dict(os.environ)
        env["DATABASE_URL"] = url_for(self.db)
        env["AW_BOOTSTRAP_API_KEY"] = self.key
        log = open(self.log, "a", encoding="utf-8")  # noqa: SIM115 -- the child's output
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "hub.main:app",
                "--port",
                str(self.port),
                "--host",
                "127.0.0.1",
            ],
            cwd=str(HUB_DIR),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        end = time.time() + 120
        while time.time() < end:
            if self.proc.poll() is not None:
                raise RuntimeError(f"hub exited; see {self.log}")
            try:
                if self.api("GET", "/projects")[0] == 200:
                    return
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)
        raise RuntimeError(f"hub did not come up; see {self.log}")

    def kill(self) -> None:
        if self.proc is not None:
            subprocess.run(
                ["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True
            )
            self.proc.wait(timeout=30)
            self.proc = None

    def api(self, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/v1{path}",
            data,
            {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()[:1000]


def stat_tables(db: pathlib.Path) -> list:
    c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return sorted({r[0] for r in c.execute("SELECT tbl FROM sqlite_stat1")})
    except sqlite3.Error:
        return []
    finally:
        c.close()


def drive_durable_and_lifespan_stats(scratch: pathlib.Path) -> None:
    db = scratch / "durable.db"
    hub = Hub(db, scratch / "durable-hub.log")
    root = scratch / "durable-project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    hub.start()
    try:
        code, project = hub.api("POST", "/projects/open", {"path": str(root), "name": "perfdb"})
        assert code in (200, 201), (code, project)
        pid = project["id"]  # type: ignore[index]
        code, task = hub.api("POST", f"/projects/{pid}/tasks", {"title": "survives a kill"})
        answered = code
        task_id = task.get("id") if isinstance(task, dict) else None
        hub.kill()  # no shutdown: the process is terminated
        # Rows the statistics refresh has something to measure; the Hub is down while they land.
        c = sqlite3.connect(db, timeout=30)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        for i in range(200):
            c.execute(
                "INSERT INTO agent_outputs (id, project_id, agent, content, kind, sequence, timestamp) "
                "VALUES (?, ?, 'drive', 'x', 'text', ?, ?)",
                (f"out-drive{i:06d}", pid, i, now),
            )
            c.execute(
                "INSERT INTO event_logs (id, project_id, event_type, agent, data, severity, timestamp) "
                "VALUES (?, ?, 'context_warning', 'drive', '{}', 'info', ?)",
                (f"evt-drive{i:06d}", pid, now),
            )
        c.commit()
        c.close()
        hub.start()
        code, got = hub.api("GET", f"/projects/{pid}/tasks/{task_id}")
        check(
            "durable",
            "a task answered 201 is present after kill -9 and restart",
            answered == 201 and code == 200,
            f"create {answered}, read after restart {code}",
        )
        # The running Hub's first maintenance pass refreshes the statistics.
        end = time.time() + 150
        tables: list = []
        while time.time() < end:
            tables = stat_tables(db)
            if {"agent_outputs", "event_logs"} <= set(tables):
                break
            time.sleep(2)
        check(
            "stats-current",
            "a running Hub's first maintenance pass writes sqlite_stat1",
            {"agent_outputs", "event_logs"} <= set(tables),
            f"sqlite_stat1 tables: {tables}",
        )
    finally:
        hub.kill()
    text = (scratch / "durable-hub.log").read_text(encoding="utf-8", errors="replace")
    lines = [line for line in text.splitlines() if "journal" in line.lower()]
    check(
        "wal-on",
        "the startup line names WAL on a local scratch database",
        any("wal" in line.lower() for line in lines),
        lines[-1] if lines else "no journal line",
    )


def backup_inventory() -> list:
    """File copies of a database anywhere in hub/, src/ or scripts/ (D3: none may remain)."""
    pattern = re.compile(
        r"(shutil\.copy\w*\(|copyfile\(|Copy-Item\s|^\s*cp\s+[^=\s]|robocopy\s|read_bytes\(\))"
        r"[^\n]*(\.db\b|agentweave\.db|\bDB\b|_db\b)",
        re.IGNORECASE,
    )
    hits = []
    for top in ("hub/hub", "src", "scripts"):
        for path in (REPO / top).rglob("*"):
            if path.suffix not in (".py", ".ps1", ".sh", ".md", ".cs") or not path.is_file():
                continue
            if path.name == "perf_database.py" or "static" in path.parts:
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if pattern.search(line):
                    hits.append(
                        f"{path.relative_to(REPO).as_posix()}:{number}: {line.strip()[:120]}"
                    )
    return hits


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--only", default="")
    parser.add_argument("--seconds", default="30")
    args = parser.parse_args()
    source = pathlib.Path(args.source)
    refuse_operator_db(source)
    only = set(filter(None, args.only.split(",")))
    want = lambda name: not only or name in only  # noqa: E731
    scratch = (
        pathlib.Path(tempfile.gettempdir()) / "aw-perf-database" / time.strftime("%Y%m%d-%H%M%S")
    )
    scratch.mkdir(parents=True)
    print(f"scratch: {scratch}\nsource copy of: {source}\n")
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True
    )
    print(f"tree: {commit.stdout.strip()}\n")

    if want("wal"):
        r = child("pragmas", scratch / "pragmas.db")
        conns = r.get("connections", [])
        check(
            "wal-on",
            "4 pooled connections on a scratch file run WAL, synchronous=FULL, a WAL bound",
            bool(conns)
            and all(
                c["journal_mode"] == "wal"
                and c["synchronous"] == 2
                and (c["journal_size_limit"] or 0) > 0
                for c in conns
            ),
            json.dumps(conns or r),
        )
        existing = copy_of(source, scratch / "existing.db")
        r = child("pragmas", existing)
        c = sqlite3.connect(f"file:{existing.as_posix()}?mode=ro", uri=True)
        after = c.execute("PRAGMA journal_mode").fetchone()[0]
        c.close()
        check(
            "wal-on",
            "a rollback-journal copy runs WAL once the Hub has opened it",
            after == "wal",
            f"journal_mode afterwards: {after}",
        )
        r = child("fallback", scratch / "fallback.db")
        lines = r.get("journal_lines") or []
        check(
            "wal-fallback",
            "a Hub whose WAL request is refused serves, and names its journal mode",
            r.get("health") == 200 and any("delete" in line.lower() for line in lines),
            f"health {r.get('health')}, journal lines {lines or r}",
        )

    if want("reads"):
        db = copy_of(source, scratch / "reads.db")
        r = child("reads", db, args.seconds)
        check(
            "reads-under-writes",
            f"1 writer flat out + 4 readers of /agents for {args.seconds}s: read p90 < {READ_P90_BOUND_MS:.0f}ms",
            (r.get("read_p90_ms") or 1e9) < READ_P90_BOUND_MS and not r.get("error_count"),
            json.dumps(r),
        )

    if want("durable"):
        try:
            drive_durable_and_lifespan_stats(scratch)
        except Exception as exc:  # noqa: BLE001
            check("durable", "kill-and-restart drive ran", False, str(exc)[:400])

    if want("backups"):
        hits = backup_inventory()
        check(
            "backups-consistent",
            "no file copy of a database in hub/, src/ or scripts/",
            not hits,
            "; ".join(hits) or "none found",
        )
        r = child("backups", scratch / "backups.db", str(scratch))
        mode = r.get("journal_mode")
        for name, outcome in (r.get("paths") or {}).items():
            ok = outcome.get("integrity") == "ok" and outcome.get("present") == outcome.get(
                "committed_before"
            )
            if name.startswith("CONTROL"):
                print(f"INFO [backups-consistent] {name} under {mode}: {json.dumps(outcome)}")
                continue
            check(
                "backups-consistent", f"{name}, taken mid-write ({mode})", ok, json.dumps(outcome)
            )
        check(
            "backups-consistent",
            "the backups were taken from a WAL database",
            mode == "wal",
            f"journal_mode {mode}" + ("" if r.get("paths") else f" {r}"),
        )

    if want("retention"):
        db = copy_of(source, scratch / "retention.db")
        r = child("retention", db)
        first, changed = r.get("first") or {}, r.get("changed") or {}
        check(
            "trace-retention",
            "the sweep removes every span older than the window and keeps every newer one",
            bool(first)
            and first["older_remaining"] == 0
            and first["newer_removed"] == 0
            and first["after"] < first["before"],
            json.dumps(first or r),
        )
        check(
            "trace-retention",
            "a changed window is honoured by the next sweep",
            r.get("changed_setting") == 1
            and bool(changed)
            and changed["older_remaining"] == 0
            and changed["newer_removed"] == 0
            and changed["after"] < changed["before"],
            json.dumps(changed or r),
        )

    if want("stall"):
        db = copy_of(source, scratch / "stall.db")
        r = child("stall", db)
        bound = (r.get("idle_max_ms") or 0) + STALL_SLACK_MS
        check(
            "retention-no-stall",
            "no GET /agents during the first sweep exceeds its idle time + 100ms",
            r.get("during_max_ms") is not None
            and r["during_max_ms"] <= bound
            and r.get("spans_left") == 0,
            json.dumps(r),
        )

    if want("stats"):
        db = copy_of(source, scratch / "stats.db")
        r = child("stats", db)
        check(
            "stats-current",
            "the Hub's statistics refresh on a never-analysed copy writes sqlite_stat1",
            {"agent_outputs", "event_logs"} <= set(r.get("after") or []),
            json.dumps(r),
        )

    if want("indexes"):
        for how, db in (
            ("fresh", scratch / "fresh-head.db"),
            ("upgrade", copy_of(source, scratch / "upgrade.db")),
        ):
            r = child("indexes", db, how)
            check(
                "hot-read-indexes",
                f"[{how}] the newest context reading is found through (project, event type, agent, ...)",
                bool(r.get("covers")),
                f"head {r.get('version')}, index {r.get('index')} {r.get('index_columns')}, plan {r.get('plan') or r}",
            )
            check(
                "hot-read-indexes",
                f"[{how}] no agent_outputs index is a leading prefix of another",
                "prefix_pairs" in r and not r["prefix_pairs"],
                "; ".join(r.get("prefix_pairs") or []) or str(r)[:300],
            )

    print("\n== summary")
    by_requirement: dict = {}
    for requirement, _name, ok, _detail in results:
        by_requirement.setdefault(requirement, []).append(ok)
    for requirement, oks in by_requirement.items():
        print(f"{'PASS' if all(oks) else 'FAIL'} {requirement} ({sum(oks)}/{len(oks)})")
    bad = [r for r in results if not r[2]]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (scratch: {scratch})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        run_child(sys.argv[2:])
    else:
        main()
