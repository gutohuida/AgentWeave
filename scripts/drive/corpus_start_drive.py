"""Acceptance drive for `a-project-with-no-specs-is-offered-a-start` (PNSOS-1), 2026-11-17: the
criteria only a running Hub and a real browser can answer, written failing first, before the server
(PNSOS-2), the UI (PNSOS-3) and the drafts (PNSOS-4) are built.

Starts its own Hub from THIS checkout's `hub/` on a scratch port and a fresh database (default :8024
and a temp file; AW_DRIVE_PORT / AW_DRIVE_DB move them), on 127.0.0.1, and refuses a port something
already answers on. It stands in for the trial Hub the criteria name: :8010 serves whichever checkout
launched it (F1121), so a drive pointed there judges the wrong code. Never :8000 or :8010. Projects are
registered and arranged through the Hub's own routes; nothing is written into the database (one
read-only query reads who created the start document, which no route returns). Two real agent turns
can run, both bound to Haiku: the one ac-start-existing queues, and the greenfield interview.

Projects, each a fresh temporary folder:

  code     a git repo with source files, no spec/; agents Alpha (no charter) and Bravo (Spec Author)
  none     a git repo with source files, no agents
  empty    an empty folder; agent Greeter (Haiku)
  unadopted  a git repo holding spec/changes/x/spec.json the Hub has no record of; agent Alpha
  gone     a git repo with source files; agent Alpha (watches the set-up item leave)
  filter   one change document; agent Alpha
  map      system map "Ledger map" proposing Alpha billing / Beta ledger / Gamma export (no draft,
           an exploring draft, a draft approved and folded), and system map "Second map" proposing
           Delta audit / Echo search

The contract the drive probes (the design names the behaviour; these names are what it reads):
  The offer: `[data-testid=corpus-start-offer]`, holding one `[data-testid=corpus-start-option]` per
  start, `data-start` = `existing-code` | `greenfield`, the recommended one first with
  `data-recommended="true"` and the word "Recommended" in it. Each option's start control is
  `[data-testid=corpus-start-take]`. Taking it shows `[data-testid=corpus-start-agent]`, the picker
  (a <select>, or an element whose `data-value` is the chosen agent and whose
  `[data-testid=corpus-start-agent-option][data-agent=<name>]` children choose), and
  `[data-testid=corpus-start-confirm]`. With no open agent the offer has no take control and holds
  `[data-testid=corpus-start-add-agent]`.
  The set-up item: `[data-testid=setup-list] [data-testid=setup-item-specification]`
  (`data-key="specification"`), its action opening the offer; dismissed and restored like the
  repository item (Project settings, "Show it again").
  The map's page: one `[data-testid=map-capability-row]` per proposed title, `data-title`,
  `data-state` = no-draft | exploring | approved | current | declined, `data-draft` the draft's path
  when there is one; clicking a row with a draft opens that draft.
Every assertion reads its own element, never `body`.

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. Screenshots go to testbed/corpus-start-drive/<HHMMSS>/.

    py -3.11 scripts/drive/corpus_start_drive.py                    # own Hub on :8024
    py -3.11 scripts/drive/corpus_start_drive.py --only ac-greenfield
    py -3.11 scripts/drive/corpus_start_drive.py --skip-live        # no real agent turn
    py -3.11 scripts/drive/corpus_start_drive.py --self-test        # the drive's own logic, no Hub
"""

import argparse
import json
import os
import pathlib
import re
import secrets
import socket
import sqlite3
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
PORT = int(os.environ.get("AW_DRIVE_PORT") or 8024)
HUB = f"http://127.0.0.1:{PORT}"
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "drive-pnsos" / STAMP
DB = pathlib.Path(os.environ.get("AW_DRIVE_DB") or SCRATCH / "hub.db")
KEY = "aw_live_" + secrets.token_hex(16)
OUT = REPO / "testbed" / "corpus-start-drive" / STAMP
HAIKU = "claude-haiku-5-5"
ORDER = ["ac-spec-tab-offer", "ac-detect-code", "ac-filters-unchanged", "ac-overview-item", "ac-overview-gone",
         "ac-agent-choice", "ac-start-existing", "ac-map-creates-saved", "ac-map-links", "ac-greenfield"]
LIVE = {"ac-start-existing", "ac-greenfield"}  # checks that start a real (Haiku) agent turn

OFFER = "[data-testid=corpus-start-offer]"
OPTION = f"{OFFER} [data-testid=corpus-start-option]"
PICKER = "[data-testid=corpus-start-agent]"
CONFIRM = "[data-testid=corpus-start-confirm]"
SETUP_ITEM = "[data-testid=setup-list][data-place={place}] [data-testid=setup-item-specification]"
MAP_ROW = "[data-testid=map-capability-row]"
LIST = "aside.aw-sp-list"
SPEC_PAGE = "[data-testid=spec-page]"

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


def opens(url, path):
    """The app's URL names `path` as its document."""
    return f"document={path}" in decoded(url)


def conversation_of(url):
    """`(agent, conversation)` the app's URL names, or `(None, None)`."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url or "").query)
    return (query.get("agent") or [None])[0], (query.get("conversation") or [None])[0]


def options_verdict(options, recommended):
    """`(ok, detail)` over the offer's options, in page order, each `(start, data-recommended, text)`:
    both starts, `recommended` first, it alone marked recommended and saying so."""
    starts = [o[0] for o in options]
    if sorted(starts) != ["existing-code", "greenfield"]:
        return False, f"starts {starts}, wanted existing-code and greenfield"
    if starts[0] != recommended:
        return False, f"first start is {starts[0]}, wanted {recommended}"
    first, second = options
    if first[1] != "true" or "recommended" not in (first[2] or "").lower():
        return False, f"{recommended} is not marked recommended (data-recommended={first[1]!r}, text {first[2][:60]!r})"
    if second[1] == "true" or "recommended" in (second[2] or "").lower():
        return False, f"{second[0]} is marked recommended too"
    return True, f"{starts} with {recommended} first and marked recommended"


def asks_about_scope(text):
    """The agent's first reply asks the operator something about the problem, users or scope."""
    low = (text or "").lower()
    return "?" in low and bool(re.search(r"problem|scope|user|who |goal|non-goal|build|purpose", low))


def created_by_operator(events):
    """`events` are `(kind, actor_kind)` rows of a document: it was created by the operator."""
    return any(kind == "created" and actor == "operator" for kind, actor in events)


def setup_ids(project, part):
    return [i.get("id") for i in ((project or {}).get("setup") or {}).get(part, [])]


def baseline_line(key, reached, failed, detail):
    return (f"check {key}: reached={'yes' if reached else 'no'} "
            f"failed_at_assertion={'yes' if failed else 'no'} -- {detail}")


def self_test():
    rec = lambda s: (s, "true", f"{s} Recommended")  # noqa: E731
    plain = lambda s: (s, None, s)  # noqa: E731
    cases = [
        (opens("http://h/?tab=spec&document=spec%2Fa%2Fspec.json", "spec/a/spec.json"), True),
        (opens("http://h/?tab=spec", "spec/a/spec.json"), False),
        (conversation_of("http://h/?project=p&agent=Alpha&conversation=c1"), ("Alpha", "c1")),
        (conversation_of("http://h/?project=p&tab=spec"), (None, None)),
        (options_verdict([rec("existing-code"), plain("greenfield")], "existing-code")[0], True),
        (options_verdict([rec("greenfield"), plain("existing-code")], "greenfield")[0], True),
        (options_verdict([plain("greenfield"), rec("existing-code")], "existing-code")[0], False),
        (options_verdict([plain("existing-code"), plain("greenfield")], "existing-code")[0], False),
        (options_verdict([rec("existing-code"), rec("greenfield")], "existing-code")[0], False),
        (options_verdict([rec("existing-code")], "existing-code")[0], False),
        (asks_about_scope("What problem does this project solve, and who are its users?"), True),
        (asks_about_scope("I wrote the roadmap."), False),
        (asks_about_scope("Ready?"), False),
        (created_by_operator([("created", "operator"), ("saved", "agent")]), True),
        (created_by_operator([("created", "agent")]), False),
        (setup_ids({"setup": {"items": [{"id": "agent"}], "dismissed": []}}, "items"), ["agent"]),
        (setup_ids({}, "dismissed"), []),
        (baseline_line("k", True, True, "d"), "check k: reached=yes failed_at_assertion=yes -- d"),
        (len(ORDER), 10), (LIVE <= set(ORDER), True),
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


def document_events(document_path, project_id):
    """`(kind, actor_kind)` of each lifecycle event of one document, read-only from the drive's own
    database: no route returns who created a document."""
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(
            "select e.kind, e.actor_kind from spec_document_events e join spec_documents d on d.id = e.document_id "
            "where d.project_id = ? and d.path = ? order by e.rowid", (project_id, document_path)).fetchall()
    finally:
        con.close()


# --------------------------------------------------------------------------- the fixture


def expect(code, want, what, out):
    if code not in want:
        raise Setup(f"{what}: {code} {str(out)[:500]}")
    return out


SOURCE = {
    "app.py": "def main():\n    print('hello')\n\n\nif __name__ == '__main__':\n    main()\n",
    "billing.py": "def total(items):\n    return sum(i['price'] for i in items)\n",
    "README.md": "A throwaway project with code, for the corpus-start drive.\n",
}


class Project:
    """One throwaway project, arranged through the Hub's routes only."""

    def __init__(self, name, files=None, repo=True, agents=()):
        self.name = name
        self.files = files if files is not None else SOURCE
        self.repo = repo
        self.agents = agents  # (name, charter name or None), in order
        self.pid = ""
        self.base = ""
        self.root = SCRATCH / f"proj-{name}"

    def open(self):
        self.root.mkdir(parents=True)
        for rel, text in self.files.items():
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        if self.repo:
            git(self.root, "init", "-q", "-b", "main")
            if self.files:
                git(self.root, "add", "-A")
                git(self.root, "commit", "-q", "-m", "seed")
        code, project = api("POST", "/projects/open", {"path": str(self.root), "name": f"pnsos-{self.name}-{STAMP}"})
        expect(code, (200, 201), f"project {self.name} opens", project)
        self.pid, self.base = project["id"], f"/projects/{project['id']}"
        if self.repo and self.files:
            code, out = api("PUT", f"{self.base}/settings", {"main_branch": "main"})
            expect(code, (200,), f"{self.name}: main branch", out)
        if self.agents:
            code, runner = api("POST", f"{self.base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
            expect(code, (200, 201), f"{self.name}: the Haiku runner", runner)
            for agent, charter in self.agents:
                body = {"name": agent, "runner_id": runner["id"]}
                if charter:
                    body["charter_id"] = self.charter(charter)
                code, out = api("POST", f"{self.base}/agents", body)
                expect(code, (200, 201), f"{self.name}: agent {agent}", out)
        return self

    def charter(self, name):
        code, out = api("GET", f"{self.base}/charters")
        expect(code, (200,), f"{self.name}: charters", out)
        found = next((c for c in out if c.get("name") == name), None)
        if found:
            return found["id"]
        content = (REPO / "hub" / "hub" / "data" / "charters" / "spec.md").read_text(encoding="utf-8")
        code, out = api("POST", f"{self.base}/charters", {"name": name, "content": content})
        expect(code, (200, 201), f"{self.name}: charter {name}", out)
        return out["id"]

    def summary(self):
        code, out = api("GET", f"/projects/{self.pid}")
        expect(code, (200,), f"{self.name}: project summary", out)
        return out

    def documents(self):
        code, out = api("GET", f"{self.base}/project/documents")
        expect(code, (200,), f"{self.name}: documents", out)
        return out.get("documents", [])

    def create(self, title, kind, path=None):
        body = {"title": title, "kind": kind, **({"path": path} if path else {})}
        code, out = api("POST", f"{self.base}/project/documents", body)
        expect(code, (201,), f"{self.name}: create {kind} {title}", out)
        return out.get("path") or (out.get("document") or {}).get("path")

    def save(self, path, kind, title, extra):
        body = {"schema_version": 1, "kind": kind, "title": title, "summary": f"{title}, a drive fixture.",
                "problem": "The drive needs one.",
                "scope": {"in_scope": ["the drive"], "non_goals": ["anything else"]}, **extra}
        return api("PUT", f"{self.base}/project/documents/{path}/content", {"document": body})

    def version(self, path):
        code, out = api("GET", f"{self.base}/project/spec?path={urllib.parse.quote(path)}")
        expect(code, (200,), f"read {path}", out)
        return out["content_version"]

    def approve(self, path):
        code, out = api("POST", f"{self.base}/project/documents/phase?path={urllib.parse.quote(path)}&to=approved",
                        {"content_version": self.version(path), "approve_anyway": True})
        expect(code, (200,), f"approve {path}", out)

    def fold(self, path, into):
        code, out = api("POST", f"{self.base}/project/documents/{path}/fold", {"into": into, "archive": False})
        expect(code, (200,), f"fold {path}", out)


def requirement(title):
    return {"requirements": [{"key": "r1", "modal": "MUST", "statement": f"{title} MUST work as it does."}],
            "acceptance_criteria": [{"key": "ok", "requirement": "r1", "given": "x", "when": "y", "then": "z",
                                     "how_to_check": "read", "checked_by": "agent"}]}


def draft(project, slug, title, creates):
    """A capability draft: a change document with no tasks naming `creates` in capabilities.creates."""
    path = project.create(title, "change-spec", f"spec/changes/{slug}/spec.json")
    code, out = project.save(path, "change-spec", title,
                             {**requirement(title), "tasks": [], "capabilities": {"changes": [], "creates": [{"title": creates}]}})
    expect(code, (200,), f"save draft {path}", out)
    return path


def system_map(project, title, creates):
    """A system map proposing `creates`. Answers `(path, save status, save answer)`: the save is the
    behaviour FR-12 adds, so a refusal is the check's to judge, not the fixture's."""
    path = project.create(title, "system-map")
    code, out = project.save(path, "system-map", title, {**requirement(title), "capabilities": {"creates": [{"title": t} for t in creates]}})
    return path, code, out


class Fixture:
    def __init__(self):
        self.p = {}
        self.paths = {}
        self.maps = {}
        self.broken = {}  # check key -> why its fixture could not be arranged


GROUPS = [  # (fixture, the checks that need it); a fixture that cannot be arranged fails only its checks
    ("code", ("ac-spec-tab-offer", "ac-detect-code", "ac-agent-choice", "ac-overview-item", "ac-start-existing")),
    ("none", ("ac-agent-choice",)),
    ("empty", ("ac-detect-code", "ac-greenfield")),
    ("unadopted", ("ac-detect-code",)),
    ("gone", ("ac-overview-gone",)),
    ("filter", ("ac-filters-unchanged",)),
    ("map", ("ac-map-creates-saved", "ac-map-links")),
]


def arrange_one(fx, name):
    if name == "code":
        fx.p["code"] = Project("code", agents=[("Alpha", None), ("Bravo", "Spec Author")]).open()
    elif name == "none":
        fx.p["none"] = Project("none").open()
    elif name == "empty":
        fx.p["empty"] = Project("empty", files={}, repo=False, agents=[("Greeter", None)]).open()
    elif name == "unadopted":
        files = {**SOURCE, "spec/changes/x/spec.json": json.dumps(
            {"schema_version": 1, "kind": "change-spec", "title": "X", "summary": "an unadopted file"})}
        fx.p["unadopted"] = Project("unadopted", files=files, agents=[("Alpha", None)]).open()
    elif name == "gone":
        fx.p["gone"] = Project("gone", agents=[("Alpha", None)]).open()
    elif name == "filter":
        f = fx.p["filter"] = Project("filter", agents=[("Alpha", None)]).open()
        fx.paths["only"] = f.create("Only change", "change-spec", "spec/changes/only/spec.json")
    elif name == "map":
        m = fx.p["map"] = Project("map", agents=[("Alpha", None)]).open()
        fx.paths["beta"] = draft(m, "beta-ledger", "Beta ledger draft", "Beta ledger")
        fx.paths["gamma"] = draft(m, "gamma-export", "Gamma export draft", "Gamma export")
        fx.maps["ledger"] = system_map(m, "Ledger map", ["Alpha billing", "Beta ledger", "Gamma export"])
        fx.maps["second"] = system_map(m, "Second map", ["Delta audit", "Echo search"])
        # Gamma's draft is approved and folded into the capability created for it: it reads current.
        m.approve(fx.paths["gamma"])
        cap = m.create("Gamma export", "capability", "spec/capabilities/gamma-export/spec.json")
        m.fold(fx.paths["gamma"], cap)
        fx.paths["gamma-cap"] = cap


def arrange(fx, only):
    for name, keys in GROUPS:
        if not any(k in only for k in keys):
            continue
        try:
            arrange_one(fx, name)
        except Setup as exc:
            print(f"SETUP {name}: {exc}", flush=True)
            for key in keys:
                fx.broken.setdefault(key, f"fixture {name}: {exc}")
    print("projects " + ", ".join(f"{k}={v.pid}" for k, v in fx.p.items()), flush=True)


# --------------------------------------------------------------------------- the browser


def shot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    except Exception as exc:  # noqa: BLE001 -- a picture is evidence, not the assertion
        print(f"  (no screenshot {name}: {exc})")


def url(project, tab="spec", **extra):
    return f"{HUB}/?{urllib.parse.urlencode({'project': project.pid, 'tab': tab, **extra})}"


def goto(page, address):
    page.goto(address, wait_until="domcontentloaded")
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


def list_empty_text(page):
    """The Spec list's own empty-state element's text, or '' when there is none."""
    box = page.locator(f"{LIST} .aw-sp-list-empty")
    return box.first.inner_text() if box.count() else ""


def empty_page_text(page):
    """What the Spec page shows in place of a list today for an empty corpus ("No specification
    yet", `.aw-sp-empty-page`), or '' when there is none: named in a failure so it says what was seen."""
    box = page.locator(f"{SPEC_PAGE} .aw-sp-empty-page")
    return " ".join(box.first.inner_text().split())[:120] if box.count() else ""


def open_spec_tab(page, project):
    goto(page, url(project))
    if not present(page, SPEC_PAGE, 10000):
        raise NotReached(f"the Spec tab of {project.name} shows no Spec page ({SPEC_PAGE})")
    page.wait_for_timeout(1000)


def offer_options(page):
    options = page.locator(OPTION)
    return [(options.nth(i).get_attribute("data-start"), options.nth(i).get_attribute("data-recommended"),
             options.nth(i).inner_text()) for i in range(options.count())]


def picker_state(page):
    """`(selected agent, choosable agents)` the picker shows."""
    return page.evaluate(
        """(sel) => { const el = document.querySelector(sel); if (!el) return [null, []];
        if (el.tagName === 'SELECT') return [el.value, Array.from(el.options).map(o => o.value)];
        const opts = Array.from(el.querySelectorAll('[data-testid=corpus-start-agent-option]'))
          .map(o => o.getAttribute('data-agent'));
        return [el.getAttribute('data-value'), opts]; }""", PICKER)


def take_start(page, start, agent=None):
    """Take `start` from the offer on the page, choosing `agent` if given; answers the picker's
    `(selected, choosable)` as it was before any choice."""
    take = page.locator(f"{OPTION}[data-start={start}] [data-testid=corpus-start-take]")
    need(take.count() == 1, f"the {start} option has {take.count()} start controls, wanted one")
    take.click()
    need(present(page, PICKER, 4000), f"taking the {start} start asked for no agent ({PICKER})")
    state = picker_state(page)
    if agent:
        if page.locator(PICKER).evaluate("el => el.tagName") == "SELECT":
            page.select_option(PICKER, agent)
        else:
            page.locator(PICKER).click()
            page.click(f"[data-testid=corpus-start-agent-option][data-agent={agent}]")
    return state


# --------------------------------------------------------------------------- the checks


def check_spec_tab_offer(fx, page):
    p = fx.p["code"]
    open_spec_tab(page, p)
    present(page, OFFER, 4000)
    shot(page, "spec-tab-offer")
    need(page.locator(OFFER).count() == 1 and page.locator(OFFER).is_visible(),
         f"an empty corpus with code shows no offer {OFFER}; the Spec page shows {empty_page_text(page) or list_empty_text(page)!r}")
    ok, detail = options_verdict(offer_options(page), "existing-code")
    need(ok, detail)
    need("No documents match." not in page.locator(SPEC_PAGE).inner_text(), "the Spec page still says \"No documents match.\" beside the offer")
    record("ac-spec-tab-offer", True, True, f"offer shown: {detail}; no \"No documents match.\"")


def check_detect_code(fx, page):
    seen = []
    for name, recommended in (("code", "existing-code"), ("empty", "greenfield")):
        p = fx.p[name]
        open_spec_tab(page, p)
        present(page, OFFER, 4000)
        shot(page, f"detect-{name}")
        need(page.locator(OFFER).count() == 1, f"project {name}: no offer {OFFER}; the Spec page shows {empty_page_text(page)!r}")
        ok, detail = options_verdict(offer_options(page), recommended)
        need(ok, f"project {name}: {detail}")
        seen.append(f"{name}: {recommended} first")
    p = fx.p["unadopted"]
    open_spec_tab(page, p)
    page.wait_for_timeout(1500)
    shot(page, "detect-unadopted")
    need(page.locator(OFFER).count() == 0, "a project with an unadopted spec file is offered a start")
    record("ac-detect-code", True, True, "; ".join(seen) + "; unadopted spec file: no offer")


def check_filters_unchanged(fx, page):
    p = fx.p["filter"]
    open_spec_tab(page, p)
    if not present(page, LIST, 6000):
        raise NotReached(f"a corpus with one document shows no list ({LIST})")
    chip = page.locator(f"{LIST} .aw-sp-list-filters button", has_text="Roadmaps")
    if chip.count() != 1:
        raise NotReached("no Roadmaps filter chip in the list")
    chip.click()
    page.wait_for_timeout(800)
    shot(page, "filters-unchanged")
    empty = list_empty_text(page)
    need("No documents match." in empty, f"a filter excluding the one document: the list says {empty!r}")
    clear = page.locator(f"{LIST} .aw-sp-list-empty button", has_text="Clear filters")
    need(clear.count() == 1, "no Clear filters in the list's empty state")
    need(page.locator(OFFER).count() == 0, "a filtered non-empty corpus is offered a start")
    record("ac-filters-unchanged", True, True, "\"No documents match.\" and Clear filters, no offer (regression guard)")


def overview_item(page, project):
    goto(page, url(project, tab="overview"))
    return present(page, SETUP_ITEM.format(place="overview"), 6000)


def check_overview_item(fx, page):
    p = fx.p["code"]
    shown = overview_item(page, p)
    shot(page, "overview-item-shown")
    need(shown, f"Overview of an empty corpus shows no specification set-up item ({SETUP_ITEM.format(place='overview')}); "
                f"items {setup_ids(p.summary(), 'items')}")
    item = page.locator(SETUP_ITEM.format(place="overview"))
    action = item.locator("button").last
    action.click()
    need(present(page, OFFER, 4000), "the set-up item's action does not open the offer")
    shot(page, "overview-item-opens-offer")
    goto(page, url(p, tab="overview"))
    dismiss = page.locator(SETUP_ITEM.format(place="overview")).locator("button", has_text="Not for this project")
    need(dismiss.count() == 1, "the specification set-up item cannot be dismissed")
    dismiss.click()
    page.wait_for_timeout(1000)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    shot(page, "overview-item-dismissed")
    need(page.locator(SETUP_ITEM.format(place="overview")).count() == 0, "the dismissed item is back after a reload")
    need("specification" in setup_ids(p.summary(), "dismissed"), f"the Hub does not record the dismissal: {p.summary().get('setup')}")
    goto(page, url(p, tab="environment", section="general"))
    restore = page.locator("[data-testid=setup-list][data-place=settings] .aw-setup-dismissed span",
                           has_text=re.compile("spec", re.I)).locator("button", has_text="Show it again")
    need(present(page, "[data-testid=setup-list][data-place=settings]", 6000) and restore.count() == 1,
         "Project settings lists no way to show the specification item again")
    shot(page, "settings-restore")
    restore.click()
    page.wait_for_timeout(1000)
    again = overview_item(page, p)
    shot(page, "overview-item-restored")
    need(again, "the restored item is not shown on Overview")
    record("ac-overview-item", True, True, "shown, opens the offer, gone after dismiss and reload, shown again after restore")


def check_overview_gone(fx, page):
    p = fx.p["gone"]
    need(overview_item(page, p), "Overview of an empty corpus shows no specification set-up item to watch")
    shot(page, "overview-gone-before")
    p.create("First change", "change-spec", "spec/changes/first/spec.json")
    live = poll(lambda: page.locator(SETUP_ITEM.format(place="overview")).count() == 0, 10, 0.5)
    if not live:
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
    shot(page, "overview-gone-after")
    need(page.locator(SETUP_ITEM.format(place="overview")).count() == 0, "a document exists and the set-up item is still shown")
    summary = p.summary()
    need("specification" not in setup_ids(summary, "items"), "the Hub still lists the specification item")
    need("specification" not in setup_ids(summary, "dismissed"), "the item is recorded as dismissed")
    record("ac-overview-gone", True, True, f"gone {'without' if live else 'after'} a reload, not recorded as dismissed")


def check_agent_choice(fx, page):
    p = fx.p["code"]
    open_spec_tab(page, p)
    need(present(page, OFFER, 4000), "no offer to take a start from")
    selected, choosable = take_start(page, "existing-code")
    shot(page, "agent-choice-picker")
    need(selected == "Bravo", f"the picker preselects {selected!r}, wanted Bravo (the one Spec Author agent)")
    need("Alpha" in choosable, f"Alpha cannot be chosen instead: {choosable}")
    n = fx.p["none"]
    open_spec_tab(page, n)
    present(page, OFFER, 4000)
    shot(page, "agent-choice-none")
    need(page.locator(OFFER).count() == 1, "a project with no agent shows no offer at all")
    takes = page.locator(f"{OFFER} [data-testid=corpus-start-take], {OFFER} {CONFIRM}").count()
    need(takes == 0, f"a project with no agent offers {takes} start controls")
    need(page.locator(f"{OFFER} [data-testid=corpus-start-add-agent]").count() == 1, "the offer does not link to adding an agent")
    record("ac-agent-choice", True, True, f"preselected Bravo of {choosable}; no agent: no start, links to adding one")


def check_start_existing(fx, page):
    p = fx.p["code"]
    open_spec_tab(page, p)
    need(present(page, OFFER, 4000), "no offer to take the existing-code start from")
    take_start(page, "existing-code", agent="Alpha")
    page.click(CONFIRM)
    poll(lambda: conversation_of(page.url)[1] is not None, 15, 0.5)
    shot(page, "start-existing-conversation")
    agent, conversation = conversation_of(page.url)
    need(agent == "Alpha" and conversation, f"the start did not open Alpha's conversation: {decoded(page.url)}")
    maps = [d for d in p.documents() if d.get("kind") == "system-map"]
    need(len(maps) == 1, f"{len(maps)} system-map documents, wanted one")
    doc = maps[0]
    need(doc.get("phase") == "exploring", f"the system map is {doc.get('phase')}, wanted exploring")
    events = document_events(doc["path"], p.pid)
    need(created_by_operator(events), f"the system map was not created by the operator: {events}")
    code, queue = api("GET", f"{p.base}/queue/Alpha")
    expect(code, (200,), "Alpha's queue", queue)
    mine = [e for e in queue if e.get("conversation_id") == conversation and e.get("origin_type") == "operator"]
    need(mine, f"no operator-origin entry for Alpha in conversation {conversation}: {[(e.get('origin_type'), e.get('conversation_id')) for e in queue]}")
    need(doc["path"] in mine[0].get("content", ""), "the queued entry does not name the system map")
    open_spec_tab(page, p)
    row = page.locator(f"{LIST} button.aw-sp-list-row[title^='{doc.get('title')} ']")
    present(page, f"{LIST} button.aw-sp-list-row", 4000)
    shot(page, "start-existing-spec-tab")
    need(row.count() == 1, f"the Spec list does not list the system map {doc.get('title')!r}")
    need(page.locator(OFFER).count() == 0, "the offer is still shown once the corpus has a document")
    record("ac-start-existing", True, True,
           f"system map {doc['path']} exploring, operator-created; entry {mine[0]['id']} ({mine[0].get('state')}) in {conversation}; listed, no offer")


def map_rows(page):
    rows = page.locator(MAP_ROW)
    return [(rows.nth(i).get_attribute("data-title"), rows.nth(i).get_attribute("data-state"),
             rows.nth(i).get_attribute("data-draft")) for i in range(rows.count())]


def open_map(page, project, path):
    goto(page, url(project, document=path))
    present(page, MAP_ROW, 6000)


def check_map_creates_saved(fx, page):
    m = fx.p["map"]
    path, code, out = fx.maps["second"]
    need(code == 200, f"saving a system map with capabilities.creates is refused: {code} {str(out)[:200]}")
    code, read = api("GET", f"{m.base}/project/spec?path={urllib.parse.quote(path)}")
    expect(code, (200,), "read the map", read)
    content = read.get("content") if isinstance(read.get("content"), dict) else read
    titles = [c.get("title") if isinstance(c, dict) else c
              for c in ((content.get("capabilities") or {}).get("creates")) or []]
    need(sorted(titles) == ["Delta audit", "Echo search"], f"the read returns creates {titles}")
    open_map(page, m, path)
    shot(page, "map-creates-saved")
    shown = [r[0] for r in map_rows(page)]
    need(sorted(t or "" for t in shown) == ["Delta audit", "Echo search"], f"the map's page shows {shown}")
    record("ac-map-creates-saved", True, True, f"saved, read back and shown: {shown}")


def check_map_links(fx, page):
    m = fx.p["map"]
    path, code, out = fx.maps["ledger"]
    open_map(page, m, path)
    shot(page, "map-links")
    rows = map_rows(page)
    want = {"Alpha billing": ("no-draft", None), "Beta ledger": ("exploring", fx.paths["beta"]),
            "Gamma export": ("current", fx.paths["gamma"])}
    got = {t: (s, d) for t, s, d in rows}
    need(sorted(got) == sorted(want),
         f"the map's page lists {sorted(got)}, wanted {sorted(want)} (the map's save answered {code}: {str(out)[:160]})")
    wrong = [f"{t}: {got[t]} wanted {w}" for t, w in want.items() if got[t] != w]
    need(not wrong, "; ".join(wrong))
    none = page.locator(f"{MAP_ROW}[data-title='Alpha billing']")
    need(none.locator("a, button").count() == 0 or none.locator("a, button").first.get_attribute("href") is None,
         "the row with no draft links somewhere")
    for title in ("Beta ledger", "Gamma export"):
        open_map(page, m, path)
        row = page.locator(f"{MAP_ROW}[data-title='{title}']")
        link = row.locator("a, button").first
        (link if link.count() else row).click()
        page.wait_for_timeout(1500)
        need(opens(page.url, want[title][1]), f"clicking {title} opened {decoded(page.url)}, wanted {want[title][1]}")
    record("ac-map-links", True, True, "three rows with their own states; each draft row opens its own draft")


def check_greenfield(fx, page):
    p = fx.p["empty"]
    open_spec_tab(page, p)
    need(present(page, OFFER, 4000), "an empty folder is offered no start")
    take_start(page, "greenfield", agent="Greeter")
    page.click(CONFIRM)
    poll(lambda: conversation_of(page.url)[1] is not None, 15, 0.5)
    agent, conversation = conversation_of(page.url)
    need(agent == "Greeter" and conversation, f"the greenfield start did not open Greeter's conversation: {decoded(page.url)}")
    roadmaps = [d for d in p.documents() if d.get("kind") == "roadmap"]
    need(len(roadmaps) == 1 and roadmaps[0].get("phase") == "exploring",
         f"roadmaps {[(d.get('path'), d.get('phase')) for d in roadmaps]}, wanted one in exploring")

    def reply():
        code, out = api("GET", f"{p.base}/agent/Greeter/chat/{conversation}")
        texts = [e["content"] for e in (out or {}).get("entries", []) if e.get("kind") == "agent_output"] if code == 200 else []
        operator = [e for e in (out or {}).get("entries", []) if e.get("kind") == "operator_input"] if code == 200 else []
        return texts, operator

    poll(lambda: bool(reply()[0]), 300, 5)
    texts, operator = reply()
    page.wait_for_timeout(2000)
    shot(page, "greenfield-first-reply")
    need(texts, "the agent gave no reply within five minutes")
    need(asks_about_scope(texts[0]), f"the first reply does not ask about the problem or scope: {texts[0][:200]!r}")
    pane = page.locator("[data-testid=conversation-pane]")
    snippet = texts[0].strip().splitlines()[0][:40]
    need(pane.count() == 1 and snippet in pane.inner_text(), "the open conversation does not show the agent's first reply")
    typed = [e for e in operator if e.get("delivery_state") != "delivered" or "roadmap" not in (e.get("content") or "")]
    need(not typed, f"the operator typed before the reply: {len(typed)} other operator inputs")
    record("ac-greenfield", True, True, f"roadmap {roadmaps[0]['path']} exploring; first reply: {texts[0][:100]!r}")


STEPS = [("ac-spec-tab-offer", check_spec_tab_offer), ("ac-detect-code", check_detect_code),
         ("ac-filters-unchanged", check_filters_unchanged), ("ac-overview-item", check_overview_item),
         ("ac-overview-gone", check_overview_gone), ("ac-agent-choice", check_agent_choice),
         ("ac-map-creates-saved", check_map_creates_saved), ("ac-map-links", check_map_links),
         # last: each takes a start, which ends the offer for its project
         ("ac-start-existing", check_start_existing), ("ac-greenfield", check_greenfield)]


def run_checks(fx, only):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch()
        for key, fn in STEPS:
            if only and key not in only:
                continue
            if key in fx.broken:
                record(key, False, False, fx.broken[key])
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
    parser.add_argument("--skip-live", action="store_true", help="leave out the checks that start a real agent turn")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    if str(PORT) in ("8000", "8010"):
        sys.exit("REFUSING: this drive starts its own Hub and never runs on :8000 or :8010")
    if port_answers():
        sys.exit(f"REFUSED: :{PORT} already answers, and it may be running another checkout's code "
                 "(F1121). Pick another AW_DRIVE_PORT; this drive does not reuse a Hub.")
    only = {k.strip() for k in args.only.split(",") if k.strip()} or set(ORDER)
    if args.skip_live:
        only -= LIVE
    SCRATCH.mkdir(parents=True, exist_ok=True)
    proc = start_hub(SCRATCH / "hub.log")
    setup_error = None
    fx = Fixture()
    try:
        arrange(fx, only)
        run_checks(fx, only)
    except Setup as exc:
        setup_error = str(exc)
        print(f"SETUP: {exc}", flush=True)
    finally:
        stop_hub(proc)
    print("\n== drive_baseline")
    failed = False
    for key in ORDER:
        if key not in only:
            continue
        reached, failed_here, detail = checks.get(key, (False, False, setup_error or "not run"))
        failed = failed or failed_here or not reached
        print(baseline_line(key, reached, failed_here, detail))
    print(f"output: {OUT}")
    sys.exit(1 if failed or setup_error else 0)


if __name__ == "__main__":
    main()
