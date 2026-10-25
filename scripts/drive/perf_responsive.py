"""Acceptance drive for `the-app-stays-responsive-while-agents-run` -- one `--scenario` per criterion.

    py -3.11 scripts/drive/perf_responsive.py --scenario lists --db <database>

Every scenario prints its measurement and exits 0 on pass, 1 on fail, 2 when it could not run.

Safety, enforced in code and not by convention:
  * Never contacts :8000 and never opens the operator's database for writing. `--db` is only ever a
    SOURCE: it is read through SQLite's backup API (`mode=ro`) into a scratch copy, and every Hub the
    drive starts runs on that copy.
  * In-process scenarios run the app through an ASGI transport with the lifespan off.
  * Browser scenarios run a scratch Hub (uvicorn, in this process, on a free port, lifespan off, so
    the drive owns the event stream: it publishes to `sse_manager` directly).
  * A Hub on a copy with the lifespan ON (real-runner turns) refuses to start unless jobs, loops and
    queued input in that copy are already disabled (`disable_scheduling`): starting one without that
    spawned a real agent run during the investigation.

Note: the criterion for `streams` says "a scratch database"; this drive uses a scratch COPY of the
operator's database (the same data the other in-process scenarios measure), never the original.

Scenarios: one-event, no-overlap, line-appears, run-budget (--runner claude|copilot|codex-replay|codex),
idle-budget, lists, lists-10x, loops, same-answers (--base <sha>), streams, burst.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import re
import shutil
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parents[2]
HOME = Path.home()
OPERATOR_DB = HOME / ".agentweave" / "hub" / "data" / "agentweave.db"
TRIAL_DB = HOME / ".agentweave" / "hub" / "profiles" / "trial" / "agentweave.db"
PROJECT = "proj-d85a82bf4216"
KEY = "aw_live_perfdrive00000000000000000000"
HEADERS = {"Authorization": f"Bearer {KEY}"}
FORBIDDEN_PORT = 8000

IN_PROCESS = {"lists", "lists-10x", "loops", "same-answers", "burst", "streams", "lists-measure", "dump"}
BROWSER = {"one-event", "no-overlap", "line-appears", "run-budget", "idle-budget"}


SHOTS = Path(tempfile.gettempdir()) / "perf-responsive-shots"


class CannotRun(Exception):
    pass


def p(*a: Any) -> None:
    print(*a, flush=True)


def prefix() -> str:
    return f"/api/v1/projects/{PROJECT}"


# --------------------------------------------------------------------------------------- databases


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def make_copy(src: Path, tmp: Path, name: str = "work.db") -> Path:
    """A scratch copy of `src`, read through `mode=ro`, with a drive credential added. `src` is never written."""
    if not src.exists():
        raise CannotRun(f"database {src} does not exist")
    dst = tmp / name
    if _same_file(src, dst):
        raise CannotRun("refusing to use the source as its own copy")
    uri = "file:" + src.resolve().as_posix() + "?mode=ro"
    s = sqlite3.connect(uri, uri=True)
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
    finally:
        s.close()
    d.execute(
        "INSERT OR REPLACE INTO operator_credentials (id, label, revoked, created_at) "
        "VALUES (?, 'perf drive', 0, datetime('now'))",
        (KEY,),
    )
    d.commit()
    d.close()
    migrate_to_head(dst)
    return dst


_MIGRATE = """
import asyncio, sqlite3, sys
from alembic.config import Config
from alembic.script import ScriptDirectory
from hub.db.engine import _run_alembic_upgrade
from pathlib import Path
import hub.db.engine as e
asyncio.run(_run_alembic_upgrade())
head = ScriptDirectory.from_config(Config(str(Path(e.__file__).parent.parent / "alembic.ini"))).get_current_head()
c = sqlite3.connect(sys.argv[1])
have = c.execute("select version_num from alembic_version").fetchone()[0]
print("MIGRATED", have, head)
sys.exit(0 if have == head else 1)
"""


def migrate_to_head(db: Path) -> None:
    """Upgrade the scratch copy to this checkout's head, as the Hub does when it starts.

    The operator's database sits at whatever revision their Hub last started on; measuring this
    checkout's queries against it without its migrations measures them without their indexes
    (`0144` turned a 655 ms `/agents` into 21 ms on the 2026-10-25 copy).
    """
    env = dict(os.environ, DATABASE_URL="sqlite+aiosqlite:///" + db.resolve().as_posix())
    r = subprocess.run(
        [sys.executable, "-c", _MIGRATE, str(db)],
        cwd=str(REPO / "hub"), env=env, capture_output=True, text=True,
    )
    if r.returncode:
        raise CannotRun("could not migrate the scratch copy to head:\n" + r.stdout[-600:] + r.stderr[-600:])
    p("  " + [ln for ln in r.stdout.splitlines() if ln.startswith("MIGRATED")][-1])


def project_exists(db: Path) -> bool:
    c = sqlite3.connect(str(db))
    try:
        return c.execute("select 1 from projects where id=?", (PROJECT,)).fetchone() is not None
    finally:
        c.close()


def pick_agent(db: Path, wanted: Optional[str] = None) -> Dict[str, Optional[str]]:
    """The agent and its newest open conversation: the one with the most conversations unless named."""
    c = sqlite3.connect(str(db))
    try:
        if wanted:
            agent = wanted
        else:
            row = c.execute(
                "select agent from conversations where project_id=? and lifecycle='open' "
                "group by agent order by count(*) desc limit 1",
                (PROJECT,),
            ).fetchone()
            if not row:
                raise CannotRun("no open conversation in the copy for the project")
            agent = row[0]
        conv = c.execute(
            "select id, provider_session_id from conversations where project_id=? and agent=? and "
            "lifecycle='open' order by updated_at desc limit 1",
            (PROJECT, agent),
        ).fetchone()
        if not conv:
            raise CannotRun(f"agent {agent} has no open conversation")
        return {"agent": agent, "conversation_id": conv[0], "session_id": conv[1]}
    finally:
        c.close()


def disable_scheduling(db: Path) -> None:
    """Switch off everything in the copy that could start an agent run by itself when a Hub's lifespan is on."""
    c = sqlite3.connect(str(db))
    try:
        c.execute("update ai_jobs set enabled=0")
        c.execute("delete from apscheduler_jobs")
        c.execute("update loops set stopped_at=coalesce(stopped_at, datetime('now')) where stopped_at is null")
        c.execute("update inbound_queue_entries set state='withdrawn' where state='queued'")
        c.execute("update projects set allow_agent_jobs=0")
        c.commit()
    finally:
        c.close()


def scheduling_problems(db: Path) -> List[str]:
    c = sqlite3.connect(str(db))
    try:
        out = []
        n = c.execute("select count(*) from ai_jobs where enabled=1").fetchone()[0]
        if n:
            out.append(f"{n} enabled jobs")
        n = c.execute("select count(*) from apscheduler_jobs").fetchone()[0]
        if n:
            out.append(f"{n} scheduled apscheduler jobs")
        n = c.execute("select count(*) from loops where stopped_at is null").fetchone()[0]
        if n:
            out.append(f"{n} running loops")
        n = c.execute("select count(*) from inbound_queue_entries where state='queued'").fetchone()[0]
        if n:
            out.append(f"{n} queued inbound entries")
        return out
    finally:
        c.close()


def working_directory(db: Path) -> Optional[str]:
    c = sqlite3.connect(str(db))
    try:
        row = c.execute("select working_directory from projects where id=?", (PROJECT,)).fetchone()
        return row[0] if row else None
    finally:
        c.close()


def inside_temp(path: Optional[str]) -> bool:
    if not path:
        return False
    try:
        p_ = Path(path).resolve()
        return Path(tempfile.gettempdir()).resolve() in p_.parents
    except OSError:
        return False


def sandbox_repo(db: Path, tmp: Path) -> Path:
    """A scratch git repo under the temp dir, bound to the copy's project so real agent runs touch only it."""
    repo = (tmp / "scratch-repo").resolve()
    repo.mkdir()
    (repo / ".agentweave").mkdir()
    (repo / ".agentweave" / "project.json").write_text(
        json.dumps({"version": 1, "project_id": PROJECT}), encoding="utf-8")
    for cmd in (["init", "-q"], ["config", "user.email", "drive@example.invalid"], ["config", "user.name", "perf drive"],
                ["commit", "-q", "--allow-empty", "-m", "scratch"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
    c = sqlite3.connect(str(db))
    try:
        key = "windows:" + os.path.normcase(os.path.normpath(str(repo))) if os.name == "nt" else f"posix:{repo}"
        c.execute("update projects set working_directory=?, path_key=?, directory_state='available' where id=?",
                  (str(repo), key, PROJECT))
        c.commit()
    finally:
        c.close()
    return repo


def use_db(db: Path, hub_dir: Path) -> None:
    """Point this process's Hub import at `db`. Must run before `hub` is imported."""
    if "hub.main" in sys.modules:
        raise CannotRun("hub already imported in this process")
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + db.resolve().as_posix()
    sys.path.insert(0, str(hub_dir))


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    if port == FORBIDDEN_PORT:
        return free_port()
    return port


# ------------------------------------------------------------------------------------- scratch Hub


class DelayAgents:
    """ASGI wrapper that delays GET .../agents (the agent list) by `delay` seconds."""

    def __init__(self, app: Any, delay: float) -> None:
        self.app, self.delay = app, delay

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if (
            self.delay
            and scope["type"] == "http"
            and scope["method"] == "GET"
            and scope["path"] == f"{prefix()}/agents"
        ):
            await asyncio.sleep(self.delay)
        await self.app(scope, receive, send)


class ScratchHub:
    def __init__(self, db: Path, lifespan: bool, delay_agents: float = 0.0) -> None:
        self.db, self.lifespan, self.delay = db, lifespan, delay_agents
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.server: Any = None
        self.task: Optional[asyncio.Task] = None

    async def __aenter__(self) -> "ScratchHub":
        import uvicorn
        from hub.main import app

        if self.port == FORBIDDEN_PORT:
            raise CannotRun("refusing :8000")
        if self.lifespan:
            bad = scheduling_problems(self.db)
            if bad:
                raise CannotRun(
                    "refusing to start a Hub with the lifespan on: the copy still has " + ", ".join(bad)
                    + " (call disable_scheduling on the copy first)"
                )
            wd = working_directory(self.db)
            if not inside_temp(wd) or _same_file(Path(wd), REPO):
                raise CannotRun(
                    f"refusing to start a Hub with the lifespan on: the copy's project working_directory is {wd!r}, "
                    "not a scratch repo under the temp dir (call sandbox_repo on the copy first); real agent runs "
                    "would write branches and worktrees into it"
                )
        cfg = uvicorn.Config(
            DelayAgents(app, self.delay) if self.delay else app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            lifespan="on" if self.lifespan else "off",
        )
        self.server = uvicorn.Server(cfg)
        self.task = asyncio.create_task(self.server.serve())
        for _ in range(300):
            if self.server.started:
                return self
            await asyncio.sleep(0.1)
        raise CannotRun("scratch Hub did not start")

    async def __aexit__(self, *exc: Any) -> None:
        self.server.should_exit = True
        try:
            await asyncio.wait_for(self.task, 20)
        except Exception:
            self.task.cancel()


def api_client(app: Any = None, base: Optional[str] = None):
    import httpx

    if app is not None:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t", headers=HEADERS, timeout=120
        )
    return httpx.AsyncClient(base_url=base, headers=HEADERS, timeout=httpx.Timeout(120, read=None))


# ------------------------------------------------------------------------------- in-process scenarios


async def time_route(c: Any, url: str, n: int = 5) -> Dict[str, Any]:
    r = await c.get(url)  # first request warms imports and caches; it is not measured
    if r.status_code != 200:
        raise CannotRun(f"{url} answered {r.status_code}: {r.text[:200]}")
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        await c.get(url)
        ts.append(time.perf_counter() - t)
    return {"median_ms": statistics.median(ts) * 1000, "all_ms": [round(x * 1000, 1) for x in ts]}


def list_urls(agent: str) -> Dict[str, str]:
    P = prefix()
    return {
        "agents": f"{P}/agents",
        "conversations": f"{P}/conversations",
        "agent-conversations": f"{P}/agent/{agent}/conversations",
    }


async def measure_lists(db: Path, hub_dir: Path, agent: Optional[str]) -> Dict[str, float]:
    use_db(db, hub_dir)
    from hub.main import app

    a = pick_agent(db, agent)["agent"]
    out = {}
    async with api_client(app) as c:
        for name, url in list_urls(a).items():
            out[name] = (await time_route(c, url))["median_ms"]
    return out


def multiply_tables(db: Path, factor: int = 10) -> Dict[str, int]:
    """Multiply agent_outputs, event_logs and trace_spans `factor` times in `db` (a scratch copy)."""
    c = sqlite3.connect(str(db))
    counts = {}
    try:
        for table in ("agent_outputs", "event_logs", "trace_spans"):
            info = c.execute(f"pragma table_info({table})").fetchall()
            cols = [r[1] for r in info]
            pk = [r[1] for r in info if r[5]]
            if len(pk) != 1:
                raise CannotRun(f"{table} has no single-column primary key")
            before = c.execute(f"select count(*) from {table}").fetchone()[0]
            maxrow = c.execute(f"select max(rowid) from {table}").fetchone()[0]
            for k in range(1, factor):
                sel = ", ".join(f"{col} || '-x{k}'" if col == pk[0] else col for col in cols)
                c.execute(
                    f"insert into {table} ({', '.join(cols)}) select {sel} from {table} where rowid <= ?",
                    (maxrow,),
                )
            counts[table] = (before, c.execute(f"select count(*) from {table}").fetchone()[0])
        c.commit()
    finally:
        c.close()
    return counts


def _subprocess_measure(db: Path, args: argparse.Namespace) -> Dict[str, float]:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--scenario", "lists-measure", "--db", str(db),
           "--copied", "--hub-dir", str(args.hub_dir)]
    if args.agent:
        cmd += ["--agent", args.agent]
    r = subprocess.run(cmd, capture_output=True, text=True)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT ")]
    if r.returncode or not line:
        raise CannotRun("measure subprocess failed:\n" + r.stdout[-800:] + r.stderr[-800:])
    return json.loads(line[-1][7:])


async def sc_lists_measure(args: argparse.Namespace) -> int:
    res = await measure_lists(Path(args.db), args.hub_dir, args.agent)
    p("RESULT " + json.dumps(res))
    return 0


async def sc_lists(args: argparse.Namespace, db: Path) -> int:
    res = await measure_lists(db, args.hub_dir, args.agent)
    ok = True
    for name, ms in res.items():
        good = ms < 60
        ok &= good
        p(f"  {name:22s} median {ms:7.1f} ms   (< 60)   {'ok' if good else 'FAIL'}")
    return 0 if ok else 1


async def sc_lists_10x(args: argparse.Namespace, db: Path, tmp: Path) -> int:
    big = tmp / "big.db"
    shutil.copy(db, big)
    counts = multiply_tables(big)
    p("  rows (before -> after):", {k: f"{a}->{b}" for k, (a, b) in counts.items()})
    base = _subprocess_measure(db, args)
    bigm = _subprocess_measure(big, args)
    ok = True
    for name in base:
        ratio = bigm[name] / max(base[name], 0.001)
        good = ratio < 1.5
        ok &= good
        p(f"  {name:22s} 1x {base[name]:7.1f} ms   10x {bigm[name]:7.1f} ms   ratio {ratio:5.2f}  (< 1.5)   {'ok' if good else 'FAIL'}")
    return 0 if ok else 1


async def sc_loops(args: argparse.Namespace, db: Path) -> int:
    use_db(db, args.hub_dir)
    from sqlalchemy import event

    from hub.db.engine import engine
    from hub.main import app

    count = {"n": 0, "on": False}

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count(*_a: Any) -> None:
        if count["on"]:
            count["n"] += 1

    ok = True
    async with api_client(app) as c:
        for name in ("loops", "jobs"):
            url = f"{prefix()}/{name}"
            timing = await time_route(c, url)
            stmts = []
            for _ in range(5):
                count["n"], count["on"] = 0, True
                await c.get(url)
                count["on"] = False
                stmts.append(count["n"])
            good = max(stmts) <= 25 and timing["median_ms"] < 80
            ok &= good
            p(f"  GET /{name:6s} statements {stmts} (max <= 25)   median {timing['median_ms']:6.1f} ms (< 80)   {'ok' if good else 'FAIL'}")
    return 0 if ok else 1


POLL_MIX = ["agents", "loops", "conversations", "AGENT_OUTPUT", "accounting", "AGENT_CONVERSATIONS", "tasks", "questions"]


def poll_urls(agent: str) -> List[str]:
    P = prefix()
    m = {
        "AGENT_OUTPUT": f"{P}/agents/{agent}/output",
        "AGENT_CONVERSATIONS": f"{P}/agent/{agent}/conversations",
    }
    return [m.get(x, f"{P}/{x}") for x in POLL_MIX]


async def sc_burst(args: argparse.Namespace, db: Path) -> int:
    use_db(db, args.hub_dir)
    from hub.main import app

    agent = pick_agent(db, args.agent)["agent"]
    urls = poll_urls(agent)
    async with api_client(app) as c:
        for u in urls:
            r = await c.get(u)
            if r.status_code != 200:
                raise CannotRun(f"{u} answered {r.status_code}")
        lat: Dict[str, List[float]] = collections.defaultdict(list)

        async def one(u: str) -> None:
            t = time.perf_counter()
            await c.get(u)
            lat[u.rsplit("/", 2)[-1] if u.endswith("output") else u.split(PROJECT)[-1]].append(time.perf_counter() - t)

        t0 = time.perf_counter()
        await asyncio.gather(*[one(urls[i % len(urls)]) for i in range(24)])
        wall = time.perf_counter() - t0
    worst = max(max(v) for v in lat.values())
    for k, v in lat.items():
        p(f"  {k:36s} n={len(v)} median {statistics.median(v)*1000:7.1f} ms   max {max(v)*1000:7.1f} ms")
    good = worst <= 0.6
    p(f"  24 requests, wall {wall*1000:.0f} ms, slowest {worst*1000:.0f} ms (<= 600)   {'ok' if good else 'FAIL'}")
    return 0 if good else 1


async def sc_streams(args: argparse.Namespace, db: Path) -> int:
    use_db(db, args.hub_dir)
    import httpx

    url = f"{prefix()}/events"
    statuses: List[int] = []
    held: List[Any] = []
    async with ScratchHub(db, lifespan=False) as hub:
        async with httpx.AsyncClient(
            base_url=hub.base, headers=HEADERS, timeout=httpx.Timeout(60, read=None),
            limits=httpx.Limits(max_connections=None, max_keepalive_connections=0),
        ) as c:

            async def open_one() -> int:
                cm = c.stream("GET", url)
                try:
                    r = await asyncio.wait_for(cm.__aenter__(), 50)
                except Exception as e:  # noqa: BLE001
                    return -1 if not isinstance(e, asyncio.TimeoutError) else -2
                if r.status_code != 200:
                    await cm.__aexit__(None, None, None)
                    return r.status_code
                it = r.aiter_raw()  # kept referenced: a collected iterator closes the stream
                try:
                    await asyncio.wait_for(it.__anext__(), 10)
                except Exception:  # noqa: BLE001
                    await cm.__aexit__(None, None, None)
                    return -3
                held.append((cm, it))
                return 200

            # One at a time, as tabs open: opened concurrently the streams do not all hold a connection
            # at once, which hides the leak. After the first refusal the rest wait out the pool
            # timeout together, so a leaking Hub costs ~30s here, not 30s per stream.
            statuses = []
            for _ in range(50):
                s = await open_one()
                statuses.append(s)
                if s != 200:
                    break
            if len(statuses) < 50:
                statuses += await asyncio.gather(*[open_one() for _ in range(50 - len(statuses))])
            opened = sum(1 for s in statuses if s == 200)
            p(f"  first 50 streams: {opened} opened with a first frame; others: {dict(collections.Counter(s for s in statuses if s != 200))}")
            t = time.perf_counter()
            s51 = await open_one()
            p(f"  51st stream: {'first frame received' if s51 == 200 else f'FAILED ({s51})'} after {time.perf_counter()-t:.2f}s")
            t = time.perf_counter()
            try:
                r = await asyncio.wait_for(c.get(f"{prefix()}/agents"), 60)
                code, dt = r.status_code, time.perf_counter() - t
            except Exception as e:  # noqa: BLE001
                code, dt = type(e).__name__, time.perf_counter() - t
            p(f"  GET /agents with 50+ streams held: {code} in {dt:.2f}s (200, < 1)")
            for cm, _it in held:
                try:
                    await asyncio.wait_for(cm.__aexit__(None, None, None), 5)
                except Exception:  # noqa: BLE001
                    pass
    good = opened == 50 and s51 == 200 and code == 200 and dt < 1.0
    return 0 if good else 1


# ----------------------------------------------------------------------------------------- same-answers

TIME_TOLERANCE_S = 300


def _as_time(v: Any) -> Optional[float]:
    from datetime import datetime, timezone

    if isinstance(v, str) and re.match(r"^\d{4}-\d\d-\d\dT", v):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.timestamp()
        except ValueError:
            return None
    return None


def diff_bodies(a: Any, b: Any, path: str, now: float, out: List[str], ignored: List[str]) -> None:
    if type(a) is not type(b):
        out.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: present on one side only")
            else:
                diff_bodies(a[k], b[k], f"{path}.{k}", now, out, ignored)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                diff_bodies(x, y, f"{path}[{i}]", now, out, ignored)
    elif a != b:
        ta, tb = _as_time(a), _as_time(b)
        if ta is not None and tb is not None and abs(ta - now) < TIME_TOLERANCE_S and abs(tb - now) < TIME_TOLERANCE_S:
            ignored.append(path)  # both state "about now": a clock field
        else:
            out.append(f"{path}: {str(a)[:60]!r} != {str(b)[:60]!r}")


def same_routes(db: Path) -> List[str]:
    P = prefix()
    c = sqlite3.connect(str(db))
    try:
        agents = [r[0] for r in c.execute(
            "select agent from conversations where project_id=? group by agent order by count(*) desc limit 5", (PROJECT,))]
    finally:
        c.close()
    return [f"{P}/agents", f"{P}/conversations", f"{P}/loops", f"{P}/jobs"] + [
        f"{P}/agent/{a}/conversations" for a in agents
    ]


async def sc_dump(args: argparse.Namespace) -> int:
    db = Path(args.db)
    use_db(db, args.hub_dir)
    import hub as hubpkg
    from hub.main import app

    bodies = {}
    async with api_client(app) as c:
        for u in same_routes(db):
            r = await c.get(u)
            bodies[u] = {"status": r.status_code, "body": r.json() if r.status_code == 200 else r.text[:300]}
    Path(args.out).write_text(json.dumps({"hub": hubpkg.__file__, "at": time.time(), "bodies": bodies}), encoding="utf-8")
    return 0


async def sc_same(args: argparse.Namespace, db: Path, tmp: Path) -> int:
    if not args.base:
        raise CannotRun("same-answers needs --base <master sha>")
    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", args.base], capture_output=True, text=True)
    if sha.returncode:
        raise CannotRun(f"unknown revision {args.base}")
    base_dir = tmp / "base-checkout"
    subprocess.run(["git", "-C", str(REPO), "worktree", "add", "--detach", str(base_dir), sha.stdout.strip()],
                   check=True, capture_output=True)
    try:
        outs = {}
        for label, hub_dir in (("base", base_dir / "hub"), ("current", REPO / "hub")):
            dbcopy = tmp / f"same-{label}.db"
            shutil.copy(db, dbcopy)
            out = tmp / f"{label}.json"
            r = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--scenario", "dump", "--db", str(dbcopy),
                 "--copied", "--hub-dir", str(hub_dir), "--out", str(out)],
                capture_output=True, text=True, cwd=str(tmp))
            if r.returncode:
                raise CannotRun(f"{label} dump failed:\n{r.stdout[-600:]}\n{r.stderr[-1200:]}")
            outs[label] = json.loads(out.read_text(encoding="utf-8"))
        p(f"  base hub:    {outs['base']['hub']}")
        p(f"  current hub: {outs['current']['hub']}")
        ok = True
        now = (outs["base"]["at"] + outs["current"]["at"]) / 2
        for u in outs["base"]["bodies"]:
            a, b = outs["base"]["bodies"][u], outs["current"]["bodies"].get(u)
            diffs: List[str] = []
            ignored: List[str] = []
            diff_bodies(a, b, "", now, diffs, ignored)
            good = not diffs
            ok &= good
            p(f"  {u.replace(prefix(), ''):44s} status {a['status']}/{b['status']}  {'equal' if good else 'DIFFERS'}"
              f"{f' ({len(ignored)} clock fields ignored)' if ignored else ''}")
            for d in diffs[:5]:
                p("      " + d)
        return 0 if ok else 1
    finally:
        subprocess.run(["git", "-C", str(REPO), "worktree", "remove", "--force", str(base_dir)], capture_output=True)


# ------------------------------------------------------------------------------------ browser scenarios

PROJECT_PATH_RE = re.compile(r"/api/v1/projects/[^/]+")


class RequestLog:
    """Every request the page sends to the Hub, with start, end and in-flight tracking."""

    def __init__(self, page: Any, base: str) -> None:
        self.base, self.rows, self.live = base, [], {}
        page.on("request", self._start)
        page.on("requestfinished", self._end)
        page.on("requestfailed", self._end)

    def _start(self, req: Any) -> None:
        if req.url.startswith(self.base + "/api/"):
            row = {"t0": time.time(), "t1": None, "method": req.method, "url": req.url,
                   "path": PROJECT_PATH_RE.sub("", req.url.split("?")[0][len(self.base):])}
            self.rows.append(row)
            self.live[req] = row

    def _end(self, req: Any) -> None:
        row = self.live.pop(req, None)
        if row:
            row["t1"] = time.time()

    def gets(self, since: float, until: float = 1e18) -> List[Dict[str, Any]]:
        return [r for r in self.rows if r["method"] == "GET" and since <= r["t0"] < until
                and not r["path"].endswith("/events")]

    def window_counts(self, since: float, window: float = 60.0) -> List[int]:
        ts = sorted(r["t0"] for r in self.rows if r["t0"] >= since)
        return [sum(1 for t in ts if t0 <= t < t0 + window) for t0 in ts] or [0]


SEED = """
sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %(key)r, hubUrl: %(hub)r}));
localStorage.setItem('agentweave-selected-project', %(proj)r);
"""


async def open_chat(pw: Any, hub: ScratchHub, who: Dict[str, Optional[str]], _tmp: Path):
    shots = SHOTS
    shots.mkdir(exist_ok=True)
    browser = await pw.chromium.launch()
    ctx = await browser.new_context(viewport={"width": 1600, "height": 1000})
    await ctx.add_init_script(SEED % {"key": KEY, "hub": hub.base, "proj": PROJECT})
    page = await ctx.new_page()
    log = RequestLog(page, hub.base)
    conv = f"&conversation={who['conversation_id']}" if who["conversation_id"] else ""
    await page.goto(f"{hub.base}/?project={PROJECT}&agent={who['agent']}{conv}", wait_until="domcontentloaded")
    try:
        if who["conversation_id"]:
            await page.locator("[data-testid='conversation-pane']").first.wait_for(timeout=30000)
        else:  # a new conversation has no pane yet, only its composer
            await page.get_by_placeholder(re.compile(r"^Message ")).first.wait_for(timeout=30000)
    except Exception as e:  # noqa: BLE001
        shot = shots / "open-chat-failed.png"
        await page.screenshot(path=str(shot))
        raise CannotRun(f"could not open the chat screen for {who['agent']} ({type(e).__name__}); screenshot {shot}")
    return browser, page, log


async def settle(log: RequestLog, quiet: float = 4.0, limit: float = 40.0) -> None:
    """Wait until nothing is in flight and nothing has started for `quiet` seconds."""
    end = time.time() + limit
    while time.time() < end:
        last = max([r["t0"] for r in log.rows] or [0])
        if not log.live and time.time() - last >= quiet:
            return
        await asyncio.sleep(0.5)
    p(f"  WARNING: the tab never went quiet within {limit:.0f}s; what follows measures a storm already running")


def tally(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    return dict(collections.Counter(f"GET {r['path']}" for r in rows))


async def sc_one_event(args: argparse.Namespace, db: Path, tmp: Path) -> int:
    use_db(db, args.hub_dir)
    from playwright.async_api import async_playwright

    from hub.sse import sse_manager

    who = pick_agent(db, args.agent)
    async with ScratchHub(db, lifespan=False) as hub, async_playwright() as pw:
        browser, page, log = await open_chat(pw, hub, who, tmp)
        await settle(log)
        t0 = time.time()
        sse_manager.publish(PROJECT, "context_warning", {
            "agent": who["agent"], "conversation_id": who["conversation_id"], "percent": 41.0,
            "context_tokens": 82000, "context_window": 200000, "observed_at": time.time(), "model": "perf-drive"})
        await page.wait_for_timeout(2500)
        rows = log.gets(t0, t0 + 2.5)
        await browser.close()
    counts = tally(rows)
    p("  GETs after one context_warning (2.5s):", json.dumps(counts, indent=2) if counts else "none")
    multi = {k: v for k, v in counts.items() if v > 1}
    output = [k for k in counts if re.search(rf"/agents/{re.escape(who['agent'])}/output$", k)]
    p(f"  routes re-read more than once: {multi or 'none'};  GET of /agents/{who['agent']}/output: {output or 'none'}")
    return 0 if not multi and not output else 1


async def sc_no_overlap(args: argparse.Namespace, db: Path, tmp: Path) -> int:
    use_db(db, args.hub_dir)
    from playwright.async_api import async_playwright

    from hub.sse import sse_manager

    who = pick_agent(db, args.agent)
    async with ScratchHub(db, lifespan=False, delay_agents=2.0) as hub, async_playwright() as pw:
        browser, page, log = await open_chat(pw, hub, who, tmp)
        await settle(log, quiet=5.0, limit=60)
        t0 = time.time()
        a = who["agent"]
        events = [("context_warning", {"agent": a, "percent": 40.0, "context_tokens": 80000, "observed_at": time.time()}),
                  ("queue_entry_queued", {"agent": a}), ("queue_entry_delivered", {"agent": a}),
                  ("queue_entry_released", {"agent": a}),
                  ("context_warning", {"agent": a, "percent": 41.0, "context_tokens": 82000, "observed_at": time.time() + 1})]
        for et, data in events:
            sse_manager.publish(PROJECT, et, data)
            await asyncio.sleep(0.1)
        await page.wait_for_timeout(9000)
        rows = [r for r in log.gets(t0) if r["path"] == "/agents"]
        await browser.close()
    now = time.time() + 1
    spans = sorted((r["t0"], r["t1"] or now) for r in rows)
    peak = 0
    for t, _e in spans:
        peak = max(peak, sum(1 for s, e in spans if s <= t < e))
    p(f"  GET /agents in the 9.5s after five events: {len(rows)} total, peak in flight {peak}  (peak <= 1, total <= 2)")
    return 0 if peak <= 1 and len(rows) <= 2 else 1


async def post_output(c: Any, who: Dict[str, Optional[str]], text: str, seq: int, run_id: str) -> None:
    r = await c.post(f"{prefix()}/agents/{who['agent']}/output", json={
        "content": text, "kind": "text", "session_id": who["session_id"] or "perf-drive-session",
        "payload": {"version": 1, "text": text}, "run_id": run_id, "sequence": seq})
    if r.status_code >= 300:
        raise CannotRun(f"POST output answered {r.status_code}: {r.text[:200]}")


async def sc_line_appears(args: argparse.Namespace, db: Path, tmp: Path) -> int:
    use_db(db, args.hub_dir)
    from playwright.async_api import async_playwright

    who = pick_agent(db, args.agent)
    marker = f"perf-drive-line-{uuid.uuid4().hex[:8]}"
    async with ScratchHub(db, lifespan=False) as hub, async_playwright() as pw:
        browser, page, log = await open_chat(pw, hub, who, tmp)
        await settle(log)
        t0 = time.time()
        async with api_client(base=hub.base) as c:
            await post_output(c, who, marker, 1, "perf-drive-run")
        await page.wait_for_timeout(3000)
        visible = await page.get_by_text(marker).count() > 0
        if os.environ.get("PERF_DEBUG"):
            async with api_client(base=hub.base) as c:
                h = (await c.get(f"{prefix()}/agent/{who['agent']}/chat/{who['conversation_id']}")).text
                p("  debug: marker in picked conversation's history:", marker in h, "| picked", who, "| page url", page.url)
        if not visible and os.environ.get('PERF_SHOT'):
            await page.screenshot(path=os.environ['PERF_SHOT'])
        rows = log.gets(t0)
        await browser.close()
    counts = tally(rows)
    # `/agent/{a}/chat` and `/agent/{a}/chat/{conversation}` are both that conversation's chat history: the
    # open conversation is the only one the tab shows, so a history GET without an id re-reads it too.
    bad = {k: v for k, v in counts.items()
           if re.search(r"/agent/[^/]+/chat(/|$)", k) or re.search(r"/agents/[^/]+/output$", k) or k == "GET /agents"}
    p(f"  line visible in the conversation: {visible}")
    p("  GETs after the line (3s):", json.dumps(counts, indent=2) if counts else "none")
    p(f"  forbidden GETs: {bad or 'none'}")
    return 0 if visible and not bad else 1


PROMPT = ("Do this slowly, one step at a time, with a separate tool call per step: run `echo step-N` in a shell "
          "for N from 1 to 40, waiting about 5 seconds between steps (for example with `sleep 5`), and "
          "say one short sentence after each. Do not stop early.")


async def make_runner_agent(hub: ScratchHub, runner: str, model: Optional[str]) -> Dict[str, Optional[str]]:
    """An agent in the copy bound to `runner`, with no conversation yet: the turn is sent from the composer."""
    default = {"copilot": "claude-haiku-5.5", "claude": "claude-haiku-5-5"}.get(runner)
    model = model or default
    if not model:
        raise CannotRun(f"--runner {runner} needs --model")
    name = f"perfdrive-{runner}"
    async with api_client(base=hub.base) as c:
        r = await c.post(f"{prefix()}/agents", json={"name": name, "provider": runner, "model": model})
        if r.status_code >= 300 and "exist" not in r.text.lower():
            raise CannotRun(f"creating the {runner} agent answered {r.status_code}: {r.text[:300]}")
    return {"agent": name, "conversation_id": None, "session_id": None}


async def send_from_composer(page: Any, _tmp: Path) -> None:
    shots = SHOTS
    shots.mkdir(exist_ok=True)
    box = page.get_by_placeholder(re.compile(r"^Message "))
    try:
        await box.first.wait_for(timeout=20000)
        await box.first.fill(PROMPT)
        await box.first.press("Enter")
    except Exception as e:  # noqa: BLE001
        await page.screenshot(path=str(shots / "composer-failed.png"))
        raise CannotRun(f"could not send from the composer ({type(e).__name__}); screenshot {shots / 'composer-failed.png'}")


async def replay_turn(hub: ScratchHub, who: Dict[str, Optional[str]], db: Path, seconds: float, source: Optional[str]) -> str:
    """Replay a recorded turn's output rows and context readings onto the conversation at their recorded pace."""
    c0 = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    try:
        rows = c0.execute(
            "select run_id, count(*) n from agent_outputs where project_id=? and run_id is not null "
            "group by run_id order by n desc limit 1", (PROJECT,)).fetchone()
        if source:
            run_id = source
        elif rows:
            run_id = rows[0]
        else:
            raise CannotRun("the copy holds no recorded run to replay (pass --replay-run <run id>)")
        recorded = c0.execute(
            "select content, kind, payload, sequence, timestamp from agent_outputs where run_id=? order by sequence",
            (run_id,)).fetchall()
    finally:
        c0.close()
    from datetime import datetime

    from hub.sse import sse_manager

    def ts(s: str) -> float:
        return datetime.fromisoformat(s.replace("Z", "")).timestamp()

    end = time.time() + seconds
    seq, n = 0, 0
    async with api_client(base=hub.base) as c:
        while time.time() < end:
            prev = None
            for content, kind, payload, _s, stamp in recorded:
                gap = 0.0 if prev is None else min(max(ts(stamp) - prev, 0.0), 4.0)
                prev = ts(stamp)
                await asyncio.sleep(gap)
                seq += 1
                await c.post(f"{prefix()}/agents/{who['agent']}/output", json={
                    "content": content, "kind": kind, "session_id": who["session_id"] or "perf-drive-session",
                    "payload": json.loads(payload) if isinstance(payload, str) else payload,
                    "run_id": f"replay-{run_id}", "sequence": seq})
                n += 1
                if n % 8 == 0:  # a turn reports context use as it goes, on every runner
                    sse_manager.publish(PROJECT, "context_warning", {
                        "agent": who["agent"], "conversation_id": who["conversation_id"], "percent": 20.0 + n % 40,
                        "context_tokens": 40000 + n * 100, "context_window": 200000, "observed_at": time.time()})
                if time.time() >= end:
                    break
    return f"replayed {n} recorded rows of run {run_id}"


async def watch_output(db: Path, agent: str, stamps: List[float], stop: asyncio.Event) -> None:
    """Record when new agent_outputs rows for `agent` appear in the scratch copy."""
    last = None
    while not stop.is_set():
        c = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
        try:
            n = c.execute("select count(*) from agent_outputs where project_id=? and agent=?", (PROJECT, agent)).fetchone()[0]
        except sqlite3.Error:
            n = last
        finally:
            c.close()
        if last is not None and n is not None and n > last:
            stamps.append(time.time())
        last = n if n is not None else last
        try:
            await asyncio.wait_for(stop.wait(), 1.0)
        except asyncio.TimeoutError:
            pass


async def sc_run_budget(args: argparse.Namespace, db: Path, tmp: Path) -> int:
    use_db(db, args.hub_dir)
    from playwright.async_api import async_playwright

    real = args.runner in ("claude", "copilot", "codex")
    if real:
        disable_scheduling(db)  # a real turn needs the lifespan; nothing else may start with it
        repo = sandbox_repo(db, tmp)  # and its agents must work in a scratch repo, not this one
        p(f"  real runs are bound to the scratch repo {repo}")
    stamps: List[float] = []
    stop = asyncio.Event()
    watcher: Optional[asyncio.Task] = None
    async with ScratchHub(db, lifespan=real) as hub, async_playwright() as pw:
        # A drive-created agent and a new conversation, never an existing agent's session.
        who = await make_runner_agent(hub, args.runner, args.model) if real else pick_agent(db, args.agent)
        browser, page, log = await open_chat(pw, hub, who, tmp)
        await settle(log)
        t0 = time.time()
        if real:
            watcher = asyncio.create_task(watch_output(db, who["agent"], stamps, stop))
            await send_from_composer(page, tmp)
            await asyncio.sleep(args.seconds)
            note = f"real {args.runner} turn, sent from the composer"
        else:
            note = await replay_turn(hub, pick_agent(db, args.agent), db, args.seconds, args.replay_run)
        stop.set()
        if watcher:
            await watcher
        await browser.close()
    if real:
        if not stamps:
            raise CannotRun("the turn produced no output rows: nothing streamed, so the window measures an idle tab")
        p(f"  output arrived from t0+{stamps[0] - t0:.0f}s to t0+{stamps[-1] - t0:.0f}s ({len(stamps)} polls saw new rows)")
        if stamps[-1] - stamps[0] < 120:
            raise CannotRun(
                f"output arrived over only {stamps[-1] - stamps[0]:.0f}s, short of the two minutes the criterion needs "
                "(raise --seconds if the turn started late)")
    return report_budget(log, t0, note, limit=40, window=60.0, seconds=args.seconds)


def report_budget(log: RequestLog, t0: float, note: str, limit: int, window: float, seconds: float) -> int:
    counts = log.window_counts(t0, window)
    total = len([r for r in log.rows if r["t0"] >= t0])
    by = collections.Counter(f"{r['method']} {r['path']}" for r in log.rows if r["t0"] >= t0)
    p(f"  {note}; {total} requests in {seconds:.0f}s")
    for k, v in by.most_common(8):
        p(f"    {v:5d}  {k}")
    peak = max(counts)
    p(f"  busiest one-minute window: {peak} requests (limit {limit})")
    return 0 if peak <= limit else 1


async def sc_idle_budget(args: argparse.Namespace, db: Path, tmp: Path) -> int:
    use_db(db, args.hub_dir)
    from playwright.async_api import async_playwright

    who = pick_agent(db, args.agent)
    async with ScratchHub(db, lifespan=False) as hub, async_playwright() as pw:
        browser, page, log = await open_chat(pw, hub, who, tmp)
        await settle(log)
        t0 = time.time()
        await page.wait_for_timeout(int(args.idle_seconds * 1000))
        total = len([r for r in log.rows if r["t0"] >= t0])
        by = collections.Counter(f"{r['method']} {r['path']}" for r in log.rows if r["t0"] >= t0)
        await browser.close()
    for k, v in by.most_common(8):
        p(f"    {v:5d}  {k}")
    p(f"  {total} requests in {args.idle_seconds:.0f}s idle (limit 30 per 300s; {total / args.idle_seconds * 60:.1f} a minute)")
    limit = 30 * args.idle_seconds / 300
    return 0 if total <= limit else 1


# ------------------------------------------------------------------------------------------------ main

SCENARIOS = ["one-event", "no-overlap", "line-appears", "run-budget", "idle-budget", "lists", "lists-10x",
             "loops", "same-answers", "streams", "burst"]


def parse() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", required=True, choices=SCENARIOS + ["lists-measure", "dump"])
    ap.add_argument("--db", help="SOURCE database to copy (read-only). In-process default: the operator's; browser: the trial's.")
    ap.add_argument("--copied", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--hub-dir", type=Path, default=REPO / "hub", help="directory holding the `hub` package to import")
    ap.add_argument("--agent")
    ap.add_argument("--base", help="same-answers: the master revision this slice starts from")
    ap.add_argument("--runner", choices=["claude", "copilot", "codex-replay", "codex"], default="claude")
    ap.add_argument("--model", help="run-budget: model override for a real turn (e.g. haiku)")
    ap.add_argument("--seconds", type=float, default=280.0, help="run-budget: how long to hold the window (a real turn can take ~100s to start)")
    ap.add_argument("--idle-seconds", type=float, default=300.0)
    ap.add_argument("--replay-run", help="codex-replay: the run id to replay (default: the copy's longest run)")
    ap.add_argument("--out")
    return ap.parse_args()


async def amain(args: argparse.Namespace) -> int:
    if str(FORBIDDEN_PORT) in (os.environ.get("AW_HUB", ""),) or ":8000" in os.environ.get("AW_HUB", ""):
        raise CannotRun("AW_HUB points at :8000; this drive never contacts it")
    sc = args.scenario
    if sc == "lists-measure":
        return await sc_lists_measure(args)
    if sc == "dump":
        return await sc_dump(args)
    default_src = TRIAL_DB if sc in BROWSER else OPERATOR_DB
    src = Path(args.db) if args.db else default_src
    with tempfile.TemporaryDirectory(prefix="perf-responsive-", ignore_cleanup_errors=True) as t:
        tmp = Path(t)
        db = make_copy(src, tmp)
        if not project_exists(db):
            raise CannotRun(f"{PROJECT} is not in {src}")
        p(f"scenario {sc}: source {src} (read-only) -> scratch copy {db}")
        if sc == "lists":
            return await sc_lists(args, db)
        if sc == "lists-10x":
            return await sc_lists_10x(args, db, tmp)
        if sc == "loops":
            return await sc_loops(args, db)
        if sc == "burst":
            return await sc_burst(args, db)
        if sc == "streams":
            return await sc_streams(args, db)
        if sc == "same-answers":
            return await sc_same(args, db, tmp)
        if sc == "one-event":
            return await sc_one_event(args, db, tmp)
        if sc == "no-overlap":
            return await sc_no_overlap(args, db, tmp)
        if sc == "line-appears":
            return await sc_line_appears(args, db, tmp)
        if sc == "run-budget":
            return await sc_run_budget(args, db, tmp)
        if sc == "idle-budget":
            return await sc_idle_budget(args, db, tmp)
    raise CannotRun(f"unknown scenario {sc}")


def main() -> int:
    args = parse()
    if args.scenario in ("lists-measure", "dump") and not args.copied:
        p("internal scenario: use the public ones")
        return 2
    try:
        code = asyncio.run(amain(args))
    except CannotRun as e:
        p(f"CANNOT RUN: {e}")
        return 2
    p(f"{args.scenario}: {'PASS' if code == 0 else 'FAIL'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
