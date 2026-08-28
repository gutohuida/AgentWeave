"""Full-surface sweep, part 5: the spec flow end to end, operator-only.

Rows 9 and 10 of the coverage matrix, driven all the way through — create, write real content, close
the exploration, propose, approve, watch requirements materialise, record evidence against one, and
read coverage.

Operator-only, and that is the point: `PUT /project/documents/{path}/content` lets an operator write
the payload directly, so the whole lifecycle is reachable without spawning a provider run. Nothing
here costs a token.

Run: AW_PROJECT=<proj> AW_KEY=<key> py -3.11 scripts/drive/t_spec_end_to_end.py
"""

import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

BASE = f"/projects/{P}/project"


def step(label, method, path, body=None, expect=None, show_body=False):
    code, out = api(method, path, body)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    flag = "" if ok else "   <-- UNEXPECTED"
    print(f"  {label}: {code}{flag}")
    detail = out.get("detail") if isinstance(out, dict) else None
    if isinstance(detail, dict):
        detail = detail.get("message")
    if isinstance(detail, str):
        print(f"      refusal: {detail[:240]}")
    elif show_body or not ok:
        print(f"      {json.dumps(out, default=str)[:500]}")
    return code, out


PAYLOAD = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": "A queue entry states why it is waiting",
    "summary": "Queued input records the refusal that stopped its last delivery, so the queue "
    "status route can explain itself instead of guessing.",
    "problem": "GET /queue/{agent}/status re-derives a handful of read-only conditions and "
    "reported waiting_reason: null for every refusal raised deeper inside the trigger.",
    "scope": {
        "in_scope": ["the queue status route", "the entry's recorded reason"],
        "non_goals": ["changing which refusals are raised", "the operator's trigger response"],
    },
    "requirements": [
        {
            "key": "state-the-reason",
            "statement": "A queued entry SHALL record the refusal that stopped its last delivery "
            "attempt, in the words the refusal used.",
            "modal": "SHALL",
            "rationale": "Restating each condition in the status route puts two copies of every "
            "refusal in the codebase and leaves the next one invisible again.",
        },
        {
            "key": "no-guessing",
            "statement": "The status route MUST NOT infer a waiting reason it was not told.",
            "modal": "MUST",
        },
    ],
    "acceptance_criteria": [
        {
            "key": "reason-survives",
            "requirement": "state-the-reason",
            "given": "an entry whose last delivery was refused because a peer holds the task's "
            "checkout",
            "when": "the operator reads the queue status for that agent",
            "then": "the response carries the refusal's own sentence rather than null",
        },
        {
            "key": "nothing-invented",
            "requirement": "no-guessing",
            "given": "an entry that has never been through a delivery attempt",
            "when": "the operator reads the queue status for that agent",
            "then": "no waiting reason is reported",
        },
    ],
    "tasks": [
        {
            "key": "record-on-refusal",
            "title": "Record the refusal on each selected entry",
            "description": "In the trigger's refusal branch, write the error's own detail onto "
            "every entry the turn would have carried, before the transient classification is "
            "asked, so both branches record it.",
            "requirements": ["state-the-reason"],
        },
        {
            "key": "status-reads-not-guesses",
            "title": "The status route reads the recorded reason",
            "description": "Replace the status route's re-derivation with a read of the entry's "
            "recorded reason, so a refusal it was never told about is reported as absent rather "
            "than inferred.",
            "requirements": ["no-guessing"],
            "depends_on": ["record-on-refusal"],
        },
    ],
    "design": "The refusal branch already has the only copy of the refusal's words. It writes them "
    "onto each selected entry before classifying the error, so both branches record it.",
    "lifecycle": "One-off change; reconciled into the queue capability document afterwards.",
}

print("=" * 78)
print("ROW 9/10 — the spec flow end to end, operator only")
print("=" * 78)

code, doc = step("create a document", "POST", f"{BASE}/documents",
                 {"title": PAYLOAD["title"]}, expect=(200, 201))
path = doc["path"]
q = urllib.parse.quote(path, safe="")
print(f"      path: {path}")

step("write real content", "PUT", f"{BASE}/documents/{q}/content",
     {"document": PAYLOAD}, expect=(200, 201), show_body=False)

code, out = step("propose while exploring is open", "POST", f"{BASE}/documents/propose?path={q}",
                 {"reason": "sweep"})
if isinstance(out, dict) and "blocking" in out:
    print(f"      blocking: {[b.get('code') for b in out['blocking']]}")
    print(f"      phase after: {out.get('phase')!r}")

step("close the exploration", "POST", f"{BASE}/documents/close-exploration?path={q}",
     {"reason": "sweep"}, expect=(200, 201))
code, out = step("propose now", "POST", f"{BASE}/documents/propose?path={q}", {"reason": "sweep"},
                 expect=(200, 201))
if isinstance(out, dict):
    print(f"      blocking: {[b.get('code') for b in out.get('blocking', [])]}")
    print(f"      phase after: {out.get('phase')!r}")

code, out = step("approve it", "POST", f"{BASE}/documents/phase?path={q}&to=approved",
                 {"reason": "sweep"}, expect=(200, 201))
if isinstance(out, dict):
    print(f"      phase after: {out.get('phase')!r}")

print()
print("--- did tasks materialise onto the board?")
code, tasks = step("list tasks", "GET", f"/projects/{P}/tasks", expect=200)
trows = tasks if isinstance(tasks, list) else tasks.get("tasks", [])
from_doc = [t_ for t_ in trows if "refusal" in str(t_.get("title", "")).lower()
            or "status route" in str(t_.get("title", "")).lower()]
print(f"      tasks on the board: {len(trows)}; from this document: {len(from_doc)}")
for t_ in from_doc[:4]:
    print(f"        {t_.get('id')}  {str(t_.get('title'))[:52]:<52} {t_.get('status')}")

print()
print("--- did requirements materialise?")
code, reqs = step("list requirements", "GET", f"{BASE}/spec/requirements", expect=200)
rows = reqs if isinstance(reqs, list) else reqs.get("requirements", [])
# Coverage is the honest source for "which requirements belong to this document" — the listing
# keys on `document_id`, and the path is what the caller holds.
code, cov0 = api("GET", f"{BASE}/spec/coverage?document={q}")
mine = cov0.get("requirements", []) if isinstance(cov0, dict) else []
print(f"      requirements in project: {len(rows)}; on this document: {len(mine)}")
for r in mine[:4]:
    print(f"        {r.get('identifier')}  state={r.get('state')!r} "
          f"tasks={r.get('linked_task_ids')}")

identifier = mine[0].get("identifier") if mine else None

print()
print("--- evidence against a real requirement")
if identifier:
    step("record evidence naming no document", "POST", f"{BASE}/spec/evidence",
         {"identifier": identifier, "kind": "test", "summary": "driven by the sweep",
          "locator": "hub/tests/test_inbound_queue.py"})
    # The refusal above is correct and says exactly what to add: several documents in this project
    # declare an FR-1, so the identifier alone does not name one requirement.
    step("record evidence naming the document", "POST", f"{BASE}/spec/evidence",
         {"identifier": identifier, "document": path, "kind": "test",
          "summary": "driven by the sweep",
          "locator": "hub/tests/test_inbound_queue.py"}, expect=(200, 201))
    code, evs = step("list evidence", "GET", f"{BASE}/spec/evidence", expect=200)
    items = evs if isinstance(evs, list) else evs.get("evidence", [])
    print(f"      evidence rows: {len(items)}")
    eid = items[-1].get("id") if items else None
    if eid:
        step("accept it as the operator", "POST", f"{BASE}/spec/evidence/{eid}/decision",
             {"decision": "accepted", "reason": "sweep"}, expect=(200, 201))
        step("accept it again", "POST", f"{BASE}/spec/evidence/{eid}/decision",
             {"decision": "accepted", "reason": "sweep again"})
        step("read its reviews", "GET", f"{BASE}/spec/evidence/{eid}/reviews", expect=200)
else:
    print("      no requirement materialised — nothing to attach evidence to")

print()
print("--- coverage, and what it says about a requirement with accepted evidence")
code, cov = step("coverage", "GET", f"{BASE}/spec/coverage?document={q}", expect=200,
                 show_body=True)

print()
print("--- editing an approved document, and drift")
step("rewrite an approved document's content", "PUT", f"{BASE}/documents/{q}/content",
     {"document": {**PAYLOAD, "summary": "rewritten after approval"}})
step("detect drift", "POST", f"{BASE}/spec/drift/detect", {}, expect=(200, 201))
code, drift = step("read drift", "GET", f"{BASE}/spec/drift", expect=200)
items = drift if isinstance(drift, list) else drift.get("drift", drift.get("items", []))
print(f"      drift rows: {len(items) if isinstance(items, list) else '?'}")

print()
print("done")
