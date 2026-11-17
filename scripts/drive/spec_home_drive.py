"""Acceptance drive for `spec-home-shows-what-is-being-built-what-was-built-and-how-it-relates`
(SHWBB-1), 2026-11-17: the nine acceptance criteria that only a running Hub and a real browser can
answer, written failing first, before the routes (SHWBB-2) and the home (SHWBB-3) are built.

Starts its own Hub from THIS checkout's `hub/` on a scratch port and a fresh database (default :8023
and a temp file; AW_DRIVE_PORT / AW_DRIVE_DB move them), on 127.0.0.1, and refuses a port something
already answers on. Never :8000 or :8010. No agent turn is run: every build is started, worked to
`approved` and landed through the Hub's own routes by the operator's hand (the flow's job is disabled
the moment it exists, so no firing spends a turn; any that did would bind Haiku). Nothing is written
into the database directly.

Fixture, one throwaway git project on `main` (project A) and a second for the capability page (B):

  A  roadmap  "Rho roadmap" with slices s1 "First slice", s2 "Second slice"
     changes  Foxtrot (finished build, in no roadmap, changes Cobalt), Yankee (running, no roadmap,
              changes Dune), Xray (running, newest build, slice s2 of Rho, changes Cobalt)
     capabilities  Cobalt (waiting: Xray, Foxtrot = 2), Dune (waiting: Yankee = 1), Ember (no change)
     Zulu, a change nothing builds until ac-live starts it
  B  capability "Tango cap" with changes T1 and T2 folded in that order (T1 archived by its fold,
     T2 left approved-and-folded), and T3 approved and waiting

The contract the drive probes is the design's (the spec's `design`), nothing else:
  GET .../project/builds rows are read by the page; `data-testid`s `spec-home` (sections
  `spec-home-building`, `spec-home-recent`, `spec-home-relations`, `spec-home-capabilities`, in that
  order), rows `spec-home-build-row` / `spec-home-recent-row` (data-document), links
  `spec-home-link` (data-rel = roadmap | slice | capability, data-path), `.aw-map-node` (data-col =
  roadmap | change | capability, data-lit), `.aw-map-thread`, `spec-home-capability-row` (data-path,
  data-lit), and on a capability page `capability-touched-row` (data-path, data-state = waiting |
  folded); the list button is `spec-list-control`. A text assertion is always read from its own row's
  or box's element, never `body` (the roadmap drive's ac-facts matched a sidebar row). Body fields go
  in the JSON body; the routes that take `path` take it in the query, as the app does.

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. Screenshots go to testbed/spec-home-drive/<HHMMSS>/.

    py -3.11 scripts/drive/spec_home_drive.py                    # own Hub on :8023
    py -3.11 scripts/drive/spec_home_drive.py --only ac-hover
    py -3.11 scripts/drive/spec_home_drive.py --self-test        # the drive's own logic, no Hub
"""

import argparse
import json
import os
import pathlib
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
STAMP = time.strftime("%H%M%S")
PORT = int(os.environ.get("AW_DRIVE_PORT") or 8023)
HUB = f"http://127.0.0.1:{PORT}"
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "drive-shwbb" / STAMP
DB = pathlib.Path(os.environ.get("AW_DRIVE_DB") or SCRATCH / "hub.db")
KEY = "aw_live_" + secrets.token_hex(16)
OUT = REPO / "testbed" / "spec-home-drive" / STAMP
ORDER = ["ac-home-click", "ac-building", "ac-relations", "ac-map", "ac-hover", "ac-back",
         "ac-capabilities", "ac-touched", "ac-live"]

checks = {}  # key -> (reached, failed, detail)


class Setup(Exception):
    """Something the drive depends on could not be arranged."""


class NotReached(Exception):
    """A check could not get as far as its own assertion."""


class Failed(Exception):
    """A check's own assertion did not hold."""


def record(key, reached, ok, detail):
    checks[key] = (reached, reached and not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)


# --------------------------------------------------------------------------- pure logic (self-tested)


def decoded(url):
    return urllib.parse.unquote(url or "")


def opens(url, path, anchor=None):
    """The app's URL names `path` as its document (and `anchor` as the fragment, if asked)."""
    text = decoded(url)
    return f"document={path}" in text and (anchor is None or anchor in text)


def done_of_total(text):
    """`(done, total)` from "1 of 3 done" / "1/3", or None."""
    match = re.search(r"\b(\d+)\s*(?:of|/)\s*(\d+)\b", text or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def row_facts(text):
    """`(ok, detail)`: a Building now row shows done-of-total, a waiting-to-land count and a start time."""
    low = (text or "").lower()
    progress = done_of_total(text)
    landing = bool(re.search(r"\d+\s*(waiting|landing)|(waiting|landing)\D{0,12}\d+", low))
    started = bool(re.search(r"start", low)) and bool(
        re.search(r"\bago\b|\bjust now\b|\d{1,2}:\d{2}|\b[a-z]{3}\s+\d{1,2}\b|\d{4}-\d{2}-\d{2}", low))
    return bool(progress) and landing and started, f"done-of-total {progress}, waiting-to-land {landing}, start time {started}"


def in_order(positions):
    """True when `positions` (document order of each section, None for a missing one) is strictly rising."""
    return all(p is not None for p in positions) and all(a < b for a, b in zip(positions, positions[1:]))


def lit_verdict(lit, bright, dim):
    """`(ok, detail)`: every key of `bright` reads data-lit=true and every key of `dim` data-lit=false;
    `lit` maps a key to the attribute's value (None when absent)."""
    wrong = [f"{k}={lit.get(k)!r}" for k in bright if lit.get(k) != "true"]
    wrong += [f"{k}={lit.get(k)!r}" for k in dim if lit.get(k) != "false"]
    return not wrong, "lit/dim wrong: " + ", ".join(wrong) if wrong else "lit and dim as expected"


def cleared(lit):
    left = [f"{k}={v!r}" for k, v in lit.items() if v is not None]
    return not left, ("still set: " + ", ".join(left)) if left else "every data-lit cleared"


def newest_first(stamps):
    return all(a >= b for a, b in zip(stamps, stamps[1:]))


def waiting_count(text):
    match = re.search(r"(\d+)\s*waiting", text or "", re.I)
    return int(match.group(1)) if match else None


def baseline_line(key, reached, failed, detail):
    return (f"check {key}: reached={'yes' if reached else 'no'} "
            f"failed_at_assertion={'yes' if failed else 'no'} -- {detail}")


def self_test():
    ok_row = "Xray change\n1 of 2 done\n0 waiting to land\nstarted 3 minutes ago"
    cases = [
        (opens("http://h/?tab=spec&document=spec%2Fa%2Fspec.json&anchor=slice-s2", "spec/a/spec.json", "slice-s2"), True),
        (opens("http://h/?tab=spec&document=spec%2Fa%2Fspec.json", "spec/a/spec.json", "slice-s2"), False),
        (opens("http://h/?tab=spec", "spec/a/spec.json"), False),
        (done_of_total("2 of 5 done"), (2, 5)), (done_of_total("3/4"), (3, 4)), (done_of_total("none"), None),
        (row_facts(ok_row)[0], True),
        (row_facts("Xray change\n1 of 2 done\nstarted 3 minutes ago")[0], False),
        (row_facts("Xray change\n1 of 2 done\n0 waiting to land")[0], False),
        (row_facts("Xray change\n0 waiting to land\nstarted 3 minutes ago")[0], False),
        (in_order([1, 2, 3, 4, 9]), True), (in_order([1, 3, 2]), False), (in_order([1, None]), False),
        (lit_verdict({"a": "true", "b": "false"}, ["a"], ["b"])[0], True),
        (lit_verdict({"a": "true", "b": None}, ["a"], ["b"])[0], False),
        (lit_verdict({"a": "false"}, ["a"], [])[0], False),
        (cleared({"a": None, "b": None})[0], True), (cleared({"a": None, "b": "false"})[0], False),
        (newest_first([3, 2, 2, 1]), True), (newest_first([1, 2]), False),
        (waiting_count("Cobalt cap 2 waiting"), 2), (waiting_count("Ember cap"), None),
        (baseline_line("k", True, True, "d"), "check k: reached=yes failed_at_assertion=yes -- d"),
        (len(ORDER), 9), (ORDER[0], "ac-home-click"), (ORDER[-1], "ac-live"),
    ]
    bad = [(i, got, want) for i, (got, want) in enumerate(cases) if got != want]
    for i, got, want in bad:
        print(f"self-test case {i}: got {got!r}, wanted {want!r}")
    print("self-test:", "PASS" if not bad else "FAIL", f"({len(cases) - len(bad)}/{len(cases)})")
    return not bad


# --------------------------------------------------------------------------- the Hub


def api(method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()[:4000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        return 0, str(exc)


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def poll(fn, secs, every=0.5):
    end = time.time() + secs
    while time.time() < end:
        if fn():
            return True
        time.sleep(every)
    return bool(fn())


def port_answers():
    with socket.socket() as sock:
        sock.settimeout(2)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def start_hub(log_path):
    DB.parent.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if "tool-server" not in p.replace("\\", "/"))
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    if not poll(lambda: api("GET", "/projects", timeout=5)[0] == 200, 120, 2.0):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        sys.exit(f"setup error: the Hub did not come up; see {log_path}")
    print(f"started a Hub on :{PORT} from {REPO / 'hub'} on {DB}", flush=True)
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    print(f"stopped the Hub on :{PORT}", flush=True)


# --------------------------------------------------------------------------- the fixture


def expect(code, want, what, out):
    if code not in want:
        raise Setup(f"{what}: {code} {str(out)[:500]}")
    return out


class Project:
    """One throwaway project, arranged through the Hub's routes only."""

    def __init__(self, name):
        self.name = name
        self.pid = ""
        self.base = ""
        self.titles = {}   # path -> title
        self.jobs = []

    def open(self):
        root = SCRATCH / f"proj-{self.name}"
        root.mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        (root / "README.md").write_text("A throwaway project for the spec-home drive.\n", encoding="utf-8")
        git(root, "add", "README.md")
        git(root, "commit", "-q", "-m", "seed")
        code, project = api("POST", "/projects/open", {"path": str(root), "name": f"shwbb-{self.name}-{STAMP}"})
        expect(code, (200, 201), "the project opens", project)
        self.pid, self.base = project["id"], f"/projects/{project['id']}"
        code, out = api("PUT", f"{self.base}/settings", {"main_branch": "main"})
        expect(code, (200,), "main branch", out)
        code, runner = api("POST", f"{self.base}/runners", {"name": "Haiku", "cli": "claude", "model": "claude-haiku-5-5"})
        expect(code, (200, 201), "the Haiku runner", runner)
        for agent in ("Builder", "Architect"):
            code, out = api("POST", f"{self.base}/agents", {"name": agent, "runner_id": runner["id"]})
            expect(code, (200, 201), f"agent {agent}", out)

    def document(self, path, title, kind, extra):
        code, out = api("POST", f"{self.base}/project/documents", {"title": title, "kind": kind, "path": path})
        expect(code, (201,), f"create {path}", out)
        body = {"schema_version": 1, "kind": kind, "title": title, "summary": f"{title}, a drive fixture.",
                "problem": "The drive needs one.",
                "scope": {"in_scope": ["the drive"], "non_goals": ["anything else"]}, **extra}
        code, out = api("PUT", f"{self.base}/project/documents/{path}/content", {"document": body})
        expect(code, (200,), f"save {path}", out)
        self.titles[path] = title

    def capability(self, slug, title):
        path = f"spec/capabilities/{slug}/spec.json"
        code, out = api("POST", f"{self.base}/project/documents", {"title": title, "kind": "capability", "path": path})
        expect(code, (201,), f"create {path}", out)
        self.titles[path] = title
        return path

    def roadmap(self, slug, title, slices):
        path = f"spec/roadmaps/{slug}/spec.json"
        self.document(path, title, "roadmap", {
            "slices": [{"key": k, "title": t, "intent": f"{t} works.", "done": f"{t} is shown.", "builds_after": []}
                       for k, t in slices],
            "requirements": [], "acceptance_criteria": [], "tasks": []})
        self.approve(path)
        return path

    def change(self, slug, title, roadmap=None, capabilities=(), requirement="r1"):
        path = f"spec/changes/{slug}/spec.json"
        extra = {
            "requirements": [{"key": requirement, "modal": "MUST", "statement": f"{title} MUST say so."}],
            "acceptance_criteria": [{"key": "ok", "requirement": requirement, "given": "x", "when": "y", "then": "z",
                                     "how_to_check": "read", "checked_by": "agent"}],
            "tasks": [{"key": "t1", "title": f"{title} task", "description": "d", "files": ["a.txt"],
                       "requirements": [requirement]}],
            "capabilities": {"changes": list(capabilities), "creates": []}}
        if roadmap:
            extra["roadmap"] = {"document": roadmap[0], "slice": roadmap[1]}
        self.document(path, title, "change-spec", extra)
        return path

    def version(self, path):
        code, out = api("GET", f"{self.base}/project/spec?path={path}")
        expect(code, (200,), f"read {path}", out)
        return out["content_version"]

    def approve(self, path):
        code, out = api("POST", f"{self.base}/project/documents/phase?path={path}&to=approved",
                        {"content_version": self.version(path), "approve_anyway": True})
        expect(code, (200,), f"approve {path}", out)

    def build(self, path):
        """Approve and build `path` as the operator does, then disable its flow's job: the drive hands the
        work through by hand and no firing may spend a turn."""
        code, out = api("POST", f"{self.base}/project/documents/approve-and-build?path={path}",
                        {"delivery_agent": "Builder", "driver": "flow", "approve_anyway": True,
                         "content_version": self.version(path)})
        expect(code, (200,), f"build {path}", out)
        job = ((out.get("build_outcome") or {}).get("flow") or {}).get("job_id")
        if job:
            api("PATCH", f"{self.base}/jobs/{job}", {"enabled": False})
        return out

    def land(self, path):
        """Work `path`'s one task to approved and landed through the operator's routes: its build finishes."""
        code, out = api("GET", f"{self.base}/tasks")
        expect(code, (200,), "tasks", out)
        doc = next((r for r in api("GET", f"{self.base}/project/builds")[1]["builds"] if r.get("document_title") == self.titles[path]), None)
        mine = [t for t in out["tasks"] if doc and t.get("build_id") == doc["id"]]
        if not mine:
            raise Setup(f"no task of {path}'s build")
        for task in mine:
            for state in ("assigned", "in_progress", "completed"):
                body = {"status": state, **({"assignee": "Builder"} if state == "assigned" else {})}
                code, out = api("PATCH", f"{self.base}/tasks/{task['id']}", body)
                expect(code, (200,), f"{state} {task['id']}", out)
            code, out = api("POST", f"{self.base}/tasks/{task['id']}/land", {})
            expect(code, (200,), f"land {task['id']}", out)
        if not poll(lambda: api("GET", f"{self.base}/project/builds")[1]["builds"][0].get("state") != "running"
                    or any(r["document_title"] == self.titles[path] and r["state"] == "finished"
                           for r in api("GET", f"{self.base}/project/builds")[1]["builds"]), 20):
            raise Setup(f"the build of {path} did not finish")

    def fold(self, path, into, archive):
        code, out = api("POST", f"{self.base}/project/documents/{path}/fold", {"into": into, "archive": archive})
        expect(code, (200,), f"fold {path}", out)


class Fixture:
    def __init__(self):
        self.a = Project("home")
        self.b = Project("cap")
        self.p = {}


def arrange(fx):
    a = fx.a
    a.open()
    cobalt = a.capability("cobalt", "Cobalt cap")
    dune = a.capability("dune", "Dune cap")
    ember = a.capability("ember", "Ember cap")
    rho = a.roadmap("rho", "Rho roadmap", [("s1", "First slice"), ("s2", "Second slice")])
    foxtrot = a.change("foxtrot", "Foxtrot change", capabilities=[cobalt])
    yankee = a.change("yankee", "Yankee change", capabilities=[dune])
    xray = a.change("xray", "Xray change", roadmap=(rho, "s2"), capabilities=[cobalt])
    zulu = a.change("zulu", "Zulu change")
    # Foxtrot's build finishes first, then Yankee's starts, then Xray's: Xray is the newest build.
    a.build(foxtrot)
    a.land(foxtrot)
    time.sleep(1.2)
    a.build(yankee)
    time.sleep(1.2)
    a.build(xray)
    # Zulu is left written, not approved: the Build button approves and builds in one call, and
    # refuses a document that is already approved (`phase_unchanged`).
    fx.p.update(cobalt=cobalt, dune=dune, ember=ember, rho=rho, foxtrot=foxtrot, yankee=yankee, xray=xray, zulu=zulu)

    b = fx.b
    b.open()
    tango = b.capability("tango", "Tango cap")
    t1 = b.change("t1", "Tone one", capabilities=[tango], requirement="r1")
    t2 = b.change("t2", "Tone two", capabilities=[tango], requirement="r2")
    t3 = b.change("t3", "Tone three", capabilities=[tango], requirement="r3")
    b.approve(t3)
    for path in (t1, t2):   # a change is folded once its work is decided: build it and land its one task
        b.build(path)
        b.land(path)
    b.fold(t1, tango, archive=True)    # folded, then archived by its own fold
    time.sleep(1.2)
    b.fold(t2, tango, archive=False)   # folded later: the newest fold
    fx.p.update(tango=tango, t1=t1, t2=t2, t3=t3)
    print(f"projects {a.pid} (home) and {b.pid} (capability page)", flush=True)


# --------------------------------------------------------------------------- the browser


def shot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    except Exception as exc:  # noqa: BLE001 -- a picture is evidence, not the assertion
        print(f"  (no screenshot {name}: {exc})")


def spec_url(project, document=None, tab="spec"):
    query = {"project": project.pid, "tab": tab}
    if document:
        query["document"] = document
    return f"{HUB}/?{urllib.parse.urlencode(query)}"


def goto(page, url):
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)


def present(page, selector, ms=4000):
    try:
        page.wait_for_selector(selector, timeout=ms)
        return True
    except Exception:  # noqa: BLE001 -- absence is the answer
        return False


def need(ok, detail):
    if not ok:
        raise Failed(detail)


def home_url(fx):
    return spec_url(fx.a)


def open_home(fx, page):
    """From an open document, click the list control: the home must be what it shows."""
    goto(page, spec_url(fx.a, fx.p["xray"]))
    if not present(page, "[data-testid=spec-list-control]", 8000):
        raise NotReached("no list control [data-testid=spec-list-control] on an open document")
    page.click("[data-testid=spec-list-control]")
    page.wait_for_timeout(1000)


def node(page, col, title):
    return page.locator(f".aw-map-node[data-col={col}]", has_text=title)


def check_home_click(fx, page):
    open_home(fx, page)
    shot(page, "home-click")
    need(present(page, "[data-testid=spec-home]", 4000), "the list control does not show [data-testid=spec-home]")
    ids = ["spec-home-building", "spec-home-recent", "spec-home-relations", "spec-home-capabilities"]
    positions = page.evaluate(
        """(ids) => { const home = document.querySelector('[data-testid=spec-home]');
        const els = ids.map(i => home && home.querySelector('[data-testid=' + i + ']'))
          .concat([document.querySelector('aside.aw-sp-list')]);
        const ranked = els.map((e, i) => [e, i]).filter(([e]) => e)
          .sort((x, y) => (x[0].compareDocumentPosition(y[0]) & 4) ? -1 : 1);
        return els.map((e, i) => e ? ranked.findIndex(([, j]) => j === i) : null); }""", ids)
    need(in_order(positions), f"sections not in order building, recent, relations, capabilities, then the list: {positions}")
    # the list keeps its saved filters: press one chip, leave, come back
    chip = page.locator("aside.aw-sp-list .aw-sp-list-filters button[aria-pressed]").nth(1)
    chip.click()
    pressed = chip.get_attribute("aria-pressed")
    goto(page, spec_url(fx.a, tab="overview"))
    goto(page, spec_url(fx.a))
    last = decoded(page.url)
    need(opens(page.url, fx.p["xray"]) or fx.p["xray"] in last or present(page, "[data-testid=spec-list-control]", 3000),
         "coming back to the Spec tab did not open the last document")
    need(not present(page, "[data-testid=spec-home]", 1500), "coming back to the Spec tab showed the home, not the last document")
    page.click("[data-testid=spec-list-control]")
    page.wait_for_timeout(800)
    again = page.locator("aside.aw-sp-list .aw-sp-list-filters button[aria-pressed]").nth(1).get_attribute("aria-pressed")
    need(again == pressed, f"the list's saved filter was not kept ({pressed} -> {again})")
    record("ac-home-click", True, True, "home above the list, sections in order, last document reopened, filters kept")


def building_rows(page):
    return page.locator("[data-testid=spec-home-build-row]")


def check_building(fx, page):
    open_home(fx, page)
    need(present(page, "[data-testid=spec-home-building]", 4000), "no [data-testid=spec-home-building] section")
    rows = building_rows(page)
    docs = [rows.nth(i).get_attribute("data-document") for i in range(rows.count())]
    need(len(docs) == 2, f"{len(docs)} spec-home-build-row rows, wanted exactly 2 (running builds): {docs}")
    need(docs == [fx.p["xray"], fx.p["yankee"]], f"rows {docs}, wanted newest build first {[fx.p['xray'], fx.p['yankee']]}")
    for i, doc in enumerate(docs):
        ok, detail = row_facts(rows.nth(i).inner_text())
        need(ok, f"row {doc}: {detail} :: {rows.nth(i).inner_text()[:140]!r}")
    section = page.locator("[data-testid=spec-home-building]").inner_text()
    need(fx.p["foxtrot"] not in "".join(docs), "the finished build is among Building now")
    goto(page, spec_url(fx.b))
    need(present(page, "[data-testid=spec-home-building]", 4000), "project with no running build: no [data-testid=spec-home-building] section")
    need(building_rows(page).count() == 0, f"{building_rows(page).count()} build rows in a project with no running build")
    empty = page.locator("[data-testid=spec-home-building]").inner_text().lower()
    need(re.search(r"nothing (is )?(being )?built|no (running )?builds?", empty) is not None,
         f"with no running build the section does not say nothing is being built :: {empty[:120]!r}")
    record("ac-building", True, True, f"two rows newest first with facts; section reads {section[:60]!r}; empty state says {empty[:40]!r}")


def first_link(page, scope, rel):
    return scope.locator(f"[data-testid=spec-home-link][data-rel={rel}]").first


def check_relations(fx, page):
    open_home(fx, page)
    need(present(page, "[data-testid=spec-home-build-row]", 4000), "no [data-testid=spec-home-build-row] rows")
    row = building_rows(page).first
    need(row.get_attribute("data-document") == fx.p["xray"], "the first row is not the newest building change")
    for rel, path, anchor in (("roadmap", fx.p["rho"], None), ("slice", fx.p["rho"], "slice-s2"),
                              ("capability", fx.p["cobalt"], None)):
        link = first_link(page, building_rows(page).first, rel)
        need(link.count() > 0, f"the first row has no spec-home-link data-rel={rel}")
        need(link.get_attribute("data-path") == path, f"{rel} link names {link.get_attribute('data-path')}, wanted {path}")
        link.click()
        page.wait_for_timeout(1200)
        need(opens(page.url, path, anchor), f"clicking the {rel} link went to {decoded(page.url)}, wanted {path} {anchor or ''}")
        open_home(fx, page)
    recent = page.locator("[data-testid=spec-home-recent-row]", has=page.locator(f"xpath=self::*[@data-document='{fx.p['foxtrot']}']"))
    need(page.locator(f"[data-testid=spec-home-recent-row][data-document='{fx.p['foxtrot']}']").count() == 1,
         "the finished change has no spec-home-recent-row")
    text = page.locator(f"[data-testid=spec-home-recent-row][data-document='{fx.p['foxtrot']}']").inner_text().lower()
    need("not in a roadmap" in text, f"the finished change's row does not say it is not in a roadmap :: {text[:120]!r}")
    del recent
    record("ac-relations", True, True, "roadmap, slice and capability links each open their document; second row says not in a roadmap")


def threads(page):
    return page.locator("[data-testid=spec-home-relations] .aw-map-thread")


def thread_joins(page):
    """Each map thread as (end, end, stroke-dasharray), the ends named by the box nearest each endpoint."""
    return [tuple(t) for t in page.evaluate(
        """() => {
        const home = document.querySelector('[data-testid=spec-home-relations]');
        const boxes = [...home.querySelectorAll('.aw-map-node')].map(n => ({t: n.innerText.trim(), r: n.getBoundingClientRect()}));
        const near = (x, y) => { let best = null, bd = 1e9;
          for (const b of boxes) { const dx = Math.max(b.r.left - x, 0, x - b.r.right), dy = Math.max(b.r.top - y, 0, y - b.r.bottom);
            const d = Math.hypot(dx, dy); if (d < bd) { bd = d; best = b.t; } }
          return bd < 24 ? best : '?'; };
        return [...home.querySelectorAll('.aw-map-thread')].map(p => {
          const svg = p.ownerSVGElement, m = p.getScreenCTM(), n = p.getTotalLength();
          const at = len => { const q = svg.createSVGPoint(); const pt = p.getPointAtLength(len); q.x = pt.x; q.y = pt.y; return q.matrixTransform(m); };
          const a = at(0), b = at(n);
          return [near(a.x, a.y), near(b.x, b.y), getComputedStyle(p).strokeDasharray];
        }); }""")]


def check_map(fx, page):
    open_home(fx, page)
    need(present(page, "[data-testid=spec-home-relations] .aw-map-node", 4000), "no .aw-map-node in [data-testid=spec-home-relations]")
    shot(page, "map")
    wanted = [("roadmap", "Rho roadmap"), ("change", "Xray change"), ("change", "Foxtrot change"), ("capability", "Cobalt cap")]
    for col, title in wanted:
        need(node(page, col, title).count() == 1, f"no .aw-map-node[data-col={col}] titled {title!r}")
    xs = [node(page, col, title).first.bounding_box()["x"] for col, title in (wanted[0], wanted[1], wanted[3])]
    need(xs[0] < xs[1] < xs[2], f"columns not roadmap < change < capability: x {xs}")
    joined = thread_joins(page)
    count = len(joined)
    need(count >= 3, f"{count} .aw-map-thread paths; wanted at least Xray to Rho, Xray to Cobalt, Foxtrot to Cobalt")
    seen = {(a, b) for a, b, _ in joined}
    for a, b in (("Xray change", "Rho roadmap"), ("Xray change", "Cobalt cap"), ("Foxtrot change", "Cobalt cap")):
        need((a, b) in seen or (b, a) in seen, f"no thread joins {a!r} to {b!r}: threads join {sorted(seen)}")
    xray = {d for a, b, d in joined if "Xray change" in (a, b)}
    foxtrot = {d for a, b, d in joined if "Foxtrot change" in (a, b)}
    need(len(xray) == 1 and not (xray & foxtrot),
         f"a running build's threads do not all differ from a finished one's (Xray stroke-dasharray {sorted(xray)}, Foxtrot {sorted(foxtrot)})")
    styles = xray | foxtrot
    node(page, "capability", "Cobalt cap").first.click()
    page.wait_for_timeout(1200)
    need(opens(page.url, fx.p["cobalt"]), f"clicking the capability's box went to {decoded(page.url)}")
    record("ac-map", True, True, f"{count} threads, {len(set(styles))} styles, boxes in columns, capability box opens")


def lit_snapshot(page, fx):
    """data-lit of every element the criterion names, by a key of its own."""
    p = fx.p
    snap = {}
    for key, path in (("X-row", p["xray"]), ("Y-row", p["yankee"])):
        snap[key] = page.locator(f"[data-testid=spec-home-build-row][data-document='{path}']").first.get_attribute("data-lit") \
            if page.locator(f"[data-testid=spec-home-build-row][data-document='{path}']").count() else "missing"
    for key, col, title in (("R-map", "roadmap", "Rho roadmap"), ("X-map", "change", "Xray change"),
                            ("C-map", "capability", "Cobalt cap"), ("Y-map", "change", "Yankee change"),
                            ("D-map", "capability", "Dune cap")):
        box = node(page, col, title)
        snap[key] = box.first.get_attribute("data-lit") if box.count() else "missing"
    for key, path in (("C-cap", p["cobalt"]), ("D-cap", p["dune"])):
        row = page.locator(f"[data-testid=spec-home-capability-row][data-path='{path}']")
        snap[key] = row.first.get_attribute("data-lit") if row.count() else "missing"
    return snap


def check_hover(fx, page):
    open_home(fx, page)
    need(present(page, "[data-testid=spec-home-relations] .aw-map-node", 4000), "no map boxes to hover")
    bright = ["X-row", "R-map", "X-map", "C-map", "C-cap"]
    dim = ["Y-row", "Y-map", "D-map", "D-cap"]
    node(page, "capability", "Cobalt cap").first.hover()
    page.wait_for_timeout(500)
    ok, detail = lit_verdict(lit_snapshot(page, fx), bright, dim)
    shot(page, "hover-map-box")
    need(ok, "hovering Cobalt's map box: " + detail)
    page.mouse.move(2, 2)
    page.wait_for_timeout(500)
    ok, detail = cleared(lit_snapshot(page, fx))
    need(ok, "moving away: " + detail)
    page.locator(f"[data-testid=spec-home-build-row][data-document='{fx.p['xray']}']").first.hover()
    page.wait_for_timeout(500)
    ok, detail = lit_verdict(lit_snapshot(page, fx), bright, dim)
    shot(page, "hover-row")
    need(ok, "hovering Xray's row: " + detail)
    page.mouse.move(2, 2)
    page.wait_for_timeout(500)
    ok, detail = cleared(lit_snapshot(page, fx))
    need(ok, "moving away from the row: " + detail)
    record("ac-hover", True, True, "map box and row both light X, R and C in rows, map and Capabilities; Y and D dim; cleared on leaving")


def check_back(fx, page):
    """The change's page links to its roadmap (at its slice) and to each capability; the roadmap's slice
    links to the change; the capability lists it. A link is any button or anchor in the page's main area
    (the document list beside it is not the page's link), found by its document's title."""
    main = "[data-testid=spec-page] :is(a, button):not(aside *)"
    for what, title, path, anchor in (("roadmap", "Rho roadmap", fx.p["rho"], "slice-s2"),
                                      ("capability", "Cobalt cap", fx.p["cobalt"], None)):
        goto(page, spec_url(fx.a, fx.p["xray"]))
        if what == "roadmap":
            shot(page, "back-change")
        link = page.locator(main).filter(has_text=title)
        need(link.count() > 0, f"the change's page has no link to its {what} {title!r}")
        link.first.click()
        page.wait_for_timeout(1200)
        need(opens(page.url, path, anchor), f"the {what} link went to {decoded(page.url)}, wanted {path} {anchor or ''}")
    goto(page, spec_url(fx.a, fx.p["rho"]))
    need(present(page, "#slice-s2", 4000), "the roadmap's page has no #slice-s2")
    link = page.locator("#slice-s2 :is(a, button)").filter(has_text="Xray change")
    need(link.count() > 0, "the roadmap's slice s2 does not link to the change that specifies it")
    link.first.click()
    page.wait_for_timeout(1200)
    need(opens(page.url, fx.p["xray"]), f"the slice link went to {decoded(page.url)}")
    goto(page, spec_url(fx.a, fx.p["cobalt"]))
    row = page.locator(f"[data-testid=capability-touched-row][data-path='{fx.p['xray']}']")
    need(present(page, "[data-testid=capability-touched-row]", 4000) and row.count() == 1,
         "the capability's page does not list the change in a capability-touched-row")
    row.first.click()
    page.wait_for_timeout(1200)
    need(opens(page.url, fx.p["xray"]), f"the capability's row opened {decoded(page.url)}")
    record("ac-back", True, True, "change links to roadmap slice and capability; slice links back; capability lists the change")


def check_capabilities(fx, page):
    open_home(fx, page)
    need(present(page, "[data-testid=spec-home-capabilities]", 4000), "no [data-testid=spec-home-capabilities] section")
    rows = page.locator("[data-testid=spec-home-capability-row]")
    paths = sorted(rows.nth(i).get_attribute("data-path") for i in range(rows.count()))
    want = sorted([fx.p["cobalt"], fx.p["dune"], fx.p["ember"]])
    need(paths == want, f"capability rows {paths}, wanted {want}")
    cobalt = page.locator(f"[data-testid=spec-home-capability-row][data-path='{fx.p['cobalt']}']")
    need(waiting_count(cobalt.inner_text()) == 2, f"Cobalt row says {cobalt.inner_text()!r}, wanted 2 waiting")
    ember = page.locator(f"[data-testid=spec-home-capability-row][data-path='{fx.p['ember']}']")
    need(ember.count() == 1 and waiting_count(ember.inner_text()) in (None, 0), "the untouched capability's row is missing or shows waiting")
    ember.click()
    page.wait_for_timeout(1200)
    need(opens(page.url, fx.p["ember"]), f"clicking the capability row went to {decoded(page.url)}")
    record("ac-capabilities", True, True, "three capability rows, Cobalt 2 waiting, Ember present, row opens the capability")


def check_touched(fx, page):
    goto(page, spec_url(fx.b, fx.p["tango"]))
    need(present(page, "[data-testid=capability-touched-row]", 6000), "no [data-testid=capability-touched-row] on the capability's page")
    shot(page, "touched")
    rows = page.locator("[data-testid=capability-touched-row]")
    got = [(rows.nth(i).get_attribute("data-path"), rows.nth(i).get_attribute("data-state")) for i in range(rows.count())]
    need(len(got) == 3, f"{len(got)} capability-touched-row rows, wanted 3: {got}")
    folded = [p for p, s in got if s == "folded"]
    waiting = [p for p, s in got if s == "waiting"]
    need(len(folded) == 2 and waiting == [fx.p["t3"]], f"states {got}, wanted two folded and T3 waiting")
    need(folded == [fx.p["t2"], fx.p["t1"]], f"folded rows {folded}, wanted newest fold first {[fx.p['t2'], fx.p['t1']]}")
    for i, (path, state) in enumerate(got):
        text = rows.nth(i).inner_text()
        if state == "folded":
            need(bool(re.search(r"\d{4}-\d{2}-\d{2}|\b[A-Z][a-z]{2}\s+\d{1,2}\b|\bago\b|today|just now", text)), f"folded row {path} shows no fold date :: {text[:80]!r}")
    for path, _state in got:
        goto(page, spec_url(fx.b, fx.p["tango"]))
        need(present(page, "[data-testid=capability-touched-row]", 6000), "the capability's page lost its touched rows on return")
        row = page.locator(f"[data-testid=capability-touched-row][data-path='{path}']")
        need(row.count() == 1, f"touched row for {path} is missing on return")
        link = row.locator("a, button").first
        (link if link.count() else row).click()
        page.wait_for_timeout(1200)
        need(opens(page.url, path), f"touched row {path} opened {decoded(page.url)}")
    record("ac-touched", True, True, "three rows, two folded (newest fold first, dated) and one waiting, each opens its own change")


def check_live(fx, page):
    open_home(fx, page)
    need(present(page, "[data-testid=spec-home]", 4000), "no [data-testid=spec-home] to watch")
    page.evaluate("window.__shwbbNoReload = true")
    zulu = fx.p["zulu"]
    fx.a.build(zulu)
    started = poll(lambda: page.locator(f"[data-testid=spec-home-build-row][data-document='{zulu}']").count() == 1, 10, 0.5)
    on_map = node(page, "change", "Zulu change").count() == 1
    shot(page, "live-started")
    need(started, "a build that started did not appear in Building now within ten seconds")
    need(on_map, "a build that started did not appear in the map within ten seconds")
    fx.a.land(zulu)
    moved = poll(lambda: page.locator(f"[data-testid=spec-home-recent-row][data-document='{zulu}']").count() == 1
                 and page.locator(f"[data-testid=spec-home-build-row][data-document='{zulu}']").count() == 0, 10, 0.5)
    shot(page, "live-finished")
    need(moved, "a build that finished did not move to Recently built within ten seconds")
    need(page.evaluate("window.__shwbbNoReload === true"), "the page reloaded")
    record("ac-live", True, True, "started: Building now and map; finished: Recently built; no reload")


def run_checks(fx, only):
    from playwright.sync_api import sync_playwright

    steps = [("ac-home-click", check_home_click), ("ac-building", check_building), ("ac-relations", check_relations),
             ("ac-map", check_map), ("ac-hover", check_hover), ("ac-back", check_back),
             ("ac-capabilities", check_capabilities), ("ac-touched", check_touched), ("ac-live", check_live)]
    with sync_playwright() as play:
        browser = play.chromium.launch()
        for key, fn in steps:
            if only and key not in only:
                continue
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            context.add_init_script(
                "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
                "localStorage.setItem('agentweave-prefs', JSON.stringify({mode: 'dark'})); } catch (e) {}"
                % (json.dumps(KEY), json.dumps(HUB)))
            page = context.new_page()
            try:
                fn(fx, page)
            except Failed as exc:
                record(key, True, False, str(exc))
                shot(page, f"{key}-failed")
            except (NotReached, Setup) as exc:
                record(key, False, False, str(exc))
            except Exception as exc:  # noqa: BLE001 -- a check that could not run says so, it does not pass
                record(key, False, False, f"{type(exc).__name__}: {str(exc)[:200]}")
            finally:
                context.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true", help="check the drive's own logic only; no Hub")
    parser.add_argument("--only", default="", help="comma-separated check keys to run (iteration)")
    parser.add_argument("--seed-only", action="store_true", help="arrange the fixture and stop")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    if str(PORT) in ("8000", "8010"):
        sys.exit("REFUSING: this drive starts its own Hub and never runs on :8000 or :8010")
    if port_answers():
        sys.exit(f"REFUSED: :{PORT} already answers, and it may be running another checkout's code "
                 "(F1121). Pick another AW_DRIVE_PORT; this drive does not reuse a Hub.")
    only = {k.strip() for k in args.only.split(",") if k.strip()}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    proc = start_hub(SCRATCH / "hub.log")
    setup_error = None
    fx = Fixture()
    try:
        arrange(fx)
        if not args.seed_only:
            run_checks(fx, only)
    except Setup as exc:
        setup_error = str(exc)
        print(f"SETUP: {exc}", flush=True)
    finally:
        stop_hub(proc)
    print("\n== drive_baseline")
    failed = False
    for key in ORDER:
        if only and key not in only:
            continue
        reached, failed_here, detail = checks.get(key, (False, False, setup_error or "not run"))
        failed = failed or failed_here or not reached
        print(baseline_line(key, reached, failed_here, detail))
    print(f"output: {OUT}")
    sys.exit(1 if failed or setup_error else 0)


if __name__ == "__main__":
    main()
