"""Acceptance drive for `every-overview-control-lands-where-you-can-act-on-it` (EOCLW-1), 2026-11-28:
every acceptance criterion of FR-1..FR-7, written failing first, before the Hub's dismissable needs
and operator stall end (EOCLW-2), the Needs you page (EOCLW-3) and the tidied Overview (EOCLW-4) are
built. Their checkers run it green and fix only the drive, never the behaviour.

Starts its own Hub from THIS checkout's `hub/` on a scratch port and a fresh database (default :8027
and a temp file; AW_DRIVE_PORT / AW_DRIVE_DB move them), on 127.0.0.1, and refuses a port something
already answers on. Never :8000 or :8010: a seeded stall or question in the project whose build is
running would be acted on by its mender and its agents. It is a drive, not part of the test suite.

No real agent turn is run. Every waiting item is arranged in the database the Hub reads, through
the Hub's own models (so their defaults apply), the roadmap through the Hub's document routes; every
close is then made by the page, and every verdict read back through the Hub's routes.

Three projects, each a throwaway git repository on `main`:

  A  one need of every kind: main failing (a check that could not run), approved work that did not
     land (an integration_failed stall), a stall on a task (review_unstaffed, so it has remedies), a
     stall with neither task nor conversation, two questions asked in a conversation, a review the
     operator holds, a pending permission request, a check that could not run, a next-slice offer
     (it carries no waiting time), a reopening warning, a main-moved notice; and a profile whose
     queue is held by the hop budget, so the Profile status chip shows.
  C  a question and two pending permission requests: one of them is decided through the route after
     the page loaded and before Dismiss all, so its close is refused.
  D  exactly six dismissable items (question, permission request, stall, main-moved notice,
     next-slice offer, reopening warning) and a review.

The checks, in the order they run (A's read-only ones first, its closing ones after, then C, D):
  closable-per-kind, needs-page-lists-all, no-epoch, tiles-inert, stall-opens-with-remedies,
  answer-opens-conversation, mark-seen-in-place, try-again-in-place, dismiss-closes-question,
  stall-ended-by-operator, dismiss-all-partial, dismiss-all-asks-first, dismiss-all-closes-every-kind.

The page contract the drive probes (EOCLW-3/4 may rename these; their checker then fixes the drive):
  * the Overview's link to the page is `[data-testid=overview-needs-link]` (or a link named "Needs
    you"); today's nearest control, the Needs you tile, is clicked when it is missing, which is what
    an operator does now, and the check fails at its own assertion on where it lands;
  * the page is `[data-testid=needs-page]`, at an address of its own; each item is
    `[data-testid=need-row][data-need-id=<the need's id in GET /overview>]`, holding
    `[data-testid=need-open]` (the row body), its verb as a button of its own named by the verb
    ("Mark seen", "Try again", "Answer", ...), `[data-testid=need-dismiss]` where the Hub says it is
    dismissable, and a refusal or failure in words in `[data-testid=need-reason]`;
  * `[data-testid=needs-dismiss-all]` opens a confirmation (role dialog or alertdialog) naming the
    count, with `[data-testid=needs-dismiss-all-confirm]` / `[data-testid=needs-dismiss-all-cancel]`;
    after it, `[data-testid=needs-dismiss-summary]` says how many closed and how many could not;
  * GET /projects/{id}/overview gives each need `dismissable` (bool), and the operator's stall end
    records the operator (`ended_by == "operator"`, or the outcome detail saying so);
  * a stall on a task opens the task with `[data-testid=stall-remedies-<stall id>]` and the reason;
  * the Overview's verbs on today's code are spans inside the row's button: a "press" clicks the
    element whose text is the verb, which is the same click an operator makes.

Every control click is logged as `click <tab> <control>: url=<path?query> heading=<h1/h2> named=<yes|no>`.
Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. Screenshots go to testbed/overview-controls/<HHMMSS>/.

    py -3.11 scripts/drive/overview_controls.py                  # own Hub on :8027
    py -3.11 scripts/drive/overview_controls.py --only tiles-inert,no-epoch
    py -3.11 scripts/drive/overview_controls.py --keep           # leave the Hub up afterwards
    py -3.11 scripts/drive/overview_controls.py --self-test      # the drive's own logic, no Hub
"""

import argparse
import datetime
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
PORT = int(os.environ.get("AW_DRIVE_PORT") or 8027)
if PORT in (8000, 8010):
    sys.exit("REFUSING: this drive starts its own Hub and never runs on :8000 or :8010")
HUB = f"http://127.0.0.1:{PORT}"
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "drive-overview-controls" / STAMP
DB = pathlib.Path(os.environ.get("AW_DRIVE_DB") or SCRATCH / "hub.db")
OUT = REPO / "testbed" / "overview-controls" / STAMP
KEY = "aw_live_" + secrets.token_hex(16)
HAIKU = "claude-haiku-4-5-20251001"
ORDER = ["closable-per-kind", "needs-page-lists-all", "no-epoch", "tiles-inert",
         "stall-opens-with-remedies", "answer-opens-conversation", "mark-seen-in-place",
         "try-again-in-place", "dismiss-closes-question", "stall-ended-by-operator",
         "dismiss-all-partial", "dismiss-all-asks-first", "dismiss-all-closes-every-kind"]
# FR-7's list.
DISMISSABLE = {"question": True, "permission": True, "stall": True, "main_moved": True, "offer": True,
               "reopening": True, "review": False, "merge": False, "check": False, "main": False}
VERBS = ("Mark seen", "Try again", "Answer", "Review", "Allow or deny", "Draft", "Open", "Open checks",
         "Open the build")
TILE_LABELS = ("Needs you", "Running", "Finished today", "Spend", "Main and checks")
TIME_WORDS = re.compile(r"\b(\d+\s?(s|m|h|d|w|min|mins|hours?|days?)\b|ago\b|just now|"
                        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s\d{1,2}|1970)", re.I)

checks = {}  # key -> (reached, failed, detail)
clicks = []  # the click log


class Setup(Exception):
    """Something the drive depends on could not be arranged; not a verdict on the product."""


class NotReached(Exception):
    """A check could not get as far as its own assertion."""


def record(key, reached, ok, detail):
    checks[key] = (reached, not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)


# --------------------------------------------------------------------------- the drive's own logic


def dismissable_verdict(needs):
    """[(need id, kind, got, wanted)] for each need whose `dismissable` is not FR-7's answer."""
    wrong = []
    for need in needs:
        wanted = DISMISSABLE.get(need.get("kind"))
        got = need.get("dismissable", "absent")
        if wanted is None or got is not wanted:
            wrong.append((need.get("id"), need.get("kind"), got, wanted))
    return wrong


def shows_a_time(text):
    return bool(TIME_WORDS.search(text or ""))


def path_of(url):
    parts = urllib.parse.urlsplit(url)
    return parts.path + ("?" + parts.query if parts.query else "")


def same_place(before, after):
    """Two URLs name the same page: path and query alike, a fragment aside."""
    return path_of(before) == path_of(after)


def strip_flag(body):
    """GET /overview's body with every need's `dismissable` taken away (an older Hub)."""
    body = json.loads(json.dumps(body))
    for need in body.get("needs") or []:
        need.pop("dismissable", None)
    return body


def summary_counts(text):
    """(closed, could not) read from Dismiss all's summary, or None where it says no number."""
    closed = re.search(r"(\d+)\s+(?:items?\s+)?(?:were\s+)?closed", text or "", re.I)
    refused = re.search(r"(\d+)\s+(?:items?\s+)?(?:could\s*n[o']t|couldn't|were\s+refused|refused)",
                        text or "", re.I)
    return (int(closed.group(1)) if closed else None, int(refused.group(1)) if refused else None)


def self_test():
    needs = [{"id": "q", "kind": "question", "dismissable": True},
             {"id": "r", "kind": "review", "dismissable": False},
             {"id": "s", "kind": "stall"}]
    assert dismissable_verdict(needs) == [("s", "stall", "absent", True)]
    assert dismissable_verdict([{"id": "x", "kind": "review", "dismissable": True}])
    assert not shows_a_time("Draft the next slice: Manager indicators")
    assert shows_a_time("Jan 1 1970") and shows_a_time("12m") and shows_a_time("3 hours ago")
    assert same_place("http://h/?project=p&tab=overview", "http://h/?project=p&tab=overview#x")
    assert not same_place("http://h/?project=p&tab=overview", "http://h/?project=p&tab=tasks")
    body = {"needs": [{"id": "a", "dismissable": True}]}
    assert "dismissable" not in strip_flag(body)["needs"][0] and body["needs"][0]["dismissable"]
    assert summary_counts("2 closed, 1 could not be closed") == (2, 1)
    assert summary_counts("Closed 3 items") == (None, None)
    assert summary_counts("3 items closed; 1 couldn't") == (3, 1)
    print("self-test passed")


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
        text = exc.read().decode(errors="replace")[:4000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        return 0, str(exc)


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def poll(fn, secs, every=1.0):
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


def hub_env():
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if "tool-server" not in p.replace("\\", "/"))
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    return env


def start_hub(log_path):
    if port_answers():
        sys.exit(f"setup error: something already answers on :{PORT}; set AW_DRIVE_PORT")
    DB.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=hub_env(), stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    if not poll(lambda: api("GET", "/projects", timeout=5)[0] == 200, 120, 2):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        sys.exit(f"setup error: the Hub did not come up; see {log_path}")
    print(f"started a Hub on :{PORT} from {REPO / 'hub'} on {DB}", flush=True)
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    print(f"stopped the Hub on :{PORT}", flush=True)


# The seeding runs in a child process with the Hub's models on the scratch database, so the
# drive's own process never imports the Hub (and its settings) at all.
SEED_CHILD = r"""
import json, sys
from datetime import datetime, timedelta, timezone
import sqlalchemy as sa
from sqlalchemy.orm import Session
import hub.db.models as m
rows, db = json.loads(sys.stdin.read()), sys.argv[1]
engine = sa.create_engine("sqlite:///" + db, connect_args={"timeout": 30})
now = datetime.now(timezone.utc)
def value(v):
    if isinstance(v, dict) and set(v) == {"ago_minutes"}:
        return now - timedelta(minutes=v["ago_minutes"])
    return v
with Session(engine) as s:
    for row in rows:
        model = getattr(m, row.pop("_model"))
        s.add(model(**{k: value(v) for k, v in row.items()}))
        s.flush()
    s.commit()
print("seeded", len(rows))
"""

# The stall detector's own call, made again for a stall's cause and task (stall-ended-by-operator).
DETECT_CHILD = r"""
import asyncio, json, sys
from hub import stalls
from hub.db.engine import async_session_factory
a = json.loads(sys.argv[1])
async def main():
    async with async_session_factory() as db:
        stall, new = await stalls.record(db, a["project"], cause=a["cause"], subject=a["subject"],
                                         text=a["text"], task_id=a.get("task_id"))
        print(json.dumps({"id": stall.id, "new": new, "ended_at": str(stall.ended_at)}))
asyncio.run(main())
"""


def seed(rows):
    out = subprocess.run(["py", "-3.11", "-c", SEED_CHILD, DB.as_posix()], input=json.dumps(rows),
                         cwd=str(REPO / "hub"), env=hub_env(), capture_output=True, text=True)
    if out.returncode != 0:
        raise Setup(f"seeding failed: {out.stderr[-1500:]}")


def detect_again(project, cause, subject, text, task_id):
    out = subprocess.run(
        ["py", "-3.11", "-c", DETECT_CHILD, json.dumps({"project": project, "cause": cause,
                                                         "subject": subject, "text": text,
                                                         "task_id": task_id})],
        cwd=str(REPO / "hub"), env=hub_env(), capture_output=True, text=True)
    if out.returncode != 0:
        raise NotReached(f"the detection pass could not run: {out.stderr[-800:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def ago(minutes):
    return {"ago_minutes": minutes}


# --------------------------------------------------------------------------- the fixture


class Project:
    def __init__(self, name):
        self.name = name
        self.root = SCRATCH / name
        self.pid = ""
        self.base = ""
        self.ids = {}  # what each criterion acts on

    def open(self):
        self.root.mkdir(parents=True)
        git(self.root, "init", "-q", "-b", "main")
        (self.root / "README.md").write_text(f"Overview controls drive {self.name}\n", encoding="utf-8")
        (self.root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-q", "-m", "seed")
        code, out = api("POST", "/projects/open", {"path": str(self.root),
                                                   "name": f"ov-{self.name}-{STAMP}"})
        if code not in (200, 201):
            raise Setup(f"project {self.name}: {code} {out}")
        self.pid = out["id"]
        self.base = f"/projects/{self.pid}"
        api("PATCH", self.base, {"main_branch": "main"})
        code, runner = api("POST", f"{self.base}/runners", {"name": "Haiku", "cli": "claude",
                                                            "model": HAIKU})
        if code not in (200, 201):
            raise Setup(f"runner {self.name}: {code} {runner}")
        for agent in ("Asker", "Builder"):
            code, out = api("POST", f"{self.base}/agents", {"name": agent, "runner_id": runner["id"]})
            if code not in (200, 201):
                raise Setup(f"agent {agent}: {code} {out}")
        return self

    def doc(self, kind, title, extra):
        path = f"spec/{'roadmaps' if kind == 'roadmap' else 'changes'}/{self.name.lower()}-" \
               f"{re.sub(r'[^a-z]+', '-', title.lower()).strip('-')}/spec.json"
        code, out = api("POST", f"{self.base}/project/documents", {"title": title, "kind": kind,
                                                                   "path": path})
        if code != 201:
            raise Setup(f"create {path}: {code} {str(out)[:300]}")
        body = {"schema_version": 1, "kind": kind, "title": title,
                "summary": f"{title}, a drive fixture.", "problem": "The drive needs one.",
                "scope": {"in_scope": ["the drive"], "non_goals": ["anything else"]}, **extra}
        code, out = api("PUT", f"{self.base}/project/documents/{path}/content", {"document": body})
        if code != 200:
            raise Setup(f"save {path}: {code} {str(out)[:600]}")
        con = sqlite3.connect(DB.as_posix(), timeout=30)
        try:
            con.execute("update spec_documents set phase='approved', first_approved_at=? "
                        "where project_id=? and path=?",
                        (datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
                         self.pid, path))
            con.commit()
        finally:
            con.close()
        doc_id = ro("select id from spec_documents where project_id=? and path=?", (self.pid, path))[0][0]
        return path, doc_id

    def conversation(self, agent, title):
        conv = f"conv-{secrets.token_hex(6)}"
        seed([{"_model": "Conversation", "id": conv, "project_id": self.pid, "agent": agent,
               "title": title, "title_set_by_operator": True}])
        return conv

    # One of each kind; `kinds` names which to arrange.
    def arrange(self, kinds, questions=1, permissions=1):
        p, rows, ids = self.pid, [], self.ids
        conv = self.conversation("Asker", "Asker's questions")
        ids["conversation"] = conv
        tag = secrets.token_hex(3)
        if "question" in kinds:
            ids["questions"] = []
            # The run that asked: only a question a run asked docks in its conversation's composer.
            run = f"run-asker-{self.name.lower()}-{tag}"
            rows.append({"_model": "Run", "id": run, "project_id": p, "agent": "Asker",
                         "status": "completed", "initiator": "operator", "turn_depth": 0,
                         "conversation_id": conv, "started_at": ago(35), "ended_at": ago(29)})
            for i in range(questions):
                qid = f"q-{self.name}-{i}-{tag}"
                ids["questions"].append(qid)
                rows.append({"_model": "Question", "id": qid, "project_id": p, "from_agent": "Asker",
                             "question": f"Question {i + 1} for {self.name}: which way, {tag}?",
                             "header": "Which way", "options": [{"label": "Left", "description": "l"},
                                                                {"label": "Right", "description": "r"}],
                             "conversation_id": conv, "created_by_run_id": run,
                             "created_at": ago(30 + i)})
        if "permission" in kinds:
            ids["permissions"] = []
            for i in range(permissions):
                rid = f"perm-{self.name}-{i}-{tag}"
                ids["permissions"].append(rid)
                rows.append({"_model": "PermissionRequest", "id": rid, "project_id": p,
                             "agent": "Builder", "tool_name": f"Bash{i + 1}", "status": "pending",
                             "conversation_id": conv, "created_at": ago(20 + i)})
        if "stall" in kinds:
            task = f"task-stalled-{self.name.lower()}-{tag}"
            ids["stall_task"] = task
            ids["stall"] = f"stall-task-{self.name.lower()}-{tag}"
            ids["stall_reason"] = f"Nobody could check {self.name}'s work ({tag})"
            rows += [{"_model": "Task", "id": task, "project_id": p, "title": f"Stalled work {tag}",
                      "status": "completed", "assignee": "Builder", "builder": "Builder"},
                     {"_model": "Stall", "id": ids["stall"], "project_id": p,
                      "key": f"review_unstaffed:{task}", "cause": "review_unstaffed",
                      "reason": ids["stall_reason"], "task_id": task, "first_seen_at": ago(50)}]
        if "lone_stall" in kinds:
            ids["lone_stall"] = f"stall-lone-{self.name.lower()}-{tag}"
            ids["lone_reason"] = f"The loop stopped moving and names no task ({tag})"
            rows.append({"_model": "Stall", "id": ids["lone_stall"], "project_id": p,
                         "key": f"no_progress:{tag}", "cause": "no_progress",
                         "reason": ids["lone_reason"], "first_seen_at": ago(55)})
        if "review" in kinds:
            task = f"task-review-{self.name.lower()}-{tag}"
            ids["review_task"] = task
            rows += [{"_model": "Task", "id": task, "project_id": p, "title": f"Review me {tag}",
                      "status": "under_review", "assignee": "user", "builder": "Builder"},
                     {"_model": "TaskTransition", "id": f"ttr-{tag}-{self.name}", "project_id": p,
                      "task_id": task, "from_status": "completed", "to_status": "under_review",
                      "actor_kind": "operator", "created_at": ago(40)}]
        if "merge" in kinds:
            task = f"task-merge-{self.name.lower()}-{tag}"
            ids["merge_task"] = task
            rows += [{"_model": "Task", "id": task, "project_id": p, "title": f"Merge me {tag}",
                      "status": "approved", "assignee": "Builder", "builder": "Builder"},
                     {"_model": "Stall", "id": f"stall-merge-{tag}", "project_id": p,
                      "key": f"integration_failed:{task}", "cause": "integration_failed",
                      "reason": "Approved work failed to merge", "task_id": task,
                      "first_seen_at": ago(5)}]
        if "check" in kinds:
            rows += [{"_model": "Task", "id": f"task-checked-{tag}", "project_id": p,
                      "title": "Checked", "status": "approved"},
                     {"_model": "TaskCheckRun", "id": f"tcr-{tag}", "project_id": p,
                      "task_id": f"task-checked-{tag}", "main_sha": "b" * 40, "target_shas": [],
                      "state": "failed", "results": [{"name": "hub-ui", "outcome": "could_not_run",
                                                      "missing_program": "eslint"}],
                      "started_at": ago(10), "ended_at": ago(10)}]
        if "main_moved" in kinds:
            ids["notice"] = f"mn-{self.name.lower()}-{tag}"
            rows.append({"_model": "MainNotice", "id": ids["notice"], "project_id": p,
                         "branch": "main", "old_tip": "a" * 40, "new_tip": "c" * 40, "commits": [],
                         "created_at": ago(15)})
        if "hop" in kinds:
            rows.append({"_model": "InboundQueueEntry", "id": f"qe-hop-{tag}", "project_id": p,
                         "agent": "Builder", "origin_type": "agent", "origin_agent": "Asker",
                         "content": "Held past the hop budget", "hop_depth": 99,
                         "conversation_id": conv})
        seed(rows)
        if "offer" in kinds:
            ids["roadmap"], _ = self.doc("roadmap", f"Roadmap {self.name} {tag}", {
                "slices": [{"key": "s1", "title": f"First slice {tag}", "intent": "It works.",
                            "done": "It is shown.", "builds_after": []}],
                "requirements": [], "acceptance_criteria": [], "tasks": []})
        if "reopening" in kinds:
            path, doc_id = self.doc("change-spec", f"Reopened change {self.name} {tag}", {
                "requirements": [{"key": "r1", "modal": "MUST", "statement": "It MUST hold."}],
                "acceptance_criteria": [{"key": "ok", "requirement": "r1", "given": "x", "when": "y",
                                         "then": "z", "how_to_check": "read", "checked_by": "agent"}],
                "tasks": []})
            ids["build"] = f"build-{secrets.token_hex(6)}"
            at = datetime.datetime.now(datetime.timezone.utc)
            seed([{"_model": "Build", "id": ids["build"], "project_id": p, "document_id": doc_id,
                   "state": "running", "driver": "flow", "level": "reviewed", "builders": [],
                   "reviewers": [], "reopenings": [{
                       "at": (at - datetime.timedelta(minutes=8)).isoformat(),
                       "finished_at": (at - datetime.timedelta(hours=3)).isoformat(),
                       "finished_ago": "3 hours", "tasks": []}]}])
        return self

    def overview(self):
        code, body = api("GET", f"{self.base}/overview")
        if code != 200:
            raise NotReached(f"GET /overview: {code} {str(body)[:300]}")
        return body

    def needs(self):
        return self.overview()["needs"]


# --------------------------------------------------------------------------- the page


def overview_url(project, tab=None):
    query = {"project": project.pid}
    if tab:
        query["overview"] = tab
    return f"{HUB}/?{urllib.parse.urlencode(query)}"


def session_script(project_id):
    return ("try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
            "localStorage.setItem('agentweave-selected-project', %s); } catch (e) {}"
            % (json.dumps(KEY), json.dumps(HUB), json.dumps(project_id)))


class Browser:
    def __init__(self, pw):
        self.browser = pw.chromium.launch()
        self.errors = []
        self.posts = []  # (method, url) of every write the page made

    def page(self, project):
        context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_init_script(session_script(project.pid))
        page = context.new_page()
        page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        page.on("request", lambda r: self.posts.append((r.method, r.url))
                if r.method in ("POST", "PUT", "PATCH", "DELETE") and "/api/v1/" in r.url else None)
        return page


def wait_settled(page, ms=600):
    """The page's own requests answered. Not `networkidle`: the Hub's event stream never idles."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(ms)


def open_overview(page, project, tab="dashboard"):
    """The project's Overview on *tab*, reached the way the operator does: the project opens on it,
    and the tab is chosen by its own tab button."""
    page.goto(f"{HUB}/?project={project.pid}", wait_until="domcontentloaded")
    wait_settled(page)
    overview_tab = page.get_by_role("tab", name=re.compile(r"^Overview$", re.I))
    if not page.locator("[data-slot=overview-live]").count() and overview_tab.count():
        overview_tab.first.click()
        wait_settled(page)
    if not page.locator("[data-slot=overview-live]").count():
        nav = page.get_by_role("button", name=re.compile(r"^Overview$", re.I))
        if nav.count():
            nav.first.click()
            wait_settled(page)
    if not page.locator("[data-slot=overview-live]").count():
        raise NotReached(f"the Overview did not open at {path_of(page.url)}")
    want = page.locator(f"#overview-tab-{tab}")
    if not want.count():
        raise NotReached(f"the Overview has no {tab} tab")
    want.first.click()
    wait_settled(page)
    page.locator("[data-slot=overview-live]").first.wait_for(timeout=15000)
    try:
        page.get_by_text("Loading the Overview").wait_for(state="hidden", timeout=15000)
    except Exception:  # noqa: BLE001
        pass
    return page.url


def main_area(page):
    main = page.locator("main")
    return main.first if main.count() else page.locator("body")


def heading(page):
    for sel in ("h1", "h2", "[role=heading]"):
        loc = main_area(page).locator(sel)
        for i in range(min(loc.count(), 4)):
            try:
                if loc.nth(i).is_visible():
                    return loc.nth(i).inner_text().strip()[:80]
            except Exception:  # noqa: BLE001
                continue
    return ""


def body_text(page):
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:  # noqa: BLE001
        return ""


def main_text(page):
    """The page's own content: the main area, without the rail and tabs around it."""
    try:
        return main_area(page).inner_text(timeout=5000)
    except Exception:  # noqa: BLE001
        return ""


def log_click(tab, control, page, named):
    line = (f"click {tab} {control!r}: url={path_of(page.url)} heading={heading(page)!r} "
            f"named={'yes' if named else 'no'}")
    clicks.append(line)
    print("  " + line, flush=True)


def shot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception:  # noqa: BLE001
        pass
    return path


def press_verb(row, verb):
    """Press *verb* on *row*: its own button where it has one, else the element whose text is the verb
    (today a span inside the row's button), the same click an operator makes."""
    button = row.get_by_role("button", name=re.compile(rf"^{re.escape(verb)}$"))
    if button.count():
        button.first.click()
        return "button"
    text = row.get_by_text(verb, exact=True)
    if text.count():
        text.first.click()
        return "text"
    raise NotReached(f"no {verb!r} on the row")


def overview_need_row(page, title_fragment):
    """The Overview Dashboard's row for a need, by a fragment of its title."""
    rows = page.locator("[data-testid=need-row], [data-slot=overview-need]")
    found = rows.filter(has_text=title_fragment)
    if not found.count():
        see_all = page.locator("[data-slot=overview-see-all]").filter(has_text=re.compile(r"see all", re.I))
        if see_all.count():
            see_all.first.click()
            page.wait_for_timeout(300)
            found = rows.filter(has_text=title_fragment)
    if not found.count():
        raise NotReached(f"no Overview row holds {title_fragment!r}")
    # A row is the item around its button, where the verb is a button of its own.
    return found.first


def open_needs_page(page, project):
    """Follow the Overview's Needs you link. Returns (how, url) — how is 'link' or 'tile'."""
    open_overview(page, project)
    link = page.locator("[data-testid=overview-needs-link]")
    if not link.count():
        link = page.get_by_role("link", name=re.compile(r"needs you", re.I))
    how = "link"
    if not link.count():
        # Today's nearest control: the Needs you tile.
        link = page.locator("[data-slot=overview-tile]").filter(has_text=re.compile(r"needs you", re.I))
        how = "tile"
    if not link.count():
        raise NotReached("the Overview has neither a Needs you link nor a Needs you tile")
    link.first.click()
    wait_settled(page)
    return how, page.url


def needs_page(page):
    return page.locator("[data-testid=needs-page]")


def page_rows(page):
    return page.locator("[data-testid=need-row]")


def page_row(page, need_id):
    return page.locator(f"[data-testid=need-row][data-need-id=\"{need_id}\"]")


def require_needs_page(page, project, what):
    how, url = open_needs_page(page, project)
    if not needs_page(page).count():
        return None, (f"{what}: the Needs you {how} opened {path_of(url)} "
                      f"(heading {heading(page)!r}), not a Needs you page")
    return url, None


def need_id(need):
    return need["id"]


# --------------------------------------------------------------------------- checks


def check_closable_per_kind(browser, a):
    needs = a.needs()
    kinds = sorted({n["kind"] for n in needs})
    missing = sorted(set(DISMISSABLE) - set(kinds))
    if missing:
        raise NotReached(f"the fixture lacks kinds {missing} (have {kinds})")
    wrong = dismissable_verdict(needs)
    detail = (f"{len(needs)} needs of {len(kinds)} kinds; "
              + ("each dismissable flag matches FR-7" if not wrong
                 else "wrong flags: " + ", ".join(f"{k}={g!r} (want {w})" for _, k, g, w in wrong[:10])))
    # The UI half: fed a Hub that says nothing, no Dismiss button anywhere.
    page = browser.page(a)
    body = a.overview()
    page.route(re.compile(r".*/api/v1/projects/[^/]+/overview(\?.*)?$"),
               lambda route: route.fulfill(status=200, content_type="application/json",
                                           body=json.dumps(strip_flag(body))))
    url, why = require_needs_page(page, a, "fed no flag")
    if why:
        ui_ok, ui = False, why
    else:
        buttons = page.locator("[data-testid=need-dismiss]").count() + page.locator(
            "[data-testid=needs-dismiss-all]").count() * 0
        ui_ok = buttons == 0 and page_rows(page).count() > 0
        ui = f"fed needs with no flag: {page_rows(page).count()} rows, {buttons} Dismiss buttons"
    page.unroute(re.compile(r".*/api/v1/projects/[^/]+/overview(\?.*)?$"))
    page.context.close()
    record("closable-per-kind", True, not wrong and ui_ok, f"{detail}; {ui}")


def check_needs_page_lists_all(browser, a):
    needs = a.needs()
    page = browser.page(a)
    how, url = open_needs_page(page, a)
    log_click("dashboard", f"Needs you {how}", page, bool(needs_page(page).count()))
    shot(page, "needs-page")
    if not needs_page(page).count():
        record("needs-page-lists-all", True, False,
               f"{len(needs)} waiting; the Needs you {how} opened {path_of(url)} "
               f"(heading {heading(page)!r}), not a Needs you page")
        page.context.close()
        return
    before = path_of(page.url)
    page.reload(wait_until="domcontentloaded")
    wait_settled(page, 1200)
    survived = needs_page(page).count() > 0 and path_of(page.url) == before
    listed = {page_rows(page).nth(i).get_attribute("data-need-id") for i in range(page_rows(page).count())}
    want = {need_id(n) for n in needs}
    lost = sorted(want - listed)
    page.go_back()
    wait_settled(page)
    back_ok = bool(page.locator("[data-slot=overview-live]").count())
    page.context.close()
    ok = survived and not lost and len(listed) == len(needs) and back_ok
    record("needs-page-lists-all", True, ok,
           f"page at {before}; reload kept it: {survived}; lists {len(listed)} of {len(needs)} "
           f"(GET /overview); missing {lost[:5]}; Back returned to the Overview: {back_ok}")


def check_no_epoch(browser, a):
    offer = next((n for n in a.needs() if n["kind"] == "offer"), None)
    if offer is None:
        raise NotReached("no next-slice offer is waiting")
    if offer.get("waiting_since") is not None:
        raise NotReached(f"the offer carries a waiting time ({offer['waiting_since']})")
    fragment = offer["title"].split(": ", 1)[-1]
    problems = []
    page = browser.page(a)
    for tab in ("dashboard", "briefing"):
        open_overview(page, a, tab)
        text = body_text(page)
        if "1970" in text:
            problems.append(f"{tab}: '1970' on the page")
        try:
            row = overview_need_row(page, fragment)
        except NotReached:
            row = page.locator("[data-slot=briefing-action]").filter(has_text=fragment)
        if not row.count():
            # The Briefing's needs list each item as its action link inside a list entry.
            row = page.locator("li").filter(has_text=fragment)
        if row.count():
            row_text = row.first.inner_text()
            if shows_a_time(row_text.replace(fragment, "")):
                problems.append(f"{tab}: the offer's row shows a time ({row_text!r})")
        else:
            problems.append(f"{tab}: the offer is not on the tab")
    url, why = require_needs_page(page, a, "Needs you page")
    if why:
        problems.append(why)
    else:
        if "1970" in body_text(page):
            problems.append("Needs you page: '1970' on the page")
        row = page_row(page, offer["id"])
        if not row.count():
            problems.append("Needs you page: the offer is not listed")
        elif shows_a_time(row.first.inner_text().replace(fragment, "")):
            problems.append(f"Needs you page: the offer's row shows a time ({row.first.inner_text()!r})")
    shot(page, "no-epoch")
    page.context.close()
    record("no-epoch", True, not problems, "; ".join(problems) or
           "no time shown for the offer, no 1970 on either tab or the Needs you page")


# The other controls: (tab, selector, label pattern) -> what must be on the page it opens.
def named_thing(label):
    """What a control's page must show, from its label: the item or list it names."""
    rules = [(r"chapter", r"chapter"), (r"profile", r"profile"), (r"dashboard", r"dashboard"),
             (r"build", r"build"), (r"spend|ledger|budget", r"spend|budget"),
             (r"main|branch|checks", r"main|check"), (r"needs", r"needs you")]
    for pattern, wanted in rules:
        if re.search(pattern, label, re.I):
            return wanted
    return re.escape(label.split(":")[0].strip()[:40])


def check_tiles_inert(browser, a):
    problems, notes = [], []
    page = browser.page(a)
    for tab in ("dashboard", "briefing"):
        where = open_overview(page, a, tab)
        for log in ("Open log", "Open the log"):
            if page.get_by_role("button", name=re.compile(rf"^{log}$", re.I)).count() or \
                    page.get_by_role("link", name=re.compile(rf"^{log}$", re.I)).count() or \
                    page.get_by_text(log, exact=True).count():
                problems.append(f"{tab}: {log!r} exists")
        tiles = page.locator("[data-slot=overview-tile], [data-testid=overview-tile]")
        for i in range(tiles.count()):
            where = open_overview(page, a, tab)
            tile = page.locator("[data-slot=overview-tile], [data-testid=overview-tile]").nth(i)
            label = (tile.inner_text() or "").split("\n")[0].strip()
            tile.click()
            wait_settled(page, 400)
            moved = not same_place(where, page.url) or not page.locator("[data-slot=overview-live]").count()
            log_click(tab, f"tile {label}", page, not moved)
            if moved:
                problems.append(f"{tab}: tile {label!r} opened {path_of(page.url)} ({heading(page)!r})")
    # The hop budget chip, in the Dashboard's Profile status.
    open_overview(page, a, "dashboard")
    toggle = page.locator("[aria-controls=overview-more-profiles]")
    if toggle.count():
        toggle.first.click()
        page.wait_for_timeout(1500)
    chip = page.get_by_role("button", name=re.compile(r"held by hop budget", re.I))
    if not chip.count():
        problems.append("the hop budget chip is not shown (Profile status)")
    else:
        chip.first.click()
        wait_settled(page, 800)
        field = page.get_by_label(re.compile(r"hop budget", re.I))
        has_field = field.count() > 0 or page.locator("#s-hops").count() > 0
        log_click("dashboard", "held by hop budget", page, has_field)
        shot(page, "hop-chip")
        if not has_field:
            problems.append(f"the hop budget chip opened {path_of(page.url)} ({heading(page)!r}) "
                            "with no hop budget field")
    # Every other control on both tabs: its page shows what its label names.
    for tab, slots in (("dashboard", ("overview-foot", "overview-see-all", "overview-build",
                                      "overview-activity")),
                       ("briefing", ("briefing-foot", "briefing-more", "briefing-link",
                                     "briefing-note-link"))):
        where = open_overview(page, a, tab)
        targets = []
        for slot in slots:
            loc = page.locator(f"[data-slot={slot}]")
            for i in range(loc.count()):
                label = (loc.nth(i).get_attribute("aria-label") or loc.nth(i).inner_text() or "").strip()
                targets.append((slot, i, label))
        for slot, i, label in targets:
            if re.search(r"see all|shows the first", label, re.I) and slot == "overview-see-all":
                # An in-place expander (needs, timeline), not a way out.
                if not re.search(r"build", label, re.I):
                    continue
            where = open_overview(page, a, tab)
            loc = page.locator(f"[data-slot={slot}]")
            if i >= loc.count():
                continue
            loc.nth(i).click()
            wait_settled(page, 600)
            wanted = named_thing(label)
            named = bool(re.search(wanted, heading(page) + "\n" + main_text(page)[:3000], re.I)) and \
                not same_place(where, page.url)
            log_click(tab, label[:60], page, named)
            if not named:
                problems.append(f"{tab}: {label[:50]!r} opened {path_of(page.url)} ({heading(page)!r})")
        notes.append(f"{tab}: {len(targets)} other controls")
    page.context.close()
    record("tiles-inert", True, not problems,
           ("; ".join(problems[:12]) + (f" (+{len(problems) - 12} more)" if len(problems) > 12 else ""))
           if problems else "tiles inert, no Open log, hop chip shows the field, " + ", ".join(notes))


def check_stall_opens_with_remedies(browser, a):
    problems = []
    page = browser.page(a)
    open_overview(page, a)
    row = overview_need_row(page, a.ids["stall_reason"][:30])
    target = row.locator("[data-testid=need-open]")
    (target.first if target.count() else row).click()
    wait_settled(page, 1000)
    remedies = page.locator(f"[data-testid=stall-remedies-{a.ids['stall']}]")
    reason_shown = page.get_by_text(a.ids["stall_reason"][:30]).count() > 0
    log_click("dashboard", "stall on a task", page, remedies.count() > 0 and reason_shown)
    shot(page, "stall-on-task")
    if not (remedies.count() and reason_shown):
        problems.append(f"the task stall opened {path_of(page.url)} ({heading(page)!r}): remedies "
                        f"{'shown' if remedies.count() else 'absent'}, reason "
                        f"{'shown' if reason_shown else 'absent'}")
    where = open_overview(page, a)
    row = overview_need_row(page, a.ids["lone_reason"][:30])
    target = row.locator("[data-testid=need-open]")
    (target.first if target.count() else row).click()
    wait_settled(page, 800)
    stayed = same_place(where, page.url) and page.locator("[data-slot=overview-live]").count() > 0
    reason_on_row = stayed and page.get_by_text(a.ids["lone_reason"][:30]).count() > 0
    log_click("dashboard", "stall with no task", page, stayed)
    if not (stayed and reason_on_row):
        problems.append(f"the stall with no task or conversation opened {path_of(page.url)} "
                        f"({heading(page)!r})")
    page.context.close()
    record("stall-opens-with-remedies", True, not problems, "; ".join(problems) or
           "the task stall opens its task with reason and remedies; the lone stall opens nothing")


def check_answer_opens_conversation(browser, a):
    qid = a.ids["questions"][-1]
    text = next(n["title"] for n in a.needs() if n["id"] == f"question-{qid}")
    page = browser.page(a)
    open_overview(page, a)
    row = overview_need_row(page, text[:30])
    how = press_verb(row, "Answer")
    wait_settled(page, 1500)
    in_thread = a.ids["conversation"] in page.url or "Asker" in page.url
    composer = main_area(page).locator("textarea, [contenteditable=true]")
    docked = main_area(page).get_by_text(text[:30]).count() > 0 and composer.count() > 0
    log_click("dashboard", f"Answer ({how})", page, in_thread and docked)
    shot(page, "answer")
    where = f"{path_of(page.url)} ({heading(page)!r})"
    page.context.close()
    record("answer-opens-conversation", True, in_thread and docked,
           f"Answer opened {where}; asking conversation: {in_thread}; "
           f"question docked by the composer: {docked} (a guard: holds today)")


def check_mark_seen_in_place(browser, a):
    notice = a.ids["notice"]
    title = next(n["title"] for n in a.needs() if n["id"] == f"main_moved-{notice}")
    page = browser.page(a)
    where = open_overview(page, a)
    row = overview_need_row(page, title[:25])
    how = press_verb(row, "Mark seen")
    page.wait_for_timeout(1500)
    stayed = same_place(where, page.url) and page.locator("[data-slot=overview-live]").count() > 0
    seen = ro("select seen_at from main_notices where id=?", (notice,))[0][0]
    left = stayed and poll(lambda: not overview_has(page, title[:25]), 6, 0.5)
    log_click("dashboard", f"Mark seen ({how})", page, stayed)
    shot(page, "mark-seen")
    page.context.close()
    record("mark-seen-in-place", True, stayed and bool(seen) and left,
           f"after Mark seen ({how}) the page {'stayed' if stayed else 'moved to ' + path_of(page.url)}; "
           f"notice seen_at={seen}; row left the list: {left}")


def overview_has(page, fragment):
    try:
        return page.locator("[data-testid=need-row], [data-slot=overview-need]").filter(
            has_text=fragment).count() > 0
    except Exception:  # noqa: BLE001
        return False


def check_try_again_in_place(browser, a):
    task = a.ids["merge_task"]
    page = browser.page(a)
    where = open_overview(page, a)
    browser.posts.clear()
    row = overview_need_row(page, "was approved but did not land")
    how = press_verb(row, "Try again")
    page.wait_for_timeout(2500)
    stayed = same_place(where, page.url) and page.locator("[data-slot=overview-live]").count() > 0
    retried = any(m == "POST" and f"/tasks/{task}/integrations/retry" in u for m, u in browser.posts)
    still = overview_has(page, "was approved but did not land") if stayed else False
    reason = page.locator("[data-testid=need-reason]").count() > 0 if stayed else False
    log_click("dashboard", f"Try again ({how})", page, stayed)
    shot(page, "try-again")
    page.context.close()
    record("try-again-in-place", True, stayed and retried and still and reason,
           f"after Try again ({how}) the page {'stayed' if stayed else 'moved to ' + path_of(page.url)}; "
           f"retry call made: {retried}; row stays: {still}; reason on the row: {reason}")


def dismiss_on_page(page, need):
    row = page_row(page, need)
    if not row.count():
        return f"no row for {need}"
    button = row.locator("[data-testid=need-dismiss]")
    if not button.count():
        return f"{need} has no Dismiss button"
    button.first.click()
    page.wait_for_timeout(1500)
    return None


def check_dismiss_closes_question(browser, a):
    qid = a.ids["questions"][0]
    page = browser.page(a)
    url, why = require_needs_page(page, a, "dismiss a question")
    if why:
        page.context.close()
        record("dismiss-closes-question", True, False, why)
        return
    missing = dismiss_on_page(page, f"question-{qid}")
    page.reload(wait_until="domcontentloaded")
    wait_settled(page, 1200)
    on_page = page_row(page, f"question-{qid}").count() > 0
    page.context.close()
    code, q = api("GET", f"{a.base}/questions/{qid}")
    declined = code == 200 and q.get("declined") is True
    on_overview = any(n["id"] == f"question-{qid}" for n in a.needs())
    record("dismiss-closes-question", True, not missing and declined and not on_page and not on_overview,
           f"{missing or 'Dismiss pressed'}; GET /questions/{qid} declined={q.get('declined') if code == 200 else code}; "
           f"on the page after reload: {on_page}; on the Overview: {on_overview}")


def stall_row(project, stall_id):
    rows = ro("select ended_at, outcome, outcome_detail from stalls where id=?", (stall_id,))
    return rows[0] if rows else None


def check_stall_ended_by_operator(browser, a):
    stall, task = a.ids["stall"], a.ids["stall_task"]
    page = browser.page(a)
    url, why = require_needs_page(page, a, "dismiss a stall")
    missing = why or dismiss_on_page(page, f"stall-{stall}")
    page.context.close()
    if missing:
        # Today: no Dismiss button. The stall is ended through the operator's existing route so the
        # rest of the criterion (not raised again until the task changes) is still asserted.
        api("POST", f"{a.base}/stalls/{stall}/end", {"outcome": "resolved"})
    ended_at, outcome, detail = stall_row(a, stall)
    code, listed = api("GET", f"{a.base}/stalls")
    view = next((s for s in (listed or {}).get("stalls", []) if s.get("id") == stall), {}) if code == 200 else {}
    by_operator = view.get("ended_by") == "operator" or "operator" in (detail or "").lower()
    again = detect_again(a.pid, "review_unstaffed", task, "Nobody could check it, still", task)
    key = f"review_unstaffed:{task}"
    reopened = ro("select id from stalls where project_id=? and key=? and ended_at is null", (a.pid, key))
    for stale in reopened:  # today's re-raise, so the task's change is judged on its own
        api("POST", f"{a.base}/stalls/{stale[0]}/end", {"outcome": "resolved"})
    moved, _ = api("PATCH", f"{a.base}/tasks/{task}", {"status": "in_progress"})
    after_change = detect_again(a.pid, "review_unstaffed", task, "Nobody could check it, still", task)
    ok = not missing and ended_at is not None and by_operator and not reopened and after_change["new"]
    record("stall-ended-by-operator", True, ok,
           f"{missing or 'Dismiss pressed'}; ended_at={ended_at} outcome={outcome} by operator: {by_operator}; "
           f"detection again: open stalls for the key {[r[0] for r in reopened]} (new={again['new']}); "
           f"after the task moved (PATCH {moved}): raised {after_change['new']}")


def check_dismiss_all_partial(browser, c):
    question, (refused, other) = c.ids["questions"][0], c.ids["permissions"]
    page = browser.page(c)
    url, why = require_needs_page(page, c, "Dismiss all with a refusal")
    if why:
        page.context.close()
        record("dismiss-all-partial", True, False, why)
        return
    # Decided elsewhere, a moment before the click.
    api("POST", f"{c.base}/permission-requests/{refused}/decide", {"decision": "allow"})
    button = page.locator("[data-testid=needs-dismiss-all]")
    if not button.count():
        page.context.close()
        record("dismiss-all-partial", True, False, "no Dismiss all button on the Needs you page")
        return
    button.first.click()
    page.locator("[data-testid=needs-dismiss-all-confirm]").first.click(timeout=5000)
    page.wait_for_timeout(3000)
    summary = page.locator("[data-testid=needs-dismiss-summary]")
    closed, could_not = summary_counts(summary.first.inner_text() if summary.count() else "")
    refused_row = page_row(page, f"permission-{refused}")
    reason = refused_row.locator("[data-testid=need-reason]")
    reason_text = reason.first.inner_text().strip() if reason.count() else ""
    shot(page, "dismiss-all-partial")
    page.context.close()
    code, q = api("GET", f"{c.base}/questions/{question}")
    _, perms = api("GET", f"{c.base}/permission-requests")
    perm = {p["id"]: p for p in (perms if isinstance(perms, list) else [])}
    other_closed = perm.get(other, {}).get("status") in ("denied", "deny") or perm.get(other, {}).get("dismissed")
    ok = q.get("declined") is True and other_closed and refused_row.count() >= 0 and bool(reason_text) \
        and closed == 2 and could_not == 1
    record("dismiss-all-partial", True, ok,
           f"question declined={q.get('declined')}; other request {perm.get(other, {}).get('status')}; "
           f"refused row's reason {reason_text[:80]!r}; summary says closed={closed}, could not={could_not}")


def check_dismiss_all_asks_first(browser, d):
    before = d.needs()
    dismissable = [n for n in before if DISMISSABLE[n["kind"]]]
    if len(dismissable) != 6 or len(before) != 7:
        raise NotReached(f"D holds {len(before)} needs, {len(dismissable)} dismissable (want 7 and 6)")
    page = browser.page(d)
    url, why = require_needs_page(page, d, "Dismiss all, cancelled")
    if why:
        page.context.close()
        record("dismiss-all-asks-first", True, False, why)
        return
    button = page.locator("[data-testid=needs-dismiss-all]")
    if not button.count():
        page.context.close()
        record("dismiss-all-asks-first", True, False, "no Dismiss all button on the Needs you page")
        return
    browser.posts.clear()
    button.first.click()
    page.wait_for_timeout(800)
    dialog = page.locator("[role=dialog], [role=alertdialog]")
    dialog_text = dialog.first.inner_text() if dialog.count() else ""
    writes_before_confirm = list(browser.posts)
    cancel = page.locator("[data-testid=needs-dismiss-all-cancel]")
    if cancel.count():
        cancel.first.click()
    page.wait_for_timeout(1500)
    listed = page_rows(page).count()
    page.context.close()
    after = d.needs()
    names_six = bool(re.search(r"\b6\b|\bsix\b", dialog_text, re.I))
    ok = names_six and not writes_before_confirm and listed == 7 and \
        sorted(n["id"] for n in after) == sorted(n["id"] for n in before)
    record("dismiss-all-asks-first", True, ok,
           f"confirmation {dialog_text[:80]!r} (names six: {names_six}); writes before confirming: "
           f"{writes_before_confirm[:3]}; listed after cancel: {listed}; GET /overview unchanged: "
           f"{len(after) == len(before)}")


def check_dismiss_all_closes_every_kind(browser, d):
    page = browser.page(d)
    url, why = require_needs_page(page, d, "Dismiss all, confirmed")
    if why:
        page.context.close()
        record("dismiss-all-closes-every-kind", True, False, why)
        return
    button = page.locator("[data-testid=needs-dismiss-all]")
    if not button.count():
        page.context.close()
        record("dismiss-all-closes-every-kind", True, False, "no Dismiss all button on the Needs you page")
        return
    button.first.click()
    page.locator("[data-testid=needs-dismiss-all-confirm]").first.click(timeout=5000)
    page.wait_for_timeout(4000)
    page.reload(wait_until="domcontentloaded")
    wait_settled(page, 1500)
    review_row = page_row(page, f"review-{d.ids['review_task']}")
    review_listed = review_row.count() > 0
    review_dismiss = review_row.locator("[data-testid=need-dismiss]").count() if review_listed else 0
    shot(page, "dismiss-all-every-kind")
    page.context.close()
    ids = d.ids
    state = {
        "question declined": api("GET", f"{d.base}/questions/{ids['questions'][0]}")[1].get("declined") is True,
        "permission closed": ro("select status, dismissed from permission_requests where id=?",
                                (ids["permissions"][0],))[0][0] != "pending",
        "stall ended": stall_row(d, ids["stall"])[0] is not None,
        "notice seen": ro("select seen_at from main_notices where id=?", (ids["notice"],))[0][0] is not None,
        "offer declined": not any(n["kind"] == "offer" for n in d.needs()),
        "warning dismissed": not any(n["kind"] == "reopening" for n in d.needs()),
    }
    left = [n["kind"] for n in d.needs()]
    ok = all(state.values()) and left == ["review"] and review_listed and not review_dismiss
    record("dismiss-all-closes-every-kind", True, ok,
           ", ".join(f"{k}: {v}" for k, v in state.items())
           + f"; GET /overview after reload: {left}; review listed: {review_listed}, "
             f"its Dismiss buttons: {review_dismiss}")


CHECKS = {
    "closable-per-kind": ("A", check_closable_per_kind),
    "needs-page-lists-all": ("A", check_needs_page_lists_all),
    "no-epoch": ("A", check_no_epoch),
    "tiles-inert": ("A", check_tiles_inert),
    "stall-opens-with-remedies": ("A", check_stall_opens_with_remedies),
    "answer-opens-conversation": ("A", check_answer_opens_conversation),
    "mark-seen-in-place": ("A", check_mark_seen_in_place),
    "try-again-in-place": ("A", check_try_again_in_place),
    "dismiss-closes-question": ("A", check_dismiss_closes_question),
    "stall-ended-by-operator": ("A", check_stall_ended_by_operator),
    "dismiss-all-partial": ("C", check_dismiss_all_partial),
    "dismiss-all-asks-first": ("D", check_dismiss_all_asks_first),
    "dismiss-all-closes-every-kind": ("D", check_dismiss_all_closes_every_kind),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    self_test()
    if args.self_test:
        return 0
    wanted = [k for k in ORDER if not args.only or k in args.only.split(",")]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    proc = start_hub(SCRATCH / "hub.log")
    from playwright.sync_api import sync_playwright

    try:
        projects = {
            "A": Project("A").open().arrange(
                {"question", "permission", "stall", "lone_stall", "review", "merge", "check",
                 "main_moved", "hop", "offer", "reopening"}, questions=2),
            "C": Project("C").open().arrange({"question", "permission"}, permissions=2),
            "D": Project("D").open().arrange(
                {"question", "permission", "stall", "main_moved", "offer", "reopening", "review"}),
        }
        for name, project in projects.items():
            print(f"project {name}: {project.pid} -- {len(project.needs())} needs: "
                  f"{[n['kind'] for n in project.needs()]}", flush=True)
        with sync_playwright() as pw:
            browser = Browser(pw)
            for key in wanted:
                name, fn = CHECKS[key]
                try:
                    fn(browser, projects[name])
                except NotReached as exc:
                    record(key, False, False, f"not reached: {exc}")
                except Exception as exc:  # noqa: BLE001 -- one check's crash is its own verdict
                    record(key, False, False, f"not reached: {type(exc).__name__}: {str(exc)[:300]}")
            if browser.errors:
                print(f"{len(browser.errors)} page error(s): {browser.errors[:3]}", flush=True)
            browser.browser.close()
    except Setup as exc:
        print(f"setup error: {exc}", flush=True)
        return 2
    finally:
        if args.keep:
            print(f"the Hub stays up on :{PORT} (pid {proc.pid}); key {KEY}", flush=True)
        else:
            stop_hub(proc)
    print(f"screenshots: {OUT}")
    print("--- drive_baseline ---")
    for key in wanted:
        reached, failed, detail = checks.get(key, (False, True, "not run"))
        print(f"check {key}: reached={'yes' if reached else 'no'} "
              f"failed_at_assertion={'yes' if reached and failed else 'no'} -- {detail}")
    return 1 if any(failed for _, failed, _ in checks.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
