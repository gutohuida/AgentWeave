"""Sweep B phase 2: approve anyway + approval report, rigor + history, roadmap slices, F631 step move."""
from s1018_B_lib import *  # noqa

CH = "spec/changes/scarlet-minotaur/spec.json"
c, ap = req("POST", f"{SPEC}/documents/phase?path={CH}&to=approved",
            {"reason": "accepted the gaps for the sweep", "approve_anyway": True}, cut=3000)
print("TASKS", ap.get("tasks_created"))
f = doc_file(CH)
print("HUB BLOCK", json.dumps(f.get("hub"), ensure_ascii=False)[:1500])
print("EVENTS", rows("select event_type, detail from spec_document_events where document_id=(select id from spec_documents where path=? and project_id=?) order by created_at", CH, P)[-3:])

# rigor
req("POST", f"{SPEC}/documents/{CH}/rigor", {"rigor": "bogus"})
req("POST", f"{SPEC}/documents/{CH}/rigor", {"rigor": "contract", "reason": "tests must prove it"}, cut=1200)
req("POST", f"{SPEC}/documents/{CH}/rigor", {"rigor": "gate", "reason": "stale", "expected_digest": "0" * 64}, cut=1200)
req("GET", f"{SPEC}/documents/{CH}/rigor-history", cut=1500)

# F631: a size change moves the step into the new journey
c, d = req("POST", f"{SPEC}/documents", {"title": "Size probe"}, show=False)
SP = d["path"]
req("POST", f"{SPEC}/documents/journey?path={SP}", {"size": "large"}, show=False)
req("POST", f"{SPEC}/documents/journey?path={SP}", {"step": "acceptance"})
c, d = req("POST", f"{SPEC}/documents/journey?path={SP}", {"size": "small", "reason": "smaller"})
print("F631 step after shrink:", d.get("step"), d.get("journey"))
c, d = req("POST", f"{SPEC}/documents/journey?path={SP}", {"size": "fix", "reason": "smallest"})
print("F631 step after fix:", d.get("step"), d.get("journey"))

# roadmap with slices
c, rm = req("POST", f"{SPEC}/documents", {"title": "Interval roadmap", "kind": "roadmap"}, cut=600)
RM = rm["path"]
rpay = {"schema_version": 1, "kind": "roadmap", "title": "Interval roadmap",
        "summary": "Where the interval library goes.", "problem": "Gaps in closed-interval semantics.",
        "scope": {"in_scope": ["intervals"], "non_goals": ["Open intervals"]},
        "slices": [
            {"key": "touching", "title": "Touching intervals", "intent": "merge touching intervals",
             "done": "merge([1,2],[2,3]) is [1,3]"},
            {"key": "printing", "title": "Printing", "intent": "show intervals",
             "done": "show() prints brackets", "builds_after": ["touching"]},
        ],
        "open_questions": [{"question": "Should printing use unicode brackets?", "resolved": False,
                            "slice": "printing"},
                           {"question": "Global: support floats?", "resolved": False},
                           {"question": "Bad slice ref", "resolved": False, "slice": "nope"}],
        "lifecycle": "living"}
c, w = req("PUT", f"{SPEC}/documents/{RM}/content", {"document": rpay}, cut=2000)
req("POST", f"{SPEC}/documents/close-exploration?path={RM}", show=False)
req("POST", f"{SPEC}/documents/propose?path={RM}", cut=1500)
req("POST", f"{SPEC}/documents/phase?path={RM}&to=approved", {"reason": "roadmap"}, cut=1500)
# backfill: the approved change names its slice after the fact (F674)
req("PUT", f"{SPEC}/documents/{CH}/roadmap", {"document": RM, "slice": "nope"})
req("PUT", f"{SPEC}/documents/{CH}/roadmap", {"document": "spec/changes/../x/spec.json", "slice": "touching"})
req("PUT", f"{SPEC}/documents/{CH}/roadmap", {"document": SP, "slice": "touching"})
req("PUT", f"{SPEC}/documents/{CH}/roadmap", {"document": RM, "slice": "touching"})
req("PUT", f"{SPEC}/documents/{CH}/roadmap", {"document": RM, "slice": "touching"})
req("PUT", f"{SPEC}/documents/{CH}/roadmap", {"document": RM, "slice": "printing"})
c, docs = req("GET", f"{SPEC}/documents", show=False)
for d in docs["documents"]:
    if d["path"] == RM:
        print("ROADMAP VIEW", json.dumps(d, ensure_ascii=False)[:1500])
print("ROADMAP hub block", json.dumps(doc_file(RM).get("hub"), ensure_ascii=False)[:800])
print("CH roadmap field", doc_file(CH).get("roadmap"))
print("SP=", SP, "RM=", RM)
save()
