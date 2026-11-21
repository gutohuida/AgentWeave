"""Drive F1201: the thread bar overlaps / is cut off beside the side panel.

Observation only (edits nothing under hub/ or src/). Needs a fresh drive Hub (never :8000/:8010):
  AW_HUB, AW_KEY   the Hub and its key (curl $AW_HUB/api/v1/setup/token)
  AW_PROJECT       project id, AW_AGENT (default Dev), AW_SHORT / AW_LONG conversation ids
                   (a short-titled and a 120-char-titled thread whose last run was measured, so
                   the bar shows the context-usage label)
Writes screenshots to testbed/drive1121-f1201/shots/ and prints one row per condition.
"""
import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HUB = os.environ["AW_HUB"]
KEY = os.environ["AW_KEY"]
PID = os.environ["AW_PROJECT"]
AGENT = os.environ.get("AW_AGENT", "Dev")
CONV = {"short": os.environ["AW_SHORT"], "long": os.environ["AW_LONG"]}
SHOTS = "testbed/drive1121-f1201/shots"
os.makedirs(SHOTS, exist_ok=True)
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
