"""Acceptance drive for `a-roadmap-that-is-recognisably-a-roadmap` (RTRR-1), 2026-11-16: the eleven
acceptance criteria that only a running Hub (and, for the page, a browser) can answer, written failing
first, before RTRR-2 (slice states, cost and the one offer rule), RTRR-3 (move / add slices) and RTRR-4
(the page) are built. RTRR-5 runs it green and fixes only the drive.

Starts its own Hub from THIS checkout's `hub/` on a scratch port and a fresh database (default :8022
and a temp file; AW_DRIVE_PORT / AW_DRIVE_DB move them), on 127.0.0.1, and refuses a port something
already answers on. Never :8000 or :8010. No real agent turn is run (every state the page reports is
arranged in the database: documents' phases, tasks, landings, builds, turn_usage); any that were would
bind Haiku.

Fixture project (a throwaway git repository on `main`), five roadmaps, each a real `roadmap` document
whose slices are named by real `change-spec` documents (their `roadmap` link), then set to the phase the
scenario needs:

  FIVE  five slices a..e: unclaimed; named by an exploring document; approved, no task started;
        approved with one task approved and landed and one under review; approved, every task landed.
  NOTL  one slice, approved document, two tasks approved, only one landed (the other's landing queued).
  COST  five slices: s1 built (4 tasks on main, builds' turns $11.96), s2 built ($24.42), s3 with two
        unpriced turns, s4 and s5 unclaimed.
  SV    "Spec visuals" as it stood 2026-11-16: s1 s2 built; s3 builds after s1; s4 after s3; s5 after
        none. Used by ac-list, ac-two-ready, ac-move, ac-move-warn, ac-same-offers, ac-add.
  DONE  four slices Built, two of their documents still approved (the other two archived).

The page contract the drive probes (RTRR-2..4 may rename these and RTRR-5 then follows them, not the
behaviour):
  * the roadmap's read (`GET /projects/{pid}/project/spec?path=<roadmap>`) carries `slices`, each
    {key, state, tasks_on_main, tasks_total, cost_usd, unpriced_turns, built_at | started_at,
    document, offers_drafting (bool), waits_for [keys], warning, added_after_approval, added_by}, and
    `progress` {built, total, cost_usd, unpriced_turns}. `state` is one of Not drafted / Drafting /
    Approved / Building / Built;
  * Overview's offers are `GET .../project/next-slice-offers`, each with `roadmap` and
    `next_slice.key` (or `slice`); declined with `POST .../project/documents/next-slice/decline`
    (`path` = the offer's document, else the roadmap, `slice` = its key);
  * move: `POST .../project/documents/slices/move?path=<roadmap>` {slice, position (1-based)};
  * add: `POST .../project/documents/slices/conversation?path=<roadmap>` {agent} opens a conversation
    seeded with the roadmap (`conversation_id`); the agent's tool is
    `POST /agent-actions/spec/documents/amend` {path, op: "add_slice", change: {slice: {...},
    position}} under a run credential; nothing adds a slice from a hand-filled form;
  * archive: the page's `[data-testid=roadmap-archive]` button opens `[data-testid=roadmap-archive-
    confirm]` listing the documents; its confirm button is `[data-testid=roadmap-archive-yes]`;
    the page says `done`;
  * the list: a roadmap's row holds `[data-testid=roadmap-progress]` (one mark per slice and
    `built/total`), each nested slice row `[data-testid=slice-state]`.

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. Screenshots go to testbed/rtrr-drive/<HHMMSS>/.

    py -3.11 scripts/drive/roadmap_page_drive.py                  # own Hub on :8022
    py -3.11 scripts/drive/roadmap_page_drive.py --only ac-header,ac-list
    py -3.11 scripts/drive/roadmap_page_drive.py --self-test      # the drive's own logic, no Hub
"""

import argparse
import datetime
import hashlib
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
PORT = int(os.environ.get("AW_DRIVE_PORT") or 8022)
HUB = f"http://127.0.0.1:{PORT}"
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "drive-rtrr" / STAMP
DB = pathlib.Path(os.environ.get("AW_DRIVE_DB") or SCRATCH / "hub.db")
KEY = "aw_live_" + secrets.token_hex(16)
OPERATOR_AGENT = "Architect"
ORDER = ["ac-five-states", "ac-approved-not-landed", "ac-header", "ac-facts", "ac-two-ready",
         "ac-same-offers", "ac-move", "ac-move-warn", "ac-add", "ac-done", "ac-list"]
STATES = ["not drafted", "drafting", "approved", "building", "built"]

checks = {}  # key -> (reached, failed, detail)


class Setup(Exception):
    """Something the drive depends on could not be arranged."""


class NotReached(Exception):
    """A check could not get as far as its own assertion."""


def record(key, reached, ok, detail):
    checks[key] = (reached, reached and not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)


# --------------------------------------------------------------------------- pure logic (self-tested)


def state_word(raw):
    """A slice state, normalised to one of STATES, or None."""
    word = re.sub(r"[\s_-]+", " ", str(raw or "").strip().lower())
    return word if word in STATES else None


def slices_of(read):
    """The `slices` list of a roadmap's read, wherever the Hub puts it, as {key: slice}."""
    if not isinstance(read, dict):
        return {}
    found = read.get("slices")
    if found is None and isinstance(read.get("document"), dict):
        found = read["document"].get("slices")
    if not isinstance(found, list):
        return {}
    return {str(s.get("key")): s for s in found if isinstance(s, dict) and s.get("key")}


def order_of(read):
    found = read.get("slices") if isinstance(read, dict) else None
    if found is None and isinstance(read, dict) and isinstance(read.get("document"), dict):
        found = read["document"].get("slices")
    return [str(s.get("key")) for s in found or [] if isinstance(s, dict)]


def states_in(read, keys):
    return [state_word((slices_of(read).get(k) or {}).get("state")) for k in keys]


def offered(read):
    """Slice keys a roadmap's read offers for drafting."""
    return sorted(k for k, s in slices_of(read).items() if s.get("offers_drafting"))


def overview_offers(payload, roadmap):
    """Slice keys Overview offers for `roadmap` (its path)."""
    rows = payload.get("offers", []) if isinstance(payload, dict) else []
    keys = []
    for row in rows:
        if not isinstance(row, dict) or row.get("roadmap") != roadmap:
            continue
        nxt = row.get("next_slice") or {}
        key = nxt.get("key") if isinstance(nxt, dict) else None
        keys.append(str(key or row.get("slice") or ""))
    return sorted(k for k in keys if k)


def money(text):
    """Dollar amounts in a text, as floats."""
    return [float(m.replace(",", "")) for m in re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", text or "")]


def header_verdict(text):
    """`(ok, detail)`: the page says 2 of 5 built, $36.38 and 2 unpriced turns."""
    low = (text or "").lower()
    built = bool(re.search(r"\b2\s*(of|/)\s*5\b", low))
    cost = any(abs(v - 36.38) < 0.005 for v in money(text))
    unpriced = bool(re.search(r"\b2\s+unpriced\b|\bunpriced\D{0,20}\b2\b", low))
    return built and cost and unpriced, f"2-of-5 {built}, $36.38 {cost}, 2 unpriced {unpriced}"


def facts_verdict(text, doc_title, links):
    """`(ok, detail)`: a built slice's card shows its link, 4 of 4 on main, its cost and a date."""
    low = (text or "").lower()
    linked = any(doc_title in href or "document=" in href for href in links)
    tasks = bool(re.search(r"\b4\s*(of|/)\s*4\b", low)) and "main" in low
    cost = any(abs(v - 11.96) < 0.005 for v in money(text))
    dated = bool(re.search(r"\b(built|landed)\b[^\n]{0,40}\d", low) or re.search(r"\d{4}-\d{2}-\d{2}", low))
    return linked and tasks and cost and dated, f"link {linked}, 4 of 4 on main {tasks}, $11.96 {cost}, date {dated}"


def waits_verdict(text):
    """Slice 4's card says it waits for slice 3."""
    return bool(re.search(r"wait\w*[^\n]{0,60}(slice\s*3|\bs3\b|\b3\b)", (text or "").lower()))


def self_test():
    read = {"slices": [{"key": "a", "state": "Not drafted"}, {"key": "b", "state": "BUILT", "offers_drafting": True}]}
    cases = [
        (state_word("Not_drafted"), "not drafted"), (state_word("building"), "building"),
        (state_word("done"), None), (slices_of({"document": {"slices": [{"key": "x"}]}}).keys(), {"x": 1}.keys()),
        (slices_of(None), {}), (order_of(read), ["a", "b"]), (states_in(read, ["a", "b", "z"]),
                                                              ["not drafted", "built", None]),
        (offered(read), ["b"]),
        (overview_offers({"offers": [{"roadmap": "r", "next_slice": {"key": "s5"}},
                                     {"roadmap": "r", "slice": "s3"}, {"roadmap": "q", "slice": "s9"}]}, "r"),
         ["s3", "s5"]),
        (money("cost $36.38 and $1,200"), [36.38, 1200.0]),
        (header_verdict("2 of 5 built · $36.38 · 2 unpriced turns")[0], True),
        (header_verdict("2 of 5 built · $36.38")[0], False),
        (header_verdict("1 of 5 built · $36.38 · 2 unpriced")[0], False),
        (facts_verdict("4 of 4 tasks on main · $11.96 · built 2026-11-02", "t", ["?document=t"])[0], True),
        (facts_verdict("4 of 4 tasks on main · $11.96", "t", ["?document=t"])[0], False),
        (facts_verdict("4 of 4 tasks on main · $11.96 · built 2026-11-02", "t", [])[0], False),
        (waits_verdict("Waits for slice 3"), True), (waits_verdict("Draft this slice"), False),
        (len(ORDER), 11), (ORDER[0], "ac-five-states"),
    ]
    bad = [(i, got, want) for i, (got, want) in enumerate(cases) if got != want]
    for i, got, want in bad:
        print(f"self-test case {i}: got {got!r}, wanted {want!r}")
    print("self-test:", "PASS" if not bad else "FAIL", f"({len(cases) - len(bad)}/{len(cases)})")
    return not bad


# --------------------------------------------------------------------------- the Hub


def api(method, path, body=None, timeout=120, token=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + (token or KEY), "Content-Type": "application/json"}, method=method)
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


def rw(sql, args=()):
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def poll(fn, secs, every=2.0):
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
    if not poll(lambda: api("GET", "/projects", timeout=5)[0] == 200, 120):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        sys.exit(f"setup error: the Hub did not come up; see {log_path}")
    print(f"started a Hub on :{PORT} from {REPO / 'hub'} on {DB}", flush=True)
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    print(f"stopped the Hub on :{PORT}", flush=True)


def now(days_ago=0):
    moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f")


# --------------------------------------------------------------------------- the fixture


class Fixture:
    def __init__(self):
        self.pid = ""
        self.base = ""
        self.roadmaps = {}  # name -> (path, title, [slice keys])
        self.docs = {}      # (roadmap name, slice key) -> (path, document id)
        self.agent_token = ""

    def make_document(self, path, title, payload_extra, kind):
        quoted = urllib.parse.quote(path)
        code, out = api("POST", f"{self.base}/project/documents", {"title": title, "kind": kind, "path": path})
        if code != 201:
            raise Setup(f"create {path}: {code} {str(out)[:300]}")
        body = {"schema_version": 1, "kind": kind, "title": title, "summary": f"{title}, a drive fixture.",
                "problem": "The drive needs one.",
                "scope": {"in_scope": ["the drive"], "non_goals": ["anything else"]}, **payload_extra}
        code, out = api("PUT", f"{self.base}/project/documents/{path}/content", {"document": body})
        if code != 200:
            raise Setup(f"save {path}: {code} {str(out)[:600]}")
        return quoted

    def phase(self, path, phase):
        rw("update spec_documents set phase=?, first_approved_at=? where project_id=? and path=?",
           (phase, now(10) if phase in ("approved", "archived") else None, self.pid, path))

    def doc_id(self, path):
        return ro("select id from spec_documents where project_id=? and path=?", (self.pid, path))[0][0]

    def roadmap(self, name, title, slices):
        """`slices`: [(key, title, [builds_after])]. The roadmap is approved once its slices are named."""
        path = f"spec/roadmaps/{name}/spec.json"
        self.make_document(path, title, {
            "slices": [{"key": k, "title": t, "intent": f"{t} works.", "done": f"{t} is shown.",
                        "builds_after": after} for k, t, after in slices],
            "requirements": [], "acceptance_criteria": [], "tasks": []}, "roadmap")
        self.roadmaps[name] = (path, title, [k for k, _, _ in slices])
        return path

    def slice_document(self, name, key, phase, tasks=(), cost=None, unpriced=0, running=False, built_days=None):
        """A change document naming roadmap `name`'s slice `key`, at `phase`, with `tasks`
        [(status, landing state or None)], its build's turns priced at `cost` dollars plus `unpriced`
        turns with no price."""
        rpath, rtitle, _ = self.roadmaps[name]
        path = f"spec/changes/{name}-{key}/spec.json"
        title = f"{rtitle} {key}"
        self.make_document(path, title, {
            "roadmap": {"document": rpath, "slice": key},
            "requirements": [{"key": "r1", "modal": "MUST", "statement": "The repository MUST say so."}],
            "acceptance_criteria": [{"key": "ok", "requirement": "r1", "given": "x", "when": "y", "then": "z",
                                     "how_to_check": "read", "checked_by": "agent"}],
            "tasks": []}, "change-spec")
        self.phase(path, phase)
        doc = self.doc_id(path)
        self.docs[(name, key)] = (path, doc)
        build = None
        if cost is not None or unpriced or any(st != "pending" for st, _ in tasks):
            build = f"build-{secrets.token_hex(5)}"
            rw("insert into builds (id, project_id, document_id, state, driver, level, landing, builders, reviewers,"
               " people, reopenings, created_at, stopped_at) values (?, ?, ?, ?, 'flow', 'reviewed', 'main',"
               " '[]', '[]', '{}', '[]', ?, ?)",
               (build, self.pid, doc, "running" if running else "finished", now(built_days or 12),
                None if running else now(built_days or 12)))
        task_ids = []
        for i, (status, landing) in enumerate(tasks):
            task_id = f"task-{secrets.token_hex(6)}"
            task_ids.append(task_id)
            rw("insert into tasks (id, project_id, title, description, priority, status, assignee, created_at, updated,"
               " spec_document_id, spec_task_key, build_id) values (?, ?, ?, '', 'medium', ?, 'Builder', ?, ?, ?, ?, ?)",
               (task_id, self.pid, f"{key} task {i + 1}", status, now(12), now(built_days or 11), doc,
                f"t{i + 1}", build))
            if landing:
                rw("insert into task_landings (id, project_id, task_id, state, kind, order_key, unchecked, actor_kind,"
                   " actor, reason, created_at, updated_at) values (?, ?, ?, ?, 'merge', ?, 0, 'system', 'drive',"
                   " 'drive', ?, ?)",
                   (f"land-{secrets.token_hex(6)}", self.pid, task_id, landing, float(i + 1), now(built_days or 11),
                    now(built_days or 11)))
        if build and (cost is not None or unpriced):
            anchor = task_ids[0] if task_ids else None
            if anchor is None:
                anchor = f"task-{secrets.token_hex(6)}"
                rw("insert into tasks (id, project_id, title, description, priority, status, assignee, created_at, updated,"
                   " spec_document_id, spec_task_key, build_id) values (?, ?, 'cost anchor', '', 'medium', 'pending', 'Builder',"
                   " ?, ?, ?, 'anchor', ?)", (anchor, self.pid, now(12), now(12), doc, build))
            self.turns(anchor, cost, unpriced)
        return path

    def turns(self, task_id, cost, unpriced):
        priced = [] if cost is None else [int(round(cost * 1_000_000))]
        for micros in priced + [None] * unpriced:
            run = f"run-rtrr-{secrets.token_hex(5)}"
            rw("insert into runs (id, project_id, agent, status, started_at, ended_at, initiator, turn_depth, task_id)"
               " values (?, ?, 'Builder', 'completed', ?, ?, 'autonomous', 0, ?)",
               (run, self.pid, now(11), now(11), task_id))
            rw("insert into turn_usage (id, run_id, project_id, agent, status, total_tokens,"
               " api_equivalent_usd_micros, observed_at) values (?, ?, ?, 'Builder', 'measured', 1000, ?, ?)",
               (f"tu-{secrets.token_hex(6)}", run, self.pid, micros, now(11)))

    def agent_run(self, agent):
        """A running run of `agent`, and its credential: the agent-plane tool authenticates with it."""
        run_id = "run-rtrr-" + secrets.token_hex(4)
        token = "aw_run_" + secrets.token_urlsafe(24)
        rw("insert into runs (id, project_id, agent, status, started_at, initiator, turn_depth, "
           "capability_token_hash) values (?, ?, ?, 'running', ?, 'operator', 0, ?)",
           (run_id, self.pid, agent, now(), hashlib.sha256(token.encode("utf-8")).hexdigest()))
        return run_id, token


def arrange(fx):
    root = SCRATCH / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A throwaway project for the RTRR drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"rtrr-{STAMP}"})
    if code not in (200, 201):
        raise Setup(f"the project opens: {code} {project}")
    fx.pid = project["id"]
    fx.base = f"/projects/{fx.pid}"
    code, out = api("PUT", f"{fx.base}/settings", {"main_branch": "main"})
    if code != 200:
        raise Setup(f"main branch: {code} {str(out)[:300]}")
    code, runner = api("POST", f"{fx.base}/runners", {"name": "Haiku", "cli": "claude", "model": "claude-haiku-5-5"})
    if code not in (200, 201):
        raise Setup(f"the Haiku runner: {code} {runner}")
    for name in ("Builder", OPERATOR_AGENT):
        code, out = api("POST", f"{fx.base}/agents", {"name": name, "runner_id": runner["id"]})
        if code not in (200, 201):
            raise Setup(f"agent {name}: {code} {out}")

    five = fx.roadmap("five", "Five states", [(k, f"Slice {k}", []) for k in "abcde"])
    fx.slice_document("five", "b", "exploring")
    fx.slice_document("five", "c", "approved", tasks=[("pending", None), ("pending", None)])
    fx.slice_document("five", "d", "approved", running=True,
                      tasks=[("approved", "landed"), ("under_review", None)])
    fx.slice_document("five", "e", "approved", tasks=[("approved", "landed"), ("approved", "landed")])
    fx.phase(five, "approved")

    notl = fx.roadmap("notl", "Not landed", [("a", "Slice a", [])])
    fx.slice_document("notl", "a", "approved", tasks=[("approved", "landed"), ("approved", "queued")])
    fx.phase(notl, "approved")

    cost = fx.roadmap("cost", "Costed", [(f"s{i}", f"Slice {i}", []) for i in range(1, 6)])
    fx.slice_document("cost", "s1", "approved", cost=11.96,
                      tasks=[("approved", "landed")] * 4, built_days=9)
    fx.slice_document("cost", "s2", "approved", cost=24.42, tasks=[("approved", "landed")], built_days=5)
    fx.slice_document("cost", "s3", "approved", unpriced=2, running=True, tasks=[("in_progress", None)])
    fx.phase(cost, "approved")

    sv = fx.roadmap("sv", "Spec visuals", [
        ("s1", "Slice 1", []), ("s2", "Slice 2", []), ("s3", "Slice 3", ["s1"]),
        ("s4", "Slice 4", ["s3"]), ("s5", "Slice 5", [])])
    fx.slice_document("sv", "s1", "approved", tasks=[("approved", "landed")], built_days=9)
    fx.slice_document("sv", "s2", "approved", tasks=[("approved", "landed")], built_days=5)
    fx.phase(sv, "approved")

    done = fx.roadmap("done", "All built", [(f"s{i}", f"Slice {i}", []) for i in range(1, 5)])
    for i, phase in enumerate(["archived", "archived", "approved", "approved"], 1):
        fx.slice_document("done", f"s{i}", phase, tasks=[("approved", "landed")], built_days=8 - i)
    fx.phase(done, "approved")
    print(f"project {fx.pid} at {root}", flush=True)


# --------------------------------------------------------------------------- the checks


def read(fx, name):
    code, out = api("GET", f"{fx.base}/project/spec?path={urllib.parse.quote(fx.roadmaps[name][0])}")
    if code != 200 or not isinstance(out, dict):
        raise NotReached(f"the roadmap's read: {code} {str(out)[:200]}")
    return out


def offers(fx):
    code, out = api("GET", f"{fx.base}/project/next-slice-offers")
    if code != 200:
        raise NotReached(f"the offers read: {code} {str(out)[:200]}")
    return out


def check_five_states(fx):
    got = states_in(read(fx, "five"), list("abcde"))
    want = ["not drafted", "drafting", "approved", "building", "built"]
    record("ac-five-states", True, got == want, f"states {got}, wanted {want}")


def check_approved_not_landed(fx):
    got = states_in(read(fx, "notl"), ["a"])
    record("ac-approved-not-landed", True, got == ["building"], f"state {got}, wanted ['building']")


def spec_url(fx, name):
    return f"{HUB}/?project={fx.pid}&tab=spec&document={urllib.parse.quote(fx.roadmaps[name][0], safe='')}"


def body_text(page):
    page.wait_for_timeout(3000)
    return page.inner_text("body")


def check_header(fx, page):
    page.goto(spec_url(fx, "cost"))
    text = body_text(page)
    shot(page, "header")
    ok, detail = header_verdict(text)
    record("ac-header", True, ok, detail)


def check_facts(fx, page):
    page.goto(spec_url(fx, "cost"))
    text = body_text(page)
    links = [a.get_attribute("href") or "" for a in page.locator("a").all()]
    path = fx.docs[("cost", "s1")][0]
    ok, detail = facts_verdict(text, urllib.parse.quote(path, safe=""), [urllib.parse.unquote(h) for h in links])
    shot(page, "facts")
    record("ac-facts", True, ok, detail)


def check_two_ready(fx, page):
    got = read(fx, "sv")
    want = ["s3", "s5"]
    page.goto(spec_url(fx, "sv"))
    text = body_text(page)
    shot(page, "two-ready")
    ok = offered(got) == want and waits_verdict(text)
    record("ac-two-ready", True, ok, f"read offers {offered(got)}, wanted {want}; page says slice 4 waits "
           f"for slice 3: {waits_verdict(text)}")


def check_same_offers(fx):
    road = fx.roadmaps["sv"][0]
    before_page, before_overview = offered(read(fx, "sv")), overview_offers(offers(fx), road)
    want = ["s3", "s5"]
    code, out = api("POST", f"{fx.base}/project/documents/next-slice/decline?path={urllib.parse.quote(road)}"
                    "&slice=s5", {})
    after_page, after_overview = offered(read(fx, "sv")), overview_offers(offers(fx), road)
    ok = (before_page == want and before_overview == want
          and "s5" not in after_page and "s5" not in after_overview)
    record("ac-same-offers", True, ok, f"before: page {before_page}, Overview {before_overview}; decline s5 "
           f"-> {code}; after: page {after_page}, Overview {after_overview}")


def check_move(fx):
    road = urllib.parse.quote(fx.roadmaps["sv"][0])
    code, out = api("POST", f"{fx.base}/project/documents/slices/move?path={road}", {"slice": "s5", "position": 3})
    got = order_of(read(fx, "sv"))
    phase = ro("select phase from spec_documents where project_id=? and path=?", (fx.pid, fx.roadmaps["sv"][0]))[0][0]
    refused, _ = api("POST", f"{fx.base}/project/documents/slices/move?path={road}", {"slice": "s1", "position": 3})
    events = json.dumps(ro("select actor_kind, actor, kind, detail from spec_document_events where document_id=?",
                           (fx.doc_id(fx.roadmaps["sv"][0]),)))
    named = "operator" in events.lower() and "slice" in events.lower() and "s5" in events
    ok = (code == 200 and got.index("s5") == 2 if "s5" in got else False) and phase == "approved" \
        and refused in (409, 422) and named
    record("ac-move", True, ok, f"move -> {code}, order {got}, phase {phase}, moving built s1 -> {refused}, "
           f"history names the operator and the move: {named}")


def check_move_warn(fx):
    road = urllib.parse.quote(fx.roadmaps["sv"][0])
    code, out = api("POST", f"{fx.base}/project/documents/slices/move?path={road}", {"slice": "s4", "position": 1})
    s4 = slices_of(read(fx, "sv")).get("s4") or {}
    warning = str(s4.get("warning") or "")
    ok = code == 200 and bool(re.search(r"\b(s3|slice\s*3)\b", warning.lower()))
    record("ac-move-warn", True, ok, f"move -> {code}; slice 4 warning {warning!r}")


def check_add(fx, page):
    road = fx.roadmaps["sv"][0]
    quoted = urllib.parse.quote(road)
    page.goto(spec_url(fx, "sv"))
    text = body_text(page)
    form = page.locator("form input[name=title], [data-testid=add-slice-form]").count()
    code, out = api("POST", f"{fx.base}/project/documents/slices/conversation?path={quoted}",
                    {"agent": OPERATOR_AGENT})
    conv = out.get("conversation_id") if isinstance(out, dict) else None
    _, token = fx.agent_run(OPERATOR_AGENT)
    added, out2 = api("POST", "/agent-actions/spec/documents/amend", {
        "path": road, "op": "add_slice", "reason": "drive",
        "change": {"slice": {"key": "s6", "title": "Slice 6", "intent": "x", "done": "y", "builds_after": ["s5"]},
                   "position": 6}}, token=token)
    after = read(fx, "sv")
    s6 = slices_of(after).get("s6") or {}
    amend_text = json.dumps(after)
    page.goto(spec_url(fx, "sv"))
    text = body_text(page)
    shot(page, "added")
    ok = (code == 200 and bool(conv) and form == 0 and added in (200, 201) and s6
          and s6.get("added_after_approval") and s6.get("added_by") == OPERATOR_AGENT
          and "after approval" in text.lower() and OPERATOR_AGENT in text and "unreviewed" in amend_text.lower())
    record("ac-add", True, bool(ok), f"conversation route {code} (id {conv}), hand form shown {bool(form)}, "
           f"agent tool {added}, slice 6 {s6 or 'absent'}, page says added after approval by {OPERATOR_AGENT}: "
           f"{'after approval' in text.lower() and OPERATOR_AGENT in text}")


def doc_phases(fx, name):
    paths = [fx.roadmaps[name][0]] + [p for (n, _), (p, _) in fx.docs.items() if n == name]
    return {p: ro("select phase from spec_documents where project_id=? and path=?", (fx.pid, p))[0][0]
            for p in paths}


def check_done(fx, page):
    before = doc_phases(fx, "done")
    page.goto(spec_url(fx, "done"))
    text = body_text(page)
    says_done = bool(re.search(r"roadmap is done|all (\d+ )?slices (are )?built", text.lower()))
    button = page.get_by_test_id("roadmap-archive")
    if not button.count():
        shot(page, "done")
        record("ac-done", True, False, f"page says done {says_done}; no archive action "
               "([data-testid=roadmap-archive]) on the page")
        return
    button.first.click()
    confirm = page.get_by_test_id("roadmap-archive-confirm")
    page.wait_for_timeout(1000)
    listing = confirm.inner_text() if confirm.count() else ""
    mid = doc_phases(fx, "done")
    shot(page, "done-confirm")
    page.get_by_test_id("roadmap-archive-yes").first.click()
    page.wait_for_timeout(3000)
    after = doc_phases(fx, "done")
    open_before = [p for p, ph in before.items() if ph != "archived"]
    ok = (says_done and mid == before and len(open_before) == 3 and all(p in listing for p in open_before)
          and all(ph == "archived" for ph in after.values()))
    record("ac-done", True, ok, f"says done {says_done}; listed {[p in listing for p in open_before]}; "
           f"archived before confirm {mid != before}; after confirm {after}")


def check_list(fx, page):
    page.goto(f"{HUB}/?project={fx.pid}&tab=spec")
    page.wait_for_timeout(3000)
    row = page.locator("aside.aw-sp-list").get_by_text(fx.roadmaps["sv"][1], exact=False).first
    row.wait_for(timeout=20000)
    progress = page.get_by_test_id("roadmap-progress")
    states = page.get_by_test_id("slice-state")
    marks = progress.first.locator("[data-state], .aw-sp-mark, svg circle, i, span").count() if progress.count() else 0
    shot(page, "list")
    text = progress.first.inner_text() if progress.count() else ""
    ok = progress.count() > 0 and "2/5" in text.replace(" ", "") and marks >= 5 and states.count() >= 5
    record("ac-list", True, ok, f"progress element {progress.count()} reading {text!r}, marks {marks}, "
           f"nested slice states shown {states.count()}")


OUT = [pathlib.Path(".")]


def shot(page, name):
    OUT[0].mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT[0] / f"{name}.png"), full_page=True)


def guarded(key, fn, *args):
    try:
        fn(*args)
    except NotReached as exc:
        checks[key] = (False, False, f"not reached: {exc}")
        print(f"NOT REACHED {key}: {exc}", flush=True)
    except Exception as exc:  # noqa: BLE001 - a browser or route failure before the assertion
        checks[key] = (False, False, f"not reached: {type(exc).__name__}: {str(exc)[:240]}")
        print(f"NOT REACHED {key}: {type(exc).__name__}: {str(exc)[:240]}", flush=True)


def run_checks(fx, only):
    from playwright.sync_api import sync_playwright

    def want(key):
        return not only or key in only

    with sync_playwright() as play:
        browser = play.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 940})
        context.add_init_script(
            f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));"
            f"localStorage.setItem('agentweave-selected-project', {fx.pid!r});")
        page = context.new_page()
        steps = [
            ("ac-five-states", check_five_states, (fx,)),
            ("ac-approved-not-landed", check_approved_not_landed, (fx,)),
            ("ac-header", check_header, (fx, page)),
            ("ac-facts", check_facts, (fx, page)),
            ("ac-list", check_list, (fx, page)),
            ("ac-two-ready", check_two_ready, (fx, page)),
            ("ac-move", check_move, (fx,)),
            ("ac-move-warn", check_move_warn, (fx,)),
            ("ac-same-offers", check_same_offers, (fx,)),
            ("ac-add", check_add, (fx, page)),
            ("ac-done", check_done, (fx, page)),
        ]
        for key, fn, args in steps:
            if want(key):
                guarded(key, fn, *args)
        browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true", help="check the drive's own logic only; no Hub")
    parser.add_argument("--only", default="", help="comma-separated check keys to run (iteration)")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    if str(PORT) in ("8000", "8010"):
        sys.exit("REFUSING: this drive starts its own Hub and never runs on :8000 or :8010")
    if port_answers():
        sys.exit(f"REFUSED: :{PORT} already answers, and it may be running another checkout's code "
                 "(F1121). Pick another AW_DRIVE_PORT; this drive does not reuse a Hub.")
    only = {k.strip() for k in args.only.split(",") if k.strip()}
    OUT[0] = REPO / "testbed" / "rtrr-drive" / STAMP
    SCRATCH.mkdir(parents=True, exist_ok=True)
    proc = start_hub(SCRATCH / "hub.log")
    setup_error = None
    fx = Fixture()
    try:
        arrange(fx)
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
        print(f"check {key}: reached={'yes' if reached else 'no'} "
              f"failed_at_assertion={'yes' if failed_here else 'no'} -- {detail}")
    print(f"output: {OUT[0]}")
    sys.exit(1 if failed or setup_error else 0)


if __name__ == "__main__":
    main()
