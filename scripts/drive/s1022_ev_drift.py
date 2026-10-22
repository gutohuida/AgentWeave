"""2026-10-22 evidence sweep, Drift on the landed FR-2 piece (after s1022_ev_drive.py merge + land):
an unwatched commit raises nothing; a watched one raises a candidate; answer it, answer twice,
an unknown answer, an unknown id; a later watched change after "This change is fine" (re-raised?);
then a failure probe: the repository's .git moved aside under detect and diff, and restored.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1022_ev_drift.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_v_lib import commit_file, coverage, memo, request, say, show, summary  # noqa: E402

M = memo()
P, DIR, DOC = M["project"], pathlib.Path(M["dir"]), M["doc"]
BASE = f"/projects/{P}/project"
WORK = M["work_pieces"][0]
ITEMS = (DIR / "todo/items.py").read_text(encoding="utf-8")


def drift_rows():
    st, out = request("GET", f"{BASE}/spec/drift?document={DOC}")
    return out.get("drift", []) if st == 200 else [("ERR", st, out)]


def detect(label):
    st, out = request("POST", f"{BASE}/spec/drift/detect")
    show(label, st, out)
    return out.get("raised", []) if isinstance(out, dict) else []


print("coverage before:", {k: v.get("state") for k, v in coverage(P, DOC).items()})
commit_file(DIR, "README.md", "# todo\n\nNotes.\n", "readme notes")
say("unwatched README commit raises nothing", detect("detect after README") == [])

commit_file(DIR, "todo/items.py", ITEMS.replace("return len(ITEMS)", "return len(ITEMS) + 0"), "count tweak")
raised = detect("detect after items.py")
say("watched items.py commit raises one candidate", len(raised) == 1, str(raised))
cov = coverage(P, DOC)
print("coverage FR-2:", cov.get("FR-2", {}).get("state"), cov.get("FR-2", {}).get("reason"))
print("drift rows:", [(d.get("id"), d.get("identifier") or d.get("requirement", {}).get("identifier"), d.get("state"))
                      for d in drift_rows()])
first = raised[0] if raised else None
if first:
    st, out = request("POST", f"{BASE}/spec/drift/{first}/resolve", {"resolution": "fine"})
    show("unknown answer", st, out)
    say("unknown answer 422 naming the three words", st == 422 and "no_change_required" in str(out), str(out)[:200])
    st, out = request("POST", f"{BASE}/spec/drift/{first}/resolve", {"resolution": "no_change_required"})
    show("This change is fine", st, out)
    st2, out2 = request("POST", f"{BASE}/spec/drift/{first}/resolve", {"resolution": "implementation_corrected"})
    show("answer twice", st2, out2)
    say("second answer refused naming the first", st2 == 409 and "no_change_required" in str(out2), str(out2)[:200])
st, out = request("POST", f"{BASE}/spec/drift/drift-nope/resolve", {"resolution": "no_change_required"})
say("unknown candidate 404", st == 404, f"{st} {out}")
say("rescan after 'fine' stays silent on the same change", detect("rescan same change") == [])

commit_file(DIR, "todo/items.py", ITEMS.replace("return len(ITEMS)", "return len(list(ITEMS))"), "count again")
again = detect("detect after a second watched change")
say("a later watched change re-raises", len(again) == 1, str(again))
memo(drift_first=first, drift_again=again[0] if again else None)
print("drift rows now:", [(d.get("id"), d.get("state"), d.get("resolution")) for d in drift_rows()])

# Failure probe: the repository is gone from under the Hub.
git_dir = DIR / ".git"
aside = DIR / ".git-aside"
git_dir.rename(aside)
try:
    st, out = request("POST", f"{BASE}/spec/drift/detect")
    show("detect with .git gone", st, out)
    say("detect with no repository is not a bare 500", st != 500, f"{st} {str(out)[:300]}")
    st, out = request("GET", f"{BASE}/spec/evidence/{WORK}/diff")
    show("diff with .git gone", st, out)
    say("diff with no repository answers a reason", st == 200 and bool(out.get("reason")), str(out)[:300])
    st, out = request("GET", f"{BASE}/spec/coverage?document={DOC}")
    say("coverage with no repository still answers", st == 200, f"{st} {str(out)[:200]}")
finally:
    aside.rename(git_dir)
print("restored:", git_dir.is_dir())
summary()
