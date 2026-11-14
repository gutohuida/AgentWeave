"""Acceptance drive for `dashboards-that-feel-alive-and-draw-right-the-first-time` (spdoc-17a01f1f5008).

The change's `acceptance-drive` task (DTFAD-1), written and recorded on today's master before the
slice's other tasks are built; the change's last task (`run-acceptance-drive`) runs it green. It
checks every acceptance criterion of the document, each as its own check, and ends by printing one
line per check in the drive-baseline form the Hub reads:

    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>

The motion is already on master (5a9d179), so its criteria (ac-draw-in, ac-values-move,
ac-edit-visible, ac-tooltip, ac-skeleton, ac-reduced-motion) may pass on the first run. The
guidance criteria (ac-guidance, ac-examples-draw) fail on today's master, their detail naming the
missing guidance or examples; ac-first-time-right is three real Haiku turns (--turns), every one of
which must build the five kinds cleanly, since a single turn on the pre-guidance code sometimes does.

It starts its own Hub from this checkout on a free port with a throwaway database and bootstrap key
(never :8000, never the shared trial :8010), with the real `claude` on PATH; the analyst agent is
bound to Haiku. One project, seeded with slice first-dashboard's helpers
(scripts/drive/dashboards_drive.py) plus a week of runs, some of them failed. Every browser step is
Chromium through Playwright; the page's own timers sample the motion (a Python round trip is too
slow for a 0.3 s sample), and a wrapper around `fetch` slows the run route where a criterion needs
the queries to take a while.

    py -3.11 scripts/drive/dashboards_motion_drive.py [--no-browser] [--only ac-draw-in ...] [--turns 3]

Exit 0 only when every check passes. AW_DRIVE_KEEP=1 leaves the Hub running.

THE CONTRACT this drive assumes (the document's design; a build that names something differently
changes this file, not the spec). Slices 1 and 2's routes, tools and test ids as in
dashboards_drive.py and dashboard_edit_drive.py, and the motion on master:
  dashboard-panel                    data-state shown|new; a removed panel is kept as
                                     dashboard-panel-leaving (data-state leaving) while it fades
  dashboard-skeleton                 the placeholders while the queries first run
  dashboard-tooltip                  the hovered mark's tooltip: label, series, value
  dashboard-number                   holds the real figure throughout; the count is an aria-hidden
                                     sibling drawn over it while it runs
  .aw-dash-panels.is-refreshing      while a run is fetched again; .aw-dash-chart dims under it
  .aw-dash-bar (svg, one per bar), .aw-dash-line (path, pathLength 1), .aw-dash-dot,
  .aw-dash-mark                      the marks the motion moves, and the ones hovering dims
Guidance (the guidance task):
  save_dashboard's description       names the kind for each kind of question and the four shaping
                                     rules (row order, about 15 bars by taking the top, time in
                                     order for a line, aliases as the legend and tooltip names)
  The seeded data note (src-27723331ae1d) carries each worked example as a fenced ```sql block
                                     preceded by a `Kind: `<kind>`.` line (or whose first line is
                                     `-- kind: <kind>`), one per kind.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dashboards_drive as dd  # noqa: E402 -- slice first-dashboard's helpers
import dashboard_edit_drive as ded  # noqa: E402 -- slice change-a-dashboard-by-asking's helpers
from dashboards_drive import CHECKS, Check, api, dashboards_list, p, panels_of_run, poll, run_check, said  # noqa: E402

# This drive's own scratch (the edit drive's import pointed the helpers at its own; re-point them).
dd.TMP = dd.TMP.parent.parent / "drive-dashboards-motion" / dd.STAMP
dd.DB = dd.TMP / "hub" / "agentweave.db"
dd.SHOTS = dd.TMP / "shots"
TMP, DB, SHOTS, STAMP, HAIKU = dd.TMP, dd.DB, dd.SHOTS, dd.STAMP, dd.HAIKU

ANALYST = "analyst"
KINDS = ("number", "table", "bar", "stacked_bar", "line")
NOTE_ID = "src-27723331ae1d"
ASK = ("Make me a dashboard with this week's cost as one figure, cost per spec, send-backs per model "
       "by reason, runs per day, and the latest failed runs.")

# ------------------------------------------------------------------------------------------ queries

Q_TOKENS = "select sum(total_tokens) as tokens from turn_usage"
Q_STATUS = "select status, count(*) as tasks from tasks group by status order by status"
Q_STATUS_BUMPED = ("select status, count(*) + (case when status = 'pending' then 3 else 0 end) as tasks "
                   "from tasks group by status order by status")
Q_STACKED = ("select spec_task_key as kind, sum(status = 'approved') as approved, "
             "sum(status <> 'approved') as open from tasks group by kind order by kind")
Q_DAYS = "select date(started_at) as day, count(*) as runs from runs group by day order by day"
Q_TITLES = "select title, status from tasks order by title"
Q_AGENTS = "select agent, count(*) as runs from runs group by agent order by runs desc"
Q_FOUR = ("with v(region, tasks) as (values ('North', 4), ('South', 7), ('East', 2), ('West', 5)) "
          "select region, tasks from v")
Q_SIX = ("with v(day, runs) as (values ('Mon', 3), ('Tue', 5), ('Wed', 4), ('Thu', 8), ('Fri', 6), "
         "('Sat', 2)) select day, runs from v")

#: Wraps fetch so the run route answers `window.__slowRunMs` late; set before the app loads.
SLOW_FETCH = """
(() => {
  const original = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const ms = window.__slowRunMs || 0;
    if (ms && /\\/dashboards\\/[^/?]+\\/run/.test(url)) await new Promise((r) => setTimeout(r, ms));
    return original(input, init);
  };
})();
"""

#: Samples the open dashboard each frame from the first panel's arrival until `until` ms.
DRAW_IN = """
async ([marks, until]) => {
  const frame = () => new Promise((r) => requestAnimationFrame(r));
  const deadline = performance.now() + 20000;
  let t0 = null;
  while (performance.now() < deadline) {
    if (document.querySelector('[data-testid=dashboard-panel]')) { t0 = performance.now(); break; }
    await frame();
  }
  if (t0 === null) return { error: 'no dashboard-panel appeared within 20 s' };
  const widths = (kind) => [...document.querySelectorAll(
    `[data-testid=dashboard-panel][data-kind=${kind}] .aw-dash-bar`)].map((e) => e.getBoundingClientRect().width);
  const sample = (t) => {
    const num = document.querySelector('[data-testid=dashboard-number]');
    const overlay = num && num.parentElement.querySelector('[aria-hidden=true]');
    return {
      t,
      bar: widths('bar'),
      stacked: widths('stacked_bar'),
      line: [...document.querySelectorAll('[data-kind=line] .aw-dash-line')].map(
        (e) => parseFloat(getComputedStyle(e).strokeDashoffset)),
      dots: [...document.querySelectorAll('[data-kind=line] .aw-dash-dot')].map((e) => {
        const s = getComputedStyle(e);
        return [parseFloat(s.opacity), s.transform];
      }),
      panels: [...document.querySelectorAll('[data-testid=dashboard-panel]')].map(
        (e) => parseFloat(getComputedStyle(e).opacity)),
      number: num ? num.textContent : null,
      overlay: overlay ? overlay.textContent : null,
    };
  };
  const out = { samples: {}, numbers: [] };
  const pending = Object.entries(marks);
  for (;;) {
    const t = performance.now() - t0;
    const num = document.querySelector('[data-testid=dashboard-number]');
    out.numbers.push(num ? num.textContent : null);
    for (let i = pending.length - 1; i >= 0; i--) {
      if (t >= pending[i][1]) { out.samples[pending[i][0]] = sample(t); pending.splice(i, 1); }
    }
    if (t >= until && !pending.length) break;
    await frame();
  }
  return out;
}
"""

#: Starts a per-frame record of the open dashboard into window.__tl; tags the bars first.
WATCH = """
([removed, added]) => {
  const bars = () => [...document.querySelectorAll('[data-testid=dashboard-panel][data-kind=bar] .aw-dash-bar')];
  window.__tagged = bars().map((e) => ({ el: e, w: e.getBoundingClientRect().width, label: e.getAttribute('aria-label') }));
  window.__tl = [];
  window.__stop = false;
  const t0 = performance.now();
  const view = () => document.querySelector('[data-testid=dashboard-view]');
  const loop = () => {
    const panels = document.querySelector('.aw-dash-panels');
    const chart = document.querySelector('[data-testid=dashboard-panel][data-kind=bar] .aw-dash-chart');
    const state = (id) => {
      const el = id && document.querySelector(`[data-panel-id='${id}']`);
      return el ? el.getAttribute('data-state') : null;
    };
    const v = view();
    window.__tl.push({
      t: performance.now() - t0,
      refreshing: !!panels && panels.classList.contains('is-refreshing'),
      opacity: chart ? parseFloat(getComputedStyle(chart).opacity) : null,
      running: v ? document.getAnimations().filter((a) => a.playState === 'running' && a.effect
        && a.effect.target && v.contains(a.effect.target)).map((a) => `${a.animationName || a.transitionProperty
        || a.constructor.name} on <${a.effect.target.tagName.toLowerCase()} class="${a.effect.target.getAttribute('class') || ''}">`) : null,
      removed: state(removed),
      added: state(added),
      ids: [...document.querySelectorAll('[data-testid=dashboard-panel]')].map((e) => e.getAttribute('data-panel-id')),
    });
    if (!window.__stop && window.__tl.length < 20000) requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
  return window.__tagged.length;
}
"""

#: After a run: the tagged bars, whether each is still the element on screen, and its new width.
TAGGED = """
() => {
  window.__stop = true;
  const now = [...document.querySelectorAll('[data-testid=dashboard-panel][data-kind=bar] .aw-dash-bar')];
  return {
    same: now.length === window.__tagged.length && now.every((e, i) => e === window.__tagged[i].el),
    bars: window.__tagged.map((x) => ({ connected: x.el.isConnected, before: x.w,
      after: x.el.getBoundingClientRect().width, label_before: x.label, label_after: x.el.getAttribute('aria-label') })),
    timeline: window.__tl,
  };
}
"""


def number_of(text: Any) -> Optional[float]:
    try:
        return float(str(text).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def identity(transform: str) -> bool:
    return transform in ("none", "matrix(1, 0, 0, 1, 0, 0)")


def fetched_at(page: Any) -> Optional[str]:
    el = page.get_by_test_id("dashboard-fetched-at")
    return el.first.get_attribute("data-fetched-at") if el.count() else None


#: The checks, in the order they run: the agent's turn last, since its dashboard adds to the list.
ORDER = ("ac-guidance", "ac-examples-draw", "ac-draw-in", "ac-skeleton", "ac-tooltip", "ac-reduced-motion",
         "ac-values-move", "ac-edit-visible", "ac-first-time-right")


class Drive:
    def __init__(self, browser: bool, only: Optional[List[str]] = None, turns: int = 3) -> None:
        self.browser = browser
        self.turns = turns
        self.only = only
        self.hub = dd.SubprocessHub()
        self.a = ""
        self.tools: Dict[str, str] = {}
        self.d: Dict[str, Dict[str, Any]] = {}

    # -- setup

    def setup(self) -> None:
        TMP.mkdir(parents=True, exist_ok=True)
        dd.TOOLS = ("save_dashboard",)
        self.tools = dd.contract_in_checkout()["tools"]
        self.hub.start()
        self.a, _ = dd.open_project("A")
        dd.seed_project("A", self.a)
        self.seed_week()
        code, runner = api("POST", f"/projects/{self.a}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
        if code not in (200, 201):
            raise SystemExit(f"setup error: runner: {said(code, runner)}")
        code, out = api("POST", f"/projects/{self.a}/agents", {"name": ANALYST, "runner_id": runner["id"]})
        if code not in (200, 201):
            raise SystemExit(f"setup error: agent: {said(code, out)}")
        seeds = {
            "draw": (f"Draw in {STAMP}", [("Tokens", Q_TOKENS, "number"), ("By status", Q_STATUS, "bar"),
                                          ("Approved by kind", Q_STACKED, "stacked_bar"), ("Runs by day", Q_DAYS, "line")]),
            "move": (f"Values move {STAMP}", [("By status", Q_STATUS, "bar"), ("Runs by day", Q_DAYS, "line")]),
            "four": (f"Four panels {STAMP}", [("Tokens", Q_TOKENS, "number"), ("By status", Q_STATUS, "bar"),
                                              ("Titles", Q_TITLES, "table"), ("Runs by day", Q_DAYS, "line")]),
            "tip": (f"Tooltip {STAMP}", [("Regions", Q_FOUR, "bar"), ("Week", Q_SIX, "line")]),
            "calm": (f"Reduced motion {STAMP}", [("Tokens", Q_TOKENS, "number"), ("By status", Q_STATUS, "bar"),
                                                 ("Runs by day", Q_DAYS, "line")]),
        }
        for role, (name, panels) in seeds.items():
            self.d[role] = ded.create(self.a, name, panels)
        p(f"project A {self.a}; {len(self.d)} dashboards; analyst on {HAIKU}")

    def seed_week(self) -> None:
        """Runs on each of the last seven days, with cost, a third of them failed."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        statements: List[Tuple[str, Tuple]] = []
        for day in range(7):
            for k in range(1 + day % 3):
                run_id = dd.hexid("run-")
                start = now - timedelta(days=day, hours=1 + k)
                failed = (day + k) % 3 == 0
                statements.append((
                    "insert into runs (id, project_id, agent, status, started_at, ended_at, initiator, error) "
                    "values (?,?,?,?,?,?,?,?)",
                    (run_id, self.a, "builder", "failed" if failed else "completed", dd.ts(start),
                     dd.ts(start + timedelta(minutes=5)), "autonomous",
                     f"seeded failure {day}-{k}: exit 1" if failed else None)))
                statements.append((
                    "insert into turn_usage (id, run_id, project_id, agent, status, runner, model, "
                    "api_equivalent_usd_micros, input_tokens, output_tokens, total_tokens, observed_at) "
                    "values (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (dd.hexid("tu-"), run_id, self.a, "builder", "measured", "claude", "claude-sonnet-5-5",
                     250_000 + 10_000 * day, 1000, 200, 1200, dd.ts(start + timedelta(minutes=5)))))
        dd.rw(statements)

    def id(self, role: str) -> str:
        return self.d[role]["id"]

    def run_of(self, role: str) -> List[Dict[str, Any]]:
        code, out = api("GET", f"/projects/{self.a}/dashboards/{self.id(role)}/run")
        return panels_of_run(out) if code == 200 else []

    # -- the browser

    def with_page(self, fn: Callable[[Any], Any], scheme: str = "light", reduced: bool = False,
                  slow_ms: int = 0, shot: str = "") -> Any:
        """A fresh browser on the Dashboards screen with the dashboard list shown; answers fn(page)."""
        from playwright.sync_api import sync_playwright

        SHOTS.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            chromium = pw.chromium.launch()
            ctx = chromium.new_context(viewport={"width": 1400, "height": 1000}, color_scheme=scheme,
                                       reduced_motion="reduce" if reduced else "no-preference", locale="en-US")
            ctx.add_init_script(
                "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
                "localStorage.setItem('agentweave-selected-project', %r);"
                "localStorage.setItem('agentweave-theme', %r);" % (dd.KEY, dd.HUB, self.a, scheme))
            ctx.add_init_script(SLOW_FETCH + f"\nwindow.__slowRunMs = {int(slow_ms)};")
            page = ctx.new_page()
            page.on("dialog", lambda d: d.accept())
            page.goto(f"{dd.HUB}/?project={self.a}&tab=dashboards", wait_until="domcontentloaded")
            poll(lambda: page.get_by_test_id("dashboard-row").count(), 20, 0.5)
            try:
                return fn(page)
            finally:
                if shot:
                    page.screenshot(path=str(SHOTS / f"{shot}.png"), full_page=True)
                    p(f"  screenshot {SHOTS / f'{shot}.png'}")
                chromium.close()

    def click_open(self, page: Any, role: str) -> bool:
        row = page.locator(f"[data-testid=dashboard-row][data-dashboard-id='{self.id(role)}']")
        if not row.count():
            return False
        row.first.click()
        return True

    def open_settled(self, page: Any, role: str) -> bool:
        if not self.click_open(page, role):
            return False
        ok = poll(lambda: page.get_by_test_id("dashboard-panel").count(), 20, 0.3)
        page.wait_for_timeout(2500)  # every draw-in done
        return bool(ok)

    def need_browser(self, c: Check) -> bool:
        if not self.browser:
            c.judge("driven in the browser", False, "--no-browser given")
        return self.browser

    # -- FR-1

    def ac_draw_in(self, c: Check) -> None:
        if not self.need_browser(c):
            return
        want = next((x for x in self.run_of("draw") if x.get("kind") == "number"), {})
        want_value = (want.get("rows") or [[None]])[0][0]
        marks = {"at01": 100, "at03": 300, "at15": 1500, "settled": 3500}

        def go(page: Any) -> Any:
            if not self.click_open(page, "draw"):
                return {"error": "no dashboard-row for the dashboard"}
            return page.evaluate(DRAW_IN, [marks, 3500])

        out = self.with_page(go, shot="draw-in-settled")
        if not isinstance(out, dict) or out.get("error"):
            c.judge("the dashboard opened and its panels arrived", False, str(out))
            return
        s = out["samples"]
        early, mid, done, fin = s["at01"], s["at03"], s["at15"], s["settled"]
        c.judge("the panels arrive one after another (at 0.1 s the first is further in than the last)",
                len(early["panels"]) == 4 and early["panels"][0] > early["panels"][-1],
                f"panel opacities at {early['t']:.0f} ms: {early['panels']}")
        for kind in ("bar", "stacked"):
            pairs = [(m, f) for m, f in zip(mid[kind], fin[kind]) if f > 2]
            c.judge(f"at 0.3 s every {kind} bar is narrower than its final width",
                    bool(pairs) and all(m < f - 0.5 for m, f in pairs),
                    f"at {mid['t']:.0f} ms {mid[kind]} vs final {fin[kind]}")
            c.judge(f"by 1.5 s every {kind} bar is at its final width",
                    bool(fin[kind]) and len(done[kind]) == len(fin[kind])
                    and all(abs(d - f) <= 0.5 for d, f in zip(done[kind], fin[kind])),
                    f"at {done['t']:.0f} ms {done[kind]} vs final {fin[kind]}")
        c.judge("at 0.3 s the line is partly drawn (0 < dash offset < 1)",
                bool(mid["line"]) and all(0.001 < x < 0.999 for x in mid["line"]),
                f"dash offset at {mid['t']:.0f} ms: {mid['line']}")
        c.judge("by 1.5 s the line is fully drawn and its points are in place",
                bool(done["line"]) and all(x <= 0.001 for x in done["line"]) and bool(done["dots"])
                and all(o >= 0.999 and identity(tr) for o, tr in done["dots"]),
                f"at {done['t']:.0f} ms offset {done['line']}, dots {done['dots']}")
        final = fin["number"]
        c.judge("the number's element holds the final value at every frame",
                final is not None and number_of(final) == number_of(want_value)
                and all(n == final for n in out["numbers"]),
                f"final {final!r}, run says {want_value!r}; frames {len(out['numbers'])}, distinct "
                f"{sorted(set(map(str, out['numbers'])))[:6]}")
        c.judge("the number counts up over it (at 0.3 s a count below the value is drawn over the element)",
                mid["overlay"] is not None and (number_of(mid["overlay"]) or 0) < (number_of(final) or 0),
                f"overlay at {mid['t']:.0f} ms: {mid['overlay']!r}; final {final!r}")

    # -- FR-2

    def watch_run(self, page: Any, act: Callable[[], Any], label: str, c: Check) -> None:
        """Tags the bars, does *act*, waits for the next run to land and settle, and judges."""
        page.evaluate("() => { window.__slowRunMs = 1500; }")
        page.evaluate(WATCH, [None, None])
        before = fetched_at(page)
        act()
        moved = poll(lambda: fetched_at(page) not in (None, before), 30, 0.3)
        page.wait_for_timeout(1500)
        out = page.evaluate(TAGGED)
        page.evaluate("() => { window.__slowRunMs = 0; }")
        tl = out["timeline"]
        dim = [x for x in tl if x["refreshing"] and x["opacity"] is not None and x["opacity"] < 0.9]
        c.judge(f"{label}: during the run the charts are dimmed",
                bool(moved) and bool(dim),
                f"new run landed {bool(moved)}; {len(tl)} frames, {len(dim)} dimmed, "
                f"least opacity {min((x['opacity'] for x in tl if x['opacity'] is not None), default=None)}")
        bars = out["bars"]
        changed = [b for b in bars if abs(b["after"] - b["before"]) > 0.5]
        c.judge(f"{label}: afterwards the same bar elements carry the new widths",
                bool(bars) and out["same"] and all(b["connected"] for b in bars) and bool(changed),
                f"same elements {out['same']}; {len(bars)} bars, {len(changed)} changed width: "
                + "; ".join(f"{b['label_before']} {b['before']:.1f} -> {b['label_after']} {b['after']:.1f}" for b in bars))

    def ac_values_move(self, c: Check) -> None:
        if not self.need_browser(c):
            return
        dash = self.id("move")

        def go(page: Any) -> None:
            if not self.open_settled(page, "move"):
                c.judge("the dashboard opened", False, "no panels")
                return
            dd.rw([("insert into tasks (id, project_id, title, description, status, priority, created_at, updated) "
                    "values (?,?,?,?,?,?,?,?)",
                    (dd.hexid("task-"), self.a, f"added {k}", "motion drive", "approved", "medium",
                     dd.ts(ded.now()), dd.ts(ded.now()))) for k in range(3)])
            self.watch_run(page, lambda: page.get_by_test_id("dashboard-refresh").first.click(), "Refresh", c)
            view = ded.read(self.a, dash)
            panel = next(x for x in view["panels"] if x["kind"] == "bar")

            def save() -> None:
                code, out = ded.patch(self.a, dash, view.get("version"), [
                    {"op": "change_panel", "panel_id": panel["id"], "query": Q_STATUS_BUMPED}])
                p(f"  the agent's save: {said(code, out, 200)}")
            self.watch_run(page, save, "an agent's save", c)

        self.with_page(go, shot="values-move")

    # -- FR-3

    def ac_edit_visible(self, c: Check) -> None:
        if not self.need_browser(c):
            return
        dash = self.id("four")
        view = ded.read(self.a, dash)
        table = next(x for x in view["panels"] if x["kind"] == "table")

        def go(page: Any) -> None:
            if not self.open_settled(page, "four"):
                c.judge("the dashboard opened", False, "no panels")
                return
            first = page.locator("[data-testid=dashboard-panel][data-state=new]").count()
            c.judge("on first opening no panel is marked new", first == 0, f"{first} marked new")
            ids_before = {x["id"] for x in view["panels"]}
            # The added panel's id is minted by the Hub; record by the removed id, find the added after.
            page.evaluate(WATCH, [table["id"], None])
            code, out = ded.patch(self.a, dash, view.get("version"), [
                {"op": "remove_panel", "panel_id": table["id"]},
                {"op": "add_panel", "panel": {"title": "Runs by agent", "query": Q_AGENTS, "kind": "bar"},
                 "position": None}])
            added = [x["id"] for x in (out.get("panels") or [])] if isinstance(out, dict) else []
            added = [i for i in added if i not in ids_before]
            p(f"  the agent's save: {said(code, out, 200)}; added {added}")
            page.wait_for_timeout(4000)
            tl = page.evaluate("() => { window.__stop = true; return window.__tl; }")
            # The moment the edit reached the screen: the first frame whose panels differ from the first's.
            change = next((x["t"] for x in tl if tl and x["ids"] != tl[0]["ids"]), None)
            leaving = next((x["t"] for x in tl if x["removed"] == "leaving"), None)
            gone_late = [x for x in tl if change is not None and x["t"] >= change + 600 and x["removed"] is not None]
            c.judge("the removed panel is still on screen marked leaving within 100 ms, and gone by 600 ms",
                    change is not None and leaving is not None and leaving <= change + 100 and not gone_late,
                    f"edit on screen at {change} ms, leaving from {leaving} ms; still there after 600 ms in "
                    f"{len(gone_late)} frames; states {sorted({str(x['removed']) for x in tl})}")
            state = page.locator(f"[data-panel-id='{added[0]}']").first.get_attribute("data-state") if added and \
                page.locator(f"[data-panel-id='{added[0]}']").count() else None
            c.judge("the added panel is marked new", state == "new", f"added {added}: data-state {state!r}")
            page.get_by_text("All dashboards").first.click()
            page.wait_for_timeout(500)
            self.open_settled(page, "four")
            again = page.locator("[data-testid=dashboard-panel][data-state=new]").count()
            c.judge("on reopening the dashboard nothing is marked new", again == 0, f"{again} marked new")

        self.with_page(go, shot="edit-visible")

    # -- FR-4

    def ac_tooltip(self, c: Check) -> None:
        if not self.need_browser(c):
            return
        for scheme in ("light", "dark"):
            def go(page: Any, scheme: str = scheme) -> None:
                if not self.open_settled(page, "tip"):
                    c.judge(f"{scheme}: the dashboard opened", False, "no panels")
                    return
                tip = page.get_by_test_id("dashboard-tooltip")

                def dimmed(kind: str) -> List[float]:
                    return page.evaluate(
                        "(k) => [...document.querySelectorAll(`[data-kind=${k}] .aw-dash-mark`)]"
                        ".map((e) => parseFloat(getComputedStyle(e).opacity))", kind)

                marks = (page.locator("[data-kind=bar] .aw-dash-mark").count(),
                         page.locator("[data-kind=line] .aw-dash-dot").count())
                if not c.judge(f"{scheme}: the bars and the line's points are hoverable marks", marks == (4, 6),
                               f"{marks[0]} bar marks (.aw-dash-mark), {marks[1]} line points (.aw-dash-dot); want 4 and 6"):
                    return
                page.locator("[data-kind=bar] .aw-dash-mark").nth(1).hover()
                page.wait_for_timeout(400)
                text = tip.first.inner_text() if tip.count() else None
                ops = dimmed("bar")
                c.judge(f"{scheme}: hovering the second bar names South, tasks, 7 and dims the others",
                        text is not None and all(w in text for w in ("South", "tasks", "7"))
                        and len(ops) == 4 and ops[1] >= 0.99 and all(o < 0.9 for i, o in enumerate(ops) if i != 1),
                        f"tooltip {text!r}; bar opacities {ops}")
                page.screenshot(path=str(SHOTS / f"tooltip-bar-{scheme}.png"), full_page=True)
                page.locator("[data-kind=line] .aw-dash-dot").nth(3).hover()
                page.wait_for_timeout(400)
                text = tip.first.inner_text() if tip.count() else None
                ops = dimmed("line")
                c.judge(f"{scheme}: hovering a line point names Thu, runs, 8 and dims the others",
                        text is not None and all(w in text for w in ("Thu", "runs", "8"))
                        and len(ops) == 6 and ops[3] >= 0.99 and all(o < 0.9 for i, o in enumerate(ops) if i != 3),
                        f"tooltip {text!r}; point opacities {ops}")
                page.screenshot(path=str(SHOTS / f"tooltip-line-{scheme}.png"), full_page=True)
                p(f"  screenshots {SHOTS / f'tooltip-bar-{scheme}.png'}, {SHOTS / f'tooltip-line-{scheme}.png'}")
                page.mouse.move(2, 2)
                page.wait_for_timeout(400)
                left = dimmed("bar") + dimmed("line")
                c.judge(f"{scheme}: after moving off there is no tooltip and nothing is dimmed",
                        tip.count() == 0 and all(o >= 0.99 for o in left), f"tooltips {tip.count()}; opacities {left}")

            self.with_page(go, scheme=scheme)

    # -- FR-5

    def ac_skeleton(self, c: Check) -> None:
        if not self.need_browser(c):
            return

        def go(page: Any) -> None:
            if not self.click_open(page, "draw"):
                c.judge("the dashboard opened", False, "no dashboard-row")
                return
            shown = poll(lambda: page.get_by_test_id("dashboard-skeleton").count(), 3, 0.05)
            panels_early = page.get_by_test_id("dashboard-panel").count()
            arrived = poll(lambda: page.get_by_test_id("dashboard-panel").count(), 20, 0.2)
            page.wait_for_timeout(300)
            left = page.get_by_test_id("dashboard-skeleton").count()
            c.judge("placeholders show until the panels arrive, and none remain after",
                    bool(shown) and panels_early == 0 and bool(arrived) and left == 0,
                    f"skeleton shown {bool(shown)} with {panels_early} panels; panels arrived {bool(arrived)}; "
                    f"skeletons after {left}")

        self.with_page(go, slow_ms=1200, shot="skeleton")

    # -- FR-6

    def ac_reduced_motion(self, c: Check) -> None:
        if not self.need_browser(c):
            return
        want = next((x for x in self.run_of("calm") if x.get("kind") == "number"), {})
        want_value = (want.get("rows") or [[None]])[0][0]

        def go(page: Any) -> None:
            if not self.click_open(page, "calm"):
                c.judge("the dashboard opened", False, "no dashboard-row")
                return
            out = page.evaluate(DRAW_IN, [{"first": 0, "at03": 300, "settled": 1500}, 1500])
            if not isinstance(out, dict) or out.get("error"):
                c.judge("the dashboard opened", False, str(out))
                return
            first, fin = out["samples"]["first"], out["samples"]["settled"]
            running = page.evaluate(
                "() => { const v = document.querySelector('[data-testid=dashboard-view]');"
                " return document.getAnimations().filter((a) => a.playState === 'running' && a.effect"
                " && a.effect.target && v.contains(a.effect.target)).map((a) => a.animationName"
                " || a.transitionProperty || String(a.constructor.name)); }")
            c.judge("on opening, the panels and charts are at their final state at once",
                    first["bar"] == fin["bar"] and bool(fin["bar"]) and first["panels"] and all(o >= 0.999 for o in first["panels"])
                    and all(x <= 0.001 for x in first["line"]),
                    f"first frame bars {first['bar']} vs {fin['bar']}; panels {first['panels']}; line {first['line']}")
            c.judge("the figure shows its final value at once, with no count drawn over it",
                    number_of(first["number"]) == number_of(want_value) and first["overlay"] is None
                    and all(n == first["number"] for n in out["numbers"]),
                    f"first {first['number']!r}, overlay {first['overlay']!r}, run says {want_value!r}")
            dd.rw([("insert into tasks (id, project_id, title, description, status, priority, created_at, updated) "
                    "values (?,?,?,?,?,?,?,?)",
                    (dd.hexid("task-"), self.a, f"calm {k}", "motion drive", "pending", "medium",
                     dd.ts(ded.now()), dd.ts(ded.now()))) for k in range(2)])
            page.evaluate(WATCH, [None, None])
            before = fetched_at(page)
            page.get_by_test_id("dashboard-refresh").first.click()
            poll(lambda: fetched_at(page) not in (None, before), 20, 0.3)
            page.wait_for_timeout(800)
            page.locator("[data-kind=bar] .aw-dash-mark").nth(0).hover()
            page.wait_for_timeout(200)
            tip = page.get_by_test_id("dashboard-tooltip").count()
            tl = page.evaluate("() => { window.__stop = true; return window.__tl; }")
            moving = sorted({name for x in tl for name in (x["running"] or [])})
            c.judge("no element has a running animation or transition, through opening, Refresh and hover",
                    not running and not moving and bool(tl),
                    f"running on opening {running}; running across Refresh and hover over {len(tl)} frames: "
                    f"{moving[:8]}")
            c.judge("the tooltip still shows", tip == 1, f"{tip} tooltips")

        self.with_page(go, reduced=True, shot="reduced-motion")

    # -- FR-7

    def ac_guidance(self, c: Check) -> None:
        doc = self.tools.get("save_dashboard", "")
        flat = re.sub(r"\s+", " ", doc).lower()
        questions = {
            "number for one figure": r"(one|single) (figure|number|value)",
            "bar for a ranking or comparison": r"rank|compar",
            "stacked bar for parts of a whole": r"parts? of (a |the )?whole|breakdown|composition",
            "line for change over time": r"over time|trend",
            "table for detail rows": r"detail",
        }
        rules = {
            "order rows as they should be drawn": r"order (the |your )?rows|rows in the order|in the order they",
            "about 15 bars by taking the top ones": r"\b15\b|fifteen",
            "time in order for a line": r"(time|date|day)s? (in|ascending) order|order(ed)? by (time|date|day)",
            "aliases become the legend and tooltip names": r"alias.{0,160}(legend|tooltip)|(legend|tooltip).{0,160}alias",
        }
        for label, pattern in {**questions, **rules}.items():
            c.judge(f"save_dashboard's description says: {label}", re.search(pattern, flat) is not None,
                    f"no /{pattern}/ in the description ({len(doc)} chars)")

    # -- FR-8

    def ac_examples_draw(self, c: Check) -> None:
        code, entry = api("GET", f"/projects/{self.a}/vault/entries/{NOTE_ID}")
        text = entry.get("content") or "" if isinstance(entry, dict) else ""
        examples: Dict[str, str] = {}
        # The build states each example's kind as a `Kind: `<kind>`.` line just above its fence
        # (hub/hub/data_notes.py `_example`); a `-- kind: <kind>` first line inside it also counts.
        for before, block in re.findall(r"([^\n]*)\n+```sql\s*\n(.*?)```", text, re.S):
            m = re.match(r"\s*--\s*kind:\s*([a-z_]+)", block) or re.search(r"Kind:\s*`([a-z_]+)`", before)
            if m:
                examples.setdefault(m.group(1), block.strip())
        lacking = [k for k in KINDS if k not in examples]
        c.judge("the seeded data note carries one worked example per kind",
                code == 200 and not lacking,
                f"note read {code}, {len(text)} chars; examples for {sorted(examples)}; missing {lacking}")
        if not examples:
            return
        made = ded.create(self.a, f"Worked examples {STAMP}",
                          [(f"Example {k}", q, k) for k, q in examples.items() if k in KINDS])
        code, out = api("GET", f"/projects/{self.a}/dashboards/{made['id']}/run")
        for panel in panels_of_run(out):
            c.judge(f"the {panel.get('kind')} example returns rows and draws with no warning",
                    not panel.get("error") and not panel.get("warning") and bool(panel.get("rows")),
                    f"rows {len(panel.get('rows') or [])}; error {panel.get('error')!r}; warning {panel.get('warning')!r}")

    # -- FR-9

    def ac_first_time_right(self, c: Check) -> None:
        # One green turn proves little: Haiku built all five kinds cleanly on some runs of the
        # pre-guidance code and not on others. The criterion says *an agent produces* such a
        # dashboard, so every one of TURNS independent turns must; each turn's dashboard is
        # deleted after it is judged, so the next starts from the same project.
        for n in range(1, self.turns + 1):
            self.first_time_right_turn(c, f"turn {n} of {self.turns}")

    def first_time_right_turn(self, c: Check, which: str) -> None:
        before = {d.get("id") for d in dashboards_list(self.a)[1]}
        p(f"  -- {which}")
        t = ded.turn(self.a, ANALYST, ASK)
        new = [d for d in dashboards_list(self.a)[1] if d.get("id") not in before]
        c.judge(f"{which}: the Haiku turn saved a dashboard", bool(t["run_id"]) and bool(new),
                f"run {t['run_id']}; new dashboards {[d.get('name') for d in new]}; "
                f"asked {t['questions']}; reply {t['reply'][-300:]!r}")
        self.keep_transcript(t["run_id"], which, quiet=bool(new))
        if not new:
            return
        dash = new[0]
        code, out = api("GET", f"/projects/{self.a}/dashboards/{dash['id']}/run")
        panels = panels_of_run(out)
        kinds = sorted({x.get("kind") for x in panels})
        c.judge(f"{which}: the saved dashboard has panels of the five kinds", set(KINDS) <= set(kinds),
                f"{dash.get('name')!r}: kinds {kinds}; missing {sorted(set(KINDS) - set(kinds))}")
        bad = [(x.get("title"), x.get("kind"), (x.get("error") or {}).get("message") if isinstance(x.get("error"), dict)
                else x.get("error"), x.get("warning")) for x in panels if x.get("error") or x.get("warning")]
        c.judge(f"{which}: opening it shows no error and no drawing warning on any panel",
                code == 200 and panels and not bad,
                f"run {code}; {len(panels)} panels; failing {bad}; queries "
                + " | ".join(f"{x.get('kind')}: {x.get('query')}" for x in panels)[:1500])
        # Not the criterion, which asks only that every panel draws: how well each reads, for the
        # guidance task (a line drawn newest first runs backwards; a stacked bar of one series
        # does not stack).
        for x in panels:
            labels = [r[0] for r in (x.get("rows") or [])]
            series = [i for i in range(1, len(x.get("columns") or []))
                      if all(isinstance(r[i], (int, float)) or r[i] is None for r in x.get("rows") or [])]
            if x.get("kind") == "line":
                p(f"  NOTE line {x.get('title')!r}: labels in ascending order {labels == sorted(labels, key=str)}")
            if x.get("kind") == "stacked_bar":
                p(f"  NOTE stacked bar {x.get('title')!r}: {len(series)} series {[x['columns'][i] for i in series]}; "
                  f"{len(labels)} rows, {len(set(map(str, labels)))} distinct labels")
            if x.get("kind") == "bar":
                p(f"  NOTE bar {x.get('title')!r}: {len(labels)} labels")
        if self.browser:
            self.d["asked"] = dash

            def go(page: Any) -> Any:
                self.open_settled(page, "asked")
                return (page.get_by_test_id("dashboard-panel-error").count(),
                        page.get_by_test_id("dashboard-panel-warning").count(),
                        page.get_by_test_id("dashboard-panel").count())

            errors, warnings, count = self.with_page(go, shot=f"first-time-right-{which.split()[1]}")
            c.judge(f"{which}: on the screen no panel shows an error or a warning",
                    count and not errors and not warnings, f"{count} panels, {errors} errors, {warnings} warnings")
        for d in new:
            api("DELETE", f"/projects/{self.a}/dashboards/{d['id']}")

    def keep_transcript(self, run_id: Optional[str], which: str, quiet: bool) -> None:
        """Write the turn's whole output, tool calls and results included, to the scratch; for a
        turn that saved nothing (not *quiet*) also print every dashboard tool call with what it
        answered, so a miss can be told apart (never called, called and refused, or a call that
        never left the reply)."""
        if not run_id:
            return
        rows = dd.ro("select kind, content from agent_outputs where run_id=? order by sequence", (run_id,))
        path = TMP / f"first-time-right-{which.split()[1]}-{run_id}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(f"--- {k}\n{c}" for k, c in rows), encoding="utf-8")
        p(f"  whole output of {run_id} ({len(rows)} entries): {path}")
        for k, c in [] if quiet else rows:
            if k in ("tool_use", "tool_result") and c and "dashboard" in c:
                p(f"  {k}: {c[:600]!r}")

    # -- order

    def run(self) -> None:
        try:
            self.setup()
            for key in ORDER:
                if not self.only or key in self.only:
                    run_check(key, getattr(self, key.replace("-", "_")))
        finally:
            if os.environ.get("AW_DRIVE_KEEP"):
                p(f"AW_DRIVE_KEEP: Hub left on {dd.HUB}, key {dd.KEY}, database {DB}")
            else:
                self.hub.stop()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--only", nargs="+", choices=ORDER, help="run only these checks")
    ap.add_argument("--turns", type=int, default=3,
                    help="ac-first-time-right's Haiku turns, every one of which must pass (default 3)")
    args = ap.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)
    p(f"dashboards motion drive {STAMP}; scratch {TMP}")
    Drive(browser=not args.no_browser, only=args.only, turns=max(1, args.turns)).run()

    p("\n== drive baseline")
    for key, check in CHECKS.items():
        failed = check.reached and not check.ok
        detail = "passed" if check.ok and check.reached else ("; ".join(check.details) or "no detail")
        p(f"check {key}: reached={'yes' if check.reached else 'no'} "
          f"failed_at_assertion={'yes' if failed else 'no'} -- {detail[:700]}")
    bad = [k for k, ch in CHECKS.items() if not (ch.reached and ch.ok)]
    p(f"\n{len(CHECKS) - len(bad)} of {len(CHECKS)} checks pass" + (f"; failing: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
