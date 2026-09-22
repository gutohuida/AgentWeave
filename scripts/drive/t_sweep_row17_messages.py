"""SWEEP ROW 17 — MESSAGES. Agent-to-agent peer mail, and the operator surface built on it.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 t_sweep_row17_messages.py
    AW_HUB=... AW_KEY=... py -3.11 t_sweep_row17_messages.py --teardown

**Prior coverage was read first.** Across 95 files under `scripts/drive`, exactly one line ever
touches the messages route surface (`t_hop.py:38`, a bare `GET /projects/{P}/messages` whose body
is printed, not asserted). `FINDINGS.md` has no finding against `api/v1/messages.py`. The queue
side of peer mail is well ploughed (T-HOP, row 7); the *messages* side is not. So this harness asks
the questions that only a caller of these three routes can answer:

* **What the operator's own `POST /messages` produces.** `create_message_for_actor` set
  `hop_depth = hop_budget + 1` whenever `run_id` was absent — which is every operator call, since
  only a live run has one. And what the agent's queue panel then told the operator about it.

**Since 2026-09-22 legs 1, 1b, 4 and 6 verify the repairs** of what they found (F258/F395, F261,
F262, F263) rather than detecting the defects; the questions below are the ones first asked.
* **Who ever marks a message read.** `msg.read = True` appears once in the whole Hub
  (`messages.py:375`). Two consumers depend on it: `GET /status`'s `message_counts.pending`, which
  the StatusBar renders as the `N msgs` chip, and `scheduler.py:420`'s loop pending-request reason.
* **Whether the screen those routes were built for is shipped.** `MessagesFeed`, `MessageCard`,
  `ConversationGroup`, `useMessages`, `useMessageHistory`, `useMarkRead` — 358 lines of component
  and three hooks. F215's lesson: what the operator runs is `hub/hub/static/ui`.
* **Whether the sender is checked the way the recipient is.** The recipient is resolved against the
  roster and refused with a 404; `body.sender` is a free 64-character string.
* **What the `conversation` query filter does with a conversation id.** It splits on `":"` and
  applies nothing when there is no colon.
* **Whether peer mail sent by a real agent still works.** The contrast leg: one live
  `claude-haiku-4-5` turn calling `send_message`, asserted on rows the harness did not write.

Two projects, three agents, one archived agent, one real turn. Every fixture is created here —
including `git init` and an initial commit, without which no turn can run — and removed by
`--teardown`.

**Re-runnable on the state it leaves.** Every message carries the run tag, every count is a delta
against a baseline captured in its own leg, no leg asserts an absolute total, and no leg leaves a
job enabled or a working tree dirty.
"""

import glob
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

HUB = os.environ.get("AW_HUB", "")
KEY = os.environ.get("AW_KEY", "")
if ":8000" in HUB or ":8010" in HUB:
    print("REFUSING TO RUN: 8000 is the operator's real usage and 8010 is the other trial Hub.")
    sys.exit(1)

HAIKU = "claude-haiku-4-5-20251001"
DIR = os.environ.get("AW_DRIVE_DIR", "C:\\Users\\huida\\Documents\\aw-drive-row17")
DIR2 = DIR + "-peer"
NAME = os.path.basename(DIR.rstrip("\\/"))
NAME2 = os.path.basename(DIR2.rstrip("\\/"))
ALPHA, BRAVO, RETIRED = "alpha", "bravo", "retired"
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
DB = os.environ.get("AW_DB", os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db"))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI_ASSETS = os.path.join(ROOT, "hub", "hub", "static", "ui", "assets")
UI_SRC = os.path.join(ROOT, "hub", "ui", "src")

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


def git(path, *args):
    return subprocess.run(["git", *args], cwd=path, capture_output=True, text=True)


def find_project(name):
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return next((p["id"] for p in rows if p.get("name") == name), None)


def project_count():
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return len(rows)


def ensure_repo(path, label):
    """A fixture directory that is a git repository WITH A COMMIT IN IT.

    Copied from `t_sweep_row16_logs_events_sse.py`, itself from row 15, and not decoration: a
    project whose repository has no commits cannot run a turn — `git worktree add ... HEAD` fails
    with "invalid reference: HEAD" and `POST /agent/trigger` answers an honest 200 with
    `run_id: null`.
    """
    os.makedirs(path, exist_ok=True)
    if git(path, "rev-parse", "--git-dir").returncode != 0:
        git(path, "init")
    if git(path, "rev-parse", "HEAD").returncode != 0:
        with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as fh:
            fh.write(label + " fixture\n")
        git(path, "add", "README.md")
        git(path, "-c", "user.email=drive@local", "-c", "user.name=drive",
            "commit", "-m", "fixture: initial commit so a turn can run")


def ensure_project(path, name):
    found = find_project(name)
    if found:
        return found
    ensure_repo(path, name)
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
        "POST", f"/projects/{project}/runners",
        {"name": "Haiku (cheap)", "cli": "claude", "model": HAIKU},
    )
    if code >= 300:
        sys.exit(f"could not create runner: {code} {body}")
    return body["id"]


def ensure_agent(project, name, runner):
    code, _ = api("POST", f"/projects/{project}/agents", {"name": name, "runner_id": runner})
    if code < 300:
        return name
    # `lifecycle=all`, not the default: leg 5 archives one of these agents, and the default
    # listing excludes archived rows — so a second run of this harness used to abort in setup
    # believing the agent it had archived itself no longer existed.
    _, body = api("GET", f"/projects/{project}/agents?lifecycle=all")
    rows = body if isinstance(body, list) else (body or {}).get("agents") or []
    if any(a.get("name") == name for a in rows):
        return name
    sys.exit(f"could not create or find agent {name}: {str(body)[:300]}")


def teardown():
    for name in (NAME, NAME2):
        pid = find_project(name)
        if pid:
            code, _ = api("DELETE", f"/projects/{pid}")
            print(f"deleted {name} ({pid}) -> {code}")
    for path in (DIR, DIR2):
        if os.path.isdir(path):
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
P2 = ensure_project(DIR2, NAME2)
RUNNER = ensure_runner(P)
RUNNER2 = ensure_runner(P2)
for _a in (ALPHA, BRAVO, RETIRED):
    ensure_agent(P, _a, RUNNER)
for _a in (ALPHA, BRAVO):
    ensure_agent(P2, _a, RUNNER2)
A = f"/projects/{P}"
A2 = f"/projects/{P2}"
print(f"fixture: {NAME}={P}  peer={NAME2}={P2}  tag={TAG}")


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


def send(project_path, sender, recipient, content, **extra):
    """`sender=None` is the operator. A named sender without a `run_id` is refused 422 since
    F261's repair, so only leg 4 still passes one — to check that it is."""
    body = {"to": recipient, "subject": f"row17 {TAG}", "content": content}
    if sender is not None:
        body["from"] = sender
    body.update(extra)
    return api("POST", f"{project_path}/messages", body)


def bundle_files():
    return sorted(glob.glob(os.path.join(UI_ASSETS, "*.js")))


def in_bundle(needle):
    for path in bundle_files():
        with open(path, encoding="utf-8", errors="replace") as fh:
            if needle in fh.read():
                return os.path.basename(path)
    return None


def src_refs(symbol, exclude_prefix):
    """Every file under hub/ui/src outside *exclude_prefix* that names *symbol*."""
    hits = []
    for path in glob.glob(os.path.join(UI_SRC, "**", "*.ts*"), recursive=True):
        rel = os.path.relpath(path, UI_SRC).replace("\\", "/")
        if rel.startswith(exclude_prefix):
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            if re.search(r"\b" + re.escape(symbol) + r"\b", fh.read()):
                hits.append(rel)
    return hits


def trigger(agent, message):
    code, body = api("POST", f"{A}/agent/trigger", {"agent": agent, "message": message}, timeout=90)
    if code not in (200, 201, 202):
        return None, f"trigger {code} {str(body)[:200]}"
    run_id = (body or {}).get("run_id") or (body or {}).get("id")
    return (run_id, "started") if run_id else (None, f"no run: {json.dumps(body)[:200]}")


def wait_run(run_id, wait=420):
    deadline = time.time() + wait
    while time.time() < deadline:
        rows = db_rows("SELECT id, status FROM runs WHERE id = ?", (run_id,))
        if rows and rows[0]["status"] not in ("running", "queued", "starting"):
            return rows[0]["status"]
        time.sleep(5)
    return "timeout"


# ---------------------------------------------------------------------------- LEG 0

leg(0, "preflight — the Hub under test is the one this checkout describes")

code, _probe = api("GET", "/projects")
ok("the Hub on this port answers an authenticated read", code == 200, str(code))
BASE_PROJECTS = project_count()
note("projects before this run", BASE_PROJECTS)

# Identify the database by looking up this run's OWN fixture row in it, rather than trusting a doc.
mine = db_rows("SELECT id, name FROM projects WHERE id = ?", (P,))
ok("the database read here is the one the Hub on this port serves",
   bool(mine) and mine[0]["name"] == NAME, f"{DB} -> {mine}")

limits = db_rows("SELECT hop_budget, turn_delivery_cap FROM projects WHERE id = ?", (P,))[0]
HOP_BUDGET = limits["hop_budget"]
note("project hop_budget / turn_delivery_cap", limits)


# ---------------------------------------------------------------------------- LEG 1

leg(1, "the operator's own POST /messages starts a chain at depth 0 and is delivered on its own")
# F258/F395, repaired 2026-09-22. This leg found the defect: the entry was born at hop_budget + 1,
# labelled origin_type "agent", and moved only when released by hand. It now checks the repair.

runs_before = db_rows(
    "SELECT COUNT(*) c FROM runs WHERE project_id = ? AND agent = ?", (P, BRAVO)
)[0]["c"]
code, msg = send(A, None, BRAVO, f"operator-plane send {TAG}")
ok("POST /messages accepts an operator-plane send", code == 201, f"{code} {str(msg)[:200]}")
MSG1 = (msg or {}).get("id") if isinstance(msg, dict) else None
note("message id", MSG1)
ok("...sent as the operator", isinstance(msg, dict) and msg.get("from") == "operator", str(msg))

entry = db_rows(
    "SELECT id, hop_depth, state, agent, origin_type, origin_agent, conversation_id "
    "FROM inbound_queue_entries WHERE message_id = ?", (MSG1,)
)
ok("it queued exactly one inbound entry", len(entry) == 1, str(entry))
if entry:
    e = entry[0]
    note("entry", e)
    ok("its hop_depth is 0: the operator starts a chain, it does not continue one",
       e["hop_depth"] == 0, f"depth={e['hop_depth']} budget={HOP_BUDGET}")
    ok("it is labelled the operator's, with no origin agent",
       e["origin_type"] == "operator" and e["origin_agent"] is None, str(e))
    susp = db_rows(
        "SELECT id FROM event_logs WHERE project_id = ? AND event_type = 'queue_chain_suspended' "
        "AND data LIKE ?", (P, "%" + e["id"] + "%")
    )
    ok("no queue_chain_suspended was recorded for it", not susp, str(susp))

code, qstatus = api("GET", f"{A}/queue/{BRAVO}/status")
ok("the queue panel does not blame the hop budget",
   (qstatus or {}).get("waiting_reason") != "hop budget exhausted", f"{code} {qstatus}")

print("  ..   waiting up to 5 minutes for the recipient's turn, with no release")
deadline = time.time() + 300
state_now, runs_post = None, runs_before
while time.time() < deadline:
    r = db_rows("SELECT state FROM inbound_queue_entries WHERE message_id = ?", (MSG1,))
    runs_post = db_rows(
        "SELECT COUNT(*) c FROM runs WHERE project_id = ? AND agent = ?", (P, BRAVO)
    )[0]["c"]
    state_now = r[0]["state"] if r else None
    if state_now == "delivered" and runs_post > runs_before:
        break
    time.sleep(10)
ok("it is delivered without anyone releasing it", state_now == "delivered", str(state_now))
ok("and a turn started for the recipient", runs_post > runs_before,
   f"{runs_before} -> {runs_post}")
released = db_rows(
    "SELECT id FROM event_logs WHERE project_id = ? AND event_type = 'queue_entry_released' "
    "AND data LIKE ?", (P, "%" + (entry[0]["id"] if entry else "none") + "%")
)
ok("no release was needed or recorded", not released, str(released))

code, listed = api("GET", f"{A}/messages?history=true&limit=1000")
ids = [m["id"] for m in listed] if isinstance(listed, list) else []
ok("the message is listed as sent", MSG1 in ids, f"{code} {len(ids)} messages")


# ---------------------------------------------------------------------------- LEG 1b

leg("1b", "the operator is not an agent: no roster row, no active-agent entry")

code, roster_api = api("GET", f"{A}/agents")
names = [a.get("name") for a in roster_api] if isinstance(roster_api, list) else []
ok("'operator' is not listed on the agent roster", "operator" not in names, str(names))
_, st1b = api("GET", f"{A}/status")
ok("nor among GET /status's active agents",
   "operator" not in ((st1b or {}).get("agents_active") or []), str(st1b))



# ---------------------------------------------------------------------------- LEG 2

leg(2, "nothing in the product ever marks a message read")

code, st = api("GET", f"{A}/status")
base_pending = (st or {}).get("message_counts", {}).get("pending")
base_total = (st or {}).get("message_counts", {}).get("total")
note("status message_counts before", {"pending": base_pending, "total": base_total})
# Every message this harness has ever marked read, across all its runs — the ONLY reads this
# project has. Captured rather than assumed: a second run on the state the first left starts with
# one already read, and an absolute "pending == total" would fail on the harness's own history.
read_before = db_rows(
    "SELECT COUNT(*) c FROM messages WHERE project_id = ? AND read = 1", (P,)
)[0]["c"]
note("messages this harness has marked read in earlier runs", read_before)

send(A, None, BRAVO, f"unread accrual a {TAG}")
code, m2 = send(A, None, BRAVO, f"unread accrual b {TAG}")
MSG2 = (m2 or {}).get("id") if isinstance(m2, dict) else None
_, st2 = api("GET", f"{A}/status")
pending2 = (st2 or {}).get("message_counts", {}).get("pending")
total2 = (st2 or {}).get("message_counts", {}).get("total")
ok("every new message raises the StatusBar's pending count",
   pending2 == base_pending + 2 and total2 == base_total + 2,
   f"pending {base_pending}->{pending2}, total {base_total}->{total2}")
ok("pending is total minus only what this harness itself marked read on an earlier run",
   pending2 == total2 - read_before, f"pending={pending2} total={total2} read={read_before}")

code, _ = api("PATCH", f"{A}/messages/{MSG2}/read")
ok("PATCH /read works when something calls it", code == 200, str(code))
_, st3 = api("GET", f"{A}/status")
pending3 = (st3 or {}).get("message_counts", {}).get("pending")
ok("and the count does come down when it is called", pending3 == pending2 - 1,
   f"{pending2} -> {pending3}")
row = db_rows("SELECT read, read_at FROM messages WHERE id = ?", (MSG2,))
ok("read_at is stamped", bool(row) and row[0]["read"] == 1 and row[0]["read_at"], str(row))
code, again = api("PATCH", f"{A}/messages/{MSG2}/read")
ok("marking read twice is accepted", code == 200, str(code))
code, unread = api("GET", f"{A}/messages?limit=1000")
unread_ids = [m["id"] for m in unread] if isinstance(unread, list) else []
ok("a read message leaves the default (inbox) listing", MSG2 not in unread_ids, str(code))

# The instance-wide picture, read-only. No API call is made against any project here, so the
# standing "never drive proj-5e960453 / proj-18e5d4e0" limit is respected for the two protected
# ids as well.
inst = db_rows(
    "SELECT p.id, p.name, COUNT(m.id) total, SUM(CASE WHEN m.read THEN 1 ELSE 0 END) read_n "
    "FROM projects p JOIN messages m ON m.project_id = p.id GROUP BY p.id ORDER BY total DESC"
)
for r in inst:
    note("project mail", f"{r['name']}: {r['total']} messages, {r['read_n']} read")
others = [r for r in inst if r["id"] not in (P, P2)]
ok("no message in any pre-existing project on this instance has ever been marked read",
   all((r["read_n"] or 0) == 0 for r in others),
   str([(r["name"], r["read_n"]) for r in others if (r["read_n"] or 0)]))
oldest = db_rows(
    "SELECT project_id, MIN(timestamp) t, COUNT(*) c FROM messages WHERE read = 0 "
    "AND project_id NOT IN (?, ?) GROUP BY project_id ORDER BY t LIMIT 3", (P, P2)
)
for r in oldest:
    note("oldest unread", f"{r['project_id']}: {r['c']} unread, oldest {r['t']}")


# ---------------------------------------------------------------------------- LEG 3

leg(3, "the screen those three routes were built for is not in the shipped bundle")

for sym in ("MessagesFeed", "MessageCard", "ConversationGroup"):
    refs = src_refs(sym, "components/messages/")
    ok(f"{sym} is referenced by nothing outside components/messages/", not refs, str(refs))
for hook in ("useMessages", "useMessageHistory", "useMarkRead"):
    refs = src_refs(hook, "api/messages.ts")
    outside = [r for r in refs
               if not r.startswith("components/messages/") and not r.startswith("__tests__")]
    ok(f"{hook} has no call site outside components/messages/", not outside, str(refs))

ok("the bundle directory holds at least one js chunk", bool(bundle_files()), str(UI_ASSETS))
for needle in ("Loading messages", "No message history",
               "Messages between agents will appear here.", "Group by conversation"):
    ok(f"served bundle does NOT contain {needle!r}", in_bundle(needle) is None,
       str(in_bundle(needle)))
# Control: the same grep finds strings from screens that ARE shipped, so a miss above means
# absent-from-the-bundle rather than a broken search.
ok("control: a StatusBar literal IS in the bundle", in_bundle("msgs") is not None)
ok("control: a live event name IS in the bundle", in_bundle("agent_output") is not None)
feed = os.path.join(UI_SRC, "components", "messages", "MessagesFeed.tsx")
with open(feed, encoding="utf-8") as _fh:
    note("MessagesFeed source size", f"{len(_fh.read().splitlines())} lines")


# ---------------------------------------------------------------------------- LEG 4

leg(4, "the sender is checked: without a run it can only be the operator")
# F261, repaired 2026-09-22. This leg found a forged `from` accepted, listed on the roster, and then
# refused as a recipient. It now checks the refusal and that nothing the forgery touched appears.

GHOST = f"ghost-{TAG}"
msgs_before_ghost = db_rows("SELECT COUNT(*) c FROM messages WHERE project_id = ?", (P,))[0]["c"]
code, ghost_msg = send(A, GHOST, BRAVO, f"forged sender {TAG}")
ok("a sender that is not the operator, with no run, is refused 422", code == 422,
   f"{code} {str(ghost_msg)[:200]}")
detail = json.dumps(ghost_msg) if not isinstance(ghost_msg, str) else ghost_msg
ok("...naming the name, and the way an agent does send", GHOST in detail and "send_message" in detail,
   detail[:240])
msgs_after_ghost = db_rows("SELECT COUNT(*) c FROM messages WHERE project_id = ?", (P,))[0]["c"]
ok("no message row was written", msgs_after_ghost == msgs_before_ghost,
   f"{msgs_before_ghost} -> {msgs_after_ghost}")
_, st4 = api("GET", f"{A}/status")
active = (st4 or {}).get("agents_active") or []
ok("GET /status does not list it as an active agent", GHOST not in active, str(active))
code, roster_api = api("GET", f"{A}/agents")
names = [a.get("name") for a in roster_api] if isinstance(roster_api, list) else []
ok("nor does the agent roster", GHOST not in names, str(names))

code, registered = send(A, BRAVO, ALPHA, f"a registered name, no run {TAG}")
ok("a REGISTERED agent's name without its run is refused the same way", code == 422,
   f"{code} {str(registered)[:160]}")

code, unknown = send(A, None, f"nobody-{TAG}", f"unknown recipient {TAG}")
ok("an unknown RECIPIENT is still refused 404", code == 404, f"{code} {str(unknown)[:200]}")
rej = db_rows(
    "SELECT agent, severity, data FROM event_logs WHERE project_id = ? "
    "AND event_type = 'agent_action_rejected' AND data LIKE ? ORDER BY timestamp DESC LIMIT 1",
    (P, f"%nobody-{TAG}%")
)
ok("the refusal is recorded", bool(rej), str(rej))
if rej:
    ok("...on no agent's timeline, since the operator sent it", rej[0]["agent"] is None,
       str(rej[0]))


# ---------------------------------------------------------------------------- LEG 5

leg(5, "the refusals that are there — archived agent, archived thread, contradictory directives")

api("POST", f"{A}/agents/{RETIRED}/archive")
arch = db_rows("SELECT lifecycle FROM agents WHERE project_id = ? AND name = ?", (P, RETIRED))
note("retired agent lifecycle", arch)
code, body = send(A, None, RETIRED, f"to an archived agent {TAG}")
ok("sending to an archived agent is refused 409", code == 409, f"{code} {str(body)[:160]}")
detail = json.dumps(body) if not isinstance(body, str) else body
ok("...and the refusal hands the sender its own content back", TAG in detail, detail[:200])

code, body = send(A, None, BRAVO, f"both directives {TAG}",
                  conversation_id="conv-does-not-matter", start_new_thread=True)
ok("conversation_id together with start_new_thread is refused 409", code == 409,
   f"{code} {str(body)[:160]}")

conv2 = db_rows("SELECT id FROM conversations WHERE project_id = ? LIMIT 1", (P2,))
foreign = conv2[0]["id"] if conv2 else "conv-00000000"
code, body = send(A, None, BRAVO, f"foreign thread {TAG}", conversation_id=foreign)
ok("a conversation id from another project is refused 404", code == 404,
   f"{code} {str(body)[:160]}")

code, t2 = api("POST", f"{A2}/tasks", {"title": f"row17 foreign task {TAG}"})
foreign_task = (t2 or {}).get("id") if isinstance(t2, dict) else None
note("foreign task", f"{code} {foreign_task}")
code, body = send(A, None, BRAVO, f"foreign task {TAG}", task_id=foreign_task or "task-nope")
ok("a task id from another project is refused", code >= 400, f"{code} {str(body)[:160]}")

code, body = send(A, None, BRAVO, f"bad type {TAG}", type="shout")
ok("an unknown message type is refused", code == 422, f"{code} {str(body)[:120]}")

code, body = api("POST", f"{A}/messages", {"to": BRAVO, "content": "x" * 10001})
ok("content past 10,000 characters is refused", code == 422, f"{code} {str(body)[:120]}")


# ---------------------------------------------------------------------------- LEG 6

leg(6, "what GET /messages does with the filters it advertises")

code, all_hist = api("GET", f"{A}/messages?history=true&limit=1000")
n_all = len(all_hist) if isinstance(all_hist, list) else -1
note("messages in this project", n_all)

real_conv = db_rows(
    "SELECT id FROM conversations WHERE project_id = ? ORDER BY created_at DESC LIMIT 1", (P,)
)
conv_id = real_conv[0]["id"] if real_conv else ""
# F262 and F263, repaired 2026-09-22: this leg found both filters dropping what they could not
# honour and answering 200. It now checks that they refuse.
code, filtered = api("GET", f"{A}/messages?history=true&limit=1000&conversation={conv_id}")
ok("filtering by a conversation id is refused 422, not answered with the whole project",
   code == 422, f"conversation={conv_id} -> {code} {str(filtered)[:160]}")

code, pair = api("GET", f"{A}/messages?history=true&limit=1000&conversation={ALPHA}:{BRAVO}")
n_pair = len(pair) if isinstance(pair, list) else -1
# The pair filter is still honoured. No floor on the count: leg 7's real agent mail comes later,
# and the operator is not one of the pair.
ok("an agent PAIR, 'a:b', is still a filter", code == 200 and 0 <= n_pair <= n_all,
   f"{code} {n_pair} of {n_all}")
for bad_conv in (f"{ALPHA}:", "zzz"):
    code, got = api("GET", f"{A}/messages?history=true&limit=1000&conversation={bad_conv}")
    ok(f"conversation={bad_conv!r} is refused 422", code == 422, f"{code} {str(got)[:120]}")

code, desc = api("GET", f"{A}/messages?history=true&limit=5&sort=desc")
code, asc = api("GET", f"{A}/messages?history=true&limit=5&sort=asc")
ok("sort=desc really reverses the page",
   isinstance(desc, list) and isinstance(asc, list) and desc and asc
   and desc[0]["id"] != asc[0]["id"],
   f"{desc[0]['id'] if isinstance(desc, list) and desc else None} vs "
   f"{asc[0]['id'] if isinstance(asc, list) and asc else None}")
for bad in ("DESC", "descending", "newest", "()"):
    code, got = api("GET", f"{A}/messages?history=true&limit=5&sort={bad}")
    ok(f"sort={bad!r} is refused 422, not read as ascending", code == 422, str(code))

code, default_page = api("GET", f"{A}/messages?history=true")
if isinstance(default_page, list) and isinstance(asc, list) and default_page and asc:
    ok("the default page is the OLDEST messages, ascending",
       default_page[0]["id"] == asc[0]["id"], f"{default_page[0]['id']} vs {asc[0]['id']}")

code, by_alpha = api("GET", f"{A}/messages?history=true&limit=1000&agent={ALPHA}")
senders = {m["from"] for m in by_alpha} if isinstance(by_alpha, list) else set()
recips = {m["to"] for m in by_alpha} if isinstance(by_alpha, list) else set()
ok("?agent= filters by RECIPIENT only — a prolific sender's own mail is not returned",
   recips <= {ALPHA}, f"senders={senders} recipients={recips}")


# ---------------------------------------------------------------------------- LEG 7

leg(7, "the contrast: peer mail sent by a real agent IS delivered")

msgs_before = {r["id"] for r in db_rows("SELECT id FROM messages WHERE project_id = ?", (P,))}
runs_b_before = db_rows(
    "SELECT COUNT(*) c FROM runs WHERE project_id = ? AND agent = ?", (P, BRAVO)
)[0]["c"]
prompt = (
    "You are in a wiring test. Call the send_message tool exactly once, with to_agent set to "
    "'bravo', subject set to the word ping, and a one-sentence body telling bravo that this is a "
    "wiring test and that it must not reply or use any tool. Then stop without writing files."
)
RUN, why = trigger(ALPHA, prompt)
ok("a real turn started for the sender", RUN is not None, why)
if RUN:
    status = wait_run(RUN)
    note("sender run status", status)
    sent = db_rows(
        "SELECT id, sender, recipient, created_by_run_id, conversation_id FROM messages "
        "WHERE project_id = ? AND created_by_run_id = ?", (P, RUN)
    )
    ok("the agent's message is attributed to the run that sent it", bool(sent), str(sent))
    if sent:
        m = sent[0]
        ok("...with the sender the Hub derived, not one the caller supplied",
           m["sender"] == ALPHA and m["recipient"] == BRAVO, str(m))
        ok("...and it is a message this harness did not write", m["id"] not in msgs_before)
        e = db_rows(
            "SELECT hop_depth, state, origin_type, origin_agent FROM inbound_queue_entries "
            "WHERE message_id = ?", (m["id"],)
        )
        ok("its entry is within the hop budget, one hop past its run",
           bool(e) and e[0]["hop_depth"] <= HOP_BUDGET, str(e))
        print("  ..   waiting up to 6 minutes for the recipient's turn")
        deadline = time.time() + 360
        delivered, runs_b_after = None, runs_b_before
        while time.time() < deadline:
            stt = db_rows("SELECT state FROM inbound_queue_entries WHERE message_id = ?",
                          (m["id"],))
            runs_b_after = db_rows(
                "SELECT COUNT(*) c FROM runs WHERE project_id = ? AND agent = ?", (P, BRAVO)
            )[0]["c"]
            delivered = stt[0]["state"] if stt else None
            if delivered == "delivered" and runs_b_after > runs_b_before:
                break
            time.sleep(10)
        ok("the entry reached the recipient", delivered == "delivered", str(delivered))
        ok("and a turn started for the recipient", runs_b_after > runs_b_before,
           f"{runs_b_before} -> {runs_b_after}")
        read_now = db_rows("SELECT read FROM messages WHERE id = ?", (m["id"],))
        ok("a message that was actually delivered is still not marked read",
           bool(read_now) and read_now[0]["read"] == 0, str(read_now))


# ---------------------------------------------------------------------------- LEG 8

leg(8, "project isolation, and one query that has none")

code, other = api("GET", f"{A2}/messages?history=true&limit=1000")
other_ids = {m["id"] for m in other} if isinstance(other, list) else set()
ok("this project's mail is not listed by the other project", MSG1 not in other_ids, str(code))
code, _ = api("PATCH", f"{A2}/messages/{MSG1}/read")
ok("marking it read through the other project is refused 404", code == 404, str(code))

# This leg used to mirror F264 here: `_pending_loop_request`'s message query had no project filter.
# The mirror needed `alpha -> bravo` mail in both projects, written through a runless `from`, which
# F261's repair refuses. F264 is driven live, with agent-sent mail, by `t_f264_live_loop_reason.py`.


# ---------------------------------------------------------------------------- LEG 9

leg(9, "cleanliness")

enabled = db_rows("SELECT COUNT(*) c FROM ai_jobs WHERE enabled = 1")[0]["c"]
ok("no job is enabled anywhere on this instance", enabled == 0, str(enabled))
now_count = project_count()
ok("project count is unchanged by this run", now_count == BASE_PROJECTS,
   f"{BASE_PROJECTS} -> {now_count}")
for path in (DIR, DIR2):
    r = git(path, "status", "--porcelain")
    stray = [
        ln for ln in r.stdout.splitlines()
        if ln.strip() and ".agentweave" not in ln  # the Hub's own project marker is the product's
    ]
    ok(f"{os.path.basename(path)} working tree is clean", not stray, str(stray))

print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL " + f)
