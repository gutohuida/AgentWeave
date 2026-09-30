"""Drive `a-pending-proposal-can-be-withdrawn` task 3.1, agent half: one Haiku turn submits an edit
to a `gate` document, submits it again, then revises one requirement.

Usage: AW_HUB=... AW_KEY=... AW_DB=<drive db> py -3.11 scripts/drive/d0930_withdraw_agent.py <project-id>
A throwaway Hub only (never :8000 / :8010). Prints the document path for the browser half.
"""

import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, "scripts/drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import api  # noqa: E402

PID = sys.argv[1]
A = "/projects/%s" % PID
S = A + "/project"
DB = "file:" + os.environ["AW_DB"].replace("\\", "/") + "?mode=ro"


def req(key, statement):
    return {"key": key, "statement": statement, "modal": "MUST"}


BASE = {
    "schema_version": 1, "kind": "change-spec", "title": "Withdraw drive", "summary": "One.",
    "problem": "Drive.", "scope": {"in_scope": ["README"], "non_goals": ["Else"]},
    "requirements": [req("alpha", "The README MUST mention alpha."), req("beta", "The README MUST mention beta.")],
    "acceptance_criteria": [], "tasks": [], "algorithms": [], "design": "",
    "evidence": {"checked": [], "limits": []}, "lifecycle": "one-off", "open_questions": [],
}

c, runner = api("POST", A + "/runners", {"name": "haiku (drive)", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
print("runner", c, runner.get("id"))
c, agent = api("POST", A + "/agents", {"name": "author", "runner_id": runner["id"]})
print("agent", c, str(agent)[:160])
print("posture", api("PATCH", A + "/agents/author", {"default_permission_mode": "bypassPermissions"})[0])

c, doc = api("POST", S + "/documents", {"title": "Withdraw drive", "kind": "change-spec"})
path = doc["path"]
print("document", c, path)
print("write base", api("PUT", S + "/documents/%s/content" % path, {"document": BASE})[0])
c, d = api("POST", S + "/documents/%s/rigor" % path, {"rigor": "gate", "reason": "drive: proposals"})
print("rigor", c, d.get("rigor") if isinstance(d, dict) else d)

first = [req("alpha", "The README MUST mention alpha twice."), req("beta", "The README MUST mention beta."),
         req("gamma", "The README MUST mention gamma.")]
revised = [req("alpha", "The README MUST mention alpha three times."), req("beta", "The README MUST mention beta."),
           req("gamma", "The README MUST mention gamma.")]
common = dict(path=path, title="Withdraw drive", kind="change-spec", summary="One.", problem="Drive.",
              scope=BASE["scope"])
call1 = dict(common, requirements=first)
call3 = dict(common, requirements=revised)
msg = (
    "Make exactly three calls to the AgentWeave tool submit_spec_document, one after another, with "
    "exactly these arguments (JSON), and nothing else:\n"
    "Call 1: %s\nCall 2 (the same as call 1 again): %s\nCall 3: %s\n"
    "After each call, quote the tool's full response verbatim. Do not call any other tool."
    % (json.dumps(call1), json.dumps(call1), json.dumps(call3))
)
t0 = time.time()
print("trigger", *api("POST", A + "/agent/trigger", {"agent": "author", "message": msg}, timeout=90))


def runs():
    con = sqlite3.connect(DB, uri=True)
    rows = con.execute("select id, status from runs where project_id=? and agent='author'", (PID,)).fetchall()
    con.close()
    return rows


while time.time() - t0 < 300:
    time.sleep(5)
    rs = runs()
    if rs and all(st not in ("running", "starting", "queued", "pending") for _, st in rs):
        break
print("runs", runs(), "%.0fs" % (time.time() - t0))

con = sqlite3.connect(DB, uri=True)
cols = [r[1] for r in con.execute("pragma table_info(agent_outputs)")]
text_col = "content" if "content" in cols else cols[-1]
for (body,) in con.execute("select %s from agent_outputs where agent='author' order by id" % text_col):
    s = str(body)
    if "already_pending" in s or "proposal" in s.lower():
        print("OUT:", s[:400].replace("\n", " "))
con.close()

c, props = api("GET", S + "/documents/%s/proposals" % path)
for p in props.get("proposals", []):
    print("pending", p["id"], p["unit_key"], p["change_kind"], p.get("proposer_actor_name"),
          (p.get("proposed_payload") or {}).get("statement"))
con = sqlite3.connect(DB, uri=True)
for row in con.execute("select id, unit_key, status from spec_edit_proposals order by created_at"):
    print("all", row)
con.close()
print("PATH", path)
