"""Sweep B phase 5: operator rewords FR-1 at gate rigor (F611), evidence goes stale, requirement history (0131)."""
from s1018_B_lib import *  # noqa
import urllib.parse

CH = "spec/changes/scarlet-minotaur/spec.json"
req("POST", f"{SPEC}/documents/phase?path={CH}&to=proposed", {"reason": "reopen to proposed"}, cut=400)
req("POST", f"{SPEC}/documents/phase?path={CH}&to=exploring", {"reason": "reopen to reword FR-1"}, cut=1500)
f = doc_file(CH)
payload = {k: v for k, v in f.items() if k != "hub"}
print("payload keys", list(payload.keys()))
for r in payload["requirements"]:
    if r["key"] == "r1":
        r["statement"] = "Interval.overlaps MUST return true for closed intervals that share at least one point, endpoints included."
c, w = req("PUT", f"{SPEC}/documents/{CH}/content", {"document": payload}, cut=2500)
print("EVIDENCE after reword", rows("select id, review_state, digest from requirement_evidence"))
print("REQ digest", rows("select identifier, digest, state from spec_requirements where document_id='spdoc-fa261bb8059a'"))
print("REVISIONS", rows("select * from spec_requirement_revisions where requirement_id in (select id from spec_requirements where document_id='spdoc-fa261bb8059a') order by created_at"))
q = urllib.parse.quote(CH, safe="")
c, story = req("GET", f"{SPEC}/spec/requirements/FR-1?document={q}", cut=6000)
c, cov = req("GET", f"{SPEC}/spec/coverage?document={q}", cut=3000)
# reword back exactly -> restored?
for r in payload["requirements"]:
    if r["key"] == "r1":
        r["statement"] = "Interval.overlaps MUST return true for closed intervals that share an endpoint."
c, w = req("PUT", f"{SPEC}/documents/{CH}/content", {"document": payload}, cut=800)
print("EVIDENCE after reword-back", rows("select id, review_state, digest from requirement_evidence"))
c, story = req("GET", f"{SPEC}/spec/requirements/FR-1?document={q}", cut=200)
print("REVISIONS in story:", json.dumps(story.get("revisions"), ensure_ascii=False)[:2000])
save()
