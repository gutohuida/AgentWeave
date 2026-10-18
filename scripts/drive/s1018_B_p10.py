from s1018_B_lib import *  # noqa
import urllib.parse
CH = "spec/changes/scarlet-minotaur/spec.json"; CAP = "spec/capabilities/interval-arithmetic/spec.json"
cap = {"schema_version": 1, "kind": "capability", "title": "Interval arithmetic",
       "summary": "Closed intervals.", "problem": "", "scope": {"in_scope": ["intervals"], "non_goals": ["open intervals"]},
       "requirements": [{"key": "length", "statement": "Interval.length MUST return hi minus lo.", "modal": "MUST"},
                        {"key": "strict-overlap", "statement": "Interval.overlaps MUST return true only when the interiors intersect.", "modal": "MUST"}],
       "acceptance_criteria": [{"key": "len-1", "requirement": "length", "given": "[1,4]", "when": "length()", "then": "3"},
                               {"key": "so-1", "requirement": "strict-overlap", "given": "[1,2],[2,3]", "when": "overlaps", "then": "false"}],
       "lifecycle": "living"}
c, m = req("POST", f"{SPEC}/documents/{CAP}/merge", {"payload": cap, "note": "seed capability"}, cut=1500)
c, d = req("GET", f"{SPEC}/documents/{CH}/fold-draft?into={urllib.parse.quote(CAP, safe='')}", cut=3000)
req("POST", f"{SPEC}/documents/{CH}/fold", {"into": CAP, "retire": ["nope-key"]}, cut=800)
req("POST", f"{SPEC}/documents/{CH}/fold", {"into": CAP, "requirements": [{"key": "r9"}]}, cut=800)
c, f = req("POST", f"{SPEC}/documents/{CH}/fold", {"into": CAP, "retire": ["strict-overlap"], "note": "touching intervals overlap now"}, cut=3000)
qc = urllib.parse.quote(CAP, safe="")
c, cov = req("GET", f"{SPEC}/spec/coverage?document={qc}", cut=2500)
print("CAP reqs", rows("select identifier, key, state from spec_requirements where document_id='spdoc-12aa6bcbc4dc'"))
print("CAP file requirements", [(r["key"], r["statement"][:50]) for r in doc_file(CAP)["requirements"]])
print("CAP retired block", doc_file(CAP).get("aw_retired") or [k for k in doc_file(CAP) if 'retir' in k])
print("CH phase", rows("select phase from spec_documents where path=?", CH))
save()
