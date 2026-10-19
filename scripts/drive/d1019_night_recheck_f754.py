"""Re-drive F754: a fold's `warnings` hold only the gaps it introduced; the capability's older gaps
come apart as `standing_warnings`. Real routes on a Hub from `e2e.py hub-up`.

  py -3.11 scripts/drive/d1019_night_recheck_f754.py <project-id>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
from e2e import call, request  # noqa: E402

P = sys.argv[1]
BASE = f"/projects/{P}/project"
CAP, CHANGE = "spec/capabilities/gizmos/spec.json", "spec/changes/gizmos-pulse/spec.json"

call("POST", f"{BASE}/documents", {"path": CAP, "title": "Gizmos", "kind": "capability"})
call("POST", f"{BASE}/documents/{CAP}/merge", {"payload": {
    "schema_version": 1, "kind": "capability", "title": "Gizmos",
    "requirements": [{"key": "exist", "statement": "A gizmo MUST exist.", "modal": "MUST"}],
    "acceptance_criteria": [],
}})
change = {
    "schema_version": 1, "kind": "change-spec", "title": "Gizmos pulse",
    "scope": {"in_scope": ["gizmos"], "non_goals": ["x"]},
    "requirements": [{"key": "pulse", "statement": "A gizmo MUST pulse.", "modal": "MUST"}],
    "acceptance_criteria": [],
    "delivery": {"mode": "none"},
}
call("POST", f"{BASE}/documents", {"path": CHANGE, "title": "Gizmos pulse"})
call("PUT", f"{BASE}/documents/{CHANGE}/content", {"document": change})
call("POST", f"{BASE}/documents/close-exploration?path={CHANGE}")
call("POST", f"{BASE}/documents/propose?path={CHANGE}")
call("POST", f"{BASE}/documents/phase?path={CHANGE}&to=approved", {"approve_anyway": True})
status, out = request("POST", f"{BASE}/documents/{CHANGE}/fold", {"into": CAP})
print(status)
named = lambda ws, k: [w for w in ws if w["code"] == "requirement_without_criterion" and k in w["message"]]  # noqa: E731
w, s = out.get("warnings", []), out.get("standing_warnings", [])
print("warnings:", [x["message"][:70] for x in w]); print("standing:", [x["message"][:70] for x in s])
ok = status == 200 and named(w, "pulse") and not named(w, "exist") and named(s, "exist")
print("PASS F754" if ok else "FAIL F754")
sys.exit(0 if ok else 1)
