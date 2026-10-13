"""Drive F349 slice 2 (design D4) on a scratch Hub from source: the routes that now call
`schedule_accepted` and `persist_accepted_event` still answer, record and start as before.

A real lock cannot be timed between a route's commit and its schedule (SQLite waits 30 s for a
writer, `db/engine.py` SQLITE_BUSY_TIMEOUT_SECONDS), so the failure itself is pinned by
`hub/tests/test_accepted_input_is_answered_as_accepted.py`; this drive shows the happy path of
three of the six sites, in a real process, with one real Haiku turn:

1. `POST /messages` to an agent with no runner: 201, entry queued, both events recorded.
2. `PATCH /agents/<name>` binding a Haiku runner: 200, and the queued message's turn starts and
   completes with no further action (the rebind's `schedule_accepted`).
3. `PATCH /accounting/budget`: 200, its event recorded.

Needs AW_HUB, AW_KEY, AW_DB (the scratch Hub's own SQLite file, read only).
"""

import os
import pathlib
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, show  # noqa: E402

DB = os.environ["AW_DB"]
TAG = time.strftime("%H%M%S")
root = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "scratch" / f"f349-{TAG}"
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text("f349 sites drive\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "a@example.invalid"],
    ["git", "config", "user.name", "a"],
    ["git", "add", "README.md"],
    ["git", "commit", "-m", "x"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

failures = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(label)


def rows(query, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return con.execute(query, args).fetchall()
    finally:
        con.close()


def events(pid, kind):
    return rows("select data from event_logs where project_id=? and event_type=?", (pid, kind))


c, proj = api("POST", "/projects/open", {"path": str(root), "name": f"f349-{TAG}"})
if c not in (200, 201):
    show("open", c, proj)
    sys.exit(1)
PID = proj["id"]
A = f"/projects/{PID}"
c, synced = api("POST", f"{A}/session/sync", {"data": {"agents": {"quiet": {}}}})
check("agent created unbound", c == 200, c)

# 1. A message to an agent with no runner.
c, msg = api("POST", f"{A}/messages", {"to": "quiet", "content": "Reply with the word done."})
check("message answered 201", c == 201, c)
queued = rows(
    "select id, state from inbound_queue_entries where project_id=? and agent='quiet'", (PID,)
)
check("its entry is queued", [s for _, s in queued] == ["queued"], queued)
check("message_created recorded", len(events(PID, "message_created")) == 1)
check("queue_entry_queued recorded", len(events(PID, "queue_entry_queued")) == 1)

# 2. Binding a Haiku runner starts the waiting turn.
c, runner = api(
    "POST",
    f"{A}/runners",
    {"name": f"haiku-{TAG}", "cli": "claude", "model": "claude-haiku-4-5-20251001"},
)
check("runner created", c == 201, c)
c, bound = api("PATCH", f"{A}/agents/quiet", {"runner_id": runner["id"]})
check("rebind answered 200", c == 200, c)
deadline = time.time() + 180
runs = []
while time.time() < deadline:
    runs = rows("select id, status from runs where project_id=? and agent='quiet'", (PID,))
    if runs and all(s not in ("running", "starting", "queued") for _, s in runs):
        break
    time.sleep(2)
check("a turn ran for the queued message", len(runs) == 1, runs)
check("the turn completed", bool(runs) and runs[0][1] == "completed", runs)
entry = rows(
    "select state, delivered_in_run_id from inbound_queue_entries where project_id=? and agent='quiet'",
    (PID,),
)
check(
    "the entry was delivered into that run",
    bool(runs) and entry == [("delivered", runs[0][0])],
    entry,
)

# 3. The budget PATCH.
c, budget = api("PATCH", f"{A}/accounting/budget", {"token_budget": 10_000_000})
check("budget answered 200", c == 200, c)
check("accounting_budget_updated recorded", len(events(PID, "accounting_budget_updated")) == 1)
c, _ = api("PATCH", f"{A}/accounting/budget", {"token_budget": None})

print(f"\n{len(failures)} failed" if failures else "\nall passed")
sys.exit(1 if failures else 0)
