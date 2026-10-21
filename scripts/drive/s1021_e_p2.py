"""2026-10-21 evidence sweep, phase 2 (operator routes): overturn refusals and one overturn of an
earlier-wording accepted piece; then an operator piece watching todo/total.py, a commit to it on
master, and a drift scan left open for the browser to answer.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1021_e_p2.py   (after s1021_e_f833b.py)
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_v_lib import commit_file, coverage, git, memo, request, say, show, summary  # noqa: E402

M = memo()
P, DIR, DOC = M["project"], M["dir"], M["doc"]
SPEC = f"/projects/{P}/project/spec"
stale_rejected = (M.get("f761_pieces") or ["ev-841c7f0fb485"])[0]
old_fr1 = M["f833_pieces"]["FR-1"]

st, d = request("POST", f"{SPEC}/evidence/{stale_rejected}/overturn", {"reason": "it did print 6"})
show("overturn rejected earlier-criteria FR-3 piece -> accept", st, d)
say("overturning to accept an earlier-criteria piece is 409 evidence_stale with the criteria sentence",
    st == 409 and "criteri" in json.dumps(d), json.dumps(d)[:300])
st, d = request("POST", f"{SPEC}/evidence/{old_fr1}/overturn", {})
show("overturn with no reason", st, d)
say("no reason -> 422 overturn_needs_reason", st == 422 and "reason" in json.dumps(d))
st, d = request("POST", f"{SPEC}/evidence/ev-000000000000/overturn", {"reason": "x"})
show("overturn unknown", st, d)
say("unknown piece -> 404 with a sentence", st == 404)
st, d = request("POST", f"{SPEC}/evidence/{old_fr1}/overturn", {"reason": "FR-1 was reworded (ignoring case); this watched the old wording"})
show("overturn accepted earlier-wording FR-1 piece -> reject", st, {k: d.get(k) for k in ("id", "review_state", "overturned", "task_reopen")} if isinstance(d, dict) else d)
say("an accepted earlier-wording piece can be overturned to rejected", st == 200 and d.get("review_state") == "rejected")
st, d = request("POST", f"{SPEC}/evidence/{old_fr1}/overturn", {"reason": "back"})
show("overturn it back -> accept (earlier wording)", st, d)
say("and cannot be overturned back to accepted (earlier wording)", st == 409, json.dumps(d)[:300])
st, rv = request("GET", f"{SPEC}/evidence/{old_fr1}/reviews")
print("  reviews:", [(r.get("decision"), r.get("actor"), (r.get("reason") or "")[:40]) for r in (rv.get("reviews", rv) if isinstance(rv, dict) else rv)])

# --- drift: an operator piece watching todo/total.py at its current commit ---
head = git(DIR, "rev-parse", "HEAD")
st, w = request("POST", f"{SPEC}/evidence", {"identifier": "FR-3", "document": DOC, "summary": "total() printed 6 as an int",
                                             "covers": "full", "commit": head, "locator": "todo/total.py"})
show("operator FR-3 piece watching todo/total.py", st, {k: w.get(k) for k in ("id", "review_state", "for_current_wording")} if isinstance(w, dict) else w)
print("  FR-3 coverage:", json.dumps({k: coverage(P, DOC)["FR-3"].get(k) for k in ("state", "accepted_count")}))
commit_file(DIR, "README.md", "# todo\n\nunwatched\n", "readme only")
st, d = request("POST", f"{SPEC}/drift/detect", {"document": DOC})
show("scan after an unwatched change", st, d)
say("an unwatched change raises nothing", st == 200 and not d.get("raised"), json.dumps(d)[:200])
commit_file(DIR, "todo/total.py", "from .items import ITEMS\n\n\ndef total():\n    return int(sum(q for _, q in ITEMS))\n", "total as int")
st, d = request("POST", f"{SPEC}/drift/detect", {"document": DOC})
show("scan after a watched change", st, d)
say("a watched change raises one candidate", st == 200 and len(d.get("raised") or []) == 1, json.dumps(d)[:200])
print("  FR-3 coverage:", json.dumps({k: coverage(P, DOC)["FR-3"].get(k) for k in ("state", "accepted_count")}))
memo(watch_piece=w.get("id"), drift=(d.get("raised") or [None])[0])
summary()
