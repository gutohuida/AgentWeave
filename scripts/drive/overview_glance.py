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

Three more checks (OGDBT-7), each in a project of its own:

  ac-note-quality   a two-task build: real Haiku turns build both; the operator lands one and sends
                    the other back, the Builder is held so the build stays still, every timestamp of
                    the project is set back 40 minutes and the last visit 3 hours. The operator
                    presses Refresh note on the Briefing (a real Haiku turn). Steps: refresh (its
                    POST /manager/jobs/overview-note/run answers 202), written (GET /overview's note,
                    trigger `button`, written after the press), short (< 120 words), names (the
                    landed task, the sent-back task and the build, by id, readable id or title, and
                    that it stopped moving), links (every cite answers 200 from GET /tasks/{id},
                    /project/builds/{id}/tasks, /agents/{name} or /questions/{id}, and the note shows
                    one link per cite), in-project (no id-shaped word the project does not hold, no
                    other project's name). The note is saved as note-quality.txt.
  ac-tabs-feel      tabs (Dashboard, Briefing on a project never reordered), held-moves (while the
                    mouse holds Briefing, an element labelled Briefing has moved 8 px or is
                    transformed), drag-reorders (Briefing, Dashboard after the drop),
                    keyboard-reorders (focus Briefing and try Space/ArrowRight/Space, then
                    Alt+Shift+ArrowRight, Ctrl+Shift+ArrowRight, Alt+ArrowRight; the keys that moved
                    it are printed), reload-keeps (the order after a reload, and aw.overview.tabs.v1).
  ac-looks-like-mock  the mock dev server from this checkout's hub/ui (vite.mock.config.ts, a free
                    port from 5211, AW_MOCK_PORT) is read for each shape and tab at 1280 and 1920 px,
                    and shot by shoot.py into mock-shoot/; then live projects in the busy (a
                    question, a two-task build, two held runs), quiet (nothing) and trouble (busy
                    plus a test failing on main) shapes. One step per shape, tab and width: the live
                    screen has the mock's sections and the criterion's (the Briefing's note, which
                    the mock lacks), the mock's in its order, and nothing past the viewport's edge
                    (outside a scrolling or clipping box) and no two sections or tiles overlapping.
                    Sections are read by the same script on both: the health band, the tiles, and
                    each h1/h2 by its words (SECTIONS_JS).

Prints one line per check in the `drive_baseline` shape and exits 1 if any failed:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
Screenshots and the note text go to testbed/overview-glance/<HHMMSS>/.

    py -3.11 scripts/drive/overview_glance.py                      # the trial Hub :8010, every check
    py -3.11 scripts/drive/overview_glance.py --own-hub            # a Hub from this checkout
    py -3.11 scripts/drive/overview_glance.py --checks ac-tabs-feel,ac-looks-like-mock
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
CHECK = KEY_CHECK
checks: dict[str, dict[str, tuple[bool, str]]] = {}


class Setup(Exception):
    """Something the scenario depends on, outside the criterion, could not be arranged."""


def step(name, ok, detail):
    checks.setdefault(CHECK, {})[name] = (bool(ok), detail)
    print(f"{'PASS' if ok else 'FAIL'} {CHECK} {name} -- {detail}", flush=True)
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


STALL_WORDS = re.compile(
    r"\b(stall(ed|s|ing)?|stuck|stopped|not moved|(has not|hasn't|have not|haven't) moved|no progress|idle|"
    r"no movement|without (moving|progress)|not (been )?moving|quiet for|still for)\b", re.I)
NOT_IDS = {"UTF-8", "UTF-16", "ISO-8601", "SHA-1", "SHA-256"}  # id-shaped words that are not ids
ID_TOKEN = re.compile(r"\b(?:(?:task|build|proj|run|spdoc|question|kf)-[0-9a-f]{6,}|[A-Z]{3,6}-\d+)\b")


def shift_stamp(text, minutes):
    """*text*, a stored timestamp, moved by *minutes* in the same format; None if it is not one."""
    m = re.fullmatch(r"(\d{4}-\d\d-\d\d)([T ])(\d\d:\d\d:\d\d)(\.\d{1,6})?(Z|[+-]\d\d:\d\d)?", (text or "").strip())
    if not m:
        return None
    at = dt.datetime.fromisoformat(f"{m[1]}T{m[3]}{m[4] or ''}") + dt.timedelta(minutes=minutes)
    frac = f".{at.microsecond:06d}" if m[4] else ""
    return f"{at:%Y-%m-%d}{m[2]}{at:%H:%M:%S}{frac}{m[5] or ''}"


def stamp_ago(minutes):
    return shift_stamp(_now(), -minutes)


def word_count(text):
    return len(re.findall(r"\S+", text or ""))


def names_any(text, cites, ids):
    """The note names one of *ids*: in its text, or as a cite's id or label."""
    ids = {str(i) for i in ids if i}
    return any(i in (text or "") for i in ids) or any(
        str(c.get("id")) in ids or str(c.get("label")) in ids for c in cites or [])


def outside_names(text, known, other_projects):
    """Id-like words in *text* the project does not hold, and other projects' names it uses."""
    stray = [t for t in dict.fromkeys(ID_TOKEN.findall(text or "")) if t not in known and t not in NOT_IDS]
    stray += [n for n in other_projects if n and len(n) >= 5 and n in (text or "")]
    return stray


def shown_moving(start_left, samples):
    """While held, an element labelled Briefing sits 8 px or more from where the tab started, or is transformed."""
    if start_left is None:
        return False
    return any(abs(s["left"] - start_left) >= 8 or (s.get("transform") or "none") != "none" for s in samples)


def sections_match(mock_keys, live_keys, named):
    """`(ok, words)`: the live screen has the mock's sections and the named ones, the mock's in its order."""
    missing = [k for k in dict.fromkeys([*mock_keys, *named]) if k not in live_keys]
    if missing:
        return False, f"missing {missing}"
    live_order = [k for k in live_keys if k in mock_keys]
    if live_order != list(mock_keys):
        return False, f"order {live_order}, the mock's {list(mock_keys)}"
    return True, "the mock's sections in its order"


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
        (shift_stamp("2026-11-23 08:00:00.123456", -40), "2026-11-23 07:20:00.123456"),
        (shift_stamp("2026-11-23T00:10:00+00:00", -40), "2026-11-22T23:30:00+00:00"),
        (shift_stamp("2026-11-23 08:00:00", -1), "2026-11-23 07:59:00"),
        (shift_stamp("not a time", -1), None),
        (word_count("Builder landed GNB-1.  Two  words"), 5),
        (bool(STALL_WORDS.search("The build has not moved for 40 minutes")), True),
        (bool(STALL_WORDS.search("Glance note build stalled")), True),
        (bool(STALL_WORDS.search("Everything moved along")), False),
        (names_any("GNB-1 landed", [], {"GNB-1", "task-1"}), True),
        (names_any("a task landed", [{"type": "task", "id": "task-1"}], {"task-1"}), True),
        (names_any("a task landed", [], {"task-1"}), False),
        (outside_names("GNB-1 landed, XYZ-9 too; UTF-8", {"GNB-1"}, []), ["XYZ-9"]),
        (outside_names("see other-project", set(), ["other-project", "abc"]), ["other-project"]),
        (shown_moving(100, [{"left": 100, "transform": "none"}, {"left": 60, "transform": "none"}]), True),
        (shown_moving(100, [{"left": 100, "transform": "matrix(1, 0, 0, 1, -30, 0)"}]), True),
        (shown_moving(100, [{"left": 101, "transform": "none"}]), False),
        (shown_moving(None, []), False),
        (sections_match(["health", "tiles", "needs"], ["health", "tiles", "x", "needs"], ["health"])[0], True),
        (sections_match(["health", "needs", "timeline"], ["health", "timeline", "needs"], [])[0], False),
        (sections_match(["headline", "needs"], ["headline", "needs"], ["note"]), (False, "missing ['note']")),
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


def document_payload(title=TITLE, files=(("glance.txt", TASK_TITLE),)):
    """A change document with one requirement, criterion and task per `(file, task title)`."""
    reqs, crits, tasks = [], [], []
    for n, (name, task_title) in enumerate(files, 1):
        word = name.split(".")[0]
        reqs.append({"key": f"r{n}", "modal": "MUST", "statement": f"The repository MUST hold {name}."})
        crits.append({"key": f"has-{word}", "requirement": f"r{n}", "given": "the repository",
                      "when": "it is read", "then": f"{name} says {word}",
                      "how_to_check": "read it", "checked_by": "agent"})
        tasks.append({"key": f"t{n}", "title": task_title, "requirements": [f"r{n}"], "files": [name],
                      "depends_on": [],
                      "description": (f"Create the file {name} at the repository root holding the single "
                                      f"line `{word}`. Change nothing else. Record evidence for the "
                                      "requirement with record_evidence, then complete the task.")})
    return {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "summary": f"{title}, a document for the Overview-at-a-glance drive.", "problem": "The drive needs one.",
        "scope": {"in_scope": ["the drive"], "non_goals": ["anything else"]},
        "requirements": reqs, "acceptance_criteria": crits, "tasks": tasks,
        "delivery": {"mode": "flow", "agent": BUILDER, "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *",  # once a year: the drive fires the flow itself
                     "reasons": {"mode": "The drive.", "agent": "The default builder."}},
    }


def make_build(base, pid, doc=DOC, title=TITLE, files=(("glance.txt", TASK_TITLE),)):
    """Author, approve and build *doc* as a flow at Reviewed; `(task ids in file order, job, build)`."""
    quoted = urllib.parse.quote(doc)
    payload = document_payload(title, files)
    code, out = api("POST", f"{base}/project/documents", {"title": title, "kind": "change-spec", "path": doc})
    if code != 201:
        raise Setup(f"create {doc}: {code} {str(out)[:300]}")
    code, out = api("PUT", f"{base}/project/documents/{doc}/content", {"document": payload})
    if code != 200:
        raise Setup(f"save {doc}: {code} {str(out)[:600]}")
    confirmations = [{"criterion": c["key"], "kind": "new"} for c in payload["acceptance_criteria"]]
    code, out = as_agent(pid, CHECKER, "POST", "/spec/documents/confirm-criteria",
                         {"path": doc, "confirmations": confirmations})
    if code != 200:
        raise Setup(f"confirm {doc}'s criteria: {code} {str(out)[:300]}")
    _, read = api("GET", f"{base}/project/spec?path={quoted}")
    code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                    {"reason": "drive", "approve_anyway": True, "content_version": read.get("content_version")})
    if code != 200:
        raise Setup(f"approve {doc}: {code} {str(out)[:600]}")
    code, out = api("POST", f"{base}/project/documents/build?path={quoted}",
                    {"driver": "flow", "level": "reviewed", "builder": BUILDER, "checker": CHECKER,
                     "landing": "main"})
    if code != 200:
        raise Setup(f"build {doc}: {code} {str(out)[:800]}")
    (doc_id,) = ro("select id from spec_documents where project_id=? and path=?", (pid, doc))[0]
    rows = ro("select id, loop_id, spec_task_key from tasks where spec_document_id=?", (doc_id,))
    by_key = {key: (tid, loop) for tid, loop, key in rows}
    task_ids = [by_key[f"t{n}"][0] for n in range(1, len(files) + 1)]
    (job_id,) = ro("select job_id from loops where id=?", (rows[0][1],))[0]
    build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    return task_ids, job_id, build_id


def status_of(task_id):
    return ro("select status from tasks where id=?", (task_id,))[0][0]


def live_runs(pid):
    return ro("select id from runs where project_id=? and status in ('running', 'queued', 'starting') "
              "and id not like 'run-glance-%'", (pid,))


def work(base, pid, job_id, *task_ids):
    """Fire the flow until real turns finish every one of *task_ids*, re-firing only while nothing runs."""
    end = time.time() + TURN_WAIT * len(task_ids)
    while time.time() < end and any(status_of(t) not in DONE for t in task_ids):
        if not live_runs(pid):
            code, out = api("POST", f"{base}/jobs/{job_id}/run")
            print(f"  fired {job_id}: {code} {str(out)[:120]}", flush=True)
        time.sleep(20)
    if any(status_of(t) not in DONE for t in task_ids):
        raise Setup(f"no real turn finished the tasks in time ({[status_of(t) for t in task_ids]})")
    poll(lambda: not live_runs(pid), 180)


def approve(base, task_id):
    """Accept *task_id*'s awaiting evidence (every awaiting piece when the rows name no task), then land it."""
    code, rows = api("GET", f"{base}/project/spec/evidence?review_state=awaiting")
    rows = rows.get("evidence", []) if code == 200 and isinstance(rows, dict) else []
    if any("task_id" in row for row in rows):
        rows = [row for row in rows if row.get("task_id") == task_id]
    for row in rows:
        api("POST", f"{base}/project/spec/evidence/{row['id']}/decision",
            {"decision": "accepted", "reason": "the drive's operator"})
    code, out = api("POST", f"{base}/tasks/{task_id}/land")
    if code != 200 or status_of(task_id) != "approved":
        raise Setup(f"the operator's approval: {code} {status_of(task_id)} {str(out)[:300]}")


def send_back(base, task_id):
    code, out = api("PATCH", f"{base}/tasks/{task_id}",
                    {"status": "revision_needed", "reason_class": "defect",
                     "notes": "The drive's operator sends this back: the file's line is wrong."})
    if code != 200 or status_of(task_id) != "revision_needed":
        raise Setup(f"the operator's send-back: {code} {status_of(task_id)} {str(out)[:300]}")


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

    def __init__(self, play, pid, profile="browser-profile"):
        self.pid = pid
        self.visits: list[tuple[int, object]] = []
        self.posts: list[tuple[str, int, object]] = []
        self.context = play.chromium.launch_persistent_context(
            str(SCRATCH / profile), viewport={"width": 1440, "height": 940})
        self.context.add_init_script(
            f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));"
            f"localStorage.setItem('agentweave-selected-project', {pid!r});")
        self.page = self.context.new_page()
        self.page.on("response", self._seen)

    def _seen(self, response):
        url = response.url.split("?")[0]
        if response.request.method != "POST" or "/api/v1/" not in url:
            return
        try:
            body = response.json()
        except Exception:  # noqa: BLE001 -- a body that is not JSON is recorded as text
            body = response.text()[:300]
        self.posts.append((url, response.status, body))
        if url.endswith("/overview/visit"):
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


def new_project(state, label, agents=(BUILDER, CHECKER)):
    """A throwaway git repository on `main`, opened as a project with a Haiku runner and *agents*."""
    root = SCRATCH / f"proj-{label}"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A throwaway project for the Overview-at-a-glance drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"glance-{label}-{STAMP}"})
    if code not in (200, 201):
        raise Setup(f"the project opens: {code} {project}")
    pid = project["id"]
    base = f"/projects/{pid}"
    state.update(pid=pid, base=base)
    state.setdefault("bases", []).append(base)
    code, out = api("PUT", f"{base}/settings", {"main_branch": "main"})
    if code != 200:
        raise Setup(f"the project's main branch: {code} {str(out)[:300]}")
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    if code not in (200, 201):
        raise Setup(f"the Haiku runner: {code} {haiku}")
    state["runner"] = haiku["id"]
    for name in agents:
        code, out = api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
        if code not in (200, 201):
            raise Setup(f"agent {name}: {code} {out}")
    return pid, base


def held(state, pid, agent):
    run_id = hold(pid, agent)
    state.setdefault("holds", []).append(run_id)
    return run_id


def built(state, base, pid, **kwargs):
    tasks, job, build = make_build(base, pid, **kwargs)
    state.setdefault("builds", []).append((base, build))
    return tasks, job, build


def arrange(state):
    pid, base = new_project(state, "e2e")
    (state["task"],), state["job"], state["build"] = built(state, base, pid)
    state["hold"] = held(state, pid, CHECKER)
    print(f"project {pid}; task {state['task']}, build {state['build']}", flush=True)


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


# --------------------------------------------------------------------------- ac-note-quality


NQ_DOC, NQ_TITLE = "spec/changes/glance-note/spec.json", "Glance note build"
NQ_FILES = (("landed.txt", "Write landed.txt"), ("sentback.txt", "Write sentback.txt"))
NQ_STEPS = ["refresh", "written", "short", "names", "links", "in-project"]
STILL_BACK = 40  # minutes the build's last movement is set back
VISIT_BACK = 180  # minutes the last visit is set back, so the landing and the send-back come after it
SHIFTED = {  # every timestamp of the project a build's movement is read from
    "tasks": ("updated", "created_at"),
    "task_transitions": ("created_at",),
    "task_landings": ("created_at", "updated_at", "ended_at"),
    "runs": ("started_at", "ended_at", "last_heartbeat_at", "mcp_adapter_online_at"),
    "builds": ("created_at",),
    "event_logs": ("timestamp",),
    "stalls": ("first_seen_at", "last_seen_at"),
}


def set_back(pid, minutes):
    """Move every SHIFTED timestamp of *pid* back *minutes*, each in its own stored format."""
    moved = 0
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        for table, wanted in SHIFTED.items():
            have = {r[1] for r in con.execute(f"pragma table_info({table})")}
            cols = [c for c in wanted if c in have]
            if "project_id" not in have or not cols:
                continue
            rows = con.execute(f"select rowid, {', '.join(cols)} from {table} where project_id=?", (pid,)).fetchall()
            for row in rows:
                values = [shift_stamp(v, -minutes) if isinstance(v, str) else None for v in row[1:]]
                sets = [(c, v) for c, v in zip(cols, values, strict=True) if v is not None]
                if sets:
                    con.execute(f"update {table} set {', '.join(c + '=?' for c, _ in sets)} where rowid=?",
                                [v for _, v in sets] + [row[0]])
                    moved += 1
        con.commit()
    finally:
        con.close()
    return moved


def ids_of(base, pid):
    """What the project holds that a note may name: task ids and readable ids, builds, questions."""
    known = {pid}
    known.update(x for row in ro("select id, readable_id from tasks where project_id=?", (pid,)) for x in row if x)
    known.update(r[0] for r in ro("select id from builds where project_id=?", (pid,)))
    known.update(r[0] for r in ro("select id from questions where project_id=?", (pid,)))
    return known


def resolves(base, cite):
    """`(ok, words)`: *cite* answers 200 from the Hub's route for its type, in this project."""
    kind, ident = cite.get("type"), urllib.parse.quote(str(cite.get("id") or ""), safe="")
    path = {"task": f"/tasks/{ident}", "build": f"/project/builds/{ident}/tasks",
            "profile": f"/agents/{ident}", "question": f"/questions/{ident}"}.get(kind)
    if not path or not ident:
        return False, f"{kind}:{cite.get('id')} has no route"
    code, _ = api("GET", base + path)
    return code == 200, f"{kind}:{cite.get('id')} -> {code}"


def note_quality(play):
    """ac-note-quality: since the last visit one task landed, one was sent back and the build has
    not moved for 40 minutes; the operator presses Refresh note and a real Haiku turn writes it."""
    state = STATES[CHECK]
    pid, base = new_project(state, "note")
    code, out = api("PATCH", f"{base}/manager/jobs/{JOB}", {"enabled": True, "runner_id": state["runner"], "model": HAIKU})
    print(f"  the note job on Haiku: {code} {str(out)[:160]}", flush=True)
    code, out = api("POST", f"{base}/overview/visit")
    print(f"  the operator's earlier visit: {code} {str(out)[:160]}", flush=True)
    (landed, sent), job, build = built(state, base, pid, doc=NQ_DOC, title=NQ_TITLE, files=NQ_FILES)
    held(state, pid, CHECKER)
    work(base, pid, job, landed, sent)
    held(state, pid, BUILDER)  # so the send-back starts no turn: the build stays still
    approve(base, landed)
    if not poll(lambda: landing_state(landed) == "landed", LANDING_WAIT, every=3):
        raise Setup(f"task {landed} did not land ({landing_state(landed)})")
    send_back(base, sent)
    moved = set_back(pid, STILL_BACK)
    visits = 0
    if table_exists("overview_visits"):
        visits = rw("update overview_visits set last_visit_at=?, previous_visit_at=? where project_id=?",
                    (stamp_ago(VISIT_BACK), stamp_ago(VISIT_BACK + 60), pid))
    print(f"  set back {moved} rows {STILL_BACK} minutes and {visits} visit rows {VISIT_BACK}", flush=True)
    readable = {t: (ro("select readable_id from tasks where id=?", (t,))[0][0] or t) for t in (landed, sent)}
    names = {"landed": {landed, readable[landed], NQ_FILES[0][1]}, "sent back": {sent, readable[sent], NQ_FILES[1][1]},
             "build": {build, NQ_TITLE}}
    print(f"  landed {readable[landed]}, sent back {readable[sent]}, build {build}", flush=True)

    browser = Browser(play, pid, profile="browser-note")
    try:
        browser.open("tab=overview")
        tab = browser.tab("Briefing")
        if tab is not None:
            tab.click()
            browser.page.wait_for_timeout(1500)
        button = browser.page.get_by_role("button", name=re.compile(r"refresh note", re.I))
        has_button = button.count() > 0
        pressed_at = dt.datetime.now(dt.timezone.utc)
        if has_button:
            button.first.click()
            browser.page.wait_for_timeout(3000)
        browser.shot("note-quality-1-pressed")
        runs = [(c, b) for url, c, b in browser.posts if url.endswith(f"/manager/jobs/{JOB}/run")]
        started = any(c == 202 for c, _ in runs)
        step("refresh", started, f"Briefing tab {'found' if tab is not None else 'missing'}; Refresh note button "
             f"{'found' if has_button else 'missing'}; its POST answered {[(c, str(b)[:120]) for c, b in runs] or 'nothing'}")

        def latest():
            c, v = overview(base)
            n = (v or {}).get("note") if c == 200 and isinstance(v, dict) else None
            at = parse_at((n or {}).get("written_at"))
            fresh = at is not None and at >= pressed_at - dt.timedelta(seconds=2)
            return n if n and n.get("trigger") == "button" and fresh else None

        poll(lambda: latest() is not None, NOTE_WAIT if started else 5, every=5)
        note = latest()
        text = (note or {}).get("text") or ""
        cites = (note or {}).get("cites") or []
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "note-quality.txt").write_text(text or "(no note was written)\n", encoding="utf-8")
        (OUT / "note-quality.json").write_text(json.dumps(note, indent=2), encoding="utf-8")
        step("written", bool(text), f"GET /overview's note after the press: {str(note)[:300]}")

        words = word_count(text)
        step("short", bool(text) and words < 120, f"{words} words")

        named = {what: names_any(text, cites, ids) for what, ids in names.items()}
        still = bool(STALL_WORDS.search(text))
        step("names", bool(text) and all(named.values()) and still,
             f"named {named}; says the build stopped moving: {still}; text {text[:300]!r}")

        browser.open("tab=overview")
        if browser.tab("Briefing") is not None:
            browser.tab("Briefing").click()
            browser.page.wait_for_timeout(1500)
        browser.shot("note-quality-2-note")
        box = note_box(browser.page)
        links = (box.locator("a, button").filter(has_not_text=re.compile(r"refresh", re.I)).count()
                 if box is not None and box.count() else 0)
        checked = [resolves(base, c) for c in cites]
        step("links", bool(text) and bool(cites) and all(ok for ok, _ in checked) and links == len(cites),
             f"cites {[w for _, w in checked]}; links shown in the note {links}")

        _, listed = api("GET", "/projects")
        listed = listed if isinstance(listed, list) else (listed or {}).get("projects", []) if isinstance(listed, dict) else []
        others = [p.get("name") for p in listed if isinstance(p, dict) and p.get("id") != pid]
        stray = outside_names(text, ids_of(base, pid), others)
        step("in-project", bool(text) and not stray, f"named outside the project: {stray or 'nothing'}")
    finally:
        browser.close()


# --------------------------------------------------------------------------- ac-tabs-feel


TF_STEPS = ["tabs", "held-moves", "drag-reorders", "keyboard-reorders", "reload-keeps"]
KEY_MOVES = (("Space", "ArrowRight", "Space"), ("Alt+Shift+ArrowRight",), ("Control+Shift+ArrowRight",),
             ("Alt+ArrowRight",))
TAB_ORDER_JS = """() => {
  const seen = new Map();
  for (const e of document.querySelectorAll('[role=tab], button')) {
    const name = (e.innerText || e.textContent || '').trim();
    const r = e.getBoundingClientRect();
    if (!['Dashboard', 'Briefing'].includes(name) || r.width === 0 || seen.has(name)) continue;
    seen.set(name, r.left);
  }
  return [...seen.entries()].sort((a, b) => a[1] - b[1]).map(e => e[0]);
}"""
HELD_JS = """() => [...document.querySelectorAll('*')].filter(e => (e.innerText || '').trim() === 'Briefing'
  && e.children.length <= 2 && e.getBoundingClientRect().width > 0).map(e => ({
    left: e.getBoundingClientRect().left, transform: getComputedStyle(e).transform}))"""


def tab_order(page):
    return page.evaluate(TAB_ORDER_JS)


def tabs_feel(play):
    """ac-tabs-feel: drag Briefing before Dashboard with the mouse, move it back with the keyboard, reload."""
    state = STATES[CHECK]
    pid, _ = new_project(state, "tabs", agents=())
    browser = Browser(play, pid, profile="browser-tabs")
    page = browser.page
    try:
        browser.open("tab=overview")
        browser.shot("tabs-feel-1-start")
        order = tab_order(page)
        dash, brief = browser.tab("Dashboard"), browser.tab("Briefing")
        have = dash is not None and brief is not None
        step("tabs", have and order == ["Dashboard", "Briefing"],
             f"tabs in order {order} (a project never reordered wants Dashboard, Briefing)")

        samples, start_left = [], None
        if have:
            a, b = dash.bounding_box(), brief.bounding_box()
            start_left = b["x"]
            page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
            page.mouse.down()
            page.mouse.move(b["x"] + b["width"] / 2 - 12, b["y"] + b["height"] / 2, steps=4)
            page.mouse.move(a["x"] + 4, a["y"] + a["height"] / 2, steps=12)
            page.wait_for_timeout(250)
            samples = page.evaluate(HELD_JS)
            browser.shot("tabs-feel-2-held")
            page.mouse.up()
            page.wait_for_timeout(600)
        browser.shot("tabs-feel-3-dropped")
        step("held-moves", have and shown_moving(start_left, samples),
             f"the held tab started at x={start_left}; while held {samples[:4]}")
        order = tab_order(page)
        step("drag-reorders", have and order == ["Briefing", "Dashboard"], f"after the drop {order}")

        used = None
        if have:
            for keys in KEY_MOVES:
                browser.tab("Briefing").focus()
                for key in keys:
                    page.keyboard.press(key)
                    page.wait_for_timeout(250)
                page.wait_for_timeout(400)
                if tab_order(page) == ["Dashboard", "Briefing"]:
                    used = " ".join(keys)
                    break
                page.keyboard.press("Escape")
        browser.shot("tabs-feel-4-keyboard")
        step("keyboard-reorders", have and used is not None,
             f"after the keys {tab_order(page)}; the keys that moved it: {used}")

        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3500)
        browser.shot("tabs-feel-5-reloaded")
        order = tab_order(page)
        stored = page.evaluate(
            f"() => (JSON.parse(localStorage.getItem('aw.overview.tabs.v1') || 'null') || {{}})[{pid!r}] || null")
        want = ["Dashboard", "Briefing"] if used else ["Briefing", "Dashboard"]
        step("reload-keeps", have and order == want and (stored or {}).get("order") == [w.lower() for w in want],
             f"after the reload {order}, wanted {want}; aw.overview.tabs.v1 for the project {stored}")
    finally:
        browser.close()


# --------------------------------------------------------------------------- ac-looks-like-mock


SHAPES = ("busy", "quiet", "trouble")
WIDTHS = (1280, 1920)
MOCK_ROUTES = {"Dashboard": "overview-next", "Briefing": "overview-briefing"}
NAMED = {  # the sections the criterion names (builds only where the shape has one); the mock has no note
    "Dashboard": ("health", "tiles", "needs", "timeline"),
    "Briefing": ("headline", "since", "working", "needs", "note"),
}
SECTIONS_JS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const panel = [...document.querySelectorAll('[role=tabpanel]')].find(vis);
  const root = panel || document.querySelector('.aw-od, .aw-ob') || document.querySelector('main') || document.body;
  const rules = [[/^builds in progress/i, 'builds'], [/^needs you/i, 'needs'], [/^(activity|timeline)/i, 'timeline'],
    [/^(in flight|working)/i, 'working'], [/^(since you last looked|recently finished)/i, 'since'],
    [/^spend/i, 'spend'], [/main branch/i, 'main'], [/\bnote\b/i, 'note'], [/^builds?\b/i, 'builds']];
  const keyOf = e => {
    if (e.matches('[data-testid=overview-note]')) return 'note';
    if (e.matches('[role=status][aria-label^="Project health"], .aw-od-health')) return 'health';
    if (e.matches('[aria-label="Project at a glance"], .aw-od-tiles')) return 'tiles';
    if (e.matches('h1')) return 'headline';
    if (!e.matches('h2')) return null;
    const t = (e.innerText || e.textContent || '').trim();
    for (const [re, k] of rules) if (re.test(t)) return k;
    return null;
  };
  const keys = [], boxes = {};
  for (const e of [root, ...root.querySelectorAll('*')]) {
    const k = keyOf(e);
    if (!k || k in boxes || !vis(e)) continue;
    keys.push(k);
    boxes[k] = e.matches('h1, h2') ? (e.closest('section, header, article') || e.parentElement) : e;
  }
  const W = document.documentElement.clientWidth;
  const clipped = e => { for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
    if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(a).overflowX)) return true; } return false; };
  const offenders = [];
  for (const e of root.querySelectorAll('*')) {
    const r = e.getBoundingClientRect();
    if (r.width === 0 || (r.right <= W + 1 && r.left >= -1) || clipped(e)) continue;
    const cls = typeof e.className === 'string' ? e.className.split(' ')[0] : '';
    offenders.push(`${e.tagName.toLowerCase()}.${cls} ${Math.round(r.left)}..${Math.round(r.right)}`);
    if (offenders.length >= 5) break;
  }
  const hit = (a, b) => { const p = a.getBoundingClientRect(), q = b.getBoundingClientRect();
    return Math.max(0, Math.min(p.right, q.right) - Math.max(p.left, q.left))
      * Math.max(0, Math.min(p.bottom, q.bottom) - Math.max(p.top, q.top)) > 4; };
  const overlaps = [];
  const pairs = (list, name) => { for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
    const a = list[i][1], b = list[j][1];
    if (a.contains(b) || b.contains(a) || !hit(a, b)) continue;
    overlaps.push(`${name}: ${list[i][0]} / ${list[j][0]}`); } };
  pairs(Object.entries(boxes), 'sections');
  pairs([...root.querySelectorAll('[data-slot=overview-tile]')].filter(vis).map((e, i) => [`tile ${i + 1}`, e]), 'tiles');
  return {root: String(root.className || root.tagName).slice(0, 60), keys,
    page_overflow: document.documentElement.scrollWidth > W + 1, offenders, overlaps};
}"""


def free_port(start):
    port = start
    while port_answers(port):
        port += 1
    return port


def start_mock():
    """The mock dev server from this checkout's hub/ui (vite.mock.config.ts), on a free port."""
    port = free_port(int(os.environ.get("AW_MOCK_PORT") or 5211))
    log = open(SCRATCH / "mock.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(["npx.cmd" if os.name == "nt" else "npx", "vite", "--config", "vite.mock.config.ts",
                             "--port", str(port), "--strictPort", "--host", "127.0.0.1"], cwd=str(REPO / "hub" / "ui"),
                            stdout=log, stderr=subprocess.STDOUT)
    if not poll(lambda: port_answers(port), 90):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        raise Setup(f"the mock server did not come up; see {SCRATCH / 'mock.log'}")
    return proc, port


def mock_sections(play, port):
    """Each shape and tab of the approved mock at each width: its sections in order, and a screenshot."""
    browser = play.chromium.launch()
    found = {}
    try:
        for shape in SHAPES:
            for tab, route in MOCK_ROUTES.items():
                for width in WIDTHS:
                    page = browser.new_page(viewport={"width": width, "height": 1000})
                    query = "" if shape == "busy" else f"?state={shape}"
                    page.goto(f"http://127.0.0.1:{port}/mock.html#tab/{route}{query}")
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(1500)
                    found[(shape, tab, width)] = page.evaluate(SECTIONS_JS)
                    OUT.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(OUT / f"mock-{shape}-{tab.lower()}-{width}.png"), full_page=True)
                    page.close()
    finally:
        browser.close()
    if not any(got["keys"] for got in found.values()):
        raise Setup(f"the mock showed no sections: {found}")
    return found


def shoot_mock(port):
    """The mock's own screenshots, taken by shoot.py, beside the drive's."""
    routes = [f"tab/{r}" + ("" if s == "busy" else f"?state={s}") for s in SHAPES for r in MOCK_ROUTES.values()]
    done = subprocess.run(["py", "-3.11", str(REPO / "hub" / "ui" / "mock" / "shoot.py"), str(OUT / "mock-shoot"),
                           *routes, "--tall"], env=dict(os.environ, AW_MOCK_PORT=str(port)),
                          capture_output=True, text=True, timeout=600)
    shots = [line for line in done.stdout.splitlines() if line.strip()]
    print(f"  shoot.py: exit {done.returncode}, {len(shots)} shots in {OUT / 'mock-shoot'} "
          f"{done.stderr.strip()[-200:]}", flush=True)


def shape_project(state, shape):
    """A live project in *shape*: quiet holds nothing; busy a question, a build in progress and two
    running runs; trouble the same with a test failing on main."""
    if shape == "quiet":
        return new_project(state, shape, agents=())[0]
    pid, base = new_project(state, shape)
    held(state, pid, BUILDER)
    held(state, pid, CHECKER)  # two running runs, and no turn starts on the build
    built(state, base, pid, doc=f"spec/changes/glance-{shape}/spec.json", title=f"Glance {shape} build",
          files=(("one.txt", "Write one.txt"), ("two.txt", "Write two.txt")))
    code, out = api("POST", f"{base}/questions",
                    {"from_agent": BUILDER, "question": "Keep the cache for thirty seconds?", "blocking": False,
                     "header": "Cache", "multi_select": False,
                     "options": [{"label": "Yes", "description": "Thirty seconds of cache."},
                                 {"label": "No", "description": "No cache."}]})
    if code not in (200, 201):
        raise Setup(f"the {shape} question: {code} {str(out)[:300]}")
    if shape == "trouble":
        rw("insert into known_failing_tests (id, project_id, check_name, test, kind, first_seen, last_seen, "
           "passes, counted_runs) values (?, ?, 'hub-tests', 'tests/test_glance.py::test_main', 'fails on main', "
           "?, ?, 0, '[]')", ("kf-glance-" + secrets.token_hex(4), pid, _now(), _now()))
    return pid


def looks_like_mock(play):
    """ac-looks-like-mock: both tabs of the busy, quiet and trouble shapes at 1280 and 1920 px, against the mock."""
    state = STATES[CHECK]
    proc, port = start_mock()
    try:
        mock = mock_sections(play, port)
        shoot_mock(port)
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    for key, got in mock.items():
        if got["page_overflow"] or got["offenders"] or got["overlaps"]:
            print(f"  WARN the mock itself overflows or overlaps at {key}: {got}", flush=True)
    projects = {shape: shape_project(state, shape) for shape in SHAPES}
    for shape, pid in projects.items():
        browser = Browser(play, pid, profile=f"browser-{shape}")
        try:
            for width in WIDTHS:
                browser.page.set_viewport_size({"width": width, "height": 1000})
                browser.open("tab=overview")
                for tab in MOCK_ROUTES:
                    name = f"{shape}-{tab.lower()}-{width}"
                    handle = browser.tab(tab)
                    if handle is not None:
                        handle.click()
                        browser.page.wait_for_timeout(1200)
                    live = browser.page.evaluate(SECTIONS_JS)
                    browser.shot(f"live-{name}")
                    want = mock[(shape, tab, width)]["keys"]
                    ok, why = sections_match(want, live["keys"], NAMED[tab])
                    clean = not live["page_overflow"] and not live["offenders"] and not live["overlaps"]
                    step(name, handle is not None and ok and clean,
                         f"tab {'found' if handle is not None else 'missing'}; mock {want}; live {live['keys']} "
                         f"({why}); overflow {live['page_overflow']} {live['offenders']}; overlaps {live['overlaps']}")
        finally:
            browser.close()


LM_STEPS = [f"{s}-{t.lower()}-{w}" for s in SHAPES for w in WIDTHS for t in MOCK_ROUTES]


def end_to_end(play):
    state = STATES[CHECK]
    arrange(state)
    scenario(state, play)


STATES: dict[str, dict] = {}
CHECKS = {KEY_CHECK: (STEPS, end_to_end), "ac-note-quality": (NQ_STEPS, note_quality),
          "ac-tabs-feel": (TF_STEPS, tabs_feel), "ac-looks-like-mock": (LM_STEPS, looks_like_mock)}


# --------------------------------------------------------------------------- main


def main():
    global HUB, KEY, DB, SCRATCH, CHECK
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true", help="check the drive's own logic only; no Hub")
    parser.add_argument("--hub", default="http://127.0.0.1:8010", help="a running Hub (default the trial :8010)")
    parser.add_argument("--db", default=str(TRIAL / "agentweave.db"), help="that Hub's database")
    parser.add_argument("--own-hub", action="store_true", help="start a Hub from this checkout instead")
    parser.add_argument("--checks", default="all",
                        help=f"comma-separated checks to run (default all): {', '.join(CHECKS)}")
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
    chosen = list(CHECKS) if args.checks == "all" else [c.strip() for c in args.checks.split(",") if c.strip()]
    unknown = [c for c in chosen if c not in CHECKS]
    if unknown:
        sys.exit(f"unknown checks {unknown}; the drive has {list(CHECKS)}")
    errors: dict[str, str] = {}
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as play:
            for key in chosen:
                CHECK = key
                STATES[key] = {}
                print(f"\n== {key}", flush=True)
                try:
                    CHECKS[key][1](play)
                except Setup as exc:
                    errors[key] = str(exc)
                    print(f"SETUP {key}: {exc}", flush=True)
                except Exception as exc:  # noqa: BLE001 -- one check's crash is reported, the next still runs
                    errors[key] = f"{type(exc).__name__}: {exc}"
                    print(f"ERROR {key}: {errors[key]}", flush=True)
    finally:
        for state in STATES.values():
            for run_id in state.get("holds", []):
                release(run_id)
            for base, build in state.get("builds", []):
                if build:
                    api("POST", f"{base}/project/builds/{build}/stop")
            for base in state.get("bases", []):
                api("PATCH", f"{base}/manager/jobs/{JOB}", {"enabled": False})
        if proc is not None:
            stop_hub(proc)
    print("\n== drive_baseline")
    failed_any = False
    for key in chosen:
        steps, found = CHECKS[key][0], checks.get(key, {})
        first = first_failure(steps, found)
        reached = bool(found) and key not in errors
        failed = first is not None
        if not reached:
            detail = f"setup: {errors.get(key) or 'nothing ran'}"
        elif failed:
            detail = (f"first failing assertion {first}: {found[first][1][:600]} | steps "
                      + ", ".join(f"{n}={'pass' if found[n][0] else 'FAIL'}" for n in steps if n in found))
        else:
            detail = f"all {len(steps)} assertions passed: " + ", ".join(steps)
        failed_any = failed_any or failed or not reached
        print(f"check {key}: reached={'yes' if reached else 'no'} "
              f"failed_at_assertion={'yes' if reached and failed else 'no'} -- {detail}")
    print(f"output: {OUT}")
    sys.exit(1 if failed_any else 0)


if __name__ == "__main__":
    main()
