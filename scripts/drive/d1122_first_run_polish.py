"""Acceptance drive for `first-run-and-the-overview-read-cleanly` (FRORC), 2026-11-22.

Starts its own Hub from this checkout's hub/ on a fresh database and a free port (never :8000 or
:8010; only the PID it started is stopped), serving the UI bundle in hub/hub/static/ui. The scratch
projects live in the system temp directory, outside the repo. Measures every agent-checked criterion
(ac-quarantine-form through ac-profiles-count) in Chromium and prints one line per criterion:

    check <key>: PASS|FAIL -- <what was measured>

`--assert` exits 1 if any check fails. `--shots` also writes dark, light and 900 px screenshots for
ac-screens-reviewed (the operator's check) into the run's directory. No agent turn is taken: every
state is seeded through the API or the throwaway database.

    py -3.11 scripts/drive/d1122_first_run_polish.py --assert [--shots]
"""

import argparse
import json
import os
import pathlib
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
KEY = "aw_live_" + secrets.token_hex(16)
TMP = pathlib.Path(tempfile.gettempdir()) / "d1122drive" / time.strftime("%H%M%S")
DB = TMP / "hub.db"
HAIKU5 = "claude-haiku-5-5"
HAIKU4 = "claude-haiku-4-5-20251001"
LUNA = "gpt-6-luna"
LONG = "tests/test_" + "very_long_module_name_" * 4 + "x.py::TestSomething::test_a_case_whose_id_is_far_too_long"
LONG_MARK = LONG.replace("very", "VERY")
results = []
HUB = ""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def api(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:1500]
    except urllib.error.URLError as exc:
        return 0, str(exc)


def poll(fn, secs=15.0):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render; try again
            pass
        time.sleep(0.25)
    return False


def verdict(key, ok, detail=""):
    results.append((key, bool(ok)))
    print(f"check {key}: {'PASS' if ok else 'FAIL'} -- {detail}", flush=True)


def guarded(key, fn):
    """A check that raises is a failed check, not a dead drive."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        verdict(key, False, f"drive error {type(exc).__name__}: {str(exc)[:300]}")


def start_hub():
    global HUB
    TMP.mkdir(parents=True, exist_ok=True)
    port = free_port()
    HUB = f"http://127.0.0.1:{port}"
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(TMP / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(port), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not poll(lambda: api("GET", "/projects")[0] == 200, 90):
        proc.kill()
        sys.exit(f"hub did not come up; see {TMP / 'hub.log'}")
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def open_project(name):
    root = TMP / name
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
    (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": name})
    assert code in (200, 201), (code, project)
    api("PATCH", f"/projects/{project['id']}", {"main_branch": "main"})
    return project["id"]


def runner(pid, label, cli, model):
    code, out = api("POST", f"/projects/{pid}/runners", {"name": label, "cli": cli, "model": model})
    assert code in (200, 201), (label, code, out)
    return out["id"]


def agent(pid, name, runner_id):
    code, out = api("POST", f"/projects/{pid}/agents", {"name": name, "runner_id": runner_id})
    assert code in (200, 201), (name, code, out)


class Page:
    """One Chromium page on the Hub, signed in, with a theme and a width to set."""

    def __init__(self, browser, pid):
        self.pid = pid
        self.page = browser.new_page(viewport={"width": 1400, "height": 900})
        self.page.add_init_script(
            "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))

    def go(self, query, theme="dark", width=1400, wait=".aw-topbar-tabs"):
        p = self.page
        p.set_viewport_size({"width": width, "height": 900})
        p.goto(f"{HUB}/?project={self.pid}&{query}", wait_until="domcontentloaded")
        poll(lambda: p.locator(wait).count() >= 1, 30)
        self.theme(theme)
        p.wait_for_timeout(1200)

    def theme(self, mode):
        self.page.evaluate("m => { document.documentElement.dataset.mode = m }", mode)
        self.page.wait_for_timeout(250)


def style_of(page, selector, props):
    return page.evaluate(
        """([sel, props]) => { const e = document.querySelector(sel); if (!e) return null;
        const s = getComputedStyle(e); return Object.fromEntries(props.map(p => [p, s.getPropertyValue(p)])); }""",
        [selector, props])


def visible_border_or_fill(page, selector, section_bg):
    s = style_of(page, selector, ["background-color", "border-top-color", "border-top-width", "border-top-style"])
    if not s:
        return False, "missing"
    border = s["border-top-style"] != "none" and s["border-top-width"] not in ("0px", "") \
        and s["border-top-color"] not in ("rgba(0, 0, 0, 0)", "transparent")
    fill = s["background-color"] not in ("rgba(0, 0, 0, 0)", "transparent")
    differs = (fill and s["background-color"] != section_bg) or border
    return bool(differs), json.dumps(s)


# --------------------------------------------------------------------------- the rich project

def seed_rich():
    pid = open_project("rich")
    base = f"/projects/{pid}"
    r5 = runner(pid, "Haiku 5.5", "claude", HAIKU5)
    r4 = runner(pid, "Haiku 4.5", "claude", HAIKU4)
    rl = runner(pid, "GPT-6-Luna", "codex", LUNA)
    for name in ("Builder", "Checker", "Planner", "Old"):
        agent(pid, name, r5)
    code, out = api("PATCH", f"{base}/agents/Builder", {"pool": [
        {"runner_id": r5, "effort": None, "default": True},
        {"runner_id": r4, "effort": "high", "default": False},
        {"runner_id": rl, "effort": None, "default": False}]})
    print("pool", code, str(out)[:200] if code >= 300 else "")
    code, out = api("POST", f"{base}/agents/Old/archive")
    print("archive Old", code, str(out)[:200] if code >= 300 else "")
    for who in ("Builder", "Checker", "Planner"):
        code, out = api("POST", f"{base}/tasks", {"title": f"{who} task", "description": "x", "assignee": who})
        assert code in (200, 201), (code, out)
    for i in range(2):
        code, out = api("POST", f"{base}/tasks", {"title": f"Done {i}", "description": "x", "assignee": "Builder"})
        assert code in (200, 201), (code, out)
        # A rejected task is closed without landing: the board counts it finished (`isFinished`).
        code, res = api("PATCH", f"{base}/tasks/{out['id']}", {"status": "rejected", "notes": "seeded"})
        assert code < 300, (code, res)
    return pid


def seed_quarantine(pid):
    code, out = api("PUT", f"/projects/{pid}/checks/quarantine/marks", {"check": "hub-tests", "test": LONG_MARK})
    assert code == 200, (code, out)
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        con.execute(
            "insert into quarantined_tests (id, project_id, check_name, test_id, flake_rate, flips, entered_at, passes) "
            "values (?, ?, 'hub-tests', ?, 0.31, 4, datetime('now'), 1)", ("q-d1122", pid, LONG))
        con.commit()
    finally:
        con.close()


def check_quarantine(pg, empty_pid):
    section = "[data-testid=quarantine-list]"

    def form():
        for theme in ("dark", "light"):
            pg.go("tab=overview", theme, 1100, wait=section)
            p = pg.page
            bg = style_of(p, section, ["background-color"])["background-color"]
            labels = p.locator(f"{section} .aw-ov-q-field > span").all_inner_texts()
            problems = []
            if [x.strip() for x in labels] != ["Check", "Test id"]:
                problems.append(f"labels {labels}")
            for aria in ("Check name", "Test id"):
                sel = f"{section} input[aria-label='{aria}']"
                cls = p.evaluate("s => document.querySelector(s)?.className ?? ''", sel)
                ok, detail = visible_border_or_fill(p, sel, bg)
                if "control-field" not in cls:
                    problems.append(f"{aria}: not the app input class ({cls!r})")
                if not ok:
                    problems.append(f"{aria}: no border/fill in {theme}: {detail}")
            submit = f"{section} form button[type=submit]"
            slot = p.evaluate("s => document.querySelector(s)?.dataset.slot ?? ''", submit)
            disabled = p.evaluate("s => document.querySelector(s)?.disabled", submit)
            ok, detail = visible_border_or_fill(p, submit, "rgba(0, 0, 0, 0)")
            if slot != "button":
                problems.append(f"submit is not the app Button (slot {slot!r})")
            if not disabled or not ok:
                problems.append(f"submit disabled={disabled} border/fill={ok} in {theme}: {detail}")
            if problems:
                verdict("ac-quarantine-form", False, f"{theme}: " + "; ".join(problems))
                return
        verdict("ac-quarantine-form", True, "labels, control-field inputs and a bordered disabled Button in dark and light")

    guarded("ac-quarantine-form", form)

    def rows():
        pg.go("tab=overview", "dark", 1100, wait=section)
        p = pg.page
        qrow = p.locator(f"{section} [data-testid^=quarantined-]")
        mrow = p.locator(f"{section} [data-testid^=never-quarantine-]:not([data-testid=never-quarantine-marks])")
        problems = []
        if qrow.count() != 1 or mrow.count() != 1:
            verdict("ac-quarantine-rows", False, f"rows quarantined={qrow.count()} marks={mrow.count()}")
            return
        info = p.evaluate(
            """() => [...document.querySelectorAll('[data-testid^=quarantined-],[data-testid^=never-quarantine-]:not([data-testid=never-quarantine-marks])')].map(r => {
              const rb = r.getBoundingClientRect(), end = r.querySelector('.aw-ov-row-end'), eb = end && end.getBoundingClientRect();
              const t = r.querySelector('.aw-ov-row-title'), ts = getComputedStyle(t);
              const svg = r.querySelector('.aw-ov-row-icon svg');
              return {cols: getComputedStyle(r).gridTemplateColumns.split(' ').length,
                      atEnd: !!eb && eb.right > rb.right - 24 && eb.top < rb.top + rb.height / 2 + 10 && eb.left > rb.left + rb.width * 0.4,
                      svg: !!svg && svg.innerHTML.trim().length > 0, title: t.getAttribute('title'), text: t.textContent,
                      ellipsis: ts.textOverflow === 'ellipsis' && ts.overflow === 'hidden', clipped: t.scrollWidth > t.clientWidth}; })""")
        if info[0]["cols"] != info[1]["cols"]:
            problems.append(f"layouts differ {info[0]['cols']} vs {info[1]['cols']} columns")
        for name, row in zip(("quarantined", "mark"), info):
            if not row["atEnd"]:
                problems.append(f"{name}: action not at row end")
            if not row["svg"]:
                problems.append(f"{name}: empty icon")
            if not (row["ellipsis"] and row["clipped"] and row["title"] == row["text"] and len(row["text"]) > 90):
                problems.append(f"{name}: id not cut with ellipsis + full title ({row})")
        p.set_viewport_size({"width": 1400, "height": 900})
        p.evaluate("""() => { const s = document.querySelector('[data-testid=quarantine-list]');
            s.style.width = '360px'; s.style.maxWidth = '360px'; }""")
        p.wait_for_timeout(400)
        widths = p.evaluate("""() => { const s = document.querySelector('[data-testid=quarantine-list]');
            return [s.scrollWidth, s.clientWidth]; }""")
        if widths[0] > widths[1]:
            problems.append(f"at 360 px scrollWidth {widths[0]} > clientWidth {widths[1]}")
        verdict("ac-quarantine-rows", not problems, "; ".join(problems) or f"same layout, end action, svg icons, ellipsis+title, 360 px fits {widths}")

    guarded("ac-quarantine-rows", rows)

    def empty():
        empty_pg = Page(pg.page.context.browser, empty_pid)
        empty_pg.go("tab=overview", "dark", 1100, wait=section)
        text = empty_pg.page.locator(section).inner_text()
        ok = "No test is quarantined" in text and "No test is marked" in text \
            and any(w in text for w in ("below", "form", "Name one"))
        verdict("ac-quarantine-empty", ok, text.replace("\n", " | ")[:200])
        empty_pg.page.close()

    guarded("ac-quarantine-empty", empty)


# --------------------------------------------------------------------------- first run

def check_first_run(browser, pid):
    pg = Page(browser, pid)

    def read():
        pg.go("tab=overview", "dark", 1300, wait=".aw-overview")
        p = pg.page
        return {
            "cards": p.locator("[data-testid=setup-list], [data-testid=first-run-panel]").count(),
            "welcome": p.get_by_text("Welcome. Here is how work gets done").count(),
            "items": [t.strip() for t in p.locator("[data-testid=setup-list] .aw-setup-item-title").all_inner_texts()],
            "path": p.evaluate("""() => [...document.querySelectorAll('[data-testid=first-run-path] li')]
                .map(l => l.dataset.state).join(',')"""),
            "buttons": [b.strip() for b in p.locator("[data-testid=setup-list] button, [data-testid=first-run-panel] button").all_inner_texts()],
            "quick": p.locator("a", has_text="Read the quickstart").count(),
        }

    def fresh():
        s = read()
        ok = s["cards"] == 1 and s["welcome"] == 0 and "Add a builder and a checker" in s["items"] \
            and "Start your specifications" in s["items"]
        verdict("ac-first-run-fresh", ok, json.dumps(s))
        pg.page.screenshot(path=str(TMP / "shot_firstrun_1_fresh.png"))
        return s

    guarded("ac-first-run-fresh", fresh)

    def path():
        s1 = read()
        step1 = s1["path"].split(",")[:2] == ["next", "later"]
        r = runner(pid, "Haiku", "claude", HAIKU5)
        agent(pid, "Builder", r)
        agent(pid, "Checker", r)
        s2 = read()
        step2 = s2["path"].split(",")[:2] == ["done", "next"]
        banned = [b for b in s2["buttons"] if b == "Add a profile" or (b.startswith("Ask") and "for a change" in b)]
        ok = step1 and step2 and s2["items"] == ["Start your specifications"] and not banned
        verdict("ac-first-run-path", ok, f"path before={s1['path']} after={s2['path']} items={s2['items']} banned={banned}")
        pg.page.screenshot(path=str(TMP / "shot_firstrun_2_profiles.png"))

    guarded("ac-first-run-path", path)

    def done():
        pg.go("tab=overview", "dark", 1300, wait=".aw-overview")
        item = pg.page.locator("[data-testid^=setup-item-]", has_text="Start your specifications")
        item.get_by_role("button", name="Not for this project").click()
        s = read()
        ok = s["cards"] == 0 and s["quick"] == 1
        verdict("ac-first-run-done", ok, f"cards={s['cards']} quickstart links={s['quick']}")
        pg.page.screenshot(path=str(TMP / "shot_firstrun_3_done.png"))

    guarded("ac-first-run-done", done)
    pg.page.close()


# --------------------------------------------------------------------------- rich project, the rest

def check_threads_and_pool(pg, pair_pid):
    def thread():
        pg.go("agent=Checker&conversation=__new__", "dark", 1300, wait=".aw-newconv")
        p = pg.page
        intro = p.locator(".aw-newconv").inner_text()
        composer = p.locator("form, [data-testid=composer]").last.inner_text() if p.locator("form, [data-testid=composer]").count() else ""
        both = intro + "\n" + composer
        model, cli = both.count("Haiku 5.5"), both.count("Claude Code")
        ok = "Runs on Claude Code" in intro and model == 1 and cli == 1
        verdict("ac-new-thread-once", ok, f"intro={intro.replace(chr(10), ' | ')!r} 'Haiku 5.5' x{model}, 'Claude Code' x{cli}")

    guarded("ac-new-thread-once", thread)

    def pool():
        pg.go("tab=profiles&profile=Builder&section=running", "dark", 1300, wait=".aw-pool-list")
        p = pg.page
        rows = p.locator(".aw-pool-list > li").all_inner_texts()
        want = (("Haiku 5.5", "Claude Code"), ("Haiku 4.5", "Claude Code"), ("GPT-6-Luna", "Codex"))
        problems = []
        if len(rows) != 3:
            problems.append(f"{len(rows)} rows")
        for text, (model, cli) in zip(rows, want):
            low = text.lower()
            if low.count(model.lower()) != 1 or low.count(cli.lower()) != 1:
                problems.append(f"{model}: {text.replace(chr(10), ' | ')!r} has model x{low.count(model.lower())}, {cli} x{low.count(cli.lower())}")
        verdict("ac-pool-row-once", not problems, "; ".join(problems) or "3 rows, each model once and each CLI once")

    guarded("ac-pool-row-once", pool)

    def chapters():
        pg.go("tab=overview", "dark", 1400)
        p = pg.page
        top = [t.strip() for t in p.locator("[data-slot=topbar-tab]:not([aria-hidden=true])").all_inner_texts()]
        problems = []
        if "Thread" in [t.split("\n")[0].strip() for t in top]:
            problems.append(f"top bar still has Thread: {top}")
        if not any(t.startswith("Chapters") for t in top):
            problems.append(f"top bar has no Chapters: {top}")
        pg.go("tab=overview", "dark", 900)
        more = p.locator("[data-testid=project-tab-more]")
        if more.count():
            more.click()
            menu = p.locator("[role=menu]").inner_text()
            if "Chapters" not in menu or "Thread" in menu.split():
                problems.append(f"overflow menu: {menu!r}")
            p.keyboard.press("Escape")
        elif not any(t.startswith("Chapters") for t in top):
            problems.append("no overflow menu and no tab")
        p.keyboard.press("Control+k")
        p.wait_for_timeout(500)
        p.keyboard.type("chapters")
        p.wait_for_timeout(500)
        pal = p.locator("[role=dialog]").last.inner_text() if p.locator("[role=dialog]").count() else ""
        if "Chapters" not in pal:
            problems.append(f"palette has no Chapters: {pal[:120]!r}")
        p.keyboard.press("Escape")
        pg.go("tab=thread", "dark", 1400)
        active = p.locator("[data-slot=topbar-tab][data-active=true]").first.inner_text()
        if not active.startswith("Chapters"):
            problems.append(f"?tab=thread opens {active!r}")
        verdict("ac-chapters-label", not problems, "; ".join(problems) or "Chapters in top bar, overflow and palette; tab=thread opens it")

    guarded("ac-chapters-label", chapters)

    def tasks_bar():
        problems = []
        for width in (1200, 850, 650):
            pg.go("tab=tasks", "dark", width + 280, wait=".aw-board-toolbar")
            p = pg.page
            # the content area, not the window, is what the criterion sizes
            p.evaluate("w => { const b = document.querySelector('.aw-board'); b.style.width = w + 'px'; b.style.maxWidth = w + 'px'; }", width)
            p.wait_for_timeout(400)
            m = p.evaluate("""() => { const bar = document.querySelector('.aw-board-toolbar'), bb = bar.getBoundingClientRect();
                const controls = [...bar.querySelectorAll('button, input, label, [role=group] > *')];
                const out = [];
                for (const c of controls) { const b = c.getBoundingClientRect(); if (!b.width) continue;
                    const lh = parseFloat(getComputedStyle(c).lineHeight) || 16;
                    if (b.left < bb.left - 0.5 || b.right > bb.right + 0.5) out.push('outside: ' + (c.textContent || c.ariaLabel || c.tagName).trim().slice(0, 20));
                    if (c.tagName !== 'INPUT' && c.querySelectorAll('button,label,input').length === 0 && c.textContent.trim() && b.height > lh * 2.6 - 0.1) out.push('wraps: ' + c.textContent.trim().slice(0, 20)); }
                const s = bar.querySelector('input[type=search]'), sel = bar.querySelector('[data-testid=board-select-toggle]');
                const sb = s.getBoundingClientRect(), eb = sel.getBoundingClientRect();
                return {out, search: sb.width, selectVisible: eb.width > 0 && eb.right <= bb.right + 0.5 && eb.left >= bb.left}; }""")
            if m["out"] or m["search"] < 140 or not m["selectVisible"]:
                problems.append(f"{width}px: {m}")
            pg.page.screenshot(path=str(TMP / f"shot_tasks_{width}.png"))
        verdict("ac-tasks-bar-fits", not problems, "; ".join(problems) or "3 widths: controls inside the bar, search >= 140 px, Select visible")

    guarded("ac-tasks-bar-fits", tasks_bar)

    def hidden():
        pg.go("tab=tasks", "dark", 1400, wait="[data-testid=board-hidden-finished]")
        m = pg.page.evaluate("""() => { const h = document.querySelector('[data-testid=board-hidden-finished]');
            const r = document.createRange(); r.selectNodeContents(h);
            const card = document.querySelector('[data-slot=task-card]');
            return {text: h.textContent.trim(), hidden: r.getBoundingClientRect().left, card: card ? card.getBoundingClientRect().left : null}; }""")
        ok = m["card"] is not None and abs(m["hidden"] - m["card"]) <= 2
        verdict("ac-hidden-line", ok, json.dumps(m))

    guarded("ac-hidden-line", hidden)

    def count():
        pair = Page(pg.page.context.browser, pair_pid)
        pair.go("tab=profiles", "dark", 1300, wait=".aw-pf-index")
        text = pair.page.locator(".aw-pf-order").inner_text()
        pair.page.close()
        ok = text.startswith("1 profile ")
        verdict("ac-profiles-count", ok, text.replace("\n", " | ")[:150])

    guarded("ac-profiles-count", count)


def take_shots(pg, rich_pid):
    shots = TMP / "shots"
    shots.mkdir(exist_ok=True)
    views = {
        "overview": "tab=overview", "newthread": "agent=Checker&conversation=__new__",
        "pool": "tab=profiles&profile=Builder&section=running", "tasks": "tab=tasks",
    }
    for theme, width in (("dark", 1400), ("light", 1400), ("dark", 900)):
        for name, query in views.items():
            pg.go(query, theme, width)
            label = f"{theme}{width if width != 1400 else ''}" if width == 900 else theme
            pg.page.screenshot(path=str(shots / f"{name}_{label}.png"), full_page=True)
    print(f"shots: {shots}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assert", dest="assert_", action="store_true")
    ap.add_argument("--shots", action="store_true")
    args = ap.parse_args()
    proc = start_hub()
    print(f"hub pid {proc.pid} at {HUB}, scratch in {TMP}", flush=True)
    try:
        rich = seed_rich()
        empty = open_project("empty-quarantine")
        fresh = open_project("fresh")
        seed_quarantine(rich)
        pr = runner(empty, "Haiku", "claude", HAIKU5)
        agent(empty, "Keeper", pr)
        agent(empty, "Gone", pr)
        api("POST", f"/projects/{empty}/agents/Gone/archive")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            pg = Page(browser, rich)
            check_quarantine(pg, empty)
            check_first_run(browser, fresh)
            check_threads_and_pool(pg, empty)
            if args.shots:
                take_shots(pg, rich)
            browser.close()
        print("check ac-screens-reviewed: OPERATOR -- " + (f"open {TMP / 'shots'}" if args.shots else "run with --shots"))
    finally:
        stop_hub(proc)
    failed = [k for k, ok in results if not ok]
    print(f"{len(results) - len(failed)} passed, {len(failed)} failed" + (f": {', '.join(failed)}" if failed else ""))
    if failed and args.assert_:
        sys.exit(1)


if __name__ == "__main__":
    main()
