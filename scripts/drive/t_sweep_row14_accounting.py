"""SWEEP ROW 14 — ACCOUNTING. What a turn costs, who is told, and what the budget does not bind.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 t_sweep_row14_accounting.py
    AW_HUB=... AW_KEY=... py -3.11 t_sweep_row14_accounting.py --teardown

**Prior coverage was read first and is deliberately not re-ploughed.** Two harnesses already
touch row 14, and between them they own the budget's effect on the queue:

* `t_row18_budget_reason.py` — the budget as a *waiting reason*: `PATCH /accounting/budget` set
  and cleared, an autonomous entry parked at `token budget exhausted`, and the divergence between
  the scheduler's predicate and `GET /queue/{agent}/status`'s. It never reads `GET /accounting`.
* `t_sweep_surface.py:161-166` — three bodyless probes: `GET /accounting` for a 200, and
  `PUT /projects/{p}/settings` with a positive, negative and null `token_budget`. Shape only.

F92 established, and repaired, that a run the Hub reconciles after a crash records an
**unavailable** accounting outcome rather than nothing at all. Its closing paragraph left a
question unanswered and recorded it for the operator rather than driving it: `worker_invocations`
— the checkpoint and probe spawns — "are real model calls made on the operator's behalf and appear
on no aggregate surface and in no budget."

What **none** of them touches, and what this file is about:

* **`GET /accounting/conversations/{id}`.** The per-conversation rollup has never been called.
  Zero call sites under `scripts/drive`.
* **Whether the two budget write paths agree.** `PATCH /accounting/budget`
  (`accounting.py:43`) and `PUT /projects/{id}/settings` (`projects.py:443`) both write
  `Project.token_budget`. They validate differently, they persist different events, and they
  broadcast different events. Nothing has ever compared them.
* **What the budget's promise is worth.** The operator's own words for an exhausted budget are
  rendered by `BudgetExhaustionNotice.tsx:12`: *"Autonomous turns are paused; operator messages can
  still run."* This drives what else keeps running — the checkpoint worker and the conversation
  titler, both real model calls the Hub makes on its own initiative — and whether either one
  reaches the number the operator is reading.

One project plus a second for isolation, three real `claude-haiku-4-5` turns, one checkpoint
generation and one title generation. Every fixture is created by this script — including `git init`
and an initial commit, without which no turn can run at all — and removed by `--teardown`.

**Re-runnable on the state it leaves.** Leg 6 exhausts the budget and legs 7-8 configure
checkpointing and title generation; leg 10 puts all five settings back, and the empty-project
assertions in leg 1 run against a throwaway project created in the leg itself rather than against
the fixture, whose emptiness only the first run would see.
"""

import json
import os
import queue
import shutil
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

HUB = os.environ.get("AW_HUB", "")
KEY = os.environ.get("AW_KEY", "")
if ":8000" in HUB or ":8010" in HUB:
    print("REFUSING TO RUN: 8000 is the operator's real usage and 8010 is the other trial Hub.")
    sys.exit(1)

HAIKU = "claude-haiku-4-5-20251001"
DIR = os.environ.get("AW_DRIVE_DIR", "C:\\Users\\huida\\Documents\\aw-drive-row14")
DIR_OTHER = DIR + "-other"
DIR_EMPTY = DIR + "-empty"
NAME = os.path.basename(DIR.rstrip("\\/"))
NAME_OTHER = os.path.basename(DIR_OTHER.rstrip("\\/"))
NAME_EMPTY = os.path.basename(DIR_EMPTY.rstrip("\\/"))
SPENDER = "spender"
OTHER = "other"
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
DB = os.environ.get("AW_DB", os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db"))

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(
        ("  ok   " if cond else "  FAIL ")
        + label
        + (f"  -- {detail}" if detail and not cond else "")
    )


def note(label, value):
    print(f"  ..   {label}: {value}")


def leg(n, title):
    print(f"\n=== LEG {n}: {title}")


# ---------------------------------------------------------------------------- fixture


def find_project(name):
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return next((p["id"] for p in rows if p.get("name") == name), None)


def project_count():
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return len(rows)


def ensure_repo(path):
    """A fixture directory that is a git repository WITH A COMMIT IN IT.

    Copied from `t_sweep_row13_checkpoints.py`, and not decoration: a project whose repository has
    no commits cannot run a turn — `git worktree add ... HEAD` fails with "invalid reference: HEAD"
    and `POST /agent/trigger` answers an honest 200 with `run_id: null`.
    """
    os.makedirs(path, exist_ok=True)
    run = lambda *a: subprocess.run(a, cwd=path, capture_output=True, text=True)  # noqa: E731
    if run("git", "rev-parse", "--git-dir").returncode != 0:
        run("git", "init")
    if run("git", "rev-parse", "HEAD").returncode != 0:
        with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("row 14 accounting fixture" + chr(10))
        run("git", "add", "README.md")
        run("git", "-c", "user.email=drive@local", "-c", "user.name=drive",
            "commit", "-m", "fixture: initial commit so a worktree can be added")
    head = run("git", "rev-parse", "--short", "HEAD")
    print(f"fixture repo {path} -> HEAD {head.stdout.strip() or head.stderr.strip()}")


def ensure_project(path, name):
    found = find_project(name)
    if found:
        return found
    ensure_repo(path)
    code, body = api("POST", "/projects/open", {"path": path, "name": name})
    if code >= 300:
        sys.exit(f"could not open project {name}: {code} {body}")
    return body["id"]


def ensure_runner(project):
    _, body = api("GET", f"/projects/{project}/runners")
    rows = body if isinstance(body, list) else (body or {}).get("runners") or []
    for r in rows:
        if r.get("name") == "Haiku (cheap)":
            return r["id"]
    code, body = api(
        "POST",
        f"/projects/{project}/runners",
        {"name": "Haiku (cheap)", "cli": "claude", "model": HAIKU},
    )
    if code >= 300:
        sys.exit(f"could not create runner: {code} {body}")
    return body["id"]


def ensure_agent(project, name, runner):
    code, _ = api("POST", f"/projects/{project}/agents", {"name": name, "runner_id": runner})
    if code < 300:
        return name
    _, body = api("GET", f"/projects/{project}/agents")
    rows = body if isinstance(body, list) else (body or {}).get("agents") or []
    if any(a.get("name") == name for a in rows):
        return name
    sys.exit(f"could not create or find agent {name}: {body}")


def teardown():
    for name in (NAME, NAME_OTHER, NAME_EMPTY):
        pid = find_project(name)
        if pid:
            code, _ = api("DELETE", f"/projects/{pid}")
            print(f"deleted {name} ({pid}) -> {code}")
    for path in (DIR, DIR_OTHER, DIR_EMPTY):
        if os.path.isdir(path):
            # `ignore_errors=True` alone leaves `.git` behind on Windows: git marks loose objects
            # read-only and `os.remove` raises on them. Clear the bit and retry.
            def _force(func, target, _exc):
                os.chmod(target, stat.S_IWRITE)
                func(target)

            shutil.rmtree(path, onerror=_force)
            print(f"removed {path} -> exists={os.path.isdir(path)}")
    print(f"projects now: {project_count()}")


if "--teardown" in sys.argv:
    teardown()
    sys.exit(0)


P = ensure_project(DIR, NAME)
P2 = ensure_project(DIR_OTHER, NAME_OTHER)
RUNNER = ensure_runner(P)
RUNNER2 = ensure_runner(P2)
ensure_agent(P, SPENDER, RUNNER)
ensure_agent(P2, OTHER, RUNNER2)
A = f"/projects/{P}"
A2 = f"/projects/{P2}"
print(f"fixture: {NAME}={P}  other={NAME_OTHER}={P2}  agents={SPENDER},{OTHER}  tag={TAG}")


# ---------------------------------------------------------------------------- helpers


def db_rows(sql, args=()):
    """Read the Hub's database read-only. Observation only; the Hub owns this file."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    try:
        cur = con.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        con.close()


def db_run(run_id):
    rows = db_rows("SELECT id, status, exit_code, error FROM runs WHERE id = ?", (run_id,))
    return rows[0] if rows else None


def usage_rows(project_id):
    return db_rows(
        "SELECT id, run_id, agent, status, runner, model, total_tokens, "
        "api_equivalent_usd_micros, observed_at FROM turn_usage WHERE project_id = ? "
        "ORDER BY observed_at, id",
        (project_id,),
    )


def worker_rows(project_id):
    return db_rows(
        "SELECT id, kind, cli, model, outcome, input_tokens, output_tokens, "
        "cost_usd_micros, created_at FROM worker_invocations WHERE project_id = ? "
        "ORDER BY created_at, id",
        (project_id,),
    )


def accounting(prefix=None):
    code, body = api("GET", f"{prefix or A}/accounting")
    return code, body if isinstance(body, dict) else {}


def settings(**fields):
    return api("PUT", f"{A}/settings", fields)


def get_settings():
    code, body = api("GET", f"{A}/settings")
    return code, body if isinstance(body, dict) else {}


def conversations(agent, prefix=None):
    code, body = api("GET", f"{prefix or A}/agent/{agent}/conversations")
    rows = body if isinstance(body, list) else (body or {}).get("conversations") or []
    return code, rows


def newest_conversation(agent, prefix=None):
    _, rows = conversations(agent, prefix)
    return rows[0] if rows else None


def run_turn(agent, message, *, prefix=None, wait=420, conversation_id=None):
    """One real agent turn, waited out on the run row. Returns (run_id, status)."""
    payload = {"agent": agent, "message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    code, body = api("POST", f"{prefix or A}/agent/trigger", payload)
    if code not in (200, 201, 202):
        return None, f"trigger {code} {str(body)[:200]}"
    run_id = (body or {}).get("run_id") or (body or {}).get("id")
    if not run_id:
        return None, f"no run started: {json.dumps(body)[:300]}"
    deadline = time.time() + wait
    row = None
    while time.time() < deadline:
        time.sleep(6)
        row = db_run(run_id)
        if row and row["status"] not in ("running", "queued", "starting"):
            return run_id, row["status"]
    return run_id, f"timeout(last={(row or {}).get('status')})"


def event_kinds(limit=200):
    """The project's own activity history, newest first.

    The row key is `type`, not `event_type` — the first version of this harness read the wrong one
    and reported `[None]` for every event, which looked exactly like a Hub that records nothing.
    """
    code, body = api("GET", f"{A}/events/history?limit={limit}")
    rows = body if isinstance(body, list) else (body or {}).get("events") or []
    return code, [(r.get("type"), r.get("timestamp")) for r in rows]


class SseTap:
    """A real SSE subscriber, so 'what is a listening dashboard told' is measured not read.

    EventSource cannot set headers, so the Hub issues a signed ticket; this does the same dance a
    browser does. Events arrive on a queue; `drain()` returns everything seen since the last call.
    """

    def __init__(self, project_id):
        self.q = queue.Queue()
        self.stop = threading.Event()
        code, body = api("GET", f"/projects/{project_id}/events/ticket")
        self.ticket = (body or {}).get("token") or (body or {}).get("ticket")
        self.ok = code == 200 and bool(self.ticket)
        self.project_id = project_id
        self.thread = None

    def start(self):
        if not self.ok:
            return False
        url = f"{HUB}/api/v1/projects/{self.project_id}/events?token={self.ticket}"

        def pump():
            try:
                req = urllib.request.Request(url, method="GET")
                req.add_header("Accept", "text/event-stream")
                with urllib.request.urlopen(req, timeout=180) as resp:
                    current = None
                    for raw in resp:
                        if self.stop.is_set():
                            return
                        line = raw.decode("utf-8", "replace").strip()
                        if line.startswith("event:"):
                            current = line.split(":", 1)[1].strip()
                        elif line.startswith("data:") and current:
                            self.q.put((current, line.split(":", 1)[1].strip()))
                            current = None
            except Exception as exc:  # noqa: BLE001 — a dead tap is a measurement, not a crash
                self.q.put(("__error__", f"{type(exc).__name__}: {exc}"))

        self.thread = threading.Thread(target=pump, daemon=True)
        self.thread.start()
        time.sleep(2)  # let the stream open and its hello arrive before anything is provoked
        self.drain()
        return True

    def drain(self, settle=3.0):
        time.sleep(settle)
        seen = []
        while True:
            try:
                seen.append(self.q.get_nowait())
            except queue.Empty:
                break
        return seen

    def close(self):
        self.stop.set()


# ---------------------------------------------------------------------------- LEG 1


leg(1, "an empty project's accounting says nothing rather than zero")

# A THROWAWAY project, not the fixture: the fixture is only empty on a first run, and an assertion
# that passes once is not an assertion. This one is created here and deleted at the end of the leg.
ensure_repo(DIR_EMPTY)
code, body = api("POST", "/projects/open", {"path": DIR_EMPTY, "name": NAME_EMPTY})
PE = (body or {}).get("id") if code < 300 else find_project(NAME_EMPTY)
ok("a throwaway project opens", bool(PE), f"{code} {str(body)[:160]}")

code, acc = accounting(f"/projects/{PE}")
ok("GET /accounting answers 200 on a project that has never run", code == 200, str(code))
proj = acc.get("project") or {}
ok("no turns measured", proj.get("measured_turns") == 0, json.dumps(proj))
ok("no turns unavailable", proj.get("unavailable_turns") == 0, json.dumps(proj))
ok(
    "totals are null, not zero",
    proj.get("total_tokens") is None and proj.get("input_tokens") is None,
    json.dumps(proj),
)
ok("no agent has spent anything", acc.get("agents") == [], json.dumps(acc.get("agents"))[:200])
ok("no recent turns", acc.get("recent_turns") == [], json.dumps(acc.get("recent_turns"))[:200])
bud = acc.get("budget") or {}
ok(
    "no budget is set and nothing is exhausted",
    bud.get("limit_tokens") is None
    and bud.get("used_tokens") == 0
    and bud.get("remaining_tokens") is None
    and bud.get("exhausted") is False,
    json.dumps(bud),
)
disp = acc.get("preferred_display") or {}
ok(
    "the display says usage is unavailable, not $0.00",
    disp.get("kind") == "unavailable",
    json.dumps(disp),
)
if PE:
    api("DELETE", f"/projects/{PE}")
    shutil.rmtree(DIR_EMPTY, onerror=lambda f, t, e: (os.chmod(t, stat.S_IWRITE), f(t)))
ok("the throwaway project is gone again", find_project(NAME_EMPTY) is None)


# ---------------------------------------------------------------------------- LEG 2

leg(2, "two routes write the same budget — do they refuse the same things?")

REFUSALS = [
    ("zero", 0),
    ("negative", -5),
    ("a float", 1.5),
    ("a string", "1000"),
    ("a bool", True),
]
patch_codes, put_codes = {}, {}
for label, value in REFUSALS:
    c1, b1 = api("PATCH", f"{A}/accounting/budget", {"token_budget": value})
    patch_codes[label] = c1
    c2, b2 = api("PUT", f"{A}/settings", {"token_budget": value})
    put_codes[label] = c2
    note(f"{label} ({value!r})", f"PATCH -> {c1}   PUT /settings -> {c2}")

ok("PATCH refuses zero", patch_codes["zero"] == 422, str(patch_codes["zero"]))
ok("PUT /settings refuses zero", put_codes["zero"] == 422, str(put_codes["zero"]))
ok("PATCH refuses a negative budget", patch_codes["negative"] == 422, str(patch_codes["negative"]))
ok(
    "PUT /settings refuses a negative budget",
    put_codes["negative"] == 422,
    str(put_codes["negative"]),
)
ok(
    "the two routes agree on every malformed budget",
    all(patch_codes[k] == put_codes[k] for k, _ in REFUSALS),
    f"PATCH={patch_codes}  PUT={put_codes}",
)

code, body = api("PATCH", f"{A}/accounting/budget", {})
ok("PATCH with no token_budget at all is refused", code == 422, f"{code} {str(body)[:160]}")

code, body = api("PATCH", f"{A}/accounting/budget", {"token_budget": 500000})
ok("PATCH accepts a positive budget", code == 200, f"{code} {str(body)[:200]}")
ok(
    "and answers with the budget state it just wrote",
    isinstance(body, dict) and body.get("limit_tokens") == 500000,
    str(body)[:200],
)
_, sett = get_settings()
ok(
    "GET /settings reports the budget the accounting route wrote",
    sett.get("token_budget") == 500000,
    str(sett.get("token_budget")),
)
_, acc = accounting()
ok(
    "GET /accounting reports it too",
    (acc.get("budget") or {}).get("limit_tokens") == 500000,
    json.dumps(acc.get("budget")),
)

code, _ = settings(token_budget=400000)
ok("PUT /settings accepts a positive budget", code == 200, str(code))
_, acc = accounting()
ok(
    "GET /accounting reports what the settings route wrote",
    (acc.get("budget") or {}).get("limit_tokens") == 400000,
    json.dumps(acc.get("budget")),
)

code, body = api("PATCH", f"{A}/accounting/budget", {"token_budget": None})
ok("PATCH clears the budget", code == 200 and (body or {}).get("limit_tokens") is None, str(body))
_, sett = get_settings()
ok("and GET /settings agrees it is cleared", sett.get("token_budget") is None, str(sett))


# ---------------------------------------------------------------------------- LEG 3

leg(3, "what a listening dashboard is told when the budget changes")

tap = SseTap(P)
started = tap.start()
ok("an SSE ticket opens a stream", started, "no ticket or stream")

# The newest few, not a length delta: `GET /events/history` is capped, so on the second run the
# list does not grow and a delta of `len(after) - len(before)` reports the wrong slice entirely.
_, hist_0 = event_kinds(limit=5)
api("PATCH", f"{A}/accounting/budget", {"token_budget": 300000})
patch_seen = [kind for kind, _ in tap.drain()] if started else []
_, hist_1 = event_kinds(limit=5)
# The rows themselves, timestamp included — NOT their types. Every budget write persists the same
# type, so "the newest entry is an accounting_budget_updated" was satisfied by the PREVIOUS
# write's row and reported a pass for a route that had persisted nothing at all.
patch_new = [row for row in hist_1 if row not in hist_0]
note("SSE after PATCH /accounting/budget", patch_seen)
note("history rows that are new since the PATCH", patch_new)

api("PUT", f"{A}/settings", {"token_budget": 200000})
put_seen = [kind for kind, _ in tap.drain()] if started else []
_, hist_2 = event_kinds(limit=5)
put_new = [row for row in hist_2 if row not in hist_1]
note("SSE after PUT /settings token_budget", put_seen)
note("history rows that are new since the settings write", put_new)
tap.close()

ok(
    "PATCH /accounting/budget tells listeners the budget changed",
    "accounting_budget_updated" in patch_seen,
    str(patch_seen),
)
ok(
    "PATCH /accounting/budget is written to the project's own event history",
    any(row[0] == "accounting_budget_updated" for row in patch_new),
    str(patch_new),
)
# Both routes write `Project.token_budget` and both were just given a different number. The
# accounting panel's "Project token budget" control sends the first; the environment panel's
# "Token budget" input (ProjectSettingsPanel.tsx:144) sends the second.
ok(
    "PUT /settings ALSO tells listeners the budget changed",
    "accounting_budget_updated" in put_seen,
    f"{put_seen} -- projects.py:527 broadcasts only project_settings_updated, which "
    f"useSSE.ts:551 answers by invalidating ['projects'] and never "
    f"['project', id, 'accounting']",
)
ok(
    "PUT /settings records the budget change in the project's history",
    bool(put_new),
    f"{put_new} -- projects.py:526-529 broadcasts without calling persist_event, so a "
    f"settings change leaves no trace an operator can audit",
)

api("PATCH", f"{A}/accounting/budget", {"token_budget": None})


# ---------------------------------------------------------------------------- LEG 4

leg(4, "one real turn, measured")

_, acc_base = accounting()
base = acc_base.get("project") or {}
base_measured = base.get("measured_turns") or 0
base_total = base.get("total_tokens") or 0
note("baseline", json.dumps(base))
usage_before = len(usage_rows(P))
run_id, status = run_turn(
    SPENDER,
    "Reply with exactly the six characters ROW14A and nothing else. Do not use any tools.",
)
note("run", f"{run_id} -> {status}")
ok("the turn ended", status == "completed", str(status))

rows = usage_rows(P)
ok("exactly one new accounting row", len(rows) == usage_before + 1, f"{usage_before} -> {len(rows)}")
mine = next((r for r in rows if r["run_id"] == run_id), None)
ok("the row belongs to this run", mine is not None)
if mine:
    note("row", json.dumps(mine, default=str))
    ok("its status is measured", mine["status"] == "measured", str(mine["status"]))
    ok("it carries a token total", (mine["total_tokens"] or 0) > 0, str(mine["total_tokens"]))
    ok("it records which runner spent it", mine["runner"] == "claude", str(mine["runner"]))
    ok("it records which model", (mine["model"] or "").startswith("claude-haiku"), str(mine["model"]))

_, acc = accounting()
proj = acc.get("project") or {}
note("project summary", json.dumps(proj))
ok(
    "the project counts exactly one more measured turn",
    proj.get("measured_turns") == base_measured + 1,
    f"{base_measured} -> {proj.get('measured_turns')}",
)
ok("nothing is unavailable", proj.get("unavailable_turns") == 0, json.dumps(proj))
ok(
    "the project total grew by exactly what the row says",
    mine is not None and (proj.get("total_tokens") or 0) - base_total == mine["total_tokens"],
    f"{base_total} -> {proj.get('total_tokens')} vs row {mine and mine['total_tokens']}",
)
agents = acc.get("agents") or []
ok("the spender is attributed", [a.get("agent") for a in agents] == [SPENDER], json.dumps(agents))
recent = acc.get("recent_turns") or []
ok("the turn is in recent_turns", any(r.get("run_id") == run_id for r in recent), str(len(recent)))
disp = acc.get("preferred_display") or {}
note("preferred_display", json.dumps(disp))
ok(
    "the display is no longer 'unavailable'",
    disp.get("kind") in ("allowance", "api_equivalent", "tokens"),
    json.dumps(disp),
)

CONV = (newest_conversation(SPENDER) or {}).get("id")
note("conversation", CONV)
code, conv_acc = api("GET", f"{A}/accounting/conversations/{CONV}")
conv_acc = conv_acc if isinstance(conv_acc, dict) else {}
ok("the conversation rollup answers 200", code == 200, f"{code} {str(conv_acc)[:200]}")
note("conversation rollup", json.dumps(conv_acc))
# The conversation is new on every run — `POST /agent/trigger` without a conversation_id opens
# one — so its rollup is this turn and nothing else, whatever the project has spent before.
ok(
    "the rollup is exactly this turn, not the project's history",
    mine is not None
    and conv_acc.get("total_tokens") == mine["total_tokens"]
    and conv_acc.get("measured_turns") == 1,
    json.dumps(conv_acc),
)


# ---------------------------------------------------------------------------- LEG 5

leg(5, "the conversation rollup asked about something that is not there")

# NOT folded into a shared probe loop: each of these is a different question, and the loop shape
# that once put a route's normal call beside its refusals is a mistake this sweep has already made.
code, body = api("GET", f"{A}/accounting/conversations/conv-does-not-exist")
note("a conversation id that does not exist", f"{code} {json.dumps(body)[:220]}")
ok(
    "an unknown conversation is refused rather than answered with zeros",
    code == 404,
    f"{code} {json.dumps(body)[:220]} -- accounting.py:33-40 passes the id straight to "
    f"conversation_usage, whose aggregate over no rows is a valid empty summary",
)

_, before_p1 = accounting()
_, before_p2 = accounting(A2)
p1_before = (before_p1.get("project") or {}).get("measured_turns") or 0
p2_before = (before_p2.get("project") or {}).get("measured_turns") or 0
CONV_OTHER = None
run2, status2 = run_turn(
    OTHER,
    "Reply with exactly the six characters ROW14B and nothing else. Do not use any tools.",
    prefix=A2,
)
note("other-project run", f"{run2} -> {status2}")
ok("the other project's turn ended", status2 == "completed", str(status2))
CONV_OTHER = (newest_conversation(OTHER, A2) or {}).get("id")
note("other project's conversation", CONV_OTHER)

code, body = api("GET", f"{A}/accounting/conversations/{CONV_OTHER}")
body = body if isinstance(body, dict) else {}
note("another project's conversation, asked under this one", f"{code} {json.dumps(body)[:220]}")
ok(
    "a conversation belonging to another project is refused, not silently zeroed",
    code == 404,
    f"{code} {json.dumps(body)[:220]} -- usage_accounting.py:186-196 filters on "
    f"TurnUsage.project_id, so the isolation holds but is indistinguishable from absence",
)

_, acc_p2 = accounting(A2)
_, acc_p1 = accounting()
ok(
    "the other project's turn did not move this project's total",
    (acc_p1.get("project") or {}).get("measured_turns") == p1_before,
    f"{p1_before} -> {(acc_p1.get('project') or {}).get('measured_turns')}",
)
ok(
    "and it moved the other project's by exactly one",
    (acc_p2.get("project") or {}).get("measured_turns") == p2_before + 1,
    f"{p2_before} -> {(acc_p2.get('project') or {}).get('measured_turns')}",
)
ok(
    "the two projects' agent lists do not overlap",
    {a.get("agent") for a in acc_p1.get("agents") or []}
    != {a.get("agent") for a in acc_p2.get("agents") or []},
    f"{acc_p1.get('agents')} vs {acc_p2.get('agents')}",
)


# ---------------------------------------------------------------------------- LEG 6

leg(6, "the budget's promise: autonomous turns pause, operator messages run")

_, acc = accounting()
used = ((acc.get("project") or {}).get("total_tokens")) or 0
code, bud = api("PATCH", f"{A}/accounting/budget", {"token_budget": max(1, used // 2)})
bud = bud if isinstance(bud, dict) else {}
note("budget set below what is already spent", json.dumps(bud))
ok("the budget reports itself exhausted", bud.get("exhausted") is True, json.dumps(bud))
_, acc = accounting()
ok(
    "and GET /accounting says so too",
    (acc.get("budget") or {}).get("exhausted") is True,
    json.dumps(acc.get("budget")),
)
ok(
    "remaining is clamped at zero rather than going negative",
    (acc.get("budget") or {}).get("remaining_tokens") == 0,
    json.dumps(acc.get("budget")),
)

_, acc_pre3 = accounting()
pre3_measured = (acc_pre3.get("project") or {}).get("measured_turns") or 0
# The operator's own message. `BudgetExhaustionNotice` promises this still runs.
run3, status3 = run_turn(
    SPENDER,
    "Reply with exactly the six characters ROW14C and nothing else. Do not use any tools.",
    conversation_id=CONV,
)
note("operator turn while exhausted", f"{run3} -> {status3}")
ok("an operator message still runs when the budget is exhausted", status3 == "completed", str(status3))

_, acc = accounting()
proj = acc.get("project") or {}
ok(
    "and the turn it just paid for is counted",
    proj.get("measured_turns") == pre3_measured + 1,
    f"{pre3_measured} -> {proj.get('measured_turns')}",
)
note("used now", json.dumps(acc.get("budget")))


# ---------------------------------------------------------------------------- LEG 7

leg(7, "what the Hub spends on its own initiative, while the budget says spending is paused")

workers_before = worker_rows(P)
usage_before = len(usage_rows(P))
_, acc_before = accounting()
used_before = ((acc_before.get("project") or {}).get("total_tokens")) or 0

code, _ = settings(
    checkpoint_runner_id=RUNNER,
    checkpoint_mode="offered",
    checkpoint_threshold_mode="tokens",
    checkpoint_threshold_value=2000,
)
ok("checkpointing is configured", code == 200, str(code))

code, cp = api("POST", f"{A}/conversations/{CONV}/checkpoint", {}, timeout=420)
cp = cp if isinstance(cp, dict) else {}
note("checkpoint", f"{code} {json.dumps(cp, default=str)[:260]}")
ok("the operator can take a checkpoint with the budget exhausted", code == 201, str(code))

workers_after = worker_rows(P)
new_workers = [w for w in workers_after if w["id"] not in {x["id"] for x in workers_before}]
note("worker invocations this leg", json.dumps(new_workers, default=str)[:700])
ok("taking a checkpoint really spent a model call", len(new_workers) >= 1, str(len(new_workers)))
worker_cost = sum((w["cost_usd_micros"] or 0) for w in new_workers)
worker_tokens = sum(((w["input_tokens"] or 0) + (w["output_tokens"] or 0)) for w in new_workers)
note("worker cost", f"{worker_cost} usd_micros over {worker_tokens} tokens")

_, acc_after = accounting()
proj_after = acc_after.get("project") or {}
used_after = proj_after.get("total_tokens") or 0
ok(
    "no accounting row was written for the checkpoint's spend",
    len(usage_rows(P)) == usage_before,
    f"{usage_before} -> {len(usage_rows(P))}",
)
ok(
    "the project total the operator reads did not move",
    used_after == used_before,
    f"{used_before} -> {used_after}",
)
ok(
    "and neither did the budget's used_tokens",
    (acc_after.get("budget") or {}).get("used_tokens") == used_before,
    json.dumps(acc_after.get("budget")),
)
ok(
    "the checkpoint's cost is recorded ONLY in worker_invocations",
    worker_tokens > 0 and used_after == used_before,
    f"worker_tokens={worker_tokens} project_total unchanged={used_after == used_before}",
)

# The conversation titler is the second spender, and unlike the checkpoint worker it leaves no
# cost record of any kind — `conversation_titles.py` predates `worker_invocations` and was never
# joined to it.
code, _ = settings(conversation_title_mode="generate", conversation_title_runner_id=RUNNER)
ok("title generation is configured", code == 200, str(code))
# The fallback title is the message truncated, so "a title was generated" is "the title is no
# longer the message" -- NOT "the title does not contain my marker". The marker is in the prompt
# and a titler is free to quote it, which it did: the first version of this check called a
# perfectly good generated title a failure.
TITLE_PROMPT = "Reply with exactly the six characters ROW14D and nothing else. Do not use any tools."
workers_pre_title = len(worker_rows(P))
usage_pre_title = len(usage_rows(P))
run4, status4 = run_turn(
    SPENDER,
    TITLE_PROMPT,
)
note("titled-conversation turn", f"{run4} -> {status4}")
CONV_T = (newest_conversation(SPENDER) or {}).get("id")
titled = None
for _ in range(20):
    _, rows = conversations(SPENDER)
    row = next((r for r in rows if r.get("id") == CONV_T), None)
    current = (row or {}).get("title") or ""
    if current and not TITLE_PROMPT.startswith(current.rstrip(".").rstrip("…")):
        titled = current
        break
    time.sleep(3)
note("generated title", titled)
ok("a title was generated by a real model call", bool(titled), str(titled))
ok(
    "the titler wrote no worker_invocations row",
    len(worker_rows(P)) == workers_pre_title,
    f"{workers_pre_title} -> {len(worker_rows(P))}",
)
ok(
    "the titler wrote no accounting row of its own",
    len(usage_rows(P)) == usage_pre_title + 1,  # the agent turn's row, and nothing else
    f"{usage_pre_title} -> {len(usage_rows(P))}",
)


# ---------------------------------------------------------------------------- LEG 8

leg(8, "one accounting outcome per ended run — F92's invariant, re-driven")

ended = db_rows(
    "SELECT r.id, r.status, (SELECT count(*) FROM turn_usage u WHERE u.run_id = r.id) AS n "
    "FROM runs r WHERE r.project_id = ? AND r.status NOT IN ('running','queued','starting')",
    (P,),
)
note("ended runs", json.dumps(ended, default=str)[:400])
ok("every ended run has an accounting outcome", all(r["n"] == 1 for r in ended), json.dumps(ended))
dupes = db_rows(
    "SELECT run_id, count(*) c FROM turn_usage WHERE project_id = ? GROUP BY run_id HAVING c > 1",
    (P,),
)
ok("no run has two", dupes == [], json.dumps(dupes))

_, acc = accounting()
proj = acc.get("project") or {}
summed = sum((r["total_tokens"] or 0) for r in usage_rows(P) if r["status"] == "measured")
ok(
    "the reported total is the sum of the measured rows",
    proj.get("total_tokens") == summed,
    f"{proj.get('total_tokens')} vs {summed}",
)
ok(
    "measured_turns counts the measured rows",
    proj.get("measured_turns") == len([r for r in usage_rows(P) if r["status"] == "measured"]),
    json.dumps(proj),
)


# ---------------------------------------------------------------------------- LEG 9

leg(9, "the accounting routes refuse a caller from outside")

for label, path in (
    ("project accounting", f"/projects/{P}/accounting"),
    ("conversation rollup", f"/projects/{P}/accounting/conversations/{CONV}"),
):
    req = urllib.request.Request(HUB + "/api/v1" + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            code = r.status
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", 0)
    ok(f"{label} refuses an unauthenticated caller", code in (401, 403), str(code))

code, _ = api("GET", "/projects/proj-nope-nope/accounting")
ok("an unknown project is 404, not an empty snapshot", code == 404, str(code))


# ---------------------------------------------------------------------------- LEG 10

leg(10, "put the project back the way it was found")

code, _ = api("PATCH", f"{A}/accounting/budget", {"token_budget": None})
ok("the budget is cleared", code == 200, str(code))
code, _ = settings(
    checkpoint_mode="off",
    checkpoint_threshold_mode=None,
    checkpoint_threshold_value=None,
    checkpoint_runner_id=None,
    conversation_title_mode="truncate",
    conversation_title_runner_id=None,
)
ok("checkpointing and titling are switched back off", code == 200, str(code))
_, sett = get_settings()
ok(
    "the project is back to its defaults",
    sett.get("token_budget") is None
    and sett.get("checkpoint_mode") == "off"
    and sett.get("conversation_title_mode") == "truncate",
    json.dumps(
        {
            k: sett.get(k)
            for k in ("token_budget", "checkpoint_mode", "conversation_title_mode")
        }
    ),
)

_, jobs = api("GET", f"{A}/jobs")
job_rows = jobs if isinstance(jobs, list) else (jobs or {}).get("jobs") or []
ok("no job was created, so none is left enabled", not any(j.get("enabled") for j in job_rows))


# ---------------------------------------------------------------------------- summary

print(f"\n{'=' * 70}\n{len(PASS)} passed / {len(FAIL)} failed")
for f in FAIL:
    print(f"  FAILED: {f}")
