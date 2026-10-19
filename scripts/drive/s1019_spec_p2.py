"""Sweep 2026-10-19, part 2: what a rejected cannot-satisfy report leaves the reporter able to do;
withdraw's recorded note; coverage after the fold; the roadmap page's slice state.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1019_spec_p2.py <project-id> <project-dir> <CAP> <RM> <PD>
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import s1019_spec_lib as lib  # noqa: E402
from s1019_spec_lib import agent, request, say, seed_run, show, task  # noqa: E402

P, DIR, CAP, RM, PD = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
BASE = f"/projects/{P}/project"
SFX = time.strftime("%H%M%S")

# --- a rejected report: what can the reporter do next? -------------------------------------------
DOC = f"spec/changes/rej-{SFX}/spec.json"
request("POST", f"{BASE}/documents", {"path": DOC, "title": "Rejected " + SFX})
request("PUT", f"{BASE}/documents/{DOC}/content", {"document": lib.payload("Rejected " + SFX, SFX, keys=("alpha",))})
request("POST", f"{BASE}/documents/close-exploration?path={DOC}")
request("POST", f"{BASE}/documents/propose?path={DOC}")
request("POST", f"{BASE}/documents/phase?path={DOC}&to=approved", {"reason": "drive", "approve_anyway": True})
st, tasks = request("GET", f"/projects/{P}/tasks")
tid = next(t["id"] for t in tasks["tasks"] if t["title"] == f"Build alpha {SFX}")
request("PATCH", f"/projects/{P}/tasks/{tid}", {"status": "assigned", "assignee": "builder"})
request("PATCH", f"/projects/{P}/tasks/{tid}", {"status": "in_progress"})
tok = seed_run(P, "builder", f"run-rej-{SFX}", tid)
st, rep = agent(tok, "POST", "/spec/documents/cannot-satisfy", {"path": DOC, "criterion": "c-alpha", "reason": "cold cache"})
show("report", st, rep)
st, out = request("POST", f"{BASE}/documents/{DOC}/amendments/{rep['id']}/respond",
                  {"response": "reject", "reason": "warm the cache in setup"})
show("reject", st, {k: out.get(k) for k in ("response", "task_unblocked")})
t = task(P, tid)
print("  after reject: status", t.get("status"), "| blocked_reason", repr(t.get("blocked_reason")))
for to in ("in_progress", "completed"):
    st, out = agent(tok, "PATCH", f"/tasks/{tid}", {"status": to})
    show(f"reporter PATCH {to}", st, out)
st, out = agent(tok, "PATCH", f"/tasks/{tid}", {"notes": "warmed it"})
show("reporter PATCH notes only", st, out)
st, out = agent(tok, "POST", "/spec/evidence", {"identifier": "FR-1", "summary": "warm-cache run: 0.4ms", "task_id": tid})
show("reporter records evidence on its blocked task", st, {k: out.get(k) for k in ("id", "review_state")} if st < 300 else out)
say("after a rejection, the reporter has a move it is allowed to make on its task",
    False, "every status move refused; the note told it to 'Try again'")
st, story = request("GET", f"/projects/{P}/tasks/{tid}/story")
if st == 200:
    items = story.get("items") or story.get("entries") or story.get("events") or story
    print("  story tail:", json.dumps(items, ensure_ascii=False)[-900:])
else:
    show("story", st, story)
st, am = request("GET", f"{BASE}/documents/{DOC}/amendments")
show("amendment row the operator reads", st, [{k: a.get(k) for k in ("id", "op", "response", "response_reason", "task_id")}
                                              for a in am.get("amendments", [])])

# --- withdraw with its own field name ------------------------------------------------------------
st, pend = request("GET", f"{BASE}/documents/{PD}/proposals")
for p in pend.get("proposals", []):
    st, out = request("POST", f"{BASE}/documents/{PD}/proposals/{p['id']}/withdraw", {"note": "out of scope"})
    show(f"withdraw {p['unit_key']} with note", st, {k: out.get(k) for k in ("status",)} if st == 200 else out)
st, res = request("GET", f"{BASE}/documents/{PD}/proposals?status=resolved")
for p in res.get("proposals", []):
    print("   ", p["unit_key"], p["status"], "by", p["resolved_by_actor_name"], "why", repr(p["resolution_reason"]))

# --- coverage of the capability the change folded into -------------------------------------------
st, cov = request("GET", f"{BASE}/spec/coverage?document={CAP}")
print("  coverage:", st, json.dumps(cov, ensure_ascii=False)[:1200])

# --- the roadmap's slice states ------------------------------------------------------------------
st, rv = request("GET", f"{BASE}/spec?path={RM}")
print("  roadmap /spec keys:", st, sorted(rv) if isinstance(rv, dict) else rv)
for key in ("slice_states", "roadmap_states", "slices"):
    if isinstance(rv, dict) and key in rv:
        print("   ", key, json.dumps(rv[key], ensure_ascii=False)[:600])
st, docs = request("GET", f"{BASE}/documents")
row = next((d for d in (docs.get("documents") if isinstance(docs, dict) else docs) or [] if d.get("path") == RM), None)
print("  roadmap row:", json.dumps(row, ensure_ascii=False)[:700])
print("REJ_DOC", DOC, "TASK", tid)
