"""Acceptance drive for `the-spec-header-redesigned` (spdoc-407caf5abcdb), 2026-11-02.

The change's acceptance drive, written before the build (task `acceptance-drive`) and failing on
today's code for the behaviour that is missing, not for its setup. Not part of the project's checks.

It starts its own Hub on :8020 from this checkout's `hub/` with a fresh database (never :8000 or the
trial Hub), refuses to run if :8020 already answers, and stops the Hub when it ends. It opens a
throwaway git project under `testbed/` and seeds:

  * a roadmap with slices `a` and `b` (approved), and two change documents naming slice b then
    slice a, with no parent in the spec index;
  * "Crowded", a document with one unreviewed amendment and the other messages a half-written plan
    brings (the approval gaps, the facts line's index issue, what Check finds once pressed); the
    drive prints how many message elements the banner holds;
  * a document in every state the list marks: ready to approve, with an unreviewed amendment,
    approved with open tasks and no build, done and not folded, written with a blocking gap,
    building, archived, and a capability;
  * defects recorded against two changes.

Then, in a 1920x1080 Chromium against the served bundle:

  1. page-many-messages (FR-1): header top to the body's first line on the spec page, <= 200px;
  2. panel-many-messages (FR-2): the same in the conversation's side panel at its default 480px,
     <= 320px;
  3. condensed-line (FR-4): in the page and in the panel, scrolled down the header is one line of
     <= 48px with the title, phase, count, primary action and More; at the top, and after clicking
     the line, it is expanded. The count opens the messages (FR-7) and is looked for first;
  4. slices-grouped (FR-9): in the Spec tab's list and the panel's Open a spec screen, in roadmap
     order, both slices are under the roadmap, slice a above slice b, none under 'Not in a roadmap';
  5. needs-you-groups (FR-11): in both lists, in 'What needs you' order, the groups and the reasons
     (ready to approve, amendments to review, ready to build, ready to fold);
  6. defects-folded (FR-8): the Spec tab's footer shows one 'Defects by step' line with the count
     and no change row until it is opened.

Screenshots go in the artefacts directory. Each check records its measurement and the drive goes on,
so one run shows every failure; setup problems stop it with a SETUP message instead.

    py -3.11 scripts/drive/d1102_spec_page_room.py

What today's code does is recorded at the end of this file.
"""

import json
import os
import pathlib
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8020
HUB = f"http://127.0.0.1:{PORT}"
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")


def _testbed():
    """`testbed/` of the main checkout: the Hub refuses to register a project nested in a task
    checkout, so the scratch project cannot live under this one's own `testbed/`."""
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=REPO, capture_output=True, text=True).stdout.strip()
    main = pathlib.Path(common).parent if common else REPO
    return main / "testbed"


TMP = _testbed() / "drive1102-spec-page-room" / STAMP
DB = TMP / "hub.db"
AGENT = "Scribe"
HAIKU = "claude-haiku-4-5-20251001"
VIEW = {"width": 1920, "height": 1080}
results = []

CONVERSATION = "conv-d1102"
PAGE_LIMIT, PANEL_LIMIT, CONDENSED_LIMIT = 200, 320, 48


class Stop(Exception):
    """A setup step that did not work: the drive cannot say anything about the product."""


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    return bool(ok)


def setup(ok, what, detail=""):
    if not ok:
        print(f"SETUP {what} -- {detail}", flush=True)
        raise Stop(what)


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
        text = exc.read().decode()[:2000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except urllib.error.URLError as exc:
        return 0, str(exc)


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def poll(fn, secs=15.0, every=0.25):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render; try again
            pass
        time.sleep(every)
    return False


def answering():
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", PORT)) == 0


def start_hub():
    if answering():
        sys.exit(f"refusing to run: something already answers on :{PORT}")
    TMP.mkdir(parents=True, exist_ok=True)
    # Hand the scratch Hub none of the credentials of a Hub this drive may itself run under.
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(TMP / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not poll(lambda: api("GET", "/projects")[0] == 200, 120, 0.5):
        proc.kill()
        sys.exit(f"the Hub did not come up; see {TMP / 'hub.log'}")
    print(f"started a Hub on :{PORT} from {REPO / 'hub'} on {DB}")
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


# ── The documents ──────────────────────────────────────────────────────────────────────────────

PARAGRAPH = (
    "The operator opens a specification to read what is being built and why. The text here is long "
    "enough that the page scrolls, so the header's behaviour once the body leaves its top can be "
    "driven. "
)


def change(title, *, tasks=True, gaps=False, requirements=2):
    """A change document. `gaps` leaves a requirement with no acceptance criterion and no way to
    check it, which the approval check blocks on."""
    reqs, crits = [], []
    for n in range(1, requirements + 1):
        reqs.append({"key": f"r{n}", "modal": "MUST", "rationale": None, "party": None,
                     "statement": f"The page MUST do thing {n} for {title}."})
        if gaps and n == requirements:
            continue
        crits.append({"key": f"c{n}", "requirement": f"r{n}", "given": "the page is open",
                      "when": f"thing {n} is done", "then": f"it shows thing {n}",
                      "how_to_check": f"Look at thing {n}.", "checked_by": "agent"})
    return {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "summary": f"{title}: a scratch change for the spec page drive. " + PARAGRAPH * 2,
        "problem": PARAGRAPH * 6,
        "scope": {"in_scope": [f"Thing {n}" for n in range(1, 6)], "non_goals": ["Everything else"]},
        "requirements": reqs, "acceptance_criteria": crits,
        "tasks": ([{"key": "t1", "title": "Do the work", "description": "Do it.",
                    "requirements": [f"r{n}" for n in range(1, requirements + 1)],
                    "depends_on": [], "files": ["notes.txt"],
                    "from": None, "reviewer": None}] if tasks else []),
        "algorithms": [], "design": PARAGRAPH * 12,
        "evidence": {"checked": ["notes.txt exists"], "limits": []},
        "lifecycle": "", "open_questions": [],
        "delivery": {"mode": "none"},
    }


def roadmap(title):
    return {
        "schema_version": 1, "kind": "roadmap", "title": title,
        "summary": "A scratch roadmap with two slices.", "problem": "None.",
        "scope": {"in_scope": ["Both slices"], "non_goals": []},
        "requirements": [], "acceptance_criteria": [], "tasks": [], "algorithms": [],
        "design": "", "evidence": {"checked": [], "limits": []}, "lifecycle": "",
        "open_questions": [],
        "slices": [
            {"key": "a", "title": "Slice A", "intent": "Built first.", "done": "A works.",
             "builds_after": []},
            {"key": "b", "title": "Slice B", "intent": "Built second.", "done": "B works.",
             "builds_after": ["a"]},
        ],
    }


class Project:
    def __init__(self, pid):
        self.pid = pid
        self.base = f"/projects/{pid}"
        self.ids = {}

    def create(self, path, payload, kind="change-spec"):
        code, out = api("POST", f"{self.base}/project/documents",
                        {"title": payload["title"], "kind": kind, "path": path})
        setup(code == 201, f"create {path}", f"{code} {out}")
        self.ids[path] = out.get("id")
        code, out = api("PUT", f"{self.base}/project/documents/{path}/content", {"document": payload})
        setup(code == 200, f"save {path}", f"{code} {str(out)[:800]}")

    def phase(self, path, to, **extra):
        quoted = urllib.parse.quote(path)
        _, read = api("GET", f"{self.base}/project/spec?path={quoted}")
        version = read.get("content_version") if isinstance(read, dict) else None
        code, out = api("POST", f"{self.base}/project/documents/phase?path={quoted}&to={to}",
                        {"reason": "drive", **({"approve_anyway": True, "content_version": version}
                                               if to == "approved" else {}), **extra})
        setup(code == 200, f"{path} to {to}", f"{code} {str(out)[:800]}")

    def approve(self, path):
        quoted = urllib.parse.quote(path)
        api("POST", f"{self.base}/project/documents/journey?path={quoted}",
            {"size": "small", "step": "delivery", "reason": "drive setup"})
        api("POST", f"{self.base}/project/documents/close-exploration?path={quoted}")
        self.phase(path, "approved")


def row(sql, args=()):
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


def fetch(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def stamp_event(document_id, pid, kind, detail):
    row("insert into spec_document_events (id, document_id, project_id, kind, actor_kind, actor, "
        "origin, run_id, detail, created_at) values (?, ?, ?, ?, 'agent', 'Scribe', 'submission', "
        "null, ?, ?)",
        ("evt-d1102-" + secrets.token_hex(4), document_id, pid, kind, json.dumps(detail),
         time.strftime("%Y-%m-%d %H:%M:%S.000000", time.gmtime())))


def add_build(document_id, pid, state):
    row("insert into builds (id, project_id, document_id, state, driver, level, builders, reviewers, "
        "landing, created_at) values (?, ?, ?, ?, 'flow', 'reviewed', '[]', '[]', 'main', ?)",
        ("build-d1102-" + secrets.token_hex(4), pid, document_id, state,
         time.strftime("%Y-%m-%d %H:%M:%S.000000", time.gmtime())))


def add_conversation(pid):
    """A conversation with the agent, so the conversation view and its side panel exist. Written to
    the database with every NOT NULL column the model gives no default."""
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        values = {"id": "conv-d1102", "project_id": pid, "agent": AGENT, "lifecycle": "open",
                  "title": "Reading the crowded spec", "origin": "operator"}
        for _, name, kind, notnull, default, _ in con.execute("pragma table_info(conversations)"):
            if name in values or name == "sequence" or not notnull or default is not None:
                continue
            values[name] = (time.strftime("%Y-%m-%d %H:%M:%S.000000", time.gmtime())
                            if "at" in name else 0 if "INT" in kind.upper() or "BOOL" in kind.upper()
                            else "")
        marks = ", ".join("?" * len(values))
        con.execute(f"insert into conversations ({', '.join(values)}) values ({marks})",
                    tuple(values.values()))
        con.commit()
    finally:
        con.close()
    return "conv-d1102"


ROADMAP = "spec/changes/scratch-roadmap/spec.json"
SLICE_B = "spec/changes/slice-b-change/spec.json"
SLICE_A = "spec/changes/slice-a-change/spec.json"
CROWDED = "spec/changes/crowded/spec.json"
READY = "spec/changes/ready-one/spec.json"
AMENDED = "spec/changes/amended-one/spec.json"
BUILDABLE = "spec/changes/buildable-one/spec.json"
FOLDABLE = "spec/changes/foldable-one/spec.json"
GAPPED = "spec/changes/gapped-one/spec.json"
BUILDING = "spec/changes/building-one/spec.json"
ARCHIVED = "spec/changes/archived-one/spec.json"
CAPABILITY = "spec/capabilities/scratch-capability/spec.json"
TITLES = {
    READY: "Ready one", AMENDED: "Amended one", BUILDABLE: "Buildable one", FOLDABLE: "Foldable one",
    GAPPED: "Gapped one", BUILDING: "Building one", ARCHIVED: "Archived one",
    CAPABILITY: "Scratch capability", SLICE_A: "Slice A change", SLICE_B: "Slice B change",
}


def seed():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the spec page drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"specroom-{STAMP}"})
    setup(code in (200, 201), "the project opens", f"{code} {project}")
    p = Project(project["id"])
    api("PATCH", p.base, {"main_branch": "main"})
    code, runner = api("POST", f"{p.base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    setup(code in (200, 201), "a runner", f"{code} {runner}")
    code, out = api("POST", f"{p.base}/agents", {"name": AGENT, "runner_id": runner["id"]})
    setup(code in (200, 201), f"agent {AGENT}", f"{code} {out}")

    # The roadmap and the two slices that name it; neither has a parent in the spec index.
    p.create(ROADMAP, roadmap("Scratch roadmap"), kind="roadmap")
    p.approve(ROADMAP)
    for path, slice_key, title in ((SLICE_B, "b", "Slice B change"), (SLICE_A, "a", "Slice A change")):
        p.create(path, change(title))
        code, out = api("PUT", f"{p.base}/project/documents/{path}/roadmap",
                        {"document": ROADMAP, "slice": slice_key})
        setup(code == 200, f"{title} names slice {slice_key}", f"{code} {out}")

    # One document in each state the list marks.
    p.create(READY, change("Ready one"))
    p.create(AMENDED, change("Amended one", tasks=False))
    p.approve(AMENDED)
    stamp_event(p.ids[AMENDED], p.pid, "amendment", {
        "id": "amd-d1102a", "op": "change_criterion", "target": "c1", "requirement": "r1",
        "identifier": "FR-1", "reason": "The criterion was wrong.", "how_to_check": "Look at it.",
        "tested_task_id": None})
    p.create(BUILDABLE, change("Buildable one"))
    p.approve(BUILDABLE)
    p.create(FOLDABLE, change("Foldable one", tasks=False))
    p.approve(FOLDABLE)
    add_build(p.ids[FOLDABLE], p.pid, "stopped")
    p.create(GAPPED, change("Gapped one", gaps=True))
    p.create(BUILDING, change("Building one", tasks=False))
    p.approve(BUILDING)
    add_build(p.ids[BUILDING], p.pid, "running")
    p.create(ARCHIVED, change("Archived one", tasks=False))
    p.approve(ARCHIVED)
    p.phase(ARCHIVED, "archived", no_capability_change=True)
    code, out = api("POST", f"{p.base}/project/documents",
                    {"title": "Scratch capability", "kind": "capability", "path": CAPABILITY})
    setup(code == 201, "the capability is created", f"{code} {out}")
    p.ids[CAPABILITY] = out.get("id")

    # The crowded document: a plan left half-written (approval gaps), an unreviewed amendment, and
    # a few more things the header and banner have to say.
    crowded = change("Crowded", gaps=True, requirements=4)
    crowded["tasks"] = [{"key": "t1", "title": "Do the work", "description": "Do it.",
                         "requirements": ["r1"], "depends_on": [], "files": ["notes.txt"],
                         "from": None, "reviewer": None},
                        {"key": "t2", "title": "Do more", "description": "More.",
                         "requirements": [], "depends_on": ["t1"], "files": ["notes.txt"],
                         "from": None, "reviewer": None}]
    p.create(CROWDED, crowded)
    stamp_event(p.ids[CROWDED], p.pid, "amendment", {
        "id": "amd-d1102b", "op": "change_criterion", "target": "c1", "requirement": "r1",
        "identifier": "FR-1", "reason": "The first criterion was too strict for the page.",
        "how_to_check": "Open the page and look.", "tested_task_id": None})

    # Defects on two changes, for the folded report.
    for path, count in ((AMENDED, 2), (BUILDABLE, 3)):
        for n in range(count):
            code, out = api("POST", f"{p.base}/project/documents/{path}/defects",
                            {"summary": f"Defect {n + 1} on {TITLES[path]}", "caught_by": "intake"})
            if code != 201:
                code, out = api("POST", f"{p.base}/project/documents/{path}/defects",
                                {"summary": f"Defect {n + 1}", "caught_by": "build"})
            setup(code == 201, f"a defect on {path}", f"{code} {out}")
    p.conversation = add_conversation(p.pid)
    return p


# ── The browser ────────────────────────────────────────────────────────────────────────────────

FIRST_LINE = """() => {
  const root = document.querySelector('.aw-sp-content');
  if (!root) return null;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (!node.textContent.trim()) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const rect = range.getBoundingClientRect();
    if (rect.height > 0) return rect.top;
  }
  return null;
}"""

HEADER = """() => {
  const header = document.querySelector('[data-testid=spec-document-header]');
  if (!header) return null;
  const rect = header.getBoundingClientRect();
  return {top: rect.top, height: rect.height, text: header.innerText,
          more: !!header.querySelector('[aria-label="More actions"]'),
          buttons: [...header.querySelectorAll('button')].map(b => (b.getAttribute('aria-label') || b.innerText || '').trim()).filter(Boolean),
          counts: [...header.querySelectorAll('[data-testid*=count], [data-testid*=notice], [aria-label*=message i], [aria-label*=notice i]')].length,
          condensed: header.getAttribute('data-condensed') || header.getAttribute('data-state') || header.getAttribute('data-compact')};
}"""

LIST = """(scope) => {
  const list = document.querySelector(scope);
  if (!list) return null;
  return [...list.querySelectorAll('.aw-sp-list-group')].map(g => ({
    label: g.querySelector('.aw-sp-list-label')?.innerText.trim() || null,
    roadmap: g.querySelector('[data-roadmap=true]')?.innerText.trim().split('\\n')[0] || null,
    rows: [...g.querySelectorAll('li [data-slot=spec-row]')].map(r => ({
      name: r.querySelector('.aw-sp-list-name')?.innerText.trim(),
      waiting: r.querySelector('.aw-sp-list-waiting')?.innerText.trim() || null,
      state: r.getAttribute('data-state')})),
  }));
}"""


def seed_script(pid, tabs, active):
    panel = {"version": 1, "projects": {pid: {"tabs": [{"id": t, "revealRequestId": 0} for t in tabs],
                                               "activeTabId": active, "isOpen": True}}}
    return ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);"
            "localStorage.setItem('aw.panel.tabs.v1', %r);"
            % (KEY, HUB, pid, json.dumps(panel)))


def page_url(pid, path):
    return f"{HUB}/?project={pid}&tab=spec&document={urllib.parse.quote(path, safe='')}"


def panel_url(pid, path):
    return (f"{HUB}/?project={pid}&agent={AGENT}&conversation={CONVERSATION}"
            f"&document={urllib.parse.quote(path, safe='')}")


def settle(page, selector, secs=30):
    try:
        page.locator(selector).first.wait_for(timeout=secs * 1000)
    except Exception:  # noqa: BLE001 -- reported by the check that needs it
        return False
    page.wait_for_timeout(1500)
    return True


def press_check(page):
    """Check the document as the operator would, so its findings join the other messages."""
    button = page.locator("[data-testid=spec-document-header]").first.get_by_role(
        "button", name="Check", exact=True).first
    if button.count():
        button.click(timeout=5000)
        page.wait_for_timeout(2500)
        scroll_to(page, 0)


def measure(page):
    header = page.evaluate(HEADER)
    line = page.evaluate(FIRST_LINE)
    return header, line


def scroll_to(page, top):
    page.evaluate("(top) => { const s = document.querySelector('.aw-sp-scroll'); if (s) s.scrollTop = top; }",
                  top)
    page.wait_for_timeout(700)


def condensed_checks(page, where):
    scroll_to(page, 0)
    top_header = page.evaluate(HEADER) or {}
    scroll_to(page, 900)
    scrolled = page.evaluate(HEADER) or {}
    height = scrolled.get("height")
    condensed = height is not None and height <= CONDENSED_LIMIT
    text = (scrolled.get("text") or "")
    check(f"{where} 3a scrolled, the header is one line of at most {CONDENSED_LIMIT}px",
          height is not None and height <= CONDENSED_LIMIT,
          f"height {height} (expanded {top_header.get('height')})")
    check(f"{where} 3b the condensed line keeps the title, the primary action, More and a count",
          scrolled.get("more") and "Crowded" in text and scrolled.get("counts", 0) >= 1
          and len(scrolled.get("buttons") or []) >= 2,
          f"more={scrolled.get('more')} counts={scrolled.get('counts')} "
          f"buttons={scrolled.get('buttons')} text={text[:120]!r}")
    page.screenshot(path=str(TMP / f"{where}_condensed.png"))
    scroll_to(page, 0)
    back = page.evaluate(HEADER) or {}
    check(f"{where} 3c back at the top the header is expanded again",
          condensed and back.get("height") is not None and back["height"] > CONDENSED_LIMIT
          and back["height"] == top_header.get("height"),
          f"height {back.get('height')} (first {top_header.get('height')}); "
          f"it was {'condensed' if condensed else 'not condensed'} while scrolled")
    scroll_to(page, 900)
    header = page.locator("[data-testid=spec-document-header]").first
    clicked = False
    # Click the title, which is not a control, rather than a spot that may land on the count or a button.
    for target in ("[data-testid=spec-document-header] :is(h1, h2, [data-testid*=title])",
                   "[data-testid=spec-document-header]"):
        spot = page.locator(target).first
        if spot.count():
            box = spot.bounding_box()
            if box:
                page.mouse.click(box["x"] + min(box["width"] / 2, 40), box["y"] + box["height"] / 2)
                clicked = True
                break
    page.wait_for_timeout(700)
    after = page.evaluate(HEADER) or {}
    check(f"{where} 3d clicking the condensed line expands the header",
          condensed and clicked and after.get("height") is not None
          and after["height"] > CONDENSED_LIMIT
          and header.count() > 0,
          f"height {after.get('height')} after a click on the title; "
          f"it was {'condensed' if condensed else 'not condensed'} before it")


def count_opens(page, where):
    """FR-7: the count opens the messages. Looked for by its test id or label."""
    count = page.locator("[data-testid=spec-document-header] :is([data-testid*=count], [data-testid*=notices], "
                         "[aria-label*=message i], [aria-label*=notice i])").first
    found = count.count() > 0
    opened = False
    if found:
        count.click(timeout=5000)
        page.wait_for_timeout(500)
        opened = page.locator("[data-testid*=notice], [role=dialog] .aw-spec-message, [role=menu] .aw-spec-message").count() > 0
        page.screenshot(path=str(TMP / f"{where}_count_open.png"))
        page.keyboard.press("Escape")
    check(f"{where} 2 the header has a message count that opens the messages", found and opened,
          f"count control found={found} messages shown={opened}")


def drive_page(browser, p):
    context = browser.new_context(viewport=VIEW)
    context.add_init_script(seed_script(p.pid, [], None).replace("'aw.panel.tabs.v1'", "'x.unused'"))
    page = context.new_page()
    page.goto(page_url(p.pid, CROWDED), wait_until="domcontentloaded")
    ready = settle(page, "[data-testid=spec-document-header]")
    setup(ready, "the spec page shows the Crowded document", "no header after 30s")
    messages = page.locator(".aw-sp-banner .aw-spec-message, .aw-sp-banner [data-testid*=amend]").count()
    press_check(page)
    messages = page.locator(".aw-sp-banner .aw-spec-message, .aw-sp-banner [data-testid*=amend]").count()
    print(f"  page: {messages} message elements in the banner after Check", flush=True)
    page.screenshot(path=str(TMP / "page_expanded.png"))
    header, line = measure(page)
    gap = None if line is None or header is None else round(line - header["top"], 1)
    check(f"page 1 the body's first line is at most {PAGE_LIMIT}px below the header's top",
          gap is not None and gap <= PAGE_LIMIT, f"{gap}px (header {header and header['height']}px tall)")
    count_opens(page, "page")
    condensed_checks(page, "page")

    # The Spec tab's list, in roadmap order and in 'What needs you' order.
    page.goto(page_url(p.pid, AMENDED), wait_until="domcontentloaded")
    settle(page, "aside.aw-sp-list[data-variant=column]")
    list_checks(page, "aside.aw-sp-list[data-variant=column]", "tab", None)
    # The footer is part of this list.
    footer = page.locator(".aw-sp-list-footer").first
    footer_text = footer.inner_text() if footer.count() else ""
    rows_shown = page.locator(".aw-sp-list-footer [data-testid*=defect-change], .aw-sp-list-footer li").count()
    page.screenshot(path=str(TMP / "tab_list.png"))
    check("tab 6 the footer shows Evidence and one folded 'Defects by step' line with the count, and "
          "no change row",
          "Evidence" in footer_text and "Defects by step" in footer_text and rows_shown == 0
          and "5" in footer_text,
          f"rows shown={rows_shown} footer={footer_text[:200]!r}")
    context.close()


def drive_panel(browser, p):
    context = browser.new_context(viewport=VIEW)
    tab = f"spec:{p.ids[CROWDED]}"
    context.add_init_script(seed_script(p.pid, ["specs", tab], tab))
    page = context.new_page()
    page.goto(panel_url(p.pid, CROWDED), wait_until="domcontentloaded")
    ready = settle(page, "[data-testid=spec-document-panel] [data-testid=spec-document-header]")
    setup(ready, "the panel shows the Crowded document", "no panel header after 30s")
    width = page.evaluate("() => document.querySelector('[data-testid=spec-document-panel]')?.getBoundingClientRect().width")
    press_check(page)
    page.screenshot(path=str(TMP / "panel_expanded.png"))
    header, line = measure(page)
    gap = None if line is None or header is None else round(line - header["top"], 1)
    check(f"panel 2 the body's first line is at most {PANEL_LIMIT}px below the header's top",
          gap is not None and gap <= PANEL_LIMIT,
          f"{gap}px (header {header and header['height']}px tall, panel {width}px wide)")
    count_opens(page, "panel")
    condensed_checks(page, "panel")
    context.close()

    # The panel's Open a spec screen: the Specs tab.
    context = browser.new_context(viewport=VIEW)
    context.add_init_script(seed_script(p.pid, ["specs"], "specs"))
    page = context.new_page()
    page.goto(f"{HUB}/?project={p.pid}&agent={AGENT}&conversation={CONVERSATION}",
              wait_until="domcontentloaded")
    setup(settle(page, "[data-testid=spec-picker]"), "the panel's Open a spec screen shows", "no picker")
    list_checks(page, "[data-testid=spec-picker] .aw-sp-list", "panel", None)
    page.screenshot(path=str(TMP / "panel_open_a_spec.png"))
    context.close()


def choose_order(page, label):
    """True when the order was chosen; False when the menu does not offer it."""
    for _ in range(2):
        page.locator("[data-slot=order-trigger]").first.click()
        item = page.locator(".aw-menu-item", has_text=label).first
        try:
            item.wait_for(timeout=3000)
        except Exception:  # noqa: BLE001 -- the menu did not open; press the trigger again
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            continue
        item.click()
        page.wait_for_timeout(600)
        return True
    return False


def list_checks(page, scope, where, _unused):
    # Roadmap order.
    choose_order(page, "Roadmap order")
    groups = page.evaluate(LIST, scope) or []
    page.screenshot(path=str(TMP / f"{where}_list_roadmap.png"))
    names = [r["name"] for g in groups if g["roadmap"] for r in g["rows"]]
    loose = [r["name"] for g in groups if (g["label"] or "").lower() == "not in a roadmap" for r in g["rows"]]
    wanted = ["Slice A change", "Slice B change"]
    under = [n for n in names if n in wanted]
    check(f"{where} 4 both slices are under the roadmap, slice a's above slice b's, neither under "
          f"'Not in a roadmap'",
          under == wanted and not [n for n in loose if n in wanted],
          f"under the roadmap {names}; not in a roadmap {loose}")

    # What needs you.
    offered = choose_order(page, "What needs you")
    groups = page.evaluate(LIST, scope) or []
    page.screenshot(path=str(TMP / f"{where}_list_needs_you.png"))
    # The label renders uppercase (text-transform) and innerText returns it so: key on lower case.
    by_label = {(g["label"] or "").lower(): {r["name"]: r["waiting"] for r in g["rows"]} for g in groups}
    waiting = by_label.get("waiting on you", {})
    reasons = {
        "Ready one": "ready to approve", "Amended one": "amendments to review",
        "Buildable one": "ready to build", "Foldable one": "ready to fold",
    }
    got = {n: (waiting.get(n) or "").lower() for n in reasons}
    check(f"{where} 5a Waiting on you holds the four documents with their reasons",
          offered and all(reasons[n] in got[n] for n in reasons),
          f"order offered={offered}; {got} (groups {list(by_label)})")
    check(f"{where} 5b the gap-blocked and building documents are under In progress",
          {"Gapped one", "Building one"} <= set(by_label.get("in progress", {})),
          f"In progress {list(by_label.get('in progress', {}))}")
    check(f"{where} 5c the archived one is under Finished and the capability under Capabilities",
          "Archived one" in by_label.get("finished", {})
          and "Scratch capability" in by_label.get("capabilities", {}),
          f"Finished {list(by_label.get('finished', {}))}; "
          f"Capabilities {list(by_label.get('capabilities', {}))}")


def main():
    proc = start_hub()
    try:
        try:
            p = seed()
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    drive_page(browser, p)
                    drive_panel(browser, p)
                finally:
                    browser.close()
        except Stop:
            sys.exit(2)
    finally:
        stop_hub(proc)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed on today's code (task-b5c91e1c8075 at 5f00f36 + this drive), 2026-11-02, artefacts
# testbed/drive1102-spec-page-room/191049: 0 passed, 21 failed, every one for missing behaviour:
#   page 1   body's first line 457.7px below the header's top (limit 200); header 169px tall;
#   panel 2  690.7px (limit 320); header 198px tall;
#   page/panel 2 (count) and 3a-3d: no message count in the header and no condensed line: the header
#            stays 169/198px when the body scrolls;
#   tab/panel 4  the roadmap lists 0 slices, and both slices sit under 'Not in a roadmap';
#   tab/panel 5  the shipped order menu offers no 'What needs you' (Roadmap order, Last change,
#            Phase, Title only), so no group or reason shows;
#   tab 6    the defects report starts open: two change rows under 'Defects by step', no count.
# The seeding itself ran clean: the project, 10 documents in their states, the roadmap with two
# slices, the amendments and the defects all exist on the Hub (see the screenshots).
