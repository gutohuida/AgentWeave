"""Drive of the loom Thread page (task-231a74f0b9f7). Vite dev servers from this worktree:
5191 -> trial :8010, 5192 -> operator-copy :8020, 5193 -> scale :8021; mock on 5199.
    py -3.11 testbed/drive-loom/drive.py [section ...]
"""

import json
import pathlib
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

REPO = pathlib.Path(__file__).resolve().parents[3]
HERE = REPO / "testbed" / "drive-loom"  # state (key.txt, live_project.txt) and screenshots; ignored
OUT = HERE / "shots"
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH_KEY = (HERE / "key.txt").read_text().strip()
TRIAL_KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
AW = "proj-d85a82bf4216"
SCALE = "proj-b3ac8d791e12"
MOCK = "http://127.0.0.1:5199/mock-loom.html"
results = []
errors = []


def check(name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


def api(hub, key, path):
    req = urllib.request.Request(hub + path, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def seed(key, ui, project, mode):
    return (
        "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s);"
        "localStorage.setItem('agentweave-prefs', JSON.stringify({mode: %s})); } catch (e) {}"
        % (json.dumps(key), json.dumps(ui), json.dumps(project), json.dumps(mode))
    )


class App:
    def __init__(self, browser, ui, key, project):
        self.browser, self.ui, self.key, self.project = browser, ui, key, project

    def page(self, knot=None, mode="dark", reduced=False, tz=None, w=1440, h=900, extra=""):
        ctx = self.browser.new_context(
            viewport={"width": w, "height": h},
            reduced_motion="reduce" if reduced else "no-preference",
            device_scale_factor=1,
            timezone_id=tz,
        )
        ctx.add_init_script(seed(self.key, self.ui, self.project, mode))
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}"[:300]) if m.type == "error" else None)
        url = f"{self.ui}/?project={self.project}&tab=thread" + (f"&knot={knot}" if knot else "") + extra
        pg.goto(url, wait_until="domcontentloaded")
        return pg


GEOM = """() => {
  const main = document.querySelector('.aw-loom[data-scale=surface]');
  if (!main) return null;
  const cloth = main.querySelector('.aw-loom-cloth').getBoundingClientRect();
  const beads = [...main.querySelectorAll('[data-slot=loom-bead]')].map(b => {
    const r = b.getBoundingClientRect();
    return {key: b.dataset.key, x: Math.round(r.left - cloth.left), y: Math.round(r.top - cloth.top), w: Math.round(r.width), h: Math.round(r.height),
            sx: Math.round(r.left), sel: b.getAttribute('aria-selected') === 'true', text: b.textContent};
  });
  const labels = [...main.querySelectorAll('.aw-loom-label')].map(l => {
    const r = l.getBoundingClientRect();
    return {side: l.dataset.side, x: Math.round(r.left - cloth.left), y: Math.round(r.top - cloth.top), w: Math.round(r.width), h: Math.round(r.height), text: l.textContent};
  });
  const gaps = [...main.querySelectorAll('.aw-loom-gap')].map(g => { const r = g.getBoundingClientRect(); return {x: Math.round(r.left - cloth.left), text: g.textContent}; });
  return {beads, labels, gaps, scrollLeft: main.scrollLeft, clientWidth: main.clientWidth, scrollWidth: main.scrollWidth, cloth: {w: Math.round(cloth.width), h: Math.round(cloth.height)},
          path: main.querySelector('.aw-loom-line')?.getAttribute('d')};
}"""

PANEL = """() => {
  const d = document.querySelector('.aw-loom-detail');
  if (!d) return null;
  const q = (s) => d.querySelector(s)?.textContent?.trim() ?? null;
  return {
    kind: q('.aw-loom-detail-kind'), of: q('.aw-loom-detail-of'), title: q('.aw-loom-detail-title'), summary: q('.aw-loom-detail-summary'),
    facts: [...d.querySelectorAll('.aw-loom-fact')].map(f => f.textContent.trim()),
    actors: [...d.querySelectorAll('.aw-loom-actor')].map(a => a.textContent.trim()),
    kinds: [...d.querySelectorAll('.aw-loom-kindchip')].map(a => a.textContent.trim()),
    crumbs: [...d.querySelectorAll('.aw-loom-crumb')].map(a => a.textContent.trim()),
    open: q('[data-slot=loom-open]'),
    before: d.querySelector('[aria-label="The knot before"]')?.disabled, after: d.querySelector('[aria-label="The knot after"]')?.disabled,
    innerHead: q('.aw-loom-inner-head'),
    inner: [...d.querySelectorAll('.aw-loom-inner [data-slot=loom-bead]')].map(b => ({key: b.dataset.key, sel: b.getAttribute('aria-selected') === 'true'})),
  };
}"""

HEADER = "() => ({count: document.querySelector('.aw-loom-bar-count')?.textContent, span: document.querySelector('.aw-loom-bar-span')?.textContent, jumps: [...document.querySelectorAll('[data-slot=loom-jump]')].map(b => b.disabled), weave: !!document.querySelector('[data-slot=weave-thread]')})"


def wait_loom(pg, timeout=15000):
    pg.wait_for_selector(".aw-loom[data-scale=surface] [data-slot=loom-bead]", timeout=timeout)


def selected_key(pg):
    return pg.evaluate("() => document.querySelector('.aw-loom[data-scale=surface] [aria-selected=true]')?.dataset.key ?? null")


# ─────────────────────────────────────────────────────────────────────────────────────────────


def mock_match(browser):
    """ac-mock-match / FR-13: the operator copy (same 17 chapters as the mock) with chapter 17 selected."""
    fixture = json.loads((REPO / "hub/ui/mock/thread-chapters-fixture.json").read_text(encoding="utf-8"))
    ch17 = fixture["levels"]["surface"]["knots"][-2]["key"]
    app = App(browser, "http://127.0.0.1:5192", SCRATCH_KEY, AW)
    out = {}
    for mode in ("dark", "light"):
        pg = app.page(knot=ch17, mode=mode)
        wait_loom(pg)
        pg.wait_for_timeout(2600)
        pg.screenshot(path=str(OUT / f"page_ch17_{mode}.png"))
        real = pg.evaluate(GEOM)
        rpanel = pg.evaluate(PANEL)
        rhead = pg.evaluate(HEADER)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        mp = ctx.new_page()
        mp.goto(f"{MOCK}?mode={mode}", wait_until="domcontentloaded")
        wait_loom(mp)
        mp.wait_for_timeout(2600)
        mp.screenshot(path=str(OUT / f"mock_ch17_{mode}.png"))
        mock = mp.evaluate(GEOM)
        mpanel = mp.evaluate(PANEL)
        mhead = mp.evaluate(HEADER)
        # Style comparison of the page area (below the app's top bar / the mock's bar)
        style = """() => { const s = (sel) => { const e = document.querySelector(sel); if (!e) return null; const c = getComputedStyle(e);
            return [c.fontFamily, c.fontSize, c.fontWeight, c.color, c.backgroundColor, c.stroke, c.strokeWidth].join('|'); };
            return {line: s('.aw-loom[data-scale=surface] .aw-loom-line'), bead: s('.aw-loom[data-scale=surface] .aw-loom-bead'), sel: s('.aw-loom[data-scale=surface] .aw-loom-bead[data-selected=true]'),
                    label: s('.aw-loom[data-scale=surface] .aw-loom-label-title'), when: s('.aw-loom[data-scale=surface] .aw-loom-label-when'), gap: s('.aw-loom-gap'),
                    count: s('.aw-loom-bar-count'), span: s('.aw-loom-bar-span'), title: s('.aw-loom-detail-title'), summary: s('.aw-loom-detail-summary'), kind: s('.aw-loom-detail-kind'),
                    fact: s('.aw-loom-fact dt'), page: s('.aw-loom-page'), card: s('.aw-loom-detail-card'),
                    pageBox: (() => { const r = document.querySelector('.aw-loom-page').getBoundingClientRect(); return [Math.round(r.left), Math.round(r.width)]; })(),
                    detailBox: (() => { const r = document.querySelector('.aw-loom-detail').getBoundingClientRect(); return [Math.round(r.left), Math.round(r.width), Math.round(r.height)]; })(),
                    mainBox: (() => { const r = document.querySelector('.aw-loom-main').getBoundingClientRect(); return [Math.round(r.left), Math.round(r.width), Math.round(r.height)]; })()}; }"""
        rs, ms = pg.evaluate(style), mp.evaluate(style)
        out[mode] = {"real": real, "mock": mock, "rpanel": rpanel, "mpanel": mpanel, "rhead": rhead, "mhead": mhead, "rstyle": rs, "mstyle": ms}
        mb = {b["key"]: b for b in mock["beads"]}
        same = [k for k in (b["key"] for b in real["beads"]) if k in mb]
        diffs = [(k, (rb["x"], rb["y"], rb["w"], rb["h"]), (mb[k]["x"], mb[k]["y"], mb[k]["w"], mb[k]["h"])) for rb in real["beads"] for k in [rb["key"]] if k in mb and (rb["x"], rb["y"], rb["w"], rb["h"]) != (mb[k]["x"], mb[k]["y"], mb[k]["w"], mb[k]["h"])]
        check(f"mock-match {mode}: {len(same)} shared surface knots at the same position and size", len(same) >= 17 and not diffs, f"diffs={diffs[:5]}")
        mlab = {(l["x"], l["text"]) for l in mock["labels"]}
        rlab_shared = [l for l in real["labels"] if any(l["x"] == x for x, _ in mlab)]
        lab_diff = [l for l in real["labels"][:17] if (l["x"], l["text"]) not in mlab]
        check(f"mock-match {mode}: the 17 chapter labels match (side, place, text)", not lab_diff and len(rlab_shared) >= 17,
              f"diffs={[(l['text'][:40], l['x']) for l in lab_diff[:4]]}")
        rgap = [g for g in real["gaps"] if g["x"] < (real["beads"][16]["x"] + 20)]
        check(f"mock-match {mode}: silence labels among the chapters match", rgap == [g for g in mock["gaps"] if g["x"] < mock["beads"][16]["x"] + 20], f"real={[g['text'] for g in rgap]} mock={[g['text'] for g in mock['gaps']]}")
        keys = ["kind", "title", "summary", "facts", "kinds", "open", "before", "innerHead"]
        pd = {k: (rpanel[k], mpanel[k]) for k in keys if rpanel[k] != mpanel[k]}
        check(f"mock-match {mode}: panel for chapter 17 reads the same", not pd, json.dumps(pd)[:600])
        check(f"mock-match {mode}: panel actors match by name (colours may differ)", rpanel["actors"] == mpanel["actors"], f"{rpanel['actors']} vs {mpanel['actors']}")
        sd = {k: (rs[k], ms[k]) for k in rs if rs[k] != ms[k]}
        check(f"mock-match {mode}: computed typography, colours and boxes match", not sd, json.dumps(sd)[:900])
        check(f"mock-match {mode}: header reads the same shape", rhead["count"] == mhead["count"], f"real={rhead} mock={mhead}")
        pg.context.close()
        ctx.close()
    (OUT / "mock_match.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


def operator_copy(browser):
    """The operator's own thread (17 chapters + newer loose knots): open, count, panel, before/after,
    descend, leaf, open link, days in two zones, keys, drag, wheel, address."""
    hub = "http://127.0.0.1:8020"
    app = App(browser, "http://127.0.0.1:5192", SCRATCH_KEY, AW)
    first = api(hub, SCRATCH_KEY, f"/api/v1/projects/{AW}/thread?first=true")
    chapters = [k for k in first["knots"] if k["kind"] == "chapter"]
    newest = api(hub, SCRATCH_KEY, f"/api/v1/projects/{AW}/thread")
    # open: newest selected, at the right, every knot to its left older
    pg = app.page()
    t0 = time.perf_counter()
    wait_loom(pg)
    check("opens: first knots show", True, f"{time.perf_counter() - t0:.2f}s")
    pg.wait_for_timeout(2500)
    g = pg.evaluate(GEOM)
    sel = [b for b in g["beads"] if b["sel"]]
    last = newest["knots"][-1]["key"]
    check("ac-opens-newest: the newest surface knot is selected", sel and sel[0]["key"] == last, f"selected={sel[0]['key'] if sel else None} newest={last}")
    vis = sel and 0 <= sel[0]["sx"] <= 1440
    check("ac-opens-newest: it is in view, the right-most bead", vis and sel[0]["x"] == max(b["x"] for b in g["beads"]), f"screen x={sel[0]['sx'] if sel else None}")
    order = [b["key"] for b in sorted(g["beads"], key=lambda b: b["x"])]
    check("ac-opens-newest: left to right is the route's oldest-first order", order == [k["key"] for k in newest["knots"]], f"{len(order)} beads")
    xs = sorted(b["x"] + b["w"] / 2 for b in g["beads"])
    steps = {xs[i + 1] - xs[i] for i in range(len(xs) - 1)}
    # x and w are rounded separately, so a centre can be half a pixel out; even.py measures unrounded
    steps = {s for s in steps if not any(abs(s - t) <= 1 for t in steps if t < s)}
    check("ac-even: every neighbouring pair is the same distance apart", len(steps) == 1, f"steps={steps}")
    head = pg.evaluate(HEADER)
    check("ac-count: header", head["count"] == "17 chapters" and head["span"].startswith("Mar 7 to Oct 24") and "newer knots not in a chapter yet" in head["span"], json.dumps(head))
    pg.screenshot(path=str(OUT / "op_open_dark.png"))
    # The beginning selects chapter 1
    t0 = time.perf_counter()
    pg.get_by_role("button", name="The beginning").click()
    pg.wait_for_function("k => document.querySelector('.aw-loom[data-scale=surface] [aria-selected=true]')?.dataset.key === k", arg=chapters[0]["key"], timeout=5000)
    check("ac-opens-newest: the beginning control selects chapter 1", True, f"{time.perf_counter() - t0:.2f}s; panel={pg.evaluate(PANEL)['kind']}")
    pg.wait_for_timeout(2200)
    g1 = pg.evaluate(GEOM)
    b1 = next(b for b in g1["beads"] if b["key"] == chapters[0]["key"])
    check("the beginning: chapter 1 is in view", 0 <= b1["sx"] <= 1440, f"x={b1['sx']}")
    pg.screenshot(path=str(OUT / "op_beginning_dark.png"))
    # alternation & labels away from the middle & madder
    mid = g1["cloth"]["h"] / 2
    ch = [b for b in sorted(g1["beads"], key=lambda b: b["x"])][:17]
    sides = [(b["y"] + b["h"] / 2) < mid for b in ch]
    alt = all(sides[i] != sides[i + 1] for i in range(len(sides) - 1))
    check("ac-alternate: knots alternate above and below the middle", alt, f"above={sides}")
    labs = sorted(g1["labels"], key=lambda l: l["x"])[:17]
    away = all(((l["y"] + l["h"] / 2) < (b["y"] + b["h"] / 2)) == s for l, b, s in zip(labs, ch, sides))
    check("ac-alternate: each label is on the side away from the middle", away)
    stroke = pg.evaluate("() => [getComputedStyle(document.querySelector('.aw-loom-line')).stroke, getComputedStyle(document.documentElement).getPropertyValue('--brand-madder')]")
    check("ac-alternate: the line is madder", stroke[0].replace(" ", "") in ("rgb(204,70,48)", "rgb(176,58,38)"), f"{stroke}")
    gaps = g1["gaps"]
    check("ac-silence: silences of 10+ days are labelled, same-day neighbours are not", len(gaps) > 0, f"{[g['text'] for g in gaps]}")
    # before / after
    ch16, ch17 = chapters[15], chapters[16]
    pg.close()
    pg = app.page(knot=ch16["key"])
    wait_loom(pg)
    pg.wait_for_timeout(1500)
    pg.get_by_role("button", name="The knot after").click()
    pg.wait_for_timeout(500)
    p = pg.evaluate(PANEL)
    check("ac-before-after: after on chapter 16 selects chapter 17", p["title"] == ch17["title"] and selected_key(pg) == ch17["key"], f"{p['kind']} {p['title']}")
    check("ac-before-after: on chapter 17 the after control is disabled", p["after"] is True,
          f"after disabled={p['after']} (a newer loose knot follows chapter 17; open question q-53306e0dad2d)")
    # panel for chapter 17
    check("ac-panel: Chapter 17 of 17", p["kind"].endswith("Chapter17 of 17") or "17 of 17" in (p["of"] or ""), p["kind"])
    check("ac-panel: facts", any("Oct 24 · 1 day" in f for f in p["facts"]) and any("47 knots · 97 all the way down" in f for f in p["facts"]), json.dumps(p["facts"]))
    check("ac-panel: made of", p["kinds"] == ["45 conversations", "1 vault entry", "1 document"], json.dumps(p["kinds"]))
    check("ac-panel: who", set(["manager", "Operator", "mender", "Architect"]) <= set(p["actors"]), json.dumps(p["actors"]))
    check("ac-panel: summary present", bool(p["summary"]), (p["summary"] or "")[:80])
    pg.screenshot(path=str(OUT / "op_ch17_panel.png"))
    # descend: third knot on the panel's thread
    third = pg.locator(".aw-loom-inner [data-slot=loom-bead]").nth(2)
    third.click()
    pg.wait_for_timeout(600)
    p3 = pg.evaluate(PANEL)
    check("ac-descend: third knot reads 'Conversation 3 of N' with the chapter in the trail", (p3["of"] or "").startswith("3 of") and p3["crumbs"] == [ch17["title"]], f"{p3['kind']} crumbs={p3['crumbs']}")
    pg.screenshot(path=str(OUT / "op_descend_conv3.png"))
    # open the conversation
    if p3["open"]:
        before_url = pg.url
        pg.locator("[data-slot=loom-open]").click()
        pg.wait_for_timeout(1200)
        check("ac-panel-link: 'Open the conversation' opens it", pg.url != before_url and "conversation=" in pg.url, f"{p3['open']} -> {pg.url}")
        pg.go_back()
        pg.wait_for_timeout(1500)
    # trail back up
    pg.close()
    pg = app.page(knot=None)
    wait_loom(pg)
    pg.goto(f"{app.ui}/?project={AW}&tab=thread&knot={ch17['key']}")
    wait_loom(pg)
    pg.wait_for_timeout(1500)
    pg.locator(".aw-loom-inner [data-slot=loom-bead]").nth(2).click()
    pg.wait_for_timeout(500)
    pg.locator(".aw-loom-crumb").first.click()
    pg.wait_for_timeout(500)
    check("ac-descend: choosing the chapter in the trail selects it again", pg.evaluate(PANEL)["title"] == ch17["title"])
    # leaf: find a knot under chapter 17 that holds nothing
    inner = api(hub, SCRATCH_KEY, f"/api/v1/projects/{AW}/thread?under={ch17['key']}&first=true")["knots"]
    leaf = next((k for k in inner if k["child_count"] == 0), None)
    if leaf:
        idx = [k["key"] for k in inner].index(leaf["key"])
        pg.locator(".aw-loom-inner [data-slot=loom-bead]").nth(idx).click()
        pg.wait_for_timeout(600)
        pl = pg.evaluate(PANEL)
        check("ac-leaf: a knot holding nothing shows the knots beside it, marked", pl["innerHead"].startswith("Beside it") and any(b["sel"] and b["key"] == leaf["key"] for b in pl["inner"]) and len(pl["inner"]) > 1, f"{pl['innerHead'][:30]} {len(pl['inner'])} beside")
        pg.screenshot(path=str(OUT / "op_leaf.png"))
    pg.close()
    # days in two zones
    for tz in ("Europe/Lisbon", "Africa/Lagos", "America/Bogota"):
        tp = app.page(knot=ch17["key"], tz=tz)
        wait_loom(tp)
        tp.wait_for_timeout(1500)
        lab = tp.evaluate("k => [...document.querySelectorAll('.aw-loom[data-scale=surface] .aw-loom-label')].map(l => l.textContent)[16]", ch17["key"])
        pp = tp.evaluate(PANEL)
        when = next((f for f in pp["facts"] if f.startswith("When")), "")
        check(f"ac-days ({tz}): label and panel read Oct 24 and 1 day", lab.startswith("Oct 24") and "Oct 24 · 1 day" in when and "Oct 25" not in when, f"label={lab[:30]} when={when}")
        tp.context.close()
    # keys: chapter 10 focused -> Right, Enter, Escape
    ch10, ch11 = chapters[9], chapters[10]
    kp = app.page(knot=ch10["key"])
    wait_loom(kp)
    kp.wait_for_timeout(1500)
    act = "() => ({key: document.activeElement?.dataset?.key ?? null, cls: document.activeElement?.className, inInner: !!document.activeElement?.closest('.aw-loom-inner')})"
    a0 = kp.evaluate(act)
    check("ac-address: an opened address gives the knot keyboard focus", a0["key"] == ch10["key"], json.dumps(a0))
    kp.keyboard.press("ArrowRight")
    kp.wait_for_timeout(500)
    a1 = kp.evaluate(act)
    check("ac-keys: Right selects and focuses chapter 11", selected_key(kp) == ch11["key"] and a1["key"] == ch11["key"], json.dumps(a1))
    kp.keyboard.press("Enter")
    kp.wait_for_timeout(1500)
    inner11 = api(hub, SCRATCH_KEY, f"/api/v1/projects/{AW}/thread?under={ch11['key']}&first=true")["knots"]
    p = kp.evaluate(PANEL)
    a2 = kp.evaluate(act)
    check("ac-keys: Enter selects the first knot inside chapter 11, focus following", p["title"] == inner11[0]["title"] and p["crumbs"] == [ch11["title"]] and (a2["key"] == inner11[0]["key"] or "detail-title" in (a2["cls"] or "")), f"panel={p['title'][:40]} focus={a2}")
    kp.keyboard.press("Escape")
    kp.wait_for_timeout(600)
    a3 = kp.evaluate(act)
    check("ac-keys: Escape selects chapter 11 again, focus following", kp.evaluate(PANEL)["title"] == ch11["title"] and a3["key"] == ch11["key"], json.dumps(a3))
    kp.keyboard.press("Home")
    kp.wait_for_timeout(500)
    a4 = kp.evaluate(act)
    kp.keyboard.press("End")
    kp.wait_for_timeout(500)
    a5 = kp.evaluate(act)
    g = kp.evaluate(GEOM)
    xs = sorted(g["beads"], key=lambda b: b["x"])
    check("FR-10: Home and End select the first and last loaded knot", a4["key"] == xs[0]["key"] and a5["key"] == xs[-1]["key"], f"{a4['key']} {a5['key']}")
    kp.close()
    # drag and wheel
    dp = app.page(knot=ch10["key"])
    wait_loom(dp)
    dp.wait_for_timeout(2000)
    bead = dp.locator(f".aw-loom[data-scale=surface] [data-key='{ch11['key']}']")
    box = bead.bounding_box()
    s0 = dp.evaluate("() => document.querySelector('.aw-loom[data-scale=surface]').scrollLeft")
    dp.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    dp.mouse.down()
    for i in range(1, 21):
        dp.mouse.move(box["x"] + box["width"] / 2 - 10 * i, box["y"] + box["height"] / 2)
    dp.mouse.up()
    dp.wait_for_timeout(400)
    s1 = dp.evaluate("() => document.querySelector('.aw-loom[data-scale=surface]').scrollLeft")
    check("ac-drag: dragged 200px left, the thread scrolled 200px and the selection did not change", s1 - s0 == 200 and selected_key(dp) == ch10["key"], f"scroll {s0}->{s1}, selected={selected_key(dp) == ch10['key']}")
    dp.mouse.move(700, box["y"])
    s2 = dp.evaluate("() => document.querySelector('.aw-loom[data-scale=surface]').scrollLeft")
    dp.mouse.wheel(0, 300)
    dp.wait_for_timeout(400)
    s3 = dp.evaluate("() => document.querySelector('.aw-loom[data-scale=surface]').scrollLeft")
    check("FR-10: a vertical wheel scrolls the thread sideways", s3 != s2, f"{s2}->{s3}")
    dp.close()
    # address: a run three levels below a chapter
    target = None
    for c in chapters[::-1]:
        for k1 in api(hub, SCRATCH_KEY, f"/api/v1/projects/{AW}/thread?under={c['key']}&first=true&limit=200")["knots"]:
            if not k1["child_count"]:
                continue
            for k2 in api(hub, SCRATCH_KEY, f"/api/v1/projects/{AW}/thread?under={k1['key']}&first=true&limit=200")["knots"]:
                if not k2["child_count"]:
                    continue
                for k3 in api(hub, SCRATCH_KEY, f"/api/v1/projects/{AW}/thread?under={k2['key']}&first=true&limit=200")["knots"]:
                    if k3["kind"] == "run":
                        target = (c, k1, k2, k3)
                        break
                if target:
                    break
            if target:
                break
        if target:
            break
    if not target:
        check("ac-address: found a run three levels below a chapter", False)
        return
    c, k1, k2, k3 = target
    print("address target:", [x["kind"] + ":" + x["title"][:30] for x in target])
    sp = app.page(knot=c["key"])
    wait_loom(sp)
    sp.wait_for_timeout(1500)
    for k in (k1, k2, k3):
        sp.locator(f".aw-loom-inner [data-key='{k['key']}']").click()
        sp.wait_for_timeout(1500)
    url = sp.url
    check("FR-8: selecting puts the knot's address in the URL", "knot=" in url and k3["key"].split(":")[-1] in url, url)
    sp.close()
    t0 = time.perf_counter()
    np_ = app.page(knot=None, extra="")
    np_.goto(url)
    wait_loom(np_)
    np_.wait_for_function("t => document.querySelector('.aw-loom-detail-title')?.textContent === t", arg=k3["title"], timeout=8000)
    np_.wait_for_timeout(1500)
    p = np_.evaluate(PANEL)
    a = np_.evaluate(act)
    inview = np_.evaluate("""k => { const s = document.querySelector('.aw-loom-inner .aw-loom'); const b = [...s.querySelectorAll('[data-slot=loom-bead]')].find(e => e.dataset.key === k);
        if (!b) return null; const r = b.getBoundingClientRect(), q = s.getBoundingClientRect(); return [Math.round(r.left), Math.round(q.left), Math.round(q.right)]; }""", k3["key"])
    chin = np_.evaluate("""k => { const s = document.querySelector('.aw-loom[data-scale=surface]'); const b = [...s.querySelectorAll('[data-slot=loom-bead]')].find(e => e.dataset.key === k);
        if (!b) return null; const r = b.getBoundingClientRect(), q = s.getBoundingClientRect(); return [Math.round(r.left), Math.round(q.left), Math.round(q.right), b.getAttribute('aria-selected')]; }""", c["key"])
    check("ac-address: the run is selected with the trail of its chapter and the knots between", p["title"] == k3["title"] and p["crumbs"] == [c["title"], k1["title"], k2["title"]], f"crumbs={p['crumbs']}")
    check("ac-address: in view on the panel's thread", inview and inview[1] <= inview[0] <= inview[2], f"{inview}")
    check("ac-address: its chapter is in view on the surface", chin and chin[1] <= chin[0] <= chin[2] and chin[3] == "true", f"{chin}")
    check("ac-address: it has keyboard focus", a["key"] == k3["key"] and a["inInner"], json.dumps(a))
    np_.screenshot(path=str(OUT / "op_address_3deep.png"))
    np_.close()


def click_visible_left(pg):
    """Click a surface bead that is on screen in the left part of the thread, with the mouse (no scrollIntoView)."""
    b = pg.evaluate("""() => { const s = document.querySelector('.aw-loom[data-scale=surface]'); const q = s.getBoundingClientRect();
      const all = [...s.querySelectorAll('[data-slot=loom-bead]')].map(e => ({k: e.dataset.key, r: e.getBoundingClientRect(), sel: e.getAttribute('aria-selected') === 'true'}));
      const c = all.filter(x => !x.sel && x.r.left > q.left + 60 && x.r.right < q.left + q.width * 0.35);
      const x = c[0]; return x ? {k: x.k, x: x.r.left + x.r.width / 2, y: x.r.top + x.r.height / 2} : null; }""")
    pg.mouse.click(b["x"], b["y"])
    return b["k"]


def motion(browser):
    """ac-reduced, ac-draws: draw-in at 250ms and 2s, and nothing moves under reduced motion."""
    app = App(browser, "http://127.0.0.1:5192", SCRATCH_KEY, AW)
    fixture = json.loads((REPO / "hub/ui/mock/thread-chapters-fixture.json").read_text(encoding="utf-8"))
    ch17 = fixture["levels"]["surface"]["knots"][-2]["key"]
    probe = """() => { const svg = document.querySelector('.aw-loom[data-scale=surface] .aw-loom-reveal');
      const beads = [...document.querySelectorAll('.aw-loom[data-scale=surface] .aw-loom-bead')];
      const shown = beads.filter(b => parseFloat(getComputedStyle(b).opacity) > 0.95).length;
      const anims = document.getAnimations().filter(a => a.playState === 'running').map(a => a.animationName);
      return {clip: svg ? getComputedStyle(svg).clipPath : null, shown, beads: beads.length, running: [...new Set(anims)]}; }"""
    pg = app.page(knot=ch17)
    pg.wait_for_selector(".aw-loom[data-scale=surface] .aw-loom-reveal", timeout=15000)
    pg.wait_for_timeout(250)
    a = pg.evaluate(probe)
    pg.screenshot(path=str(OUT / "draw_250ms.png"))
    pg.wait_for_timeout(1750)
    b = pg.evaluate(probe)
    pg.screenshot(path=str(OUT / "draw_2s.png"))
    check("ac-draws: partly drawn from the left a quarter second in", a["clip"] and "inset" in a["clip"] and a["shown"] < a["beads"], json.dumps(a))
    check("ac-draws: fully drawn with every knot shown within two seconds", b["shown"] == b["beads"] and (b["clip"] in ("none", None) or "0px 0px" in b["clip"] or " 0px -40px 0px" in b["clip"]), json.dumps(b))
    g_normal = pg.evaluate(GEOM)
    t_normal = pg.evaluate("() => document.querySelector('.aw-loom-page').innerText")
    pg.wait_for_timeout(1500)
    frames = []
    for i in range(4):
        frames.append(pg.evaluate("() => document.getAnimations().filter(a => a.playState === 'running').map(a => a.animationName)"))
        pg.wait_for_timeout(200)
    check("FR-11: the selected knot breathes and the glint is scheduled (normal motion)", any("aw-loom-breathe" in f for f in frames) and any("aw-loom-glint" in f for f in frames), json.dumps(frames[0]))
    # choosing a knot glides
    sl0 = pg.evaluate("() => document.querySelector('.aw-loom[data-scale=surface]').scrollLeft")
    picked = click_visible_left(pg)
    pg.wait_for_timeout(80)
    sl1 = pg.evaluate("() => document.querySelector('.aw-loom[data-scale=surface]').scrollLeft")
    pg.wait_for_timeout(1200)
    sl2 = pg.evaluate("() => document.querySelector('.aw-loom[data-scale=surface]').scrollLeft")
    check("FR-11: choosing a knot glides it into view (mid-way after 80ms)", sl0 != sl2 and sl1 not in (sl0, sl2) and selected_key(pg) == picked, f"{sl0} -> {sl1} -> {sl2}")
    pg.close()
    rp = app.page(knot=ch17, reduced=True)
    rp.wait_for_selector(".aw-loom[data-scale=surface] .aw-loom-reveal", timeout=15000)
    rp.wait_for_timeout(250)
    r = rp.evaluate(probe)
    rp.screenshot(path=str(OUT / "reduced_250ms.png"))
    check("ac-reduced: at 250ms everything is already shown, nothing running", r["shown"] == r["beads"] and not r["running"], json.dumps(r))
    rp.wait_for_timeout(1800)
    g_red = rp.evaluate(GEOM)
    t_red = rp.evaluate("() => document.querySelector('.aw-loom-page').innerText")
    same = [(b["key"], b["x"], b["y"]) for b in g_red["beads"]] == [(b["key"], b["x"], b["y"]) for b in g_normal["beads"]] and t_red == t_normal
    check("ac-reduced: the content is the same as with motion", same)
    sl0 = rp.evaluate("() => document.querySelector('.aw-loom[data-scale=surface]').scrollLeft")
    picked = click_visible_left(rp)
    rp.wait_for_timeout(30)
    rr = rp.evaluate(probe)
    sl1 = rp.evaluate("() => document.querySelector('.aw-loom[data-scale=surface]').scrollLeft")
    rp.wait_for_timeout(800)
    sl2 = rp.evaluate("() => document.querySelector('.aw-loom[data-scale=surface]').scrollLeft")
    check("ac-reduced: choosing a knot: no glide, no rise, no pulse", sl1 == sl2 and sl1 != sl0 and selected_key(rp) == picked and not [a for a in rr["running"] if a.startswith("aw-loom")], f"scroll {sl0}->{sl1}->{sl2} running={rr['running']}")
    rp.screenshot(path=str(OUT / "reduced_chosen.png"))
    rp.close()


def scale(browser):
    """ac-scale, ac-page-earlier: 165 surface knots over 10,000 items, no chapters."""
    app = App(browser, "http://127.0.0.1:5193", SCRATCH_KEY, SCALE)
    asked = []
    for attempt in range(2):
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        ctx.add_init_script(seed(SCRATCH_KEY, app.ui, SCALE, "dark"))
        pg = ctx.new_page()
        pg.on("request", lambda r: asked.append(r.url) if "/thread" in r.url else None)
        pg.goto(f"{app.ui}/?project={SCALE}&tab=projects", wait_until="domcontentloaded")
        pg.get_by_test_id("project-tab-thread").first.wait_for(timeout=20000)
        pg.wait_for_timeout(1000)
        t0 = time.perf_counter()
        pg.get_by_test_id("project-tab-thread").first.click()
        wait_loom(pg, timeout=5000)
        t_open = time.perf_counter() - t0
        pg.wait_for_timeout(2200)
        t0 = time.perf_counter()
        pg.get_by_role("button", name="The beginning").click()
        pg.wait_for_function("() => document.querySelector('.aw-loom-detail-title')?.textContent === 'Scale document 1'", timeout=5000)
        t_begin = time.perf_counter() - t0
        check(f"ac-scale (try {attempt + 1}): opening the tab and the beginning each show knots within one second", t_open < 1 and t_begin < 1, f"open {t_open:.2f}s, beginning {t_begin:.2f}s")
        pg.wait_for_timeout(1500)
        ctx.close()
    # page earlier
    pg = app.page()
    asked.clear()
    pg.on("request", lambda r: asked.append(r.url) if "/thread" in r.url else None)
    wait_loom(pg)
    pg.wait_for_timeout(2500)
    head = pg.evaluate(HEADER)
    check("FR-3: with no chapters the header counts surface knots", head["count"] == "165 knots", json.dumps(head))
    g0 = pg.evaluate(GEOM)
    sel0 = selected_key(pg)
    check("ac-page-earlier: 40 newest loaded, the 40th selected", len(g0["beads"]) == 40 and sel0 == g0["beads"][-1]["key"], f"{len(g0['beads'])} beads, selected={sel0}")
    pg.screenshot(path=str(OUT / "scale_open.png"))
    # scroll to within one screen of the left end: pick a visible reference bead first
    pg.evaluate("() => { const s = document.querySelector('.aw-loom[data-scale=surface]'); s.scrollLeft = s.clientWidth * 1.3; }")
    pg.wait_for_timeout(300)
    held = []
    pg.route("**/thread?*before=*", lambda r: held.append(r))
    asked.clear()
    pg.evaluate("() => { const s = document.querySelector('.aw-loom[data-scale=surface]'); s.scrollLeft = s.clientWidth * 0.9; }")
    pg.wait_for_function("() => true")
    for _ in range(50):
        if held:
            break
        pg.wait_for_timeout(20)
    gref = pg.evaluate(GEOM)
    ref = next(b for b in gref["beads"] if 300 < b["sx"] < 1100)
    check("ac-page-earlier: scrolling within one screen width of the left end asks for the older page", bool(held) and len(gref["beads"]) == 40, f"held={len(held)} beads={len(gref['beads'])}")
    t0 = time.perf_counter()
    for r in held:
        r.continue_()
    pg.wait_for_function("() => document.querySelectorAll('.aw-loom[data-scale=surface] [data-slot=loom-bead]').length > 40", timeout=5000)
    t_page = time.perf_counter() - t0
    pg.wait_for_timeout(300)
    g1 = pg.evaluate(GEOM)
    after_ref = next(b for b in g1["beads"] if b["key"] == ref["key"])
    check("ac-page-earlier: the next older page is requested and drawn to the left", any("before=" in u for u in asked) and len(g1["beads"]) > 40 and g1["beads"][0]["x"] < after_ref["x"], f"{len(g1['beads'])} beads, page in {t_page:.2f}s, asked={[u.split('?')[1][:60] for u in asked]}")
    check("ac-page-earlier: the selected knot is unchanged", selected_key(pg) == sel0)
    check("ac-page-earlier: the knots in view stay where they were on screen", after_ref["sx"] == ref["sx"], f"{ref['key']}: {ref['sx']} -> {after_ref['sx']}")
    check("FR-7: a page loads within one second", t_page < 1, f"{t_page:.2f}s")
    pg.screenshot(path=str(OUT / "scale_paged.png"))
    pg.close()


def trial(browser):
    """The trial Hub (:8010) itself: weave, unreadable, and the page as it is today."""
    app = App(browser, "http://127.0.0.1:5191", TRIAL_KEY, AW)
    for mode in ("dark", "light"):
        pg = app.page(mode=mode)
        wait_loom(pg)
        pg.wait_for_timeout(2600)
        pg.screenshot(path=str(OUT / f"trial_open_{mode}.png"))
        head = pg.evaluate(HEADER)
        print("trial header", mode, head)
        pg.close()
    pg = app.page()
    wait_loom(pg)
    fired = []

    def weave(route):
        fired.append(route.request.method + " " + route.request.url)
        route.fulfill(status=202, content_type="application/json", body="{}")

    pg.route("**/chapters/weave**", weave)
    pg.route("**/manager/**", weave)
    btn = pg.locator("[data-slot=weave-thread]")
    check("ac-weave: 'Weave the thread' is offered with the chapters job on", btn.count() == 1)
    if btn.count():
        btn.click()
        pg.wait_for_timeout(800)
        note = pg.locator(".aw-loom-weave-note").text_content() if pg.locator(".aw-loom-weave-note").count() else None
        check("ac-weave: pressing it asks the job to fire", bool(fired), f"{fired} note={note}")
        pg.screenshot(path=str(OUT / "trial_weave.png"))
    pg.close()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script(seed(TRIAL_KEY, app.ui, AW, "dark"))
    ctx.route("**/api/v1/projects/*/thread**", lambda r: r.fulfill(status=500, body="boom"))
    pg = ctx.new_page()
    pg.goto(f"{app.ui}/?project={AW}&tab=thread")
    pg.wait_for_selector("[role=alert]", timeout=10000)
    txt = pg.locator(".aw-thread-note[role=alert]").text_content()
    check("ac-unreadable: the page says the thread could not be read and to reload", "could not be read" in txt and "Reload" in txt, txt)
    pg.screenshot(path=str(OUT / "trial_unreadable.png"))
    ctx.close()


SECTIONS = {"mock": mock_match, "op": operator_copy, "motion": motion, "scale": scale, "trial": trial}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(SECTIONS)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in wanted:
            print(f"== {name}", flush=True)
            try:
                SECTIONS[name](browser)
            except Exception as exc:  # report and go on
                check(f"{name}: section crashed", False, repr(exc)[:500])
        browser.close()
    (OUT / f"results_{'_'.join(wanted)}.json").write_text(json.dumps({"results": results, "errors": errors[:50]}, indent=1), encoding="utf-8")
    print(f"{sum(r['ok'] for r in results)}/{len(results)} passed; {len(errors)} console errors")
    for e in errors[:10]:
        print("  ", e)
