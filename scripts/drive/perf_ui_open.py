"""Acceptance drive for slice 4 of the performance overhaul: the app opens fast and stays smooth.

    py -3.11 scripts/drive/perf_ui_open.py --scenario open   --ui-dir <a vite build output>
    py -3.11 scripts/drive/perf_ui_open.py --scenario stream --ui-dir <a vite build output>

`--ui-dir` is the UI under test: a `vite build --outDir <tmp>` of the source, so the drive measures
the source rather than the committed bundle. Every non-API request the page makes is answered from
it. Each scenario prints its measurement and exits 0 on pass, 1 on fail, 2 when it could not run.

Safety, inherited from `perf_responsive.py` and enforced in its code: the source database is only
ever read (`mode=ro`) into a scratch copy, the scratch Hub runs on that copy with its lifespan off,
on a free port that is never 8000 (nor 8010), and nothing contacts another Hub.

Scenarios (budgets in BUDGET below, all at a 6x-throttled CPU unless --throttle says otherwise):
  open    First open of a project with 25 projects in the sidebar: API requests, JavaScript loaded
          before the project screen is usable, script time, and time until it is usable.
  stream  A 1,000-row conversation, open, while 90 lines a minute stream into it: dropped frames
          and long main-thread tasks.
"""

from __future__ import annotations

import argparse
import asyncio
import mimetypes
import sqlite3
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import perf_responsive as pr  # noqa: E402  (shared copy/Hub/safety helpers)

from perf_responsive import (  # noqa: E402
    PROJECT,
    REPO,
    CannotRun,
    ScratchHub,
    api_client,
    make_copy,
    p,
    post_output,
    use_db,
)

SOURCE_DB = Path.home() / "aw-perf" / "real.db"
FORBIDDEN_PORTS = {8000, 8010}

BUDGET = {
    # open
    "api_requests": 15,
    "js_kb_before_usable": 700,
    "usable_s": 4.0,
    # stream
    "dropped_frame_pct": 10.0,
    "longest_task_ms": 150.0,
    "long_task_ms_per_line": 40.0,
}

SEED = """
// No session is seeded: the page takes the Hub's key from /setup/token as the desktop app does. A
// seeded key that differs from it is replaced mid-load, and that refetches every query once.
try { localStorage.setItem('agentweave-selected-project', %(proj)r); } catch (e) {}
window.__perf = {longTasks: [], frames: [], recording: false};
try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) window.__perf.longTasks.push({start: e.startTime, ms: e.duration});
  }).observe({type: 'longtask', buffered: true});
} catch (e) {}
(function loop(prev) {
  requestAnimationFrame((t) => { if (window.__perf.recording) window.__perf.frames.push(t - prev); loop(t); });
})(performance.now());
"""


# ------------------------------------------------------------------------------------- the copy


def seed_projects(db: Path, tmp: Path, total: int = 25) -> int:
    """Bring the copy up to `total` registered projects, as on the trial Hub the cost was measured on."""
    c = sqlite3.connect(str(db))
    try:
        have = c.execute("select count(*) from projects").fetchone()[0]
        cols = [r[1] for r in c.execute("pragma table_info(projects)")]
        template = c.execute(f"select {', '.join(cols)} from projects where id != ? limit 1", (PROJECT,)).fetchone()
        if template is None:
            template = c.execute(f"select {', '.join(cols)} from projects limit 1").fetchone()
        for i in range(total - have):
            row = dict(zip(cols, template))
            pid = f"proj-perf{i:07d}"
            wd = (tmp / f"project-{i}").resolve()
            wd.mkdir()
            row.update(id=pid, name=f"Perf project {i}", working_directory=str(wd),
                       path_key="windows:" + str(wd).lower(), directory_state="available")
            c.execute(f"insert into projects ({', '.join(cols)}) values ({', '.join('?' for _ in cols)})",
                      [row[k] for k in cols])
        c.commit()
        return c.execute("select count(*) from projects").fetchone()[0]
    finally:
        c.close()


def long_conversation(db: Path, rows: int = 1000) -> Dict[str, Optional[str]]:
    """The project's largest conversation, open, padded to `rows` output rows with older copies of its own."""
    c = sqlite3.connect(str(db))
    try:
        conv, agent, session = c.execute(
            "select o.conversation_id, o.agent, c.provider_session_id from agent_outputs o "
            "join conversations c on c.id = o.conversation_id where o.project_id=? "
            "group by o.conversation_id order by count(*) desc limit 1", (PROJECT,)).fetchone()
        c.execute("update conversations set lifecycle='open', archived_at=null, updated_at=datetime('now') where id=?",
                  (conv,))
        c.execute("update agents set lifecycle='open', archived_at=null where project_id=? and name=?", (PROJECT, agent))
        cols = [r[1] for r in c.execute("pragma table_info(agent_outputs)")]
        have = c.execute("select count(*) from agent_outputs where conversation_id=?", (conv,)).fetchone()[0]
        src = c.execute(f"select {', '.join(cols)} from agent_outputs where conversation_id=? order by timestamp, id",
                        (conv,)).fetchall()
        n, k = have, 0
        while n < rows:
            row = dict(zip(cols, src[k % len(src)]))
            row["id"] = f"perfpad-{k:06d}"
            row["timestamp"] = "2020-01-01 00:00:00." + f"{k:06d}"
            row["run_id"] = f"perfpad-run-{k // 50}"
            c.execute(f"insert into agent_outputs ({', '.join(cols)}) values ({', '.join('?' for _ in cols)})",
                      [row[x] for x in cols])
            n, k = n + 1, k + 1
        c.commit()
        return {"agent": agent, "conversation_id": conv, "session_id": session, "rows": n}
    finally:
        c.close()


async def migrate(db: Path, hub_dir: Path) -> None:
    """Point this process's Hub at the copy and bring the copy to this checkout's schema head.

    With the lifespan off nothing else would, and a copy behind head lacks the indexes the routes
    are written against (0144 alone takes `/agents` from 12s to milliseconds on the copy)."""
    use_db(db, hub_dir)
    from hub.db.engine import init_db

    await init_db()


# ---------------------------------------------------------------------------------- the browser


class UiServer:
    """Answers every non-API request from `ui_dir`, and records the JavaScript it served and when."""

    def __init__(self, ui_dir: Path, base: str) -> None:
        self.ui_dir, self.base = ui_dir, base
        self.js: List[Dict[str, Any]] = []
        if not (ui_dir / "index.html").exists():
            raise CannotRun(f"{ui_dir} has no index.html (build the UI into it first)")

    async def handle(self, route: Any) -> None:
        url = route.request.url
        if not url.startswith(self.base):
            return await route.abort()
        path = url[len(self.base):].split("?")[0]
        if path.startswith("/api") or path.startswith("/health"):
            return await route.continue_()
        fp = self.ui_dir / path.lstrip("/") if path.startswith("/assets/") else self.ui_dir / "index.html"
        if not fp.is_file():
            fp = self.ui_dir / "index.html"
        body = fp.read_bytes()
        ct = "text/javascript" if fp.suffix == ".js" else (mimetypes.guess_type(fp.name)[0] or "application/octet-stream")
        if fp.suffix == ".js":
            self.js.append({"t": time.time(), "path": path, "bytes": len(body)})
        await route.fulfill(status=200, body=body, headers={"content-type": ct})


async def open_page(pw: Any, hub: ScratchHub, ui: UiServer, throttle: float, url: str):
    browser = await pw.chromium.launch()
    ctx = await browser.new_context(viewport={"width": 1600, "height": 1000})
    await ctx.add_init_script(SEED % {"proj": PROJECT})
    page = await ctx.new_page()
    await page.route("**/*", ui.handle)
    cdp = await ctx.new_cdp_session(page)
    await cdp.send("Performance.enable")
    await cdp.send("Network.enable")
    await cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    await cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
    log = pr.RequestLog(page, hub.base)
    t0 = time.time()
    await page.goto(hub.base + url, wait_until="domcontentloaded")
    return browser, page, cdp, log, t0


async def metrics(cdp: Any) -> Dict[str, float]:
    return {m["name"]: m["value"] for m in (await cdp.send("Performance.getMetrics"))["metrics"]}


async def settle(log: Any, quiet: float = 4.0, limit: float = 60.0) -> None:
    """Wait until no request but the event stream is in flight and none has started for `quiet` s."""
    end = time.time() + limit
    while time.time() < end:
        rows = [r for r in log.rows if not r["path"].endswith("/events")]
        live = [r for r in log.live.values() if not r["path"].endswith("/events")]
        if not live and time.time() - max([r["t0"] for r in rows] or [0]) >= quiet:
            return
        await asyncio.sleep(0.5)
    p(f"  WARNING: the tab never went quiet within {limit:.0f}s")


def print_profile(profile: Dict[str, Any], top: int = 30) -> None:
    """Self time by function from a CDP CPU profile (use with an unminified build)."""
    nodes = {n["id"]: n for n in profile["nodes"]}
    self_ms: Dict[str, float] = {}
    for sample, delta in zip(profile["samples"], profile["timeDeltas"]):
        cf = nodes[sample]["callFrame"]
        key = f"{cf['functionName'] or '(anon)'}  {cf['url'].rsplit('/', 1)[-1]}:{cf['lineNumber'] + 1}"
        self_ms[key] = self_ms.get(key, 0.0) + delta / 1000.0
    for key, ms in sorted(self_ms.items(), key=lambda kv: -kv[1])[:top]:
        p(f"     {ms:8.1f} ms  {key}")


def check(name: str, value: float, limit: float, unit: str = "") -> bool:
    ok = value <= limit
    p(f"  {'ok  ' if ok else 'FAIL'} {name}: {value:g}{unit}  (budget <= {limit:g}{unit})")
    return ok


# ---------------------------------------------------------------------------------- scenarios


async def sc_open(args: argparse.Namespace, db: Path, tmp: Path) -> int:
    n = seed_projects(db, tmp)
    p(f"  projects in the sidebar: {n}")
    await migrate(db, args.hub_dir)
    from playwright.async_api import async_playwright

    async with ScratchHub(db, lifespan=False) as hub, async_playwright() as pw:
        if hub.port in FORBIDDEN_PORTS:
            raise CannotRun(f"refusing :{hub.port}")
        ui = UiServer(args.ui_dir, hub.base)
        browser, page, cdp, log, t0 = await open_page(pw, hub, ui, args.throttle, f"/?project={PROJECT}")
        try:
            await page.locator("[data-testid='topbar']").first.wait_for(timeout=60000)
            await page.locator(f"[data-testid='rail-project-{PROJECT}']").first.wait_for(timeout=60000)
            await page.locator("[data-testid^='agent-card-']").first.wait_for(timeout=60000)
        except Exception as e:  # noqa: BLE001
            shot = tmp / "open-failed.png"
            await page.screenshot(path=str(shot))
            raise CannotRun(f"the project screen never became usable ({type(e).__name__}); screenshot {shot}")
        t_usable = time.time()
        m_usable = await metrics(cdp)
        await page.wait_for_timeout(3000)
        rows = log.gets(t0, t_usable + 3.0)
        await browser.close()
    js_before = sum(x["bytes"] for x in ui.js if x["t"] <= t_usable)
    paths = sorted({r["path"] for r in rows})
    per_project = [r for r in rows if r["url"].split("?")[0].endswith("/conversations")]
    p(f"  API GETs from open until 3s after usable: {len(rows)} ({len(per_project)} conversation listings)")
    for path in paths:
        p(f"     {sum(1 for r in rows if r['path'] == path):3d}  {path}")
    if args.verbose:
        for r in sorted(rows, key=lambda r: r["t0"]):
            end = f"{r['t1'] - t0:6.2f}" if r["t1"] else "  open"
            p(f"     {r['t0'] - t0:6.2f} -> {end}  {r['url'][len(r['url'].split('/api/')[0]):]}")
    p(f"  JS files before usable:{[x['path'] for x in ui.js if x['t'] <= t_usable]}")
    p(f"  ScriptDuration at usable: {m_usable.get('ScriptDuration', 0):.2f}s, TaskDuration {m_usable.get('TaskDuration', 0):.2f}s")
    ok = check("API requests", len(rows), BUDGET["api_requests"])
    ok &= check("JS before usable", round(js_before / 1024), BUDGET["js_kb_before_usable"], " KB")
    ok &= check("time to usable", round(t_usable - t0, 2), BUDGET["usable_s"], " s")
    return 0 if ok else 1


async def sc_stream(args: argparse.Namespace, db: Path, tmp: Path) -> int:
    who = long_conversation(db)
    p(f"  conversation {who['conversation_id']} of {who['agent']}: {who['rows']} output rows")
    await migrate(db, args.hub_dir)
    from playwright.async_api import async_playwright

    async with ScratchHub(db, lifespan=False) as hub, async_playwright() as pw:
        if hub.port in FORBIDDEN_PORTS:
            raise CannotRun(f"refusing :{hub.port}")
        ui = UiServer(args.ui_dir, hub.base)
        url = f"/?project={PROJECT}&agent={who['agent']}&conversation={who['conversation_id']}"
        browser, page, cdp, log, _t0 = await open_page(pw, hub, ui, args.throttle, url)
        try:
            await page.locator("[data-testid='conversation-pane']").first.wait_for(timeout=90000)
            await page.locator("[data-turn-boundary]").first.wait_for(timeout=90000)
        except Exception as e:  # noqa: BLE001
            shot = tmp / "stream-failed.png"
            await page.screenshot(path=str(shot))
            raise CannotRun(f"the conversation never opened ({type(e).__name__}); screenshot {shot}")
        await settle(log)
        if args.verbose:
            p("  GETs while opening:", pr.tally(log.gets(0)))
        turns = await page.locator("[data-turn-boundary]").count()
        p(f"  turns rendered: {turns}")
        await page.evaluate("() => { window.__perf.longTasks = []; window.__perf.frames = []; window.__perf.recording = true }")
        t_start = await page.evaluate("() => performance.now()")
        t_wall = time.time()
        lines, interval = int(args.lines), 60.0 / args.per_minute
        run_id = f"perf-ui-run-{uuid.uuid4().hex[:6]}"
        marker = f"perf-ui-last-{uuid.uuid4().hex[:6]}"
        if args.profile:
            await cdp.send("Profiler.enable")
            await cdp.send("Profiler.start")
        async with api_client(base=hub.base) as c:
            started = time.perf_counter()
            for i in range(lines):
                text = marker if i == lines - 1 else (
                    f"Line {i + 1} of the streamed answer: **checked** `hub/hub/api/v1/agent_chat.py` "
                    f"and the [timeline](#) — item {i + 1}.")
                await post_output(c, who, text, 10_000 + i, run_id)
                await asyncio.sleep(max(0.0, started + (i + 1) * interval - time.perf_counter()))
        # Recording stops before the marker is looked for: Playwright's text search walks the whole
        # 1,000-row DOM, and on a throttled CPU that search would be most of what was measured.
        await page.wait_for_timeout(2000)
        perf = await page.evaluate("() => { window.__perf.recording = false; return window.__perf }")
        if args.profile:
            print_profile((await cdp.send("Profiler.stop"))["profile"])
        try:
            await page.get_by_text(marker).first.wait_for(timeout=30000)
            visible = True
        except Exception:  # noqa: BLE001
            visible = False
        await browser.close()
    tasks = [t for t in perf["longTasks"] if t["start"] >= t_start]
    frames = perf["frames"]
    frame_ms = 1000 / 60
    dropped = sum(max(0, round(f / frame_ms) - 1) for f in frames)
    expected = len(frames) + dropped
    pct = 100.0 * dropped / expected if expected else 0.0
    total_long = sum(t["ms"] for t in tasks)
    longest = max([t["ms"] for t in tasks] or [0.0])
    if args.verbose:
        p("  GETs while streaming:", pr.tally(log.gets(t_wall)))
    p(f"  last line visible: {visible}")
    p(f"  frames {len(frames)}, dropped {dropped} ({pct:.1f}%); long tasks {len(tasks)}, "
      f"total {total_long:.0f} ms, longest {longest:.0f} ms, per line {total_long / lines:.1f} ms")
    ok = visible
    ok &= check("dropped frames", round(pct, 1), BUDGET["dropped_frame_pct"], " %")
    ok &= check("longest task", round(longest), BUDGET["longest_task_ms"], " ms")
    ok &= check("long-task time per line", round(total_long / lines, 1), BUDGET["long_task_ms_per_line"], " ms")
    return 0 if ok else 1


def parse() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", required=True, choices=["open", "stream"])
    ap.add_argument("--ui-dir", type=Path, required=True, help="a vite build output of the UI under test")
    ap.add_argument("--db", type=Path, default=SOURCE_DB, help="SOURCE database to copy (read-only)")
    ap.add_argument("--hub-dir", type=Path, default=REPO / "hub")
    ap.add_argument("--throttle", type=float, default=6.0)
    ap.add_argument("--lines", type=int, default=90)
    ap.add_argument("--per-minute", type=float, default=90.0)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--profile", action="store_true", help="stream: print self time by function")
    return ap.parse_args()


async def amain(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="perf-ui-open-", ignore_cleanup_errors=True) as t:
        tmp = Path(t)
        db = make_copy(args.db, tmp)
        if not pr.project_exists(db):
            raise CannotRun(f"{PROJECT} is not in {args.db}")
        p(f"scenario {args.scenario} at {args.throttle:g}x CPU: source {args.db} (read-only) -> {db}; UI {args.ui_dir}")
        return await (sc_open if args.scenario == "open" else sc_stream)(args, db, tmp)


def main() -> int:
    args = parse()
    try:
        code = asyncio.run(amain(args))
    except CannotRun as e:
        p(f"CANNOT RUN: {e}")
        return 2
    p(f"{args.scenario}: {'PASS' if code == 0 else 'FAIL'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
