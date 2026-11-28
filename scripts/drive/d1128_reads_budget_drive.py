"""Acceptance drive for `screens-stop-repeating-work-on-every-read` (2026-11-28).

Run from `hub/` with AW_PERF_DB naming a backup-API copy of the operator's database:

    cd hub && AW_PERF_DB=C:/Users/huida/aw-perf/copy.db py -3.11 ../scripts/drive/d1128_reads_budget_drive.py budgets

Subcommands (exit 1 on a missed budget, 2 when a thing this drive needs is not built yet):
  budgets                      FR-3: p90 of 5 calls after a warm-up, per route, against its budget
  burst [--with-writer]        FR-4: the ten project-screen requests fired together, slowest <= 2 s
  archive                      FR-12: the one-time archive sweep on the copy, twice
  conversations                FR-13: GET conversations p90 under 60 ms (after the archive)
  bodies --record FILE         FR-14: record every route's body (not the evidence list)
  bodies --against FILE        FR-14: read again and compare; trace settings may add counts_at

In-process with the lifespan off: the Hub's lifespan would drain the copy's queued input and start
real agent runs (aw-perf/D-database.md section 0). The copy holds the operator key, so it is only
ever read from here. `--with-writer` inserts rows tagged agent/name `d1128-writer` and deletes them
when it ends, so the copy's bodies stay comparable.
"""

import argparse
import asyncio
import json
import math
import os
import sqlite3
import sys
import time
import uuid

DB = os.environ.get("AW_PERF_DB")
if not DB:
    sys.exit("AW_PERF_DB must name a copy of the operator's database")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB}"

# Measure the checkout this script lives in, not whichever one the editable install names:
# sys.path[0] is scripts/drive/, so put this repo's hub/ ahead of it.
HUB_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "hub"))
sys.path.insert(0, HUB_DIR)

import httpx  # noqa: E402

PROJECT = os.environ.get("AW_PERF_PROJECT", "proj-d85a82bf4216")
BASE = f"/api/v1/projects/{PROJECT}"
EVIDENCE = "project/spec/evidence?limit=50"
WARMUPS = 1
CALLS = 5
BURST_LIMIT_S = 2.0
CONVERSATIONS_BUDGET_MS = 60
WRITER_TAG = "d1128-writer"
# Read-time stamps: they change between two reads of an unchanged copy and mean nothing in a body.
CLOCK_KEYS = frozenset({"generated_at", "as_of"})

# (label, route relative to the project, budget in ms). "{build}" is a build id read first.
BUDGETS = [
    ("overview", "overview", 800),
    ("next-slice offers", "project/next-slice-offers", 800),
    ("project builds", "project/builds", 500),
    ("build tasks", "project/builds/{build}/tasks", 500),
    ("documents", "project/documents", 500),
    ("specs", "project/specs", 500),
    ("spec defects", "project/spec/defects", 500),
    ("ledger", "ledger", 500),
    ("evidence", EVIDENCE, 500),
    ("tasks", "tasks", 300),
    ("loops", "loops", 300),
    ("jobs", "jobs", 300),
    ("trace settings", "traces/settings", 200),
]
# The ten requests a project screen loads.
SCREEN = [
    "overview",
    "project/next-slice-offers",
    "project/builds",
    "tasks",
    "conversations",
    "project/documents",
    "loops",
    "agents",
    "jobs",
    EVIDENCE,
]
# Every route in FR-14's slice but the evidence list.
BODY_ROUTES = [(label, route) for label, route, _ in BUDGETS if route != EVIDENCE] + [
    ("conversations", "conversations")
]


def operator_key() -> str:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        row = con.execute(
            "select id from operator_credentials where revoked=0 limit 1"
        ).fetchone()
    finally:
        con.close()
    if not row:
        sys.exit("the copy holds no live operator credential")
    return row[0]


_PREPARED = False


def prepare() -> None:
    """Print the hub package measured and bring the copy to the migration head (lifespan is off)."""
    global _PREPARED
    if _PREPARED:
        return
    import hub

    loaded = os.path.normpath(os.path.dirname(os.path.abspath(hub.__file__)))
    print(f"hub package: {loaded}")
    if not loaded.startswith(HUB_DIR):
        sys.exit(f"loaded hub from {loaded}, expected under {HUB_DIR}")
    from hub.db.engine import _run_alembic_upgrade

    asyncio.run(_run_alembic_upgrade())
    print("copy migrated to head")
    _PREPARED = True


def client() -> httpx.AsyncClient:
    prepare()
    from hub.main import app

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://t",
        headers={"Authorization": f"Bearer {operator_key()}"},
        timeout=600,
    )


def p90(samples):
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]


async def get(cl, route):
    t = time.perf_counter()
    r = await cl.get(f"{BASE}/{route}")
    return r, (time.perf_counter() - t) * 1000


async def first_build(cl) -> str:
    r, _ = await get(cl, "project/builds")
    r.raise_for_status()
    body = r.json()
    rows = body if isinstance(body, list) else body.get("builds", [])
    if not rows:
        sys.exit("the copy has no build to read tasks of")
    return rows[0]["id"]


async def cmd_budgets(_args) -> int:
    failed = []
    async with client() as cl:
        build = await first_build(cl)
        for label, route, budget in BUDGETS:
            route = route.replace("{build}", build)
            for _ in range(WARMUPS):
                await get(cl, route)
            times = []
            status = 200
            for _ in range(CALLS):
                r, ms = await get(cl, route)
                status = r.status_code
                times.append(ms)
            mark = "ok  " if p90(times) <= budget and status == 200 else "FAIL"
            print(
                f"{mark} {label:18s} p90 {p90(times):7.0f} ms  budget {budget:4d} ms  "
                f"status {status}  [{', '.join(f'{t:.0f}' for t in times)}]"
            )
            if mark == "FAIL":
                failed.append(label)
    if failed:
        print(f"BUDGETS MISSED: {', '.join(failed)}")
        return 1
    print("every route within its budget")
    return 0


async def writer(stop: asyncio.Event, counts: dict) -> None:
    """5 agent-output rows and 2 trace spans a second, each its own commit, as agents write."""
    from datetime import datetime, timezone

    from hub.db.engine import async_session_factory
    from hub.db.models import AgentOutput, TraceSpan

    async def put(make):
        async with async_session_factory() as db:
            db.add(make())
            await db.commit()

    async def outputs():
        while not stop.is_set():
            await put(
                lambda: AgentOutput(
                    id=f"out-{uuid.uuid4().hex[:12]}",
                    project_id=PROJECT,
                    agent=WRITER_TAG,
                    content="x" * 1400,
                    kind="text",
                    timestamp=datetime.now(timezone.utc),
                )
            )
            counts["outputs"] += 1
            await asyncio.sleep(0.2)

    async def spans():
        while not stop.is_set():
            now = datetime.now(timezone.utc)
            await put(
                lambda: TraceSpan(
                    span_id=uuid.uuid4().hex[:16],
                    trace_id=uuid.uuid4().hex,
                    project_id=PROJECT,
                    name=WRITER_TAG,
                    operation="aw.request",
                    start_time=now,
                    trace_started_at=now,
                    attributes={},
                    events=[],
                )
            )
            counts["spans"] += 1
            await asyncio.sleep(0.5)

    await asyncio.gather(outputs(), spans())


def remove_writer_rows() -> None:
    con = sqlite3.connect(DB, timeout=60)
    try:
        con.execute("delete from agent_outputs where agent=?", (WRITER_TAG,))
        con.execute("delete from trace_spans where name=?", (WRITER_TAG,))
        con.commit()
    finally:
        con.close()


async def cmd_burst(args) -> int:
    counts = {"outputs": 0, "spans": 0}
    stop = asyncio.Event()
    wtask = None
    async with client() as cl:
        for route in SCREEN:  # warm-up, once, alone
            await get(cl, route)
        if args.with_writer:
            wtask = asyncio.create_task(writer(stop, counts))
            await asyncio.sleep(1.0)
        try:
            t = time.perf_counter()
            results = await asyncio.gather(*[get(cl, r) for r in SCREEN])
            wall = time.perf_counter() - t
        finally:
            stop.set()
            if wtask:
                await asyncio.gather(wtask, return_exceptions=True)
                remove_writer_rows()
    slowest = 0.0
    for route, (r, ms) in sorted(zip(SCREEN, results), key=lambda x: -x[1][1]):
        slowest = max(slowest, ms)
        print(f"  {ms:8.0f} ms  {r.status_code}  {route}")
    mode = "with writer" if args.with_writer else "alone"
    extra = f" (writer committed {counts['outputs']} outputs, {counts['spans']} spans)" if args.with_writer else ""
    print(f"burst {mode}: wall {wall:.1f} s, slowest {slowest / 1000:.1f} s{extra}")
    if slowest / 1000 > BURST_LIMIT_S:
        print(f"BURST TOO SLOW: slowest {slowest / 1000:.1f} s > {BURST_LIMIT_S} s")
        return 1
    return 0


async def cmd_conversations(_args) -> int:
    async with client() as cl:
        await get(cl, "conversations")
        times = [(await get(cl, "conversations"))[1] for _ in range(CALLS)]
    print(f"conversations p90 {p90(times):.0f} ms  budget {CONVERSATIONS_BUDGET_MS} ms")
    if p90(times) > CONVERSATIONS_BUDGET_MS:
        print("CONVERSATIONS TOO SLOW")
        return 1
    return 0


async def cmd_archive(_args) -> int:
    """Run the Hub's archive sweep on the copy twice (FR-11/FR-12). Mutates the copy."""
    import importlib

    sweep = None
    for modname, name in (
        ("hub.conversation_archive", "archive_finished_conversations"),
        ("hub.stalls", "archive_finished_conversations"),
    ):
        try:
            sweep = getattr(importlib.import_module(modname), name, None)
        except ImportError:
            sweep = None
        if sweep:
            break
    if sweep is None:
        print("archive sweep not built yet (hub.conversation_archive.archive_finished_conversations)")
        return 2

    from hub.db.engine import async_session_factory

    def counts():
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            return con.execute(
                "select count(*), sum(archived_by='hub'), sum(archived_by='operator'), "
                "sum(archived_at is null) from conversations where project_id=?",
                (PROJECT,),
            ).fetchone()
        finally:
            con.close()

    print("before:", counts())
    async with async_session_factory() as db:
        first = await sweep(db)
    mid = counts()
    print("after first sweep:", mid, "swept", first)
    async with async_session_factory() as db:
        second = await sweep(db)
    print("after second sweep:", counts(), "swept", second)
    if second:
        print("SECOND SWEEP ARCHIVED MORE")
        return 1
    return 0


def diff(before, after, path="", allow_added=frozenset()):
    """Differences between two JSON bodies; keys only in *after* named in allow_added are fine."""
    out = []
    if isinstance(before, dict) and isinstance(after, dict):
        for k in before.keys() | after.keys():
            if k in CLOCK_KEYS:
                continue
            p = f"{path}.{k}"
            if k not in after:
                out.append(f"{p}: missing after")
            elif k not in before:
                if k not in allow_added:
                    out.append(f"{p}: added")
            else:
                out += diff(before[k], after[k], p, allow_added)
    elif isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            out.append(f"{path}: length {len(before)} -> {len(after)}")
        for i, (b, a) in enumerate(zip(before, after)):
            out += diff(b, a, f"{path}[{i}]", allow_added)
    elif before != after:
        out.append(f"{path}: {str(before)[:60]!r} -> {str(after)[:60]!r}")
    return out


async def read_bodies(cl):
    build = await first_build(cl)
    bodies = {}
    for label, route in BODY_ROUTES:
        r, _ = await get(cl, route.replace("{build}", build))
        try:
            body = r.json()
        except ValueError:
            body = r.text
        bodies[label] = {"status": r.status_code, "body": body}
    return bodies


def writer_rows() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)
    try:
        return (
            con.execute("select count(*) from agent_outputs where agent=?", (WRITER_TAG,)).fetchone()[0]
            + con.execute("select count(*) from trace_spans where name=?", (WRITER_TAG,)).fetchone()[0]
        )
    finally:
        con.close()


async def cmd_bodies(args) -> int:
    # Leftover rows of a crashed --with-writer run would make the copy differ from a clean one.
    left = writer_rows()
    if left:
        remove_writer_rows()
        print(f"removed {left} leftover {WRITER_TAG} rows before reading")
    if writer_rows():
        print(f"REFUSED: {WRITER_TAG} rows still appear; a writer is running against this copy")
        return 2
    rc = await _bodies(args)
    if writer_rows():
        print(f"REFUSED: a {WRITER_TAG} row appeared while reading; the result cannot be trusted")
        return 2
    return rc


async def _bodies(args) -> int:
    async with client() as cl:
        if args.record:
            first = await read_bodies(cl)
            second = await read_bodies(cl)
            # A body that differs between two reads of an unchanged copy cannot be compared.
            unstable = [k for k in first if diff(first[k], second[k])]
            with open(args.record, "w") as f:
                json.dump({"routes": first, "unstable": unstable}, f, sort_keys=True)
            print(f"recorded {len(first)} routes to {args.record}; unstable between reads: {unstable}")
            return 0
        with open(args.against) as f:
            recorded = json.load(f)
        now = await read_bodies(cl)
    bad = 0
    for label, was in recorded["routes"].items():
        if label in recorded["unstable"]:
            print(f"skip {label}: differed between two reads when recorded")
            continue
        allow = frozenset({"counts_at"}) if label == "trace settings" else frozenset()
        d = diff(was, now.get(label), "", allow)
        if d:
            bad += 1
            print(f"DIFFERS {label}: {len(d)} difference(s), first: {d[:3]}")
        else:
            print(f"same   {label}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("budgets")
    b = sub.add_parser("burst")
    b.add_argument("--with-writer", action="store_true")
    sub.add_parser("archive")
    sub.add_parser("conversations")
    bo = sub.add_parser("bodies")
    g = bo.add_mutually_exclusive_group(required=True)
    g.add_argument("--record")
    g.add_argument("--against")
    args = ap.parse_args()
    fn = {
        "budgets": cmd_budgets,
        "burst": cmd_burst,
        "archive": cmd_archive,
        "conversations": cmd_conversations,
        "bodies": cmd_bodies,
    }[args.cmd]
    prepare()
    return asyncio.run(fn(args))


if __name__ == "__main__":
    sys.exit(main())
