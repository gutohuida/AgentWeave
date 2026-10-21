"""2026-10-21 evidence sweep, F833 by the operator's door: reopen the approved change, change only
c-total's `then` (FR-3) and reword FR-1's statement, re-approve, then read each requirement's
revisions (`change`) and decide builder's awaiting FR-3 piece (now an earlier wording).

  AW_E2E_STATE=... py -3.11 scripts/drive/s1021_e_f833b.py   (after s1021_e_f761.py)
"""

import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_v_lib import coverage, memo, request, say, show, summary  # noqa: E402

M = memo()
P, DOC = M["project"], M["doc"]
BASE = f"/projects/{P}/project"
piece = M["f761_pieces"][0] if M.get("f761_pieces") else "ev-841c7f0fb485"

st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=exploring", {"reason": "amend c-total and FR-1"})
show("reopen", st, {"phase": out.get("phase")} if isinstance(out, dict) else out)
doc = copy.deepcopy(M["doc_payload"])
for c in doc["acceptance_criteria"]:
    if c["key"] == "c-total":
        c["then"] = "it returns 6, as an int"
for q in doc["requirements"]:
    if q["key"] == "sorted":
        q["statement"] = "names() MUST return the item names sorted alphabetically, ignoring case."
st, out = request("PUT", f"{BASE}/documents/{DOC}/content", {"document": doc})
show("PUT", st, {k: out.get(k) for k in ("identifiers", "blocking")} if isinstance(out, dict) else out)
request("POST", f"{BASE}/documents/close-exploration?path={DOC}")
request("POST", f"{BASE}/documents/propose?path={DOC}")
st, out = request("POST", f"{BASE}/documents/phase?path={DOC}&to=approved", {"reason": "re-approve", "approve_anyway": True})
show("re-approve", st, {"phase": out.get("phase")} if isinstance(out, dict) else out)

rev = {}
for ident in ("FR-1", "FR-3"):
    st, det = request("GET", f"{BASE}/spec/requirements/{ident}")
    rev[ident] = det.get("revisions", []) if isinstance(det, dict) else []
    print(f"{ident}:", [(r.get("classification"), r.get("change"), r.get("statement")[-40:]) for r in rev[ident]])
say("FR-1's statement change reads change=reworded", (rev["FR-1"][-1:] or [{}])[0].get("change") == "reworded")
say("FR-3's criterion-only change reads change=criteria", (rev["FR-3"][-1:] or [{}])[0].get("change") == "criteria")
cov = coverage(P, DOC).get("FR-3", {})
print("FR-3 coverage:", json.dumps({k: cov.get(k) for k in ("state", "evidence_count", "accepted_count", "reason")}))
st, d = request("POST", f"{BASE}/spec/evidence/{piece}/decision", {"decision": "accepted", "reason": "watched"})
show("accept builder's earlier-criteria FR-3 piece", st, d)
txt = json.dumps(d)
say("refused 409 evidence_stale, naming the criteria, not 'reworded'", st == 409 and "reworded" not in txt and "criteri" in txt, txt[:300])
st, d = request("POST", f"{BASE}/spec/evidence/{piece}/decision", {"decision": "rejected", "reason": "earlier criteria"})
show("reject it instead", st, {k: d.get(k) for k in ("id", "review_state")} if isinstance(d, dict) else d)
summary()
