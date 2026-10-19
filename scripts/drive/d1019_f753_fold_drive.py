"""F753 acceptance drive: a fold carries algorithms and criterion rewrites, and reaches a second
capability after the archive. Real routes on a Hub started with `e2e.py hub-up`; a project opened
with `e2e.py setup` (its directory is the second argument).

  py -3.11 scripts/drive/d1019_f753_fold_drive.py <project-id> <project-dir>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
from e2e import call, request  # noqa: E402

P, DIR = sys.argv[1], pathlib.Path(sys.argv[2])
BASE = f"/projects/{P}/project"
CAP, CAP2 = "spec/capabilities/widgets/spec.json", "spec/capabilities/gadgets/spec.json"
CHANGE = "spec/changes/widgets-hover/spec.json"


def capability(title, algorithms):
    return {
        "schema_version": 1,
        "kind": "capability",
        "title": title,
        "requirements": [{"key": "exist", "statement": "A widget MUST exist.", "modal": "MUST"}],
        "acceptance_criteria": [
            {"key": "exist-c", "requirement": "exist", "given": "g", "when": "w", "then": "old"}
        ],
        "algorithms": algorithms,
    }


def on_disk(path):
    return json.loads((DIR / path).read_text(encoding="utf-8"))


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (f"  {detail}" if detail else ""))
    if not ok:
        raise SystemExit(1)


for path, title, algorithms in (
    (CAP, "Widgets", [{"name": "Hover", "steps": ["Hover.", "Glow."]}, {"name": "Idle", "steps": ["Dim."]}]),
    (CAP2, "Gadgets", []),
):
    call("POST", f"{BASE}/documents", {"path": path, "title": title, "kind": "capability"})
    call("POST", f"{BASE}/documents/{path}/merge", {"payload": capability(title, algorithms)})

change = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": "Widgets hover",
    "scope": {"in_scope": ["widgets"], "non_goals": ["gadgets"]},
    "requirements": [
        {"key": "glow", "statement": "A widget MUST glow after 50ms of hover.", "modal": "MUST"},
        {"key": "gadget", "statement": "A gadget MUST exist.", "modal": "MUST"},
    ],
    "acceptance_criteria": [
        {"key": "glow-c", "requirement": "glow", "given": "a widget", "when": "hovered 50ms", "then": "it glows"},
        {"key": "gadget-c", "requirement": "gadget", "given": "g", "when": "w", "then": "a gadget"},
    ],
    "algorithms": [
        {"name": "Hover", "steps": ["Hover.", "Wait 50ms.", "Glow."]},
        {"name": "Blink", "steps": ["Blink."]},
    ],
    "delivery": {"mode": "none"},
}
call("POST", f"{BASE}/documents", {"path": CHANGE, "title": "Widgets hover"})
call("PUT", f"{BASE}/documents/{CHANGE}/content", {"document": change})
call("POST", f"{BASE}/documents/close-exploration?path={CHANGE}")
call("POST", f"{BASE}/documents/propose?path={CHANGE}")
approved = call(
    "POST", f"{BASE}/documents/phase?path={CHANGE}&to=approved", {"approve_anyway": True}
)
check("change approved", approved["phase"] == "approved", approved["phase"])

status, draft = request("GET", f"{BASE}/documents/{CHANGE}/fold-draft?into={CAP}")
check(
    "draft lists the capability's algorithms and the folded ones",
    status == 200
    and [a["name"] for a in draft["capability_algorithms"]] == ["Hover", "Idle"]
    and [a["name"] for a in draft["algorithms"]] == ["Hover", "Blink"]
    and draft["collisions"] == ["Hover"],
    json.dumps({k: draft.get(k) for k in ("algorithms", "collisions")}),
)

before = (DIR / CAP).read_bytes()
status, refused = request("POST", f"{BASE}/documents/{CHANGE}/fold", {"into": CAP})
check(
    "a default fold over a same-named algorithm is refused, writing nothing",
    status == 409
    and refused["detail"]["code"] == "fold_key_collision"
    and (DIR / CAP).read_bytes() == before,
    json.dumps(refused)[:300],
)

status, folded = request(
    "POST",
    f"{BASE}/documents/{CHANGE}/fold",
    {
        "into": CAP,
        "requirements": [{"key": "glow", "replaces": "exist"}],
        "criteria": [{"key": "glow-c", "replaces": "exist-c"}],
        "algorithms": [{"name": "Hover", "replaces": "Hover"}, {"name": "Blink"}],
        "retire_algorithms": ["Idle"],
    },
)
check("fold into widgets", status == 200 and folded["phase"] == "archived", json.dumps(folded)[:300])
cap = on_disk(CAP)
check(
    "widgets holds the change's Hover steps, Blink, no Idle",
    cap["algorithms"]
    == [
        {"name": "Hover", "steps": ["Hover.", "Wait 50ms.", "Glow."]},
        {"name": "Blink", "steps": ["Blink."]},
    ],
    json.dumps(cap["algorithms"]),
)
criteria = {c["key"]: c for c in cap["acceptance_criteria"]}
check(
    "exist-c carries the change criterion's text under its own key",
    criteria["exist-c"]["then"] == "it glows"
    and criteria["exist-c"]["requirement"] == "exist"
    and not [k for k in criteria if k.endswith("glow-c")],
    json.dumps(sorted(criteria)),
)

status, second = request(
    "POST",
    f"{BASE}/documents/{CHANGE}/fold",
    {"into": CAP2, "requirements": [{"key": "gadget"}], "algorithms": []},
)
check(
    "the archived change folds into gadgets and stays archived",
    status == 200
    and second["phase"] == "archived"
    and second["archived"] is False
    and second["fold_state"]["capabilities"] == [CAP, CAP2],
    json.dumps(second)[:400],
)
check(
    "gadgets holds the folded requirement",
    "widgets-hover-gadget" in [r["key"] for r in on_disk(CAP2)["requirements"]],
)

before = (DIR / CAP).read_bytes()
status, again = request(
    "POST", f"{BASE}/documents/{CHANGE}/fold", {"into": CAP, "requirements": [{"key": "gadget"}]}
)
check(
    "folding it into widgets again is refused, writing nothing",
    status == 409
    and again["detail"]["code"] == "fold_already_folded"
    and (DIR / CAP).read_bytes() == before,
    json.dumps(again)[:300],
)
print("drive passed")
