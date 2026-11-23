"""Acceptance drive for `overview-at-a-glance-with-dashboard-and-briefing-tabs` (OGDBT-1),
2026-11-23: ac-drive-end-to-end, written failing first, before OGDBT-2 (GET /overview), the
visits-and-note task (POST /overview/visit, the overview-note job) and the two UI tasks are built.
The acceptance-run task runs it green against the trial Hub restarted from source.

Which Hub. By default the trial Hub on :8010 (`--hub`), whose key is read from AW_KEY or the trial
profile's bootstrap-key.txt and whose database (`--db`, the trial profile's by default) the drive
writes two things into: a held run of the Checker (so the operator approves, as in the RSRTT drive)
and the visit clock set back. `--own-hub` instead starts a Hub from THIS checkout's `hub/` on a
scratch port (default :8023, AW_DRIVE_PORT) and a fresh database, which is how today's code is
driven when :8010 may be running another checkout's (F1121). Never :8000. Real turns bind Haiku.

The scenario, in a throwaway git repository on `main` with no checks (a landing lands at once):
a Haiku runner, agents Builder and Checker, the overview-note job on Haiku, and an approved
one-task document built as a flow at Reviewed, landing on main. Then, in order (each step is one
named assertion; the drive goes on past a failed one where the next can still be tried, so the
first failure is the one reported and the build is still shown to work):

  A1 job-on        PATCH /manager/jobs/overview-note {enabled, runner, model} answers 200.
  A2 first-visit   the operator opens the Overview in a browser; the page POSTs /overview/visit,
                   answered 200 with previous_at null; GET /overview's visit.last_at is set.
  A3 built         a real Haiku turn builds the task; the operator accepts its evidence and approves
                   it (POST /tasks/{id}/land); its landing reaches `landed` on main.
  A4 clock-back    overview_visits.last_visit_at is set back 40 minutes in the database.
  A5 second-visit  the operator opens the Overview again: the page's POST /overview/visit answers
                   previous_at = the set-back first visit and note_started true.
  A6 finished      GET /overview lists the task once in `finished` as landed with a cost; the
                   Dashboard's "Finished today" tile reads 1 landed and its timeline lists the task
                   with a dollar cost.
  A7 since         the Briefing tab, opened: "Since you last looked" names a time and lists the task
                   as the 1 task finished; GET /overview's visit.previous_at is that first visit.
  A8 note          without any press (no `button` firing), GET /overview's note is written by the
                   `visit` trigger with a written_at and a cite of the task; the Briefing shows it
                   with a time, and its link to the task opens the task's drawer.
  A9 firing        GET /manager/activity?job=overview-note holds that firing: trigger `visit`,
                   outcome written, a duration and a cost; Settings > Manager lists it with its
                   result, time and cost. (The history table has no trigger column, so the trigger
                   is asserted on the route only.)

The page contract the drive probes (the UI tasks may rename these; the acceptance run then follows
the rename, not the behaviour):
  * the Overview is `/?project=<id>&tab=overview`; its tabs are role=tab (else buttons) named
    "Dashboard" and "Briefing";
  * the finished tile is `[data-slot=overview-tile]` whose aria-label starts "Finished today";
    timeline rows are `[data-slot=overview-activity]`;
  * the Briefing's since section is the `section` labelled by the heading "Since you last looked";
  * the note is `[data-testid=overview-note]`, else the `section` whose heading names a note; its
    links are buttons or anchors inside it;
  * a task's drawer is `[data-testid=task-drawer-<task id>]`;
  * Settings > Manager is `/?project=<id>&tab=environment&section=manager`, firing rows
    `[data-testid^=manager-firing-]`.

Prints the check in the `drive_baseline` shape and exits 1 if it failed:
    check ac-drive-end-to-end: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
Screenshots and the note text go to testbed/overview-glance/<HHMMSS>/.

    py -3.11 scripts/drive/overview_glance.py                      # the trial Hub :8010
    py -3.11 scripts/drive/overview_glance.py --own-hub            # a Hub from this checkout
    py -3.11 scripts/drive/overview_glance.py --self-test          # the drive's own logic, no Hub
"""

from __future__ import annotations

import argparse
import datetime as dt
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
OUT = REPO / "testbed" / "overview-glance" / STAMP
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "drive-overview-glance" / STAMP
TRIAL = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial"
HAIKU = "claude-haiku-5-5"
JOB = "overview-note"
BUILDER, CHECKER = "Builder", "Checker"
DOC, TITLE = "spec/changes/glance-one-task/spec.json", "Glance one task"
TASK_TITLE = "Write glance.txt"
KEY_CHECK = "ac-drive-end-to-end"
SET_BACK_MINUTES = 40
TURN_WAIT = 10 * 60
LANDING_WAIT = 5 * 60
NOTE_WAIT = 5 * 60
DONE = ("completed", "under_review")
STEPS = ["job-on", "first-visit", "built", "clock-back", "second-visit", "finished", "since",
         "note", "firing"]

HUB = ""
KEY = ""
DB = pathlib.Path()
results: dict[str, tuple[bool, str]] = {}


class Setup(Exception):
    """Something the scenario depends on, outside the criterion, could not be arranged."""


def step(name, ok, detail):
    results[name] = (bool(ok), detail)
    print(f"{'PASS' if ok else 'FAIL'} {name} -- {detail}", flush=True)
    return bool(ok)


# --------------------------------------------------------------------------- pure logic (self-tested)

TIME_WORDS = re.compile(
    r"(\b\d+\s*(seconds?|minutes?|mins?|hours?|hrs?|h|m)\s+ago\b|\b\d{1,2}:\d{2}\b|\bjust now\b|"
    r"\ban? (minute|hour) ago\b|\byesterday\b|\btoday\b)", re.I)
ONE_FINISHED = re.compile(r"\b(1|one) (task|piece of work)s? (has )?(finished|landed)\b|\blanded\s*1\b|\b1 landed\b",
                          re.I)
DOLLARS = re.compile(r"\$\s?\d")


def parse_at(value):
    """A Hub timestamp as an aware UTC datetime, or None. Naive values are UTC (the Hub stores UTC)."""
    if not value:
        return None
    text = str(value).strip().replace(" ", "T").replace("Z", "+00:00")
    try:
        at = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=dt.timezone.utc)


def same_moment(a, b, slack=2.0):
    a, b = parse_at(a), parse_at(b)
    return a is not None and b is not None and abs((a - b).total_seconds()) <= slack


def local_midnight():
    now = dt.datetime.now().astimezone()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def firing_cost(firing):
    """`(has_cost, words)`: a firing's usage reports dollars or tokens."""
    usage = firing.get("usage") or {}
    micros = usage.get("cost_usd_micros")
    tokens = sum(usage.get(k) or 0 for k in ("input_tokens", "output_tokens", "cache_read_tokens",
                                              "cache_write_tokens"))
    if micros:
        return True, f"${micros / 1e6:.4f}"
    return tokens > 0, f"{tokens} tokens"


def note_firings(firings, trigger):
    return [f for f in firings if f.get("job") == JOB and f.get("trigger") == trigger]


def cites_task(note, task_id):
    return any(c.get("type") == "task" and c.get("id") == task_id for c in (note or {}).get("cites") or [])


def first_failure(order, found):
    for name in order:
        if name in found and not found[name][0]:
            return name
    return None


def self_test():
    cases = [
        (bool(TIME_WORDS.search("You last looked 40 minutes ago")), True),
        (bool(TIME_WORDS.search("You last looked at 08:12")), True),
        (bool(TIME_WORDS.search("You last looked")), False),
        (bool(ONE_FINISHED.search("1 task finished since then")), True),
        (bool(ONE_FINISHED.search("Landed 1")), True),
        (bool(ONE_FINISHED.search("11 tasks finished")), False),
        (bool(DOLLARS.search("Builder landed $0.04")), True),
        (bool(DOLLARS.search("not priced")), False),
        (parse_at("2026-11-23 08:00:00.5") == dt.datetime(2026, 11, 23, 8, 0, 0, 500000, dt.timezone.utc), True),
        (parse_at("nonsense"), None),
        (same_moment("2026-11-23T08:00:00Z", "2026-11-23 08:00:01.2"), True),
        (same_moment("2026-11-23T08:00:00Z", "2026-11-23T08:40:00Z"), False),
        (firing_cost({"usage": {"cost_usd_micros": 40000}}), (True, "$0.0400")),
        (firing_cost({"usage": None})[0], False),
        (len(note_firings([{"job": JOB, "trigger": "visit"}, {"job": JOB, "trigger": "button"},
                           {"job": "chapters", "trigger": "visit"}], "visit")), 1),
        (cites_task({"cites": [{"type": "task", "id": "t1"}]}, "t1"), True),
        (cites_task({"cites": [{"type": "build", "id": "t1"}]}, "t1"), False),
        (cites_task(None, "t1"), False),
        (first_failure(STEPS, {"job-on": (True, ""), "first-visit": (False, ""), "built": (False, "")}),
         "first-visit"),
        (first_failure(STEPS, {"job-on": (True, "")}), None),
        ("T00:00:00" in local_midnight(), True),
    ]
    bad = [(i, got, want) for i, (got, want) in enumerate(cases) if got != want]
    for i, got, want in bad:
        print(f"self-test case {i}: got {got!r}, wanted {want!r}")
    print("self-test:", "PASS" if not bad else "FAIL", f"({len(cases) - len(bad)}/{len(cases)})")
    return not bad


# --------------------------------------------------------------------------- the Hub


def api(method, path, body=None, timeout=240, key=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + (key or KEY), "Content-Type": "application/json"}, method=method)
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


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def rw(sql, args=()):
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        cur = con.execute(sql, args)
        con.commit()
        return cur.rowcount
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


def port_answers(port):
    with socket.socket() as sock:
        sock.settimeout(2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start_hub(port, log_path):
    DB.parent.mkdir(parents=True, exist_ok=True)
    # The drive may run inside an agent turn on another Hub: its HUB_URL, credential and tool-server
    # bin would reach this Hub's agents, whose tool calls would then go to that other Hub.
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if "tool-server" not in p.replace("\\", "/"))
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(port), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    if not poll(lambda: api("GET", "/projects", timeout=5)[0] == 200, 120):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        sys.exit(f"setup error: the Hub did not come up; see {log_path}")
    print(f"started a Hub on :{port} from {REPO / 'hub'} on {DB}", flush=True)
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    print("stopped the drive's Hub", flush=True)


def _now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def hold(pid, agent):
    """A running run of *agent*, so the flow hands it no review; the operator is the approver."""
    run_id = "run-glance-" + secrets.token_hex(4)
    token = "aw_run_" + secrets.token_urlsafe(24)
    rw("insert into runs (id, project_id, agent, status, started_at, initiator, turn_depth, "
       "capability_token_hash) values (?, ?, ?, 'running', ?, 'operator', 0, ?)",
       (run_id, pid, agent, _now(), hashlib.sha256(token.encode("utf-8")).hexdigest()))
    return run_id


def release(run_id):
    rw("update runs set status='completed', ended_at=? where id=?", (_now(), run_id))


def as_agent(pid, agent, method, path, body=None):
    """One agent-plane call as *agent*, through a run of its own seeded for the call, as the Hub
    tests seed one; what was queued for the agent meanwhile is withdrawn so its end starts no turn."""
    run_id = "run-glance-" + secrets.token_hex(4)
    token = "aw_run_" + secrets.token_urlsafe(24)
    rw("insert into runs (id, project_id, agent, status, started_at, initiator, turn_depth, "
       "capability_token_hash) values (?, ?, ?, 'running', ?, 'autonomous', 0, ?)",
       (run_id, pid, agent, _now(), hashlib.sha256(token.encode("utf-8")).hexdigest()))
    try:
        return api(method, "/agent-actions" + path, body, key=token)
    finally:
        rw("update inbound_queue_entries set state='withdrawn', withdrawn_at=? where project_id=? and "
           "agent=? and delivered_at is null and withdrawn_at is null", (_now(), pid, agent))
        release(run_id)


def document_payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": TITLE,
        "summary": f"{TITLE}, a document for the Overview-at-a-glance drive.", "problem": "The drive needs one.",
        "scope": {"in_scope": ["the drive"], "non_goals": ["anything else"]},
        "requirements": [{"key": "r1", "modal": "MUST", "statement": "The repository MUST hold glance.txt."}],
        "acceptance_criteria": [{"key": "has-glance", "requirement": "r1", "given": "the repository",
                                 "when": "it is read", "then": "glance.txt says glance",
                                 "how_to_check": "read it", "checked_by": "agent"}],
        "tasks": [{"key": "t1", "title": TASK_TITLE, "requirements": ["r1"], "files": ["glance.txt"],
                   "depends_on": [],
                   "description": ("Create the file glance.txt at the repository root holding the single "
                                   "line `glance`. Change nothing else. Record evidence for the requirement "
                                   "with record_evidence, then complete the task.")}],
        "delivery": {"mode": "flow", "agent": BUILDER, "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *",  # once a year: the drive fires the flow itself
                     "reasons": {"mode": "The drive.", "agent": "The default builder."}},
    }


def make_build(base, pid):
    quoted = urllib.parse.quote(DOC)
    code, out = api("POST", f"{base}/project/documents", {"title": TITLE, "kind": "change-spec", "path": DOC})
    if code != 201:
        raise Setup(f"create {DOC}: {code} {str(out)[:300]}")
    code, out = api("PUT", f"{base}/project/documents/{DOC}/content", {"document": document_payload()})
    if code != 200:
        raise Setup(f"save {DOC}: {code} {str(out)[:600]}")
    code, out = as_agent(pid, CHECKER, "POST", "/spec/documents/confirm-criteria",
                         {"path": DOC, "confirmations": [{"criterion": "has-glance", "kind": "new"}]})
    if code != 200:
        raise Setup(f"confirm {DOC}'s criterion: {code} {str(out)[:300]}")
    _, read = api("GET", f"{base}/project/spec?path={quoted}")
    code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                    {"reason": "drive", "approve_anyway": True, "content_version": read.get("content_version")})
    if code != 200:
        raise Setup(f"approve {DOC}: {code} {str(out)[:600]}")
    code, out = api("POST", f"{base}/project/documents/build?path={quoted}",
                    {"driver": "flow", "level": "reviewed", "builder": BUILDER, "checker": CHECKER,
                     "landing": "main"})
    if code != 200:
        raise Setup(f"build {DOC}: {code} {str(out)[:800]}")
    (doc_id,) = ro("select id from spec_documents where project_id=? and path=?",
                   (pid, DOC))[0]
    task_id, loop_id = ro("select id, loop_id from tasks where spec_document_id=?", (doc_id,))[0]
    (job_id,) = ro("select job_id from loops where id=?", (loop_id,))[0]
    build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    return task_id, job_id, build_id


def status_of(task_id):
    return ro("select status from tasks where id=?", (task_id,))[0][0]


def live_runs(pid):
    return ro("select id from runs where project_id=? and status in ('running', 'queued', 'starting') "
              "and id not like 'run-glance-%'", (pid,))


def work(base, pid, job_id, task_id):
    """Fire the flow until a real turn finishes *task_id*, re-firing only while nothing runs."""
    end = time.time() + TURN_WAIT
    while time.time() < end and status_of(task_id) not in DONE:
        if not live_runs(pid):
            code, out = api("POST", f"{base}/jobs/{job_id}/run")
            print(f"  fired {job_id}: {code} {str(out)[:120]}", flush=True)
        time.sleep(20)
    if status_of(task_id) not in DONE:
        raise Setup(f"no real turn finished the task in {TURN_WAIT}s ({status_of(task_id)})")
    poll(lambda: not live_runs(pid), 180)


def approve(base, task_id):
    code, rows = api("GET", f"{base}/project/spec/evidence?review_state=awaiting")
    rows = rows.get("evidence", []) if code == 200 and isinstance(rows, dict) else []
    for row in rows:
        api("POST", f"{base}/project/spec/evidence/{row['id']}/decision",
            {"decision": "accepted", "reason": "the drive's operator"})
    code, out = api("POST", f"{base}/tasks/{task_id}/land")
    if code != 200 or status_of(task_id) != "approved":
        raise Setup(f"the operator's approval: {code} {status_of(task_id)} {str(out)[:300]}")


def landing_state(task_id):
    rows = ro("select state from task_landings where task_id=? order by order_key desc, id desc limit 1",
              (task_id,))
    return rows[0][0] if rows else None


def overview(base):
    query = urllib.parse.urlencode({"day_start": local_midnight(), "days": 7})
    return api("GET", f"{base}/overview?{query}")


def firings(base):
    code, out = api("GET", f"{base}/manager/activity?job={JOB}")
    return out.get("firings", []) if code == 200 and isinstance(out, dict) else []


def table_exists(name):
    return bool(ro("select 1 from sqlite_master where type='table' and name=?", (name,)))


# --------------------------------------------------------------------------- the browser


class Browser:
    """One operator session in Chromium, recording the page's POSTs to /overview/visit."""

    def __init__(self, play, pid):
        self.pid = pid
        self.visits: list[tuple[int, object]] = []
        self.context = play.chromium.launch_persistent_context(
            str(SCRATCH / "browser-profile"), viewport={"width": 1440, "height": 940})
        self.context.add_init_script(
            f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));"
            f"localStorage.setItem('agentweave-selected-project', {pid!r});")
        self.page = self.context.new_page()
        self.page.on("response", self._seen)

    def _seen(self, response):
        if response.request.method == "POST" and response.url.split("?")[0].endswith("/overview/visit"):
            try:
                body = response.json()
            except Exception:  # noqa: BLE001 -- a body that is not JSON is recorded as text
                body = response.text()[:300]
            self.visits.append((response.status, body))

    def open(self, query):
        self.page.goto(f"{HUB}/?project={self.pid}&{query}", wait_until="domcontentloaded")
        self.page.wait_for_timeout(3500)

    def shot(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)

    def tab(self, name):
        for locator in (self.page.get_by_role("tab", name=name, exact=True),
                        self.page.get_by_role("button", name=name, exact=True)):
            if locator.count():
                return locator.first
        return None

    def close(self):
        self.context.close()


def section_by_heading(page, pattern):
    """The `section` (else the nearest container) whose heading matches *pattern*."""
    heading = page.get_by_role("heading", name=pattern)
    if not heading.count():
        return None
    return heading.first.locator("xpath=ancestor::section[1]")


def note_box(page):
    box = page.get_by_test_id("overview-note")
    if box.count():
        return box.first
    return section_by_heading(page, re.compile(r"\bnote\b", re.I))


# --------------------------------------------------------------------------- the scenario


def arrange(state):
    root = SCRATCH / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A throwaway project for the Overview-at-a-glance drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"glance-{STAMP}"})
    if code not in (200, 201):
        raise Setup(f"the project opens: {code} {project}")
    pid = project["id"]
    base = f"/projects/{pid}"
    state.update(pid=pid, base=base)
    code, out = api("PUT", f"{base}/settings", {"main_branch": "main"})
    if code != 200:
        raise Setup(f"the project's main branch: {code} {str(out)[:300]}")
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    if code not in (200, 201):
        raise Setup(f"the Haiku runner: {code} {haiku}")
    state["runner"] = haiku["id"]
    for name in (BUILDER, CHECKER):
        code, out = api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
        if code not in (200, 201):
            raise Setup(f"agent {name}: {code} {out}")
    state["task"], state["job"], state["build"] = make_build(base, pid)
    state["hold"] = hold(pid, CHECKER)
    print(f"project {pid} at {root}; task {state['task']}, build {state['build']}", flush=True)


def scenario(state, play):
    base, pid, task = state["base"], state["pid"], state["task"]

    # A1 -- the overview-note job on Haiku.
    code, out = api("PATCH", f"{base}/manager/jobs/{JOB}",
                    {"enabled": True, "runner_id": state["runner"], "model": HAIKU})
    step("job-on", code == 200, f"PATCH /manager/jobs/{JOB}: {code} {str(out)[:200]}")

    browser = Browser(play, pid)
    try:
        # A2 -- the first visit, made by the page itself.
        browser.open("tab=overview")
        browser.shot("1-first-visit")
        code, view = overview(base)
        visit = (view or {}).get("visit") if code == 200 and isinstance(view, dict) else None
        posted = browser.visits[:]
        first = posted[0][1] if posted and posted[0][0] == 200 and isinstance(posted[0][1], dict) else None
        ok = bool(first) and first.get("previous_at") is None and bool((visit or {}).get("last_at"))
        state["first_at"] = (visit or {}).get("last_at")
        step("first-visit", ok, f"the page's POST /overview/visit answered {posted or 'nothing (never posted)'}; "
             f"GET /overview: {code} visit={visit if code == 200 else str(view)[:160]}")

        # A3 -- the task is built by a real turn, approved, and lands on main.
        try:
            work(base, pid, state["job"], task)
            approve(base, task)
            landed = poll(lambda: landing_state(task) == "landed", LANDING_WAIT, every=3)
            step("built", landed, f"task {task} is {status_of(task)}, its landing {landing_state(task)}")
        except Setup as exc:
            step("built", False, f"setup: {exc}")

        # A4 -- the visit clock set back, so the next open starts a new visit.
        if table_exists("overview_visits"):
            changed = rw("update overview_visits set last_visit_at = strftime('%Y-%m-%d %H:%M:%f', "
                         f"last_visit_at, '-{SET_BACK_MINUTES} minutes') where project_id=?", (pid,))
            rows = ro("select last_visit_at from overview_visits where project_id=?", (pid,))
            state["first_at"] = rows[0][0] if rows else None
            step("clock-back", changed == 1, f"{changed} overview_visits row set back {SET_BACK_MINUTES} "
                 f"minutes, last_visit_at now {state['first_at']}")
        else:
            step("clock-back", False, "the database has no overview_visits table")

        # A5 -- the second visit, a new one, starts the note.
        before = len(browser.visits)
        browser.open("tab=overview")
        browser.shot("2-dashboard")
        posted = browser.visits[before:]
        second = posted[0][1] if posted and posted[0][0] == 200 and isinstance(posted[0][1], dict) else None
        ok = bool(second) and same_moment(second.get("previous_at"), state.get("first_at")) \
            and second.get("note_started") is True
        step("second-visit", ok, f"the page's POST /overview/visit answered {posted or 'nothing (never posted)'}; "
             f"wanted previous_at={state.get('first_at')} and note_started true")

        # A6 -- finished today: the route, the tile, the timeline.
        code, view = overview(base)
        finished = [f for f in ((view or {}).get("finished") or [])
                    if f.get("task_id") == task] if code == 200 and isinstance(view, dict) else []
        priced = bool(finished) and any(f.get(k) is not None for f in finished for k in ("usd", "tokens", "credits"))
        tile = browser.page.locator("[data-slot=overview-tile][aria-label^='Finished today']")
        tile_text = tile.first.inner_text() if tile.count() else ""
        rows = browser.page.locator("[data-slot=overview-activity]").filter(has_text=TASK_TITLE)
        row_text = rows.first.inner_text() if rows.count() else ""
        ok = (len(finished) == 1 and finished[0].get("outcome") == "landed" and priced
              and re.search(r"\b1 landed\b", tile_text) and DOLLARS.search(row_text))
        step("finished", ok, f"GET /overview: {code}, finished for the task {finished or str(view)[:160]}; "
             f"tile {tile_text.replace(chr(10), ' ')[:120]!r}; timeline row {row_text.replace(chr(10), ' ')[:120]!r}")

        # A7 -- the Briefing's since-you-last-looked.
        briefing = browser.tab("Briefing")
        if briefing is not None:
            briefing.click()
            browser.page.wait_for_timeout(1500)
        browser.shot("3-briefing")
        since = section_by_heading(browser.page, re.compile(r"since you last looked", re.I))
        since_text = since.inner_text() if since is not None and since.count() else ""
        visit = (view or {}).get("visit") if code == 200 and isinstance(view, dict) else None
        ok = (briefing is not None and TIME_WORDS.search(since_text) and TASK_TITLE in since_text
              and (ONE_FINISHED.search(since_text) or re.search(r"Landed\s*1\b", since_text))
              and same_moment((visit or {}).get("previous_at"), state.get("first_at")))
        step("since", ok, f"Briefing tab {'found' if briefing is not None else 'missing'}; since section "
             f"{since_text.replace(chr(10), ' ')[:200]!r}; visit {visit}")

        # A8 -- the note, written by the visit, with no press.
        def written():
            c, v = overview(base)
            return c == 200 and isinstance(v, dict) and (v.get("note") or {}).get("trigger") == "visit"

        poll(written, NOTE_WAIT if second and second.get("note_started") else 5, every=5)
        code, view = overview(base)
        note = (view or {}).get("note") if code == 200 and isinstance(view, dict) else None
        pressed = note_firings(firings(base), "button")
        if note:
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / "note.json").write_text(json.dumps(note, indent=2), encoding="utf-8")
        browser.open("tab=overview")
        if browser.tab("Briefing") is not None:
            browser.tab("Briefing").click()
            browser.page.wait_for_timeout(1500)
        browser.shot("4-note")
        box = note_box(browser.page)
        box_text = box.inner_text() if box is not None and box.count() else ""
        opened = False
        if box is not None and box.count():
            link = box.locator("a, button").filter(has_text=re.compile(re.escape(TASK_TITLE) + r"|OGDBT|glance", re.I))
            if link.count():
                link.first.click()
                opened = poll(lambda: browser.page.get_by_test_id(f"task-drawer-{task}").count() > 0, 10, every=1)
                browser.shot("5-note-link")
        ok = (bool(note) and note.get("trigger") == "visit" and bool(note.get("written_at"))
              and cites_task(note, task) and not pressed and TIME_WORDS.search(box_text) and opened)
        step("note", ok, f"GET /overview note={str(note)[:240]}; button firings {len(pressed)}; note box "
             f"{box_text.replace(chr(10), ' ')[:160]!r}; its task link opened the drawer: {opened}")

        # A9 -- the firing, on the route and in Settings > Manager.
        visits = note_firings(firings(base), "visit")
        has_cost, cost = firing_cost(visits[0]) if visits else (False, "none")
        ok_route = (len(visits) == 1 and visits[0].get("outcome") == "written"
                    and (visits[0].get("duration_ms") or 0) > 0 and has_cost)
        _, jobs = api("GET", f"{base}/manager/jobs")
        title = next((j.get("title") for j in (jobs or {}).get("jobs", []) if j.get("key") == JOB), None) \
            if isinstance(jobs, dict) else None
        browser.open("tab=environment&section=manager")
        browser.shot("6-manager")
        rows = browser.page.locator("[data-testid^=manager-firing-]")
        if title:
            rows = rows.filter(has_text=title)
        row_text = rows.first.inner_text() if title and rows.count() else ""
        ok_ui = bool(row_text) and re.search(r"Written", row_text) and re.search(r"\d", row_text)
        step("firing", ok_route and ok_ui, f"visit firings {[(f.get('outcome'), f.get('duration_ms'), f.get('usage')) for f in visits]} "
             f"(cost {cost}); job title {title!r}; history row {row_text.replace(chr(10), ' ')[:160]!r}")
    finally:
        browser.close()


# --------------------------------------------------------------------------- main


def main():
    global HUB, KEY, DB, SCRATCH
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true", help="check the drive's own logic only; no Hub")
    parser.add_argument("--hub", default="http://127.0.0.1:8010", help="a running Hub (default the trial :8010)")
    parser.add_argument("--db", default=str(TRIAL / "agentweave.db"), help="that Hub's database")
    parser.add_argument("--own-hub", action="store_true", help="start a Hub from this checkout instead")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    proc = None
    SCRATCH.mkdir(parents=True, exist_ok=True)
    if args.own_hub:
        port = int(os.environ.get("AW_DRIVE_PORT") or 8023)
        if port in (8000, 8010):
            sys.exit("REFUSING: --own-hub never runs on :8000 or :8010")
        if port_answers(port):
            sys.exit(f"REFUSED: :{port} already answers (F1121). Pick another AW_DRIVE_PORT.")
        HUB, KEY, DB = f"http://127.0.0.1:{port}", "aw_live_" + secrets.token_hex(16), SCRATCH / "hub.db"
        proc = start_hub(port, SCRATCH / "hub.log")
    else:
        HUB = args.hub.rstrip("/")
        if HUB.endswith(":8000"):
            sys.exit("REFUSING: :8000 is the operator's Hub")
        key_file = TRIAL / "bootstrap-key.txt"
        KEY = os.environ.get("AW_KEY") or (key_file.read_text(encoding="utf-8").strip() if key_file.exists() else "")
        DB = pathlib.Path(args.db)
        if not KEY or not DB.exists():
            sys.exit(f"setup error: no key (AW_KEY or {key_file}) or no database at {DB}")
        if api("GET", "/projects", timeout=10)[0] != 200:
            sys.exit(f"setup error: {HUB} does not answer GET /projects with this key")
    state, setup_error = {}, None
    try:
        from playwright.sync_api import sync_playwright

        arrange(state)
        with sync_playwright() as play:
            scenario(state, play)
    except Setup as exc:
        setup_error = str(exc)
        print(f"SETUP: {exc}", flush=True)
    finally:
        if state.get("hold"):
            release(state["hold"])
        if state.get("build") and state.get("base"):
            api("POST", f"{state['base']}/project/builds/{state['build']}/stop")
        if state.get("base"):
            api("PATCH", f"{state['base']}/manager/jobs/{JOB}", {"enabled": False})
        if proc is not None:
            stop_hub(proc)
    print("\n== drive_baseline")
    first = first_failure(STEPS, results)
    reached = bool(results) and setup_error is None
    failed = first is not None
    if not reached:
        detail = f"setup: {setup_error or 'nothing ran'}"
    elif failed:
        detail = (f"first failing assertion {first}: {results[first][1][:600]} | steps "
                  + ", ".join(f"{n}={'pass' if results[n][0] else 'FAIL'}" for n in STEPS if n in results))
    else:
        detail = "all nine assertions passed: " + ", ".join(STEPS)
    print(f"check {KEY_CHECK}: reached={'yes' if reached else 'no'} "
          f"failed_at_assertion={'yes' if reached and failed else 'no'} -- {detail}")
    print(f"output: {OUT}")
    sys.exit(1 if failed or not reached else 0)


if __name__ == "__main__":
    main()
