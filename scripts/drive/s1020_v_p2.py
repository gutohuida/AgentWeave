"""2026-10-20 sweep, evidence x drift, phase 2 (operator routes, after the real builder/checker turns):
a requirement the checker rejected, at sketch, contract and gate rigor; drift on a merged line of
work and on operator locators, with each of the three answers; then a criterion-only amend and a
statement reword, and how the earlier pieces read in the list and in coverage.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1020_v_p2.py
"""

import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_v_lib import MEMO, commit_file, coverage, evidence, git, memo, request, say, show, summary  # noqa: E402

M = json.loads(MEMO.read_text())
P, DIR, DOC, T = M["project"], pathlib.Path(M["dir"]), M["doc"], M["tasks"]
BASE = f"/projects/{P}/project"
SPEC = f"{BASE}/spec"


def task(tid):
    return request("GET", f"/projects/{P}/tasks/{tid}")[1]


def rigor(to, reason):
    st, out = request("POST", f"{BASE}/documents/{DOC}/rigor", {"rigor": to, "reason": reason})
    show(f"rigor -> {to}", st, {k: out.get(k) for k in ("rigor", "blocking", "warnings")} if st == 200 else out)
    return st


# --- A. a rejected requirement at every rigor ------------------------------------------------------
print("t-count:", task(T["t-count"]).get("status"), "| FR-2:", coverage(P, DOC).get("FR-2", {}).get("state"))
for level in ("sketch", "contract", "gate"):
    if level != "sketch":
        rigor(level, f"drive: {level}")
    st, out = request("PATCH", f"/projects/{P}/tasks/{T['t-count']}", {"status": "approved"})
    say(f"approving t-count (FR-2 rejected) at {level} refused", st == 409, f"{st} {json.dumps(out)[:900]}")
st, hist = request("GET", f"{BASE}/documents/{DOC}/rigor-history")
show("rigor history", st, [(h.get("from_rigor"), h.get("to_rigor"), h.get("reason")) for h in (hist.get("events") or hist.get("history") or [])] if isinstance(hist, dict) else hist)
# the review route an operator uses from the drawer: completed -> under_review -> approved
st, out = request("PATCH", f"/projects/{P}/tasks/{T['t-count']}", {"status": "under_review"})
show("t-count -> under_review", st, out.get("status") if st == 200 else out)
st, out = request("PATCH", f"/projects/{P}/tasks/{T['t-count']}", {"status": "approved"})
say("approving from under_review at gate refused too", st == 409, f"{st} {json.dumps(out)[:600]}")

# the accepted requirement at gate: t-sorted approves and merges
st, out = request("PATCH", f"/projects/{P}/tasks/{T['t-sorted']}", {"status": "approved"})
say("t-sorted (FR-1 accepted) approves at gate", st == 200, f"{st} {json.dumps(out)[:400] if st != 200 else out.get('status')}")
print("   master log:", git(DIR, "log", "--oneline", "-3", "master"))
print("   integration:", json.dumps(task(T["t-sorted"]).get("integration") or {})[:300])

# --- C. drift ---------------------------------------------------------------------------------------
st, ev3 = request("POST", f"{SPEC}/evidence", {"identifier": "FR-3", "document": DOC, "summary": "total() == 6, watched by locator",
                                               "locator": "todo/total.py", "covers": "full"})
show("FR-3 locator piece at gate", st, {k: ev3.get(k) for k in ("id", "review_state")} if st == 201 else ev3)
st, ev3b = request("POST", f"{SPEC}/evidence", {"identifier": "FR-3", "document": DOC, "summary": "package init watched",
                                                "locator": "todo/__init__.py", "covers": "partial"})
commit_file(DIR, "README.md", "# todo\n\nNow documented.\n", "unwatched readme")
st, out = request("POST", f"{SPEC}/drift/detect")
say("an unwatched change raises no drift", st == 200 and not out.get("raised"), f"{st} {json.dumps(out)[:300]}")
master_before = git(DIR, "rev-parse", "master")
commit_file(DIR, "todo/items.py", (DIR / "todo/items.py").read_text(encoding="utf-8").replace("sorted(", "list("), "unsort on master")
commit_file(DIR, "todo/total.py", "from .items import ITEMS\n\n\ndef total():\n    return sum(q for _, q in ITEMS) + 0\n", "total touched")
commit_file(DIR, "todo/__init__.py", "VERSION = 1\n", "init touched")
st, out = request("POST", f"{SPEC}/drift/detect")
show("scan after watched changes", st, out)
st, dl = request("GET", f"{SPEC}/drift?document={DOC}")
cands = [c for c in (dl.get("candidates") or dl.get("drift") or []) if c.get("state") == "candidate"] if isinstance(dl, dict) else []
print("   drift keys:", list(dl) if isinstance(dl, dict) else dl)
for c in cands:
    print("   candidate:", json.dumps({k: c.get(k) for k in ("id", "evidence_id", "identifier", "paths", "changed_paths", "reason", "summary")})[:400])
say("the merged line's FR-1 piece drifts when master changes items.py",
    any((c.get("identifier") == "FR-1") or ("items.py" in json.dumps(c)) for c in cands), f"{len(cands)} candidates")
say("the FR-3 locator pieces drift", sum("FR-3" in json.dumps(c) or "total.py" in json.dumps(c) or "__init__" in json.dumps(c) for c in cands) >= 1, "")
cov = coverage(P, DOC)
print("   coverage with drift open:", {k: (v.get("state"), v.get("reason")) for k, v in cov.items()})
st, out = request("POST", f"{SPEC}/drift/detect")
say("a second scan does not raise the same drift again", st == 200 and not out.get("raised"), f"{st} {json.dumps(out)[:300]}")
answers = ["no_change_required", "implementation_corrected", "specification_updated"]
answered = []
if cands:
    st, out = request("POST", f"{SPEC}/drift/{cands[0]['id']}/resolve", {"resolution": "fine"})
    say("an unknown answer 422 naming the three", st == 422 and "no_change_required" in json.dumps(out), f"{st} {out}")
    st, out = request("POST", f"{SPEC}/drift/drift-nope/resolve", {"resolution": "no_change_required"})
    say("an unknown candidate 404", st == 404, f"{st} {out}")
for c, a in zip(cands, answers):
    st, out = request("POST", f"{SPEC}/drift/{c['id']}/resolve", {"resolution": a})
    show(f"answer {c['id']} {a}", st, out)
    answered.append((c["id"], a, st))
if cands:
    st, out = request("POST", f"{SPEC}/drift/{cands[0]['id']}/resolve", {"resolution": "implementation_corrected"})
    say("answering twice refused, naming the first answer", st == 409 and "already answered" in json.dumps(out), f"{st} {out}")
cov = coverage(P, DOC)
print("   coverage after answers:", {k: (v.get("state"), v.get("reason")) for k, v in cov.items()})
st, out = request("POST", f"{SPEC}/drift/detect")
show("rescan after the answers (no new commits)", st, out)
# implementation_corrected was said; was it? FR-1 still unsorted on master.
print("   names() on master now:", (DIR / "todo/items.py").read_text(encoding="utf-8").splitlines()[-1])

# --- B. a criterion-only amend, then a statement reword ---------------------------------------------
st, ev3c = request("POST", f"{SPEC}/evidence", {"identifier": "FR-3", "document": DOC, "summary": "before the amend", "covers": "full"})
E_PRE = ev3c.get("id")
pre = coverage(P, DOC).get("FR-3", {})
doc = copy.deepcopy(M["doc_payload"])
for c in doc["acceptance_criteria"]:
    if c["key"] == "c-total":
        c["then"] = "it returns 6, an int"
st, out = request("PUT", f"{BASE}/documents/{DOC}/content", {"document": doc})
show("criterion-only amend (c-total.then)", st, {k: out.get(k) for k in ("blocking", "warnings", "revisions")} if isinstance(out, dict) else out)
post = coverage(P, DOC).get("FR-3", {})
piece = next((e for e in evidence(P, identifier="FR-3") if e["id"] == E_PRE), {})
print("   FR-3 before:", json.dumps({k: pre.get(k) for k in ("state", "evidence_count", "reason")}),
      "after:", json.dumps({k: post.get(k) for k in ("state", "evidence_count", "reason")}))
print("   pre-amend piece:", json.dumps({k: piece.get(k) for k in ("review_state", "for_current_wording", "digest")}))
say("a criterion-only amend marks the earlier pieces not current (as the cannot-satisfy amend did)",
    piece.get("for_current_wording") is False, "")
say("coverage does not read verified on earlier-criterion evidence alone",
    post.get("state") != "verified" or piece.get("for_current_wording") is not False, json.dumps(post)[:400])
memo(e_pre=E_PRE, drift=answered)
summary()
