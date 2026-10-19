"""F757 acceptance drive: a fold warns when the folded text names a change key the fold renames.
Real routes on a Hub started with `e2e.py hub-up`; a project opened with `e2e.py setup`.

  py -3.11 scripts/drive/d1019_f757_renamed_key_drive.py <project-id> <project-dir>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
from e2e import call, request  # noqa: E402

P, DIR = sys.argv[1], pathlib.Path(sys.argv[2])
BASE = f"/projects/{P}/project"
CAP = "spec/capabilities/widgets/spec.json"
CHANGE = "spec/changes/widgets-hover/spec.json"


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (f"  {detail}" if detail else ""))
    if not ok:
        raise SystemExit(1)


call("POST", f"{BASE}/documents", {"path": CAP, "title": "Widgets", "kind": "capability"})
call(
    "POST",
    f"{BASE}/documents/{CAP}/merge",
    {
        "payload": {
            "schema_version": 1,
            "kind": "capability",
            "title": "Widgets",
            "requirements": [{"key": "exist", "statement": "A widget MUST exist.", "modal": "MUST"}],
            "acceptance_criteria": [
                {"key": "exist-c", "requirement": "exist", "given": "g", "when": "w", "then": "t"}
            ],
        }
    },
)
change = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": "Widgets hover",
    "scope": {"in_scope": ["widgets"], "non_goals": ["gadgets"]},
    "requirements": [
        {
            "key": "glow-on-hover",
            "statement": "A widget MUST glow when hovered.",
            "modal": "MUST",
        },
        {"key": "dim-when-idle", "statement": "A widget SHOULD dim when idle.", "modal": "SHOULD"},
    ],
    "acceptance_criteria": [
        {"key": "glow-c", "requirement": "glow-on-hover", "given": "g", "when": "w", "then": "t"},
        {"key": "dim-c", "requirement": "dim-when-idle", "given": "g", "when": "w", "then": "t"},
    ],
    "algorithms": [
        {"name": "Hover", "steps": ["Hover.", "Glow, per (*glow-on-hover*).", "Dim, per `dim-when-idle`."]}
    ],
    "delivery": {"mode": "none"},
}
call("POST", f"{BASE}/documents", {"path": CHANGE, "title": "Widgets hover"})
call("PUT", f"{BASE}/documents/{CHANGE}/content", {"document": change})
call("POST", f"{BASE}/documents/close-exploration?path={CHANGE}")
call("POST", f"{BASE}/documents/propose?path={CHANGE}")
approved = call("POST", f"{BASE}/documents/phase?path={CHANGE}&to=approved", {"approve_anyway": True})
check("change approved", approved["phase"] == "approved", approved["phase"])

status, draft = request("GET", f"{BASE}/documents/{CHANGE}/fold-draft?into={CAP}")
named = [w for w in draft["warnings"] if w["code"] == "fold_renamed_key_named"]
check(
    "the default draft names both keys the algorithm steps use",
    status == 200 and len(named) == 2,
    json.dumps(named)[:500],
)

status, kept = request(
    "POST",
    f"{BASE}/documents/{CHANGE}/fold",
    {
        "into": CAP,
        "requirements": [
            {"key": "glow-on-hover", "as_key": "glow-on-hover"},
            {"key": "dim-when-idle", "as_key": "dim-when-idle"},
        ],
    },
)
check(
    "keeping the keys folds with no such warning, and the steps still name real keys",
    status == 200
    and not [w for w in kept["warnings"] if w["code"] == "fold_renamed_key_named"]
    and {"glow-on-hover", "dim-when-idle"}
    <= {r["key"] for r in json.loads((DIR / CAP).read_text(encoding="utf-8"))["requirements"]},
    json.dumps(kept["warnings"])[:300],
)
print("drive passed")
