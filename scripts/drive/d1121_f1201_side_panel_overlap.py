"""Drive F1201: the thread bar overlaps / is cut off beside the side panel.

Two modes.

--assert (the acceptance drive of spec/changes/the-thread-bar-and-composer-survive-a-wide-side-
panel, task acceptance-drive): starts a fresh Hub from this checkout's hub/ (AW_DRIVE_PORT, default
8036, a new database; or reuses one named by AW_HUB, AW_KEY and AW_DB -- never :8000 or :8010),
opens a scratch project with one Haiku agent, gives it one measured turn and a 120-character title,
and then measures every row the criteria name: the 1440 idle minimum, the 1280/1440/1920 window
sweep, the 380..651 width sweep idle and Running, the restored width after a reload, the title, the
651 -> 380 compaction order, the panel's own close control (empty and with a Watch tab, keyboard and
click), the composer's rows and the keyboard-only reach at 380 while Running. Running is a slow Bash
`sleep` turn, re-triggered while it is needed and stopped at the end. Prints one line per check
(`check <key>: reached=... failed_at_assertion=...`) and exits 1 on any failure. `--shots <prefix>`
also writes testbed/drive1121-f1201/shots/<prefix>-<col>-<idle|running>-<dark|light>.png for the
operator's review (ac-screens-reviewed). Two or three Haiku turns, about 10 minutes.

    py -3.11 scripts/drive/d1121_f1201_side_panel_overlap.py --assert [--shots after]

Without --assert: the original observation (edits nothing). Needs a fresh drive Hub:
  AW_HUB, AW_KEY   the Hub and its key (curl $AW_HUB/api/v1/setup/token)
  AW_PROJECT       project id, AW_AGENT (default Dev), AW_SHORT / AW_LONG conversation ids
                   (a short-titled and a 120-char-titled thread whose last run was measured, so
                   the bar shows the context-usage label)
Writes screenshots to testbed/drive1121-f1201/shots/ and prints one row per condition.
"""
import json
import os
import pathlib
import secrets
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

HUB = KEY = PID = None
AGENT = os.environ.get("AW_AGENT", "Dev")
CONV = {}
SHOTS = "testbed/drive1121-f1201/shots"
sys.stdout.reconfigure(encoding="utf-8")

MEASURE = """() => {
  const R = e => { if (!e) return null; const r = e.getBoundingClientRect();
     return {l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width), t: Math.round(r.top)} };
  const sep = [...document.querySelectorAll('[role=separator]')].find(s => s.getAttribute('aria-label') === 'Resize thread');
  if (!sep) return {noPanel: true};
  const col = sep.previousElementSibling, pane = document.querySelector('[data-testid=document-pane]');
  const bar = document.querySelector('[data-testid=conversation-header]');
  const q = s => bar.querySelector(s);
  const reach = e => { if (!e) return null; const r = e.getBoundingClientRect();
     const x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2;
     if (r.width === 0 || x < 0 || x > innerWidth) return false;
     const hit = document.elementFromPoint(x, y); return !!hit && (e === hit || e.contains(hit)); };
  const els = {title: q('.aw-convbar-title'), status: q('.aw-convbar-status'), ctx: q('.context-usage-control'),
     checkpoint: q('[data-testid=conversation-handoff]'), more: q('[data-testid=conversation-more]'),
     stop: q('button[title^="Stop"]')};
  const out = {col: R(col), pane: R(pane), bar: R(bar), barScrollW: bar.scrollWidth, barClientW: bar.clientWidth, vw: innerWidth};
  for (const [k, e] of Object.entries(els)) { out[k] = R(e); out[k + 'Reach'] = reach(e); }
  const comp = document.querySelector('.conversation-composer-surface');
  const tops = [];
  if (comp) for (const e of comp.querySelectorAll('button, [role=combobox], [role=button]')) {
    const r = e.getBoundingClientRect(); if (r.width === 0) continue;
    const c = Math.round(r.top + r.height / 2); if (!tops.some(t => Math.abs(t - c) < 10)) tops.push(c); }
  out.composerRows = tops.length; out.composerH = comp ? Math.round(comp.getBoundingClientRect().height) : null;
  return out;
}"""


def api_post(path, body):
    req = urllib.request.Request(HUB + "/api/v1" + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def url(which):
    return f"{HUB}/?project={PID}&agent={AGENT}&conversation={CONV[which]}"


def open_thread(pg, which):
    pg.goto(url(which))
    pg.wait_for_selector("[data-testid=conversation-header]", timeout=15000)
    pg.wait_for_timeout(1200)


def open_panel(pg):
    if pg.get_by_role("separator", name="Resize thread").count():
        return
    pg.get_by_test_id("conversation-more").click()
    pg.get_by_test_id("conversation-toggle-panel").click()
    pg.wait_for_selector("[role=separator][aria-label='Resize thread']", timeout=5000)
    pg.wait_for_timeout(600)


def drag_to(pg, x):
    sep = pg.get_by_role("separator", name="Resize thread")
    b = sep.bounding_box()
    cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    pg.mouse.move(cx, cy)
    pg.mouse.down()
    pg.mouse.move((cx + x) / 2, cy, steps=8)
    pg.mouse.move(x, cy, steps=8)
    pg.mouse.up()
    pg.wait_for_timeout(500)


def row(label, m):
    if m.get("noPanel"):
        return f"{label:58} NO PANEL (fitsAsColumn false -> overlay mode)"
    ok = lambda k: ("yes" if m[k + "Reach"] else "NO ") if m.get(k) else "absent"
    more = m["more"]
    over = more["r"] - m["col"]["r"] if more else 0
    title = m["title"]
    return (f"{label:58} col={m['col']['w']:4}(r{m['col']['r']:4}) more_r={more['r'] if more else None} "
            f"over={over:+} title_w={title['w'] if title else None} reach[title={ok('title')} ckpt={ok('checkpoint')} "
            f"more={ok('more')}] ctx_w={m['ctx']['w'] if m['ctx'] else None} "
            f"bar_scrollW/clientW={m['barScrollW']}/{m['barClientW']} composerRows={m['composerRows']}")


def new_ctx(b, w, theme="dark", h=900):
    ctx = b.new_context(viewport={"width": w, "height": h})
    pg = ctx.new_page()
    if theme == "light":
        pg.goto(HUB + "/")
        pg.wait_for_timeout(1500)
        t = pg.get_by_role("button", name="Switch to light mode")
        if t.count():
            t.first.click()
            pg.wait_for_timeout(300)
    return ctx, pg


rows = []


def record(label, pg, shot=None):
    m = pg.evaluate(MEASURE)
    rows.append((label, m))
    print(row(label, m), flush=True)
    if shot:
        pg.screenshot(path=f"{SHOTS}/{shot}.png")
    return m

# ---------------------------------------------------------------------------------------------
# --assert: the acceptance drive for spec/changes/the-thread-bar-and-composer-survive-a-wide-side-
# panel (F1201). Every row the criteria name, on a fresh Hub, exit 1 on any failure.
# ---------------------------------------------------------------------------------------------

LONG_TITLE = ("F1201 acceptance drive: a thread whose title is long enough to need truncating in "
              "the thread bar beside the side panel")[:120].ljust(120, ".")
SWEEP = (380, 420, 451, 480, 560, 651)
WINDOWS = (1280, 1440, 1920)
SLEEP_TURN = "Use the Bash tool to run exactly `sleep 110` (one call, nothing else), then reply done."

# One measurement of the bar, the title and the composer, relative to the thread column.
BAR = """() => {
  const sep = [...document.querySelectorAll('[role=separator]')].find(s => s.getAttribute('aria-label') === 'Resize thread');
  const bar = document.querySelector('[data-testid=conversation-header]');
  if (!bar) return {noBar: true};
  const col = sep ? sep.previousElementSibling : bar.parentElement;
  const C = col.getBoundingClientRect();
  const R = e => { const r = e.getBoundingClientRect();
    return {l: Math.round(r.left - C.left), r: Math.round(r.right - C.left), w: Math.round(r.width), t: Math.round(r.top)}; };
  const shown = e => !!e && e.getClientRects().length > 0 && e.getBoundingClientRect().width > 0
    && getComputedStyle(e).visibility !== 'hidden';
  // A disabled button has pointer-events: none (Checkpoint while Running), which elementFromPoint
  // passes through: lift it for the probe, so the probe asks only what covers the control.
  const reach = e => { const r = e.getBoundingClientRect(); const x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2;
    if (x < 0 || x > innerWidth) return false; const pe = e.style.pointerEvents; e.style.pointerEvents = 'auto';
    const hit = document.elementFromPoint(x, y); e.style.pointerEvents = pe;
    return !!hit && (hit === e || e.contains(hit)); };
  const name = e => (e.getAttribute('aria-label') || (e.getAttribute('aria-labelledby') || '').split(' ')
    .map(id => (document.getElementById(id) || {}).textContent || '').join(' ').trim()
    || (e.innerText || '').trim() || e.getAttribute('title') || '').trim();
  const visText = root => { let s = ''; const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (w.nextNode()) { const p = w.currentNode.parentElement; if (p.closest('[role=tooltip]')) continue;
      if (shown(p)) s += w.currentNode.textContent; } return s.trim(); };
  const buttons = [...bar.querySelectorAll('button')];
  const els = {
    status: bar.querySelector('.aw-convbar-status'),
    ctx: bar.querySelector('[data-testid=context-usage]'),
    checkpoint: bar.querySelector('[data-testid=conversation-handoff]'),
    stop: buttons.find(b => /^(Stop|Stopping)/i.test(name(b)) || /^Stop/.test(b.getAttribute('title') || '')),
    more: bar.querySelector('[data-testid=conversation-more]'),
    agent: bar.querySelector('.aw-convbar-agent'),
    title: bar.querySelector('.aw-convbar-title'),
  };
  const out = {colW: Math.round(C.width), colR: Math.round(C.right), panel: !!sep, vw: innerWidth,
    barScrollW: bar.scrollWidth, barClientW: bar.clientWidth, barScrollL: bar.scrollLeft, c: {}};
  for (const [k, e] of Object.entries(els)) {
    if (!shown(e)) { out.c[k] = null; continue; }
    const r = R(e); out.c[k] = {...r, inCol: r.l >= -0.5 && r.r <= C.width + 0.5, reach: reach(e), name: name(e)};
  }
  if (out.c.ctx) { const t = visText(els.ctx); out.c.ctx.text = t;
    out.c.ctx.mode = t.includes('/') ? 'full' : /%/.test(t) ? 'compact' : 'other'; }
  if (out.c.checkpoint) out.c.checkpoint.mode = (els.checkpoint.innerText || '').trim() ? 'label' : 'icon';
  if (out.c.agent) out.c.agent.text = (els.agent.innerText || '').trim();
  if (out.c.title) {
    const t = els.title, span = t.querySelector('.truncate') || t, node = [...span.childNodes].find(n => n.nodeType === 3);
    const full = node ? node.textContent : '';
    const cs = getComputedStyle(span), avail = span.clientWidth, truncated = span.scrollWidth > span.clientWidth + 1;
    const cv = document.createElement('canvas').getContext('2d'); cv.font = cs.font;
    const ell = truncated && cs.textOverflow === 'ellipsis' ? cv.measureText('\\u2026').width : 0;
    let n = 0; if (node) { const rg = document.createRange(); rg.setStart(node, 0);
      for (let i = 1; i <= full.length; i++) { rg.setEnd(node, i);
        if (rg.getBoundingClientRect().width + ell <= avail + 0.5) n = i; else break; } }
    Object.assign(out.c.title, {full, visibleChars: n, truncated, ellipsis: cs.textOverflow === 'ellipsis',
      titleAttr: t.getAttribute('title') || '', accName: name(t)});
  }
  const comp = document.querySelector('.conversation-composer-surface');
  const rows = [], nameless = [];
  if (comp) for (const e of comp.querySelectorAll('button, [role=combobox], [role=button], select')) {
    if (!shown(e)) continue; const r = e.getBoundingClientRect(), c = Math.round(r.top + r.height / 2);
    if (!rows.some(t => Math.abs(t - c) < 10)) rows.push(c); if (!name(e)) nameless.push(e.outerHTML.slice(0, 80)); }
  out.composerRows = rows.length; out.composerNameless = nameless; out.composer = !!comp;
  return out;
}"""

FOCUSED = """() => { const e = document.activeElement; if (!e) return null;
  const bar = document.querySelector('[data-testid=conversation-header]');
  const name = (e.getAttribute('aria-label') || (e.innerText || '').trim() || e.getAttribute('title') || '').trim();
  const sep = [...document.querySelectorAll('[role=separator]')].find(s => s.getAttribute('aria-label') === 'Resize thread');
  const C = (sep ? sep.previousElementSibling : bar).getBoundingClientRect(), r = e.getBoundingClientRect();
  const x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2, pe = e.style.pointerEvents;
  e.style.pointerEvents = 'auto'; const hit = document.elementFromPoint(x, y); e.style.pointerEvents = pe;
  const agent = bar && bar.querySelector('.aw-convbar-agent');
  return {name, testid: e.getAttribute('data-testid') || '', role: e.getAttribute('role') || '',
    inBar: !!bar && bar.contains(e), ctx: !!e.closest('[data-testid=context-usage]'),
    visible: r.left >= C.left - 0.5 && r.right <= C.right + 0.5 && !!hit && (hit === e || e.contains(hit)),
    agentL: agent ? Math.round(agent.getBoundingClientRect().left - C.left) : null,
    barScrollL: bar ? bar.scrollLeft : 0}; }"""


class Drive:
    def __init__(self, hub, key, pid, agent, conv, shots):
        self.hub, self.key, self.pid, self.agent, self.conv, self.shots = hub, key, pid, agent, conv, shots
        self.rows = {}  # criterion -> list of (row label, reached, ok, detail)

    # -- the Hub ------------------------------------------------------------------------------
    def api(self, method, path, body=None):
        req = urllib.request.Request(
            self.hub + "/api/v1" + path, data=json.dumps(body).encode() if body is not None else None,
            method=method, headers={"Authorization": "Bearer " + self.key,
                                    "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()[:2000]

    def start_running(self, pg):
        """Puts the thread in a running turn (a slow Bash sleep) unless it is in one already."""
        if self.running(pg):
            return True
        code, out = self.api("POST", f"/projects/{self.pid}/agent/trigger",
                             {"agent": self.agent, "conversation_id": self.conv, "message": SLEEP_TURN})
        if code != 200:
            print(f"  trigger refused: {code} {str(out)[:300]}", flush=True)
            return False
        t0 = time.time()
        while time.time() - t0 < 60:
            if self.running(pg):
                pg.wait_for_timeout(1500)
                return True
            pg.wait_for_timeout(500)
        return False

    def stop_running(self):
        self.api("POST", f"/projects/{self.pid}/agent/{self.agent}/stop?conversation_id={self.conv}")

    @staticmethod
    def running(pg):
        return pg.locator("[data-testid=conversation-header] .aw-convbar-status[data-running=true]").count() > 0

    # -- the page -----------------------------------------------------------------------------
    def page(self, b, w, theme="dark"):
        ctx = b.new_context(viewport={"width": w, "height": 900})
        pg = ctx.new_page()
        if theme == "light":
            pg.goto(self.hub + "/")
            pg.wait_for_timeout(1500)
            t = pg.get_by_role("button", name="Switch to light mode")
            if t.count():
                t.first.click()
                pg.wait_for_timeout(300)
        return ctx, pg

    def open_thread(self, pg):
        pg.goto(f"{self.hub}/?project={self.pid}&agent={self.agent}&conversation={self.conv}")
        pg.wait_for_selector("[data-testid=conversation-header]", timeout=20000)
        pg.wait_for_timeout(1200)

    def open_panel(self, pg, tab=True):
        if not pg.get_by_role("separator", name="Resize thread").count():
            pg.get_by_test_id("conversation-more").click()
            pg.get_by_test_id("conversation-toggle-panel").click()
            pg.wait_for_selector("[role=separator][aria-label='Resize thread']", timeout=5000)
            pg.wait_for_timeout(500)
        if tab and pg.get_by_role("button", name="Watch").count():
            pg.get_by_role("button", name="Watch").first.click()
            pg.wait_for_timeout(700)

    def col_width(self, pg):
        return pg.evaluate("""() => { const s = [...document.querySelectorAll('[role=separator]')]
          .find(s => s.getAttribute('aria-label') === 'Resize thread');
          return s ? Math.round(s.previousElementSibling.getBoundingClientRect().width) : null; }""")

    def set_col(self, pg, target):
        """Drags the divider until the thread column is `target` px (or the drag's nearest limit)."""
        sep = pg.get_by_role("separator", name="Resize thread")
        lo, hi = int(sep.get_attribute("aria-valuemin")), int(sep.get_attribute("aria-valuemax"))
        want = max(lo, min(target, hi))
        for _ in range(5):
            cur = self.col_width(pg)
            if cur is None or abs(cur - want) <= 1:
                break
            box = sep.bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            pg.mouse.move(cx, cy)
            pg.mouse.down()
            pg.mouse.move(cx + (want - cur) / 2, cy, steps=6)
            pg.mouse.move(cx + (want - cur), cy, steps=6)
            pg.mouse.up()
            pg.wait_for_timeout(350)
        return self.col_width(pg), hi

    def menu_items(self, pg):
        """The ⋯ menu's items; opened by keyboard when the panel covers ⋯ (as it does today)."""
        more = pg.get_by_test_id("conversation-more")
        try:
            more.click(timeout=2500)
        except Exception:  # noqa: BLE001 -- covered by the panel: elementFromPoint hits the panel
            more.focus()
            pg.keyboard.press("Enter")
        pg.wait_for_timeout(300)
        items = pg.evaluate("() => [...document.querySelectorAll('[role=menuitem]')].map(e => e.innerText.trim())")
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(200)
        return items

    def measure(self, pg):
        return pg.evaluate(BAR)

    def shot(self, pg, name):
        if self.shots:
            pg.screenshot(path=f"{SHOTS}/{self.shots}-{name}.png")

    # -- the checks ---------------------------------------------------------------------------
    def row(self, crit, label, reached, ok, detail=""):
        self.rows.setdefault(crit, []).append((label, bool(reached), bool(reached and ok), detail))
        state = "PASS" if reached and ok else ("FAIL" if reached else "NOT REACHED")
        print(f"  {state:11} {crit} [{label}] {detail}", flush=True)

    @staticmethod
    def bar_problems(m, need, menu=None):
        """What fails ac-bar-idle-min for the controls in `need` (Checkpoint may be in the menu)."""
        bad = []
        if m.get("noBar"):
            return ["no thread bar"]
        for k in need:
            c = m["c"].get(k)
            if c is None:
                if k == "checkpoint" and menu is not None and any(i.startswith("Checkpoint") for i in menu):
                    continue
                bad.append(f"{k} not in the bar")
                continue
            if not c["inCol"]:
                bad.append(f"{k} right={c['r']} > column {m['colW']}")
            if not c["reach"]:
                bad.append(f"{k} not hit at its centre")
        if m["barScrollW"] > m["barClientW"]:
            bad.append(f"bar scrolls {m['barScrollW']}/{m['barClientW']}")
        return bad

    def bar_row(self, crit, label, pg, running):
        m = self.measure(pg)
        need = ["status", "ctx", "checkpoint", "more"] + (["stop"] if running else [])
        menu = self.menu_items(pg) if m.get("c", {}).get("checkpoint") is None else None
        bad = self.bar_problems(m, need, menu)
        self.row(crit, label, not m.get("noBar"), not bad, f"col={m.get('colW')} " + ("; ".join(bad) or "ok"))
        return m

    def title_row(self, label, m):
        c = m["c"]
        t, a = c.get("title"), c.get("agent")
        bad = []
        if not a or not a["inCol"] or not a["reach"] or self.agent not in a.get("text", ""):
            bad.append("agent name not visible")
        if not t:
            bad.append("title not shown")
        else:
            want = min(8, len(t["full"]))
            if t["visibleChars"] < want:
                bad.append(f"title shows {t['visibleChars']} chars")
            if not t["inCol"]:
                bad.append("title outside the column")
            if t["truncated"] and not t["ellipsis"]:
                bad.append("truncated without an ellipsis")
            if LONG_TITLE not in t["titleAttr"]:
                bad.append(f"title attribute {t['titleAttr'][:40]!r}")
            if LONG_TITLE not in t["accName"]:
                bad.append(f"accessible name {t['accName'][:40]!r}")
        self.row("ac-title-visible", label, not m.get("noBar"), not bad,
                 f"col={m.get('colW')} chars={t['visibleChars'] if t else None} " + ("; ".join(bad) or "ok"))

    def composer_row(self, label, m, col):
        limit = 2 if col < 480 else 1
        bad = []
        if m["composerRows"] > limit:
            bad.append(f"{m['composerRows']} rows > {limit}")
        if m["composerNameless"]:
            bad.append(f"nameless: {m['composerNameless']}")
        self.row("ac-composer-lines", label, m.get("composer"), not bad,
                 f"col={m.get('colW')} rows={m['composerRows']} " + ("; ".join(bad) or "ok"))

    # -- the rows -----------------------------------------------------------------------------
    def idle(self, b):
        # FR-2 window sweep: a 380 px column in three windows; its 1440 row is ac-bar-idle-min.
        seen = {}
        for w in WINDOWS:
            ctx, pg = self.page(b, w)
            self.open_thread(pg)
            self.open_panel(pg)
            col, _ = self.set_col(pg, 380)
            m = self.bar_row("ac-bar-idle-min" if w == 1440 else "ac-window-independent",
                             f"{w} idle 380", pg, running=False)
            if w == 1440:
                self.bar_row("ac-window-independent", "1440 idle 380", pg, running=False)
                self.shot(pg, "380-idle-dark")
            seen[w] = ({k: (v["l"], v["r"]) if v else None for k, v in m["c"].items()}, m["composerRows"])
            ctx.close()
        base = seen[1440]
        diff = [f"{w}: {v}" for w, v in seen.items() if v != base]
        self.row("ac-window-independent", "positions and composer rows equal", True, not diff,
                 "; ".join(diff) or f"composerRows={base[1]}")

        # Idle width sweep, title and composer rows, at 1440.
        ctx, pg = self.page(b, 1440)
        self.open_thread(pg)
        self.open_panel(pg)
        for target in SWEEP:
            col, hi = self.set_col(pg, target)
            m = self.bar_row("ac-bar-sweep", f"idle {target}" + (f" (max {hi})" if hi < target else ""),
                             pg, running=False)
            if target in (380, 480):
                self.title_row(f"idle {target}", m)
                self.composer_row(f"idle {target}", m, col)
            if target in (480, 651):
                self.shot(pg, f"{target}-idle-dark")
        # FR-2 restored width: the 380 px column survives a reload, and the bar fits without a drag.
        self.set_col(pg, 380)
        pg.reload()
        pg.wait_for_selector("[data-testid=conversation-header]", timeout=20000)
        pg.wait_for_timeout(1500)
        col = self.col_width(pg)
        if col is None:
            self.row("ac-restored-min", "reload", False, False, "the panel did not reopen")
        else:
            self.bar_row("ac-restored-min", f"reload, restored col={col}", pg, running=False)
        ctx.close()

        # Light theme shots for the operator's review (ac-screens-reviewed, not asserted).
        if self.shots:
            ctx, pg = self.page(b, 1440, "light")
            self.open_thread(pg)
            self.open_panel(pg)
            for target in (380, 480, 651):
                self.set_col(pg, target)
                self.shot(pg, f"{target}-idle-light")
            ctx.close()

        # FR-4: the panel's own close control, empty and with a Watch tab, by keyboard and click.
        for tab in (False, True):
            for how in ("keyboard", "click"):
                self.panel_close_row(b, tab, how)

    def panel_close_row(self, b, tab, how):
        label = f"{'Watch tab' if tab else 'empty'} / {how}"
        ctx, pg = self.page(b, 1440)
        self.open_thread(pg)
        if tab:
            self.open_panel(pg, tab=True)
        else:
            # Empty: the panel as "Show side panel" opens it, with no tab.
            self.open_panel(pg, tab=False)
        self.set_col(pg, 380)
        pane = pg.get_by_test_id("document-pane")
        close = pane.get_by_role("button", name="Close side panel", exact=True)
        if not close.count():
            self.row("ac-panel-close", label, True, False, "no control named \"Close side panel\" in the panel")
            ctx.close()
            return
        if how == "click":
            close.first.click()
        else:
            pg.get_by_test_id("conversation-more").focus()
            hit = False
            for _ in range(80):
                pg.keyboard.press("Tab")
                f = pg.evaluate(FOCUSED)
                if f and f["name"] == "Close side panel":
                    hit = True
                    break
            if not hit:
                self.row("ac-panel-close", label, True, False, "Tab never reached \"Close side panel\"")
                ctx.close()
                return
            pg.keyboard.press("Enter")
        pg.wait_for_timeout(600)
        gone = pg.get_by_role("separator", name="Resize thread").count() == 0 and pane.count() == 0
        width = pg.evaluate("() => Math.round(document.querySelector('[data-testid=conversation-header]').getBoundingClientRect().width)")
        self.row("ac-panel-close", label, True, gone and width > 600,
                 f"panel gone={gone} bar width={width}")
        if gone:
            # *Hide side panel* stays in the menu.
            self.open_panel(pg, tab=False)
            items = self.menu_items(pg)
            self.row("ac-panel-close", f"{label}: Hide side panel stays in the menu", True,
                     "Hide side panel" in items, str(items))
        ctx.close()

    def run(self, b):
        ctx, pg = self.page(b, 1440)
        self.open_thread(pg)
        self.open_panel(pg)
        if not self.start_running(pg):
            for crit in ("ac-bar-running", "ac-compaction-order", "ac-nothing-lost"):
                self.row(crit, "running", False, False, "the thread never showed Running")
            ctx.close()
            return
        # The ⋯ menu at a wide column: what nothing-lost compares with.
        self.set_col(pg, 651)
        wide_menu = self.menu_items(pg)

        for target in SWEEP:
            self.start_running(pg)
            col, hi = self.set_col(pg, target)
            m = self.bar_row("ac-bar-sweep", f"running {target}" + (f" (max {hi})" if hi < target else ""),
                             pg, running=True)
            if target in (380, 480):
                self.bar_row("ac-bar-running", f"running {target}", pg, running=True)
                self.title_row(f"running {target}", m)
                self.composer_row(f"running {target}", m, col)
            if target in (380, 480, 651):
                self.shot(pg, f"{target}-running-dark")

        self.compaction(pg)
        self.keyboard(pg, wide_menu)
        ctx.close()

        if self.shots:
            ctx, pg = self.page(b, 1440, "light")
            self.open_thread(pg)
            self.open_panel(pg)
            if self.start_running(pg):
                for target in (380, 480, 651):
                    self.set_col(pg, target)
                    self.shot(pg, f"{target}-running-light")
            ctx.close()

    def compaction(self, pg):
        """ac-compaction-order: 651 -> 380 in 10 px steps (and 380 itself)."""
        self.start_running(pg)
        first = {}  # step -> the widest column at which it was first seen
        bad = []
        menu_checked = False
        targets = list(range(651, 380, -10)) + [380]
        for target in targets:
            if not self.running(pg):
                self.start_running(pg)
            col, _ = self.set_col(pg, target)
            m = self.measure(pg)
            c = m["c"]
            ctx_mode = c["ctx"]["mode"] if c.get("ctx") else "missing"
            ck = c["checkpoint"]["mode"] if c.get("checkpoint") else "menu"
            for step, seen in (("ctx-compact", ctx_mode == "compact"), ("ckpt-icon", ck in ("icon", "menu")),
                               ("ckpt-menu", ck == "menu")):
                if seen:
                    first.setdefault(step, col)
            if ctx_mode not in ("full", "compact"):
                bad.append(f"{col}: context usage {ctx_mode}")
            if ck != "label" and ctx_mode != "compact":
                bad.append(f"{col}: Checkpoint {ck} while the context label is full")
            if ck == "icon" and not c["checkpoint"]["name"].startswith("Checkpoint"):
                bad.append(f"{col}: icon-only Checkpoint named {c['checkpoint']['name']!r}")
            for k in ("status", "stop", "more"):
                if not c.get(k) or not c[k]["inCol"] or not c[k]["reach"]:
                    bad.append(f"{col}: {k} not usable in the bar")
            if ck == "menu" and not menu_checked:
                items = self.menu_items(pg)
                menu_checked = True
                if not any(i.startswith("Checkpoint") for i in items):
                    bad.append(f"{col}: Checkpoint is in neither the bar nor ⋯ ({items})")
        order = [first.get(s, 0) for s in ("ctx-compact", "ckpt-icon", "ckpt-menu")]
        if not order[0] >= order[1] >= order[2]:
            bad.append(f"order: ring at {order[0]}, icon at {order[1]}, into ⋯ at {order[2]}")
        self.row("ac-compaction-order", "running, 651 -> 380", True, not bad,
                 f"first seen {first}; " + ("; ".join(dict.fromkeys(bad)) or "ok"))

    def keyboard(self, pg, wide_menu):
        """ac-nothing-lost: at 380, Running, keyboard only, the bar never scrolling."""
        self.start_running(pg)
        self.set_col(pg, 380)
        pg.locator("[data-testid=conversation-header] .aw-convbar-title").focus()
        agent_l = pg.evaluate(FOCUSED)["agentL"]
        reached, scrolled, hidden = set(), 0, []
        for _ in range(12):
            pg.keyboard.press("Tab")
            pg.wait_for_timeout(80)
            f = pg.evaluate(FOCUSED)
            if not f or not f["inBar"]:
                break
            # The bar scrolls when its scroll offset or the agent name's place in the column moves.
            scrolled = max(scrolled, f["barScrollL"], abs((f["agentL"] or 0) - (agent_l or 0)))
            if not f["visible"]:
                hidden.append(f["name"] or f["testid"])
            if f["ctx"]:
                reached.add("context usage")
            if f["testid"] == "conversation-handoff":
                reached.add("Checkpoint")
            if f["name"].startswith("Stop"):
                reached.add("Stop")
            if f["testid"] == "conversation-more":
                reached.add("⋯")
        items = []
        if "⋯" in reached:
            pg.get_by_test_id("conversation-more").focus()
            scrolled = max(scrolled, pg.evaluate(FOCUSED)["barScrollL"])
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(300)
            for _ in range(20):
                f = pg.evaluate(FOCUSED)
                if f and f["role"] == "menuitem" and f["name"] not in items:
                    items.append(f["name"])
                elif items and f and f["name"] == items[0]:
                    break
                pg.keyboard.press("ArrowDown")
                pg.wait_for_timeout(60)
            pg.keyboard.press("Escape")
            if any(i.startswith("Checkpoint") for i in items):
                reached.add("Checkpoint")
        bad = [f"{x} not reached" for x in ("context usage", "Checkpoint", "Stop", "⋯") if x not in reached]
        bad += [f"⋯ item {i!r} not reached" for i in wide_menu if i not in items]
        if scrolled:
            bad.append(f"the bar scrolled ({scrolled}px)")
        if hidden:
            bad.append(f"focused but outside the column or covered: {hidden}")
        self.row("ac-nothing-lost", "running 380, keyboard", True, not bad,
                 f"reached {sorted(reached)}; items {items}; " + ("; ".join(bad) or "ok"))

    def report(self):
        failed = False
        print("\nverdict, one line per check:")
        for crit in ("ac-bar-idle-min", "ac-bar-running", "ac-bar-sweep", "ac-window-independent",
                     "ac-restored-min", "ac-title-visible", "ac-compaction-order", "ac-panel-close",
                     "ac-composer-lines", "ac-nothing-lost"):
            rows = self.rows.get(crit, [])
            reached = bool(rows) and all(r[1] for r in rows)
            ok = reached and all(r[2] for r in rows)
            failed |= not ok
            worst = next((r for r in rows if not r[2]), None)
            detail = f"{worst[0]}: {worst[3]}" if worst else f"{len(rows)} rows pass"
            print(f"check {crit}: reached={'yes' if reached else 'no'} "
                  f"failed_at_assertion={'yes' if reached and not ok else 'no'} -- {detail}")
        print("RESULT:", "FAIL" if failed else "PASS")
        return 1 if failed else 0


def setup_hub():
    """A fresh drive Hub, a scratch project, a Haiku agent and one long-titled, measured thread.

    AW_HUB/AW_KEY/AW_DB reuse a running fresh drive Hub; otherwise one is started from this
    checkout's hub/ on AW_DRIVE_PORT (default 8036) with a new database. Never :8000 or :8010.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import d1029_build_plan_in_spec as d

    d.TMP = d.TMP.parent.parent / "drive1121-f1201-assert" / d.STAMP
    if os.environ.get("AW_HUB"):
        d.HUB, d.KEY, d.DB = os.environ["AW_HUB"].rstrip("/"), os.environ["AW_KEY"], pathlib.Path(os.environ["AW_DB"])
        proc = None
    else:
        d.PORT = int(os.environ.get("AW_DRIVE_PORT") or 8036)
        if d.PORT in (8000, 8010):
            sys.exit("never the operator's or the trial Hub")
        d.HUB, d.KEY, d.DB = f"http://127.0.0.1:{d.PORT}", "aw_live_" + secrets.token_hex(16), d.TMP / "agentweave.db"
        proc = d.start_hub()
    root = d.TMP / "proj"
    root.mkdir(parents=True, exist_ok=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
    (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    d.git(root, "add", ".")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"f1201-{d.STAMP}"})
    d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    code, runner = d.api("POST", f"/projects/{pid}/runners",
                         {"name": "Haiku", "cli": "claude", "model": "claude-haiku-5-5"})
    d.check("setup: a Haiku runner", code in (200, 201), f"{code} {runner}", fatal=True)
    code, out = d.api("POST", f"/projects/{pid}/agents", {"name": "Dev", "runner_id": runner["id"]})
    d.check("setup: agent Dev", code in (200, 201), f"{code} {out}", fatal=True)
    code, out = d.api("POST", f"/projects/{pid}/agent/trigger",
                      {"agent": "Dev", "message": "Reply with the single word ok."})
    d.check("setup: a first turn", code == 200, f"{code} {out}", fatal=True)
    conv = out["conversation_id"]
    d.wait_idle(pid, 5 * 60)
    code, out = d.api("PATCH", f"/projects/{pid}/agent/Dev/conversations/{conv}", {"title": LONG_TITLE})
    d.check("setup: the thread gets a 120-character title", code == 200, f"{code} {str(out)[:200]}", fatal=True)
    _, convs = d.api("GET", f"/projects/{pid}/agent/Dev/conversations")
    usage = next((c.get("context_usage") for c in convs if c["id"] == conv), None)
    d.check("setup: the thread's last run was measured (the context label shows)", bool(usage), str(usage),
            fatal=True)
    return d, proc, pid, conv


def run_assert():
    shots = None
    if "--shots" in sys.argv:
        shots = sys.argv[sys.argv.index("--shots") + 1]
        os.makedirs(SHOTS, exist_ok=True)
    d, proc, pid, conv = setup_hub()
    drive = Drive(d.HUB, d.KEY, pid, "Dev", conv, shots)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            drive.idle(b)
            drive.run(b)
            b.close()
    finally:
        drive.stop_running()
        d.stop_hub(proc)
    return drive.report()


def observe():
    global HUB, KEY, PID, CONV
    HUB, KEY, PID = os.environ["AW_HUB"], os.environ["AW_KEY"], os.environ["AW_PROJECT"]
    CONV.update(short=os.environ["AW_SHORT"], long=os.environ["AW_LONG"])
    os.makedirs(SHOTS, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        # matrix: width x title, dark, idle; default panel, moderate, and dragged-to-minimum
        for w in (1280, 1440, 1920):
            for which in ("short", "long"):
                ctx, pg = new_ctx(b, w)
                open_thread(pg, which)
                open_panel(pg)
                tag = f"w{w} {which} idle dark"
                record(tag + " | panel default", pg, f"{w}_{which}_default")
                drag_to(pg, 700 if w < 1900 else 900)
                record(tag + " | col dragged ~moderate", pg)
                drag_to(pg, 0)
                record(tag + " | dragged to minimum", pg, f"{w}_{which}_min")
                ctx.close()

        # light theme at 1440
        ctx, pg = new_ctx(b, 1440, "light")
        open_thread(pg, "long")
        open_panel(pg)
        drag_to(pg, 0)
        record("w1440 long idle LIGHT | dragged to minimum", pg, "1440_long_min_light")
        ctx.close()

        # restored from a previous session: drag, then reload (panel open + width persisted)
        ctx, pg = new_ctx(b, 1440)
        open_thread(pg, "long")
        open_panel(pg)
        pg.get_by_role("button", name="Watch").first.click()   # a real tab: an empty panel is not restored (see notes)
        pg.wait_for_timeout(800)
        drag_to(pg, 0)
        ls = pg.evaluate("() => ({pres: localStorage.getItem('aw.spec.presentation.v1'), tabs: localStorage.getItem('aw.panel.tabs.v1')})")
        print("localStorage after drag:", ls)
        pg.reload()
        pg.wait_for_selector("[data-testid=conversation-header]")
        pg.wait_for_timeout(1500)
        record("w1440 long idle dark | RELOAD, restored min width", pg, "1440_long_restored")
        pg.goto(url("short"))
        pg.wait_for_selector("[data-testid=conversation-header]")
        pg.wait_for_timeout(1500)
        record("w1440 short idle dark | restored, other thread", pg, "1440_short_restored")
        pg.goto(url("long"))
        pg.wait_for_selector("[data-testid=conversation-header]")
        pg.wait_for_timeout(1200)
        # what-if: the operator's context label is longer ("58,345 / 1,000,000 · 5.83%")
        pg.evaluate("() => { const l = document.querySelector('.context-usage-label'); l.dataset.orig = l.textContent; l.textContent = '585,345 / 1,000,000 · 58.53%'; }")
        pg.wait_for_timeout(200)
        record("w1440 long idle | restored min, label made 1M-long (DOM what-if)", pg, "1440_long_1mlabel")
        pg.evaluate("() => { const l = document.querySelector('.context-usage-label'); l.textContent = l.dataset.orig; }")
        pg.get_by_test_id("conversation-header").locator(".aw-convbar-title").focus()
        seq = []
        for _ in range(6):
            pg.keyboard.press("Tab")
            pg.wait_for_timeout(120)
            seq.append(pg.evaluate("""() => { const e = document.activeElement; const r = e.getBoundingClientRect();
              const hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
              return (e.getAttribute('data-testid') || e.getAttribute('aria-label') || e.tagName) + ' right=' + Math.round(r.right)
                     + ' covered=' + !(hit && (hit === e || e.contains(hit))); }"""))
        print("Tab order from title (1440, min width):", seq)
        # counterfactual: hide just the context-usage label (what the <=1100px media query would do)
        pg.add_style_tag(content=".aw-convbar-end .context-usage-label{display:none!important}")
        pg.wait_for_timeout(300)
        record("w1440 long idle | min, ctx LABEL hidden by injected css", pg, "1440_long_min_nolabel")
        # panel width reset to default by double-click on the divider, then measure at 480
        pg.get_by_role("separator", name="Resize thread").dblclick()
        pg.wait_for_timeout(400)
        record("w1440 long idle | tab open, divider double-clicked (480)", pg)
        # keyboard resize: Home restores default; ArrowLeft x N shrinks
        ctx.close()

        # Narrow viewports: the only compaction rule is @media (max-width:1100px) on the viewport
        for w in (1100, 1101, 1000):
            ctx, pg = new_ctx(b, w)
            open_thread(pg, "long")
            open_panel(pg)
            pg.get_by_role("button", name="Watch").first.click()
            pg.wait_for_timeout(600)
            drag_to(pg, 0)
            record(f"w{w} long idle dark | tab open, dragged to minimum", pg, f"{w}_long_min")
            ctx.close()

        # Running: start a slow turn on each thread, measure while it runs
        for which in ("short", "long"):
            ctx, pg = new_ctx(b, 1440)
            open_thread(pg, which)
            open_panel(pg)
            drag_to(pg, 0)
            api_post(f"/projects/{PID}/agent/trigger", {"agent": AGENT, "conversation_id": CONV[which],
                     "message": "Use the Bash tool to run: sleep 45  -- then reply done."})
            t0 = time.time()
            while time.time() - t0 < 25 and pg.locator("[data-testid=conversation-header] [data-running=true]").count() == 0:
                pg.wait_for_timeout(500)
            pg.wait_for_timeout(1500)
            record(f"w1440 {which} RUNNING dark | dragged to minimum", pg, f"1440_{which}_min_running")
            drag_to(pg, 729)
            record(f"w1440 {which} RUNNING dark | divider at default 480", pg, f"1440_{which}_480_running")
            t0 = time.time()
            while time.time() - t0 < 80 and pg.locator("[data-testid=conversation-header] [data-running=true]").count():
                pg.wait_for_timeout(1000)
            ctx.close()
        b.close()
    json.dump(rows, open("testbed/drive1121-f1201/rows.json", "w"), indent=1)


if __name__ == "__main__":
    if "--assert" in sys.argv:
        sys.exit(run_assert())
    observe()
