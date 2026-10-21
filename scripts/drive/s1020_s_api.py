"""2026-10-20 sweep: Spec documents x Corpus & folding, operator routes (no agent turns).

The 10-19 sweep drove the new respond / resolved-proposals / roadmap paths; it left the journey,
Approve anyway, archive -> reopen, delete, and the corpus (Rebuild index, Adopt, Place under,
retire with an absorber) unreached. This drives those, one representative path each.

  AW_E2E_STATE=C:/Users/huida/.agentweave/e2e-s1020.json \
    py -3.11 scripts/drive/s1020_s_api.py <project-id> <project-dir>
"""

import json
import pathlib
import sys
import time

from s1019_spec_lib import payload, request, say, show, task

P, DIR = sys.argv[1], pathlib.Path(sys.argv[2])
SFX = time.strftime("%H%M%S")
BASE = f"/projects/{P}/project"


def view(path):
    st, out = request("GET", f"{BASE}/documents")
    docs = out.get("documents", out) if isinstance(out, dict) else out
    return next((d for d in docs if isinstance(d, dict) and d.get("path") == path), {"_err": (st, str(out)[:200])})


def on_disk(path):
    return json.loads((DIR / path).read_text(encoding="utf-8"))


# --- the project's own spec steps ----------------------------------------------------------------
st, j = request("GET", f"{BASE}/journey")
keys = [s["key"] for s in j.get("steps", [])]
print("built-in steps:", keys, "diagnostics:", j.get("diagnostics"))
custom = [{"key": k} for k in keys]
custom.insert(1, {"key": "threat-model", "title": "Threat model", "instructions": "Name what an attacker gains."})
st, out = request("PUT", f"{BASE}/journey", {"steps": custom})
say("a custom step saves", st == 200 and "threat-model" in json.dumps(out), f"{st} {json.dumps(out)[:300]}")
say("spec/journey.json written", (DIR / "spec" / "journey.json").exists())
st, out = request("PUT", f"{BASE}/journey", {"steps": [{"key": k} for k in reversed(keys)]})
say("built-ins out of order refused 422 naming the rule", st == 422, f"{st} {json.dumps(out)[:300]}")
st, out = request("PUT", f"{BASE}/journey", {"steps": custom[:1] + [{"key": "x" * 3, "instructions": "y" * 2100}] + custom[1:]})
say("a 2,100-char instruction refused naming the step", st == 422 and "xxx" in json.dumps(out), f"{st} {json.dumps(out)[:300]}")
st, out = request("PUT", f"{BASE}/journey", {"steps": [{"key": "Bad Key!"}] + custom})
say("a bad custom key refused", st == 422, f"{st} {json.dumps(out)[:300]}")

# --- create -> journey steps -> close -> propose -> approve 409 -> approve anyway ---------------
DOC = f"spec/changes/journey-{SFX}/spec.json"
st, out = request("POST", f"{BASE}/documents", {"path": DOC, "title": "Journey " + SFX})
show("create", st, {k: out.get(k) for k in ("phase", "step", "size", "journey")} if isinstance(out, dict) else out)
v = view(DOC)
print("  journey:", json.dumps(v.get("journey"))[:500])
st, out = request("POST", f"{BASE}/documents/journey?path={DOC}", {})
say("journey with nothing to change refused 422", st == 422, f"{st} {out}")
st, out = request("POST", f"{BASE}/documents/journey?path={DOC}", {"step": "nope"})
say("an unknown step refused naming the steps", st == 422 and "threat-model" in json.dumps(out), f"{st} {out}")
st, out = request("POST", f"{BASE}/documents/journey?path={DOC}", {"size": "huge"})
say("an unknown size refused naming the sizes", st == 422, f"{st} {out}")
st, out = request("POST", f"{BASE}/documents/journey?path={DOC}", {"size": "small", "reason": "one file"})
show("size small", st, {k: out.get(k) for k in ("step", "size")} if st == 200 else out)
st, out = request("POST", f"{BASE}/documents/journey?path={DOC}", {"step": "threat-model"})
show("step -> threat-model (custom)", st, {k: out.get(k) for k in ("step", "size")} if st == 200 else out)
hub_block = on_disk(DOC).get("hub", {})
say("the file's hub block carries step and size", hub_block.get("step") == "threat-model" and hub_block.get("size") == "small",
    json.dumps({k: hub_block.get(k) for k in ("step", "size", "phase")}))
st, out = request("PUT", f"{BASE}/documents/{DOC}/content", {"document": payload("Journey " + SFX, SFX)})
show("one-PUT write", st, {k: out.get(k) for k in ("identifiers", "blocking", "warnings")} if isinstance(out, dict) else out)
st, out = request("POST", f"{BASE}/documents/propose?path={DOC}")
show("propose before close", st, out)
st, out = request("POST", f"{BASE}/documents/close-exploration?path={DOC}")
show("close", st, {k: out.get(k) for k in ("phase", "explore_closed")} if isinstance(out, dict) else out)
st, out = request("POST", f"{BASE}/documents/journey?path={DOC}", {"step": "write"})
say("journey move after close refused (no_journey or explore closed)", st in (409, 422), f"{st} {out}")
st, out = request("POST", f"{BASE}/documents/propose?path={DOC}")
show("propose", st, {k: out.get(k) for k in ("phase", "blocking")} if isinstance(out, dict) else out)
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=proposed")
show("phase to=proposed when already proposed", st, out)
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=approved", {"reason": "first try"})
show("approve (no anyway)", st, out)
warn = out.get("detail", {}) if isinstance(out, dict) else {}
say("approve answers 409 approval_warnings listing the gaps", st == 409 and "approval_warnings" in json.dumps(out), "")
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=approved&approve_anyway=true", {"reason": "q"})
say("approve_anyway in the query refused 400 naming it (F580)", st == 400 and "approve_anyway" in json.dumps(out), f"{st} {out}")
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=approved", {"reason": "drive", "approve_anyway": True})
show("approve anyway", st, {k: out.get(k) for k in ("phase", "approval_report", "approved_anyway", "warnings")} if isinstance(out, dict) else out)
v = view(DOC)
print("  view after approve:", json.dumps({k: v.get(k) for k in ("phase", "step", "size", "journey", "approval_report")})[:700])
st, tasks = request("GET", f"/projects/{P}/tasks")
T = {t["spec_task_key"]: t["id"] for t in tasks["tasks"] if t.get("spec_task_key") and SFX in t["title"]}
print("  tasks from the approved change:", T)
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=approved", {"reason": "again", "approve_anyway": True})
show("approve an approved document again", st, out)

# --- archive refused with tasks open; reopen; proposed 409 ---------------------------------------
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=archived", {"reason": "done?"})
show("archive with tasks open (and not folded)", st, out)
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=archived", {"reason": "no cap", "no_capability_change": True})
show("archive no_capability_change with tasks open", st, out)
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=bogus")
say("an unknown phase 422 (F730)", st == 422, f"{st} {out}")
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=exploring", {"reason": "rethink"})
show("reopen approved -> exploring", st, {k: out.get(k) for k in ("phase", "step", "explore_closed")} if isinstance(out, dict) else out)
v = view(DOC)
print("  after reopen:", json.dumps({k: v.get(k) for k in ("phase", "step", "size", "explore_closed")}))
for k, tid in T.items():
    t = task(P, tid)
    print("   task", k, t.get("status"), t.get("blocked_reason"))
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=proposed")
say("exploring -> proposed directly is refused 409", st == 409, f"{st} {out}")
st, out = request("POST", f"{BASE}/documents/close-exploration?path={DOC}")
st, out = request("POST", f"{BASE}/documents/propose?path={DOC}")
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=approved", {"reason": "re-approve", "approve_anyway": True})
show("re-approve after reopen", st, {k: out.get(k) for k in ("phase",)} if isinstance(out, dict) else out)
st, tasks = request("GET", f"/projects/{P}/tasks")
T2 = [(t["spec_task_key"], t["id"], t["status"]) for t in tasks["tasks"] if t.get("spec_task_key") and SFX in t["title"]]
say("re-approval did not duplicate the tasks", len(T2) == len(T), str(T2))

# --- delete a document: an exploring one, then an approved one with tasks -------------------------
DD = f"spec/changes/del-{SFX}/spec.json"
request("POST", f"{BASE}/documents", {"path": DD, "title": "Delete me " + SFX})
st, out = request("DELETE", f"{BASE}/documents/{DD}")
show("delete exploring doc", st, out)
say("file gone after delete", not (DIR / DD).exists())
st, out = request("DELETE", f"{BASE}/documents/{DD}")
show("delete it again", st, out)
st, out = request("DELETE", f"{BASE}/documents/spec/changes/../../x/spec.json")
show("delete a path escape", st, out)

# --- corpus: capability, untracked doc, adopt, reindex, arrange ----------------------------------
CAP = f"spec/capabilities/tool-{SFX}/spec.json"
st, out = request("POST", f"{BASE}/documents", {"path": CAP, "title": "Tool " + SFX, "kind": "capability"})
show("create capability", st, {k: out.get(k) for k in ("phase", "kind")} if isinstance(out, dict) else out)
st, out = request("POST", f"{BASE}/documents/{CAP}/merge", {"payload": {
    "schema_version": 1, "kind": "capability", "title": "Tool " + SFX,
    "requirements": [{"key": "alpha", "statement": "The tool MUST handle alpha slowly.", "modal": "MUST"},
                     {"key": "legacy", "statement": "The tool MUST keep legacy mode.", "modal": "MUST"}],
    "acceptance_criteria": [{"key": "c-alpha", "requirement": "alpha", "given": "g", "when": "w", "then": "t"},
                            {"key": "c-legacy", "requirement": "legacy", "given": "g", "when": "w", "then": "t"}]}})
show("seed capability", st, {k: out.get(k) for k in ("identifiers",)} if isinstance(out, dict) else out)
UNTR = f"spec/changes/hand-{SFX}/spec.json"
(DIR / UNTR).parent.mkdir(parents=True, exist_ok=True)
hand = payload("Hand written " + SFX, SFX + "h", keys=("one",))
(DIR / UNTR).write_text(json.dumps(hand, indent=2), encoding="utf-8")
BAD = f"spec/changes/broken-{SFX}/spec.json"
(DIR / BAD).parent.mkdir(parents=True, exist_ok=True)
(DIR / BAD).write_text("{not json", encoding="utf-8")
st, idx = request("GET", f"{BASE}/documents")
show("documents index (untracked listed?)", st, {k: (v if not isinstance(v, list) else len(v)) for k, v in idx.items()}
     if isinstance(idx, dict) else str(idx)[:300])
print("  untracked:", json.dumps(idx.get("untracked") if isinstance(idx, dict) else None)[:600])
st, out = request("POST", f"{BASE}/documents/adopt", {"path": BAD})
show("adopt a broken file", st, out)
st, out = request("POST", f"{BASE}/documents/adopt", {"path": UNTR})
show("adopt the hand-written change", st, {k: out.get(k) for k in ("path", "phase", "kind", "title")} if isinstance(out, dict) else out)
st, out = request("POST", f"{BASE}/documents/adopt", {"path": UNTR})
show("adopt it again", st, out)
st, out = request("POST", f"{BASE}/spec/adopt")
show("adopt everything (corpus)", st, out)
st, out = request("POST", f"{BASE}/spec/reindex")
show("rebuild index", st, out)
say("spec/index.json exists after reindex", (DIR / "spec" / "index.json").exists())
A = f"{BASE}/spec/documents/arrange"
st, out = request("POST", A, {"path": DOC, "parent": CAP})
show("place the change under the capability", st, out)
st, out = request("POST", A, {"path": CAP, "parent": DOC})
say("a cycle refused, legibly", st in (400, 409, 422) and "cycle" in json.dumps(out).lower(), f"{st} {out}")
st, out = request("POST", A, {"path": DOC, "parent": DOC})
say("self-parent refused", st in (400, 409, 422), f"{st} {out}")
st, out = request("POST", A, {"path": DOC, "parent": "spec/changes/nope/spec.json"})
say("unknown parent refused naming it", st in (400, 404, 409, 422) and "nope" in json.dumps(out), f"{st} {out}")
idx_file = json.loads((DIR / "spec" / "index.json").read_text(encoding="utf-8")) if (DIR / "spec" / "index.json").exists() else {}
print("  index.json parent of DOC:", json.dumps(idx_file)[:600])

# --- fold: archive refused until tasks done; then fold with retire; coverage; retire capability --
st, out = request("POST", f"{BASE}/documents/{DOC}/fold", {"into": CAP})
show("fold with tasks open", st, out)
for k, tid in T.items():
    for to in ("assigned", "in_progress", "completed", "under_review", "approved"):
        body = {"status": to, **({"assignee": "operator-made"} if False else {})}
        st, out = request("PATCH", f"/projects/{P}/tasks/{tid}", body)
        if st >= 400:
            show(f"  {k} -> {to}", st, out)
    print("  ", k, task(P, tid).get("status"))
st, draft = request("GET", f"{BASE}/documents/{DOC}/fold-draft?into={CAP}")
show("fold-draft", st, draft)
st, out = request("POST", f"{BASE}/documents/{DOC}/fold", {"into": CAP, "retire": ["legacy"], "note": "drive",
                  "requirements": None})
show("fold, retiring legacy", st, out)
cap = on_disk(CAP)
print("  capability requirements:", [r["key"] for r in cap.get("requirements", [])])
print("  capability criteria:", [c["key"] for c in cap.get("acceptance_criteria", [])])
st, cov = request("GET", f"{BASE}/spec/coverage?document={CAP}")
show("capability coverage after the fold", st, cov)
print("  change after fold:", json.dumps({k: view(DOC).get(k) for k in ("phase",)}))
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=exploring", {"reason": "reopen archived"})
show("reopen the archived (folded) change", st, {k: out.get(k) for k in ("phase",)} if st == 200 else out)
st, out = request("DELETE", f"{BASE}/documents/{DOC}")
show("delete the archived change", st, out)
CAP2 = f"spec/capabilities/old-{SFX}/spec.json"
request("POST", f"{BASE}/documents", {"path": CAP2, "title": "Old " + SFX, "kind": "capability"})
st, out = request("POST", f"{BASE}/documents/phase?path={CAP2}&to=archived", {"reason": "absorbed", "absorbed_by": "spec/capabilities/nope/spec.json"})
show("retire with an unknown absorber", st, out)
st, out = request("POST", f"{BASE}/documents/phase?path={CAP2}&to=archived", {"reason": "absorbed", "absorbed_by": CAP2})
show("retire absorbed by itself", st, out)
st, out = request("POST", f"{BASE}/documents/phase?path={CAP2}&to=archived", {"reason": "absorbed into tool", "absorbed_by": CAP})
show("retire with an absorber", st, {k: out.get(k) for k in ("phase", "retirement")} if st == 200 else out)
print("  retired view:", json.dumps({k: view(CAP2).get(k) for k in ("phase", "retirement", "absorbed_by")})[:400])
st, out = request("POST", f"{BASE}/documents/phase?path={CAP}&to=archived", {"reason": "x", "absorbed_by": CAP2})
show("retire into an archived absorber", st, out)
print("DOC", DOC, "CAP", CAP, "CAP2", CAP2, "UNTR", UNTR)
